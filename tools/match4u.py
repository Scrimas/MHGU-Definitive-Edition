"""match4u.py : pairs 4U functions with their GU counterparts (the same source compiled twice), with a rating per pair.

  match4u.py build            write dump/match4u/pairs.tsv (+ report.txt; about a minute)
  match4u.py 4u ADDR...       the GU partner of the 4U function at each address, its rating and evidence
  match4u.py gu ADDR...       the same from the GU side
  match4u.py check            pairs against the ground truth below, per rating and evidence kind
Reads what tools/setup.py makes (4U dump/exefs_v11/mem.bin, GU tools/gulib), tools/ghidra_names.py's class registries
and slot names, tools/apialign2.py's monster class pairs (PAIRS). No ground-truth pair is an input: `check` scores
pairs that never voted for themselves (notes/api-map.md C / S rows, SLOT_PAIR over the paired enemy classes,
module/game.h [0x...] brackets, dump/apimap2.pkl if tools/apialign2.py made it, and slot functions paired without
class evidence, whose owner classes must then be a class pair).

Evidence kinds (a pair lists those it was made with, with their votes):
- class: the same class in both games (same DTI name and parent name; same name only, or a PAIRS monster class):
  its getDTI (slot 5), its DTI vtable's newInstance (slot 2), its own slots 0..4 (MtObject's, the same in both
  games), each where ghidra_names gives the function to that class (<Class>_vt<k>, <Class>_newInstance). Seeds.
- vtable: the same place in an equal-length run of slots between paired ones, both slots the class's own: 1 vote
  per class pair. slotmap: slot k <-> j agreed by the paired own slots of >= 2 class pairs with the same parents
  (mutual best), applied to their other own slots: votes = those class pairs.
- calls: the same place in an equal-length run of unpaired callees between paired ones (or the only callee of two
  runs) in the call sequences (bl / tail b, address order, `b f` thunks resolved) of a paired function pair: 1 vote
  per pair. callees / callers: >= 2 paired callees / callers in common, Jaccard >= 0.5 over the paired ones: votes =
  the shared ones (functions with more than NEAR callers / callees propose no candidates).
- const: a string literal or a vldr float / double that one function of each game loads: 1 vote per constant; a
  callees / callers candidate also counts every constant both load.
- globals: the data addresses a function loads (4U `ldr =`, GU GOT slots and `add pc`; strings count as const) pair
  as calls do (the same place in their address-order runs between paired ones, over all paired functions; mutual
  best, 1 vote is enough: 730 of 736 class DTIs / vtables right) and stay paired; then as callees / callers over the
  paired globals: votes = the shared ones.
Rounds: a pair whose summed votes reach the level and are strictly the best of both functions is made (one-to-one:
a tie pairs neither; a pair stays made); levels 8, 4, 2, 1, each until it adds nothing; then the same with globals
(joining sooner, their pairs led the calls astray: 7 more wrong pairs in `check`). A pair of functions that sit
among the slot functions of two classes that are no class pair, one of which has a counterpart, is never made.
Ratings (chosen with `check` and hand reading, 2026-11-21: pairs of two kinds were about 96 % right, of one kind
about 88 %; against api-map C, SLOT_PAIR and game.h, S 127 of 128 and W 30 of 32; pairs with globals votes, 16 of
17 read right):
  C  class seed of a same-name, same-parent class
  S  a class seed otherwise; or votes of at least two kinds (or slotmap, itself >= 2 class pairs) where no other
     candidate of either function has half the votes or more
  W  the rest
Cannot see: functions only a pointer or jump table reaches in 4U (their calls count to the function before), calls
through vtables or function pointers, functions without calls, constants, globals or class slots, GU code without a 4U
ancestor. A function inlined in one game and not in the other leaves its code in its caller: the caller may then
pair with the wrong half (a 4U slot-44 dispatcher's switch helper took GU's merged slot 125).
"""
import collections, difflib, os, re, sys

import numpy as np

import paths
sys.path.insert(0, paths.GU_PY)
import asm, vt  # noqa: E402
import a4u, dis4u, ghidra_names as gn, sym  # noqa: E402
from apialign2 import PAIRS  # noqa: E402

OUT = os.path.join(gn.ROOT, 'dump', 'match4u')
PAIRS_TSV = os.path.join(OUT, 'pairs.tsv')
LEVELS, NEAR = (8, 4, 2, 1), 300


def sext24(w):
    o = w & 0xFFFFFF
    return np.where(o >= 0x800000, o - 0x1000000, o)


class Game:
    """function starts, call sequences, callers, constants, globals of one game's code (T: text words from base;
    data: the address range of its data)"""
    def __init__(self, T, base, starts, word, string, strs, data):
        self.starts = np.array(sorted(starts), dtype=np.int64)
        a = base + 4 * np.arange(len(T), dtype=np.int64)
        ok = (T >> 28) == 0xE
        tgt = a + 8 + 4 * sext24(T)
        f = self.starts[np.searchsorted(self.starts, a, 'right') - 1]
        nxt = np.append(self.starts, 1 << 40)[np.searchsorted(self.starts, a, 'right')]
        known = np.isin(tgt, self.starts)
        call = ok & ((T & 0x0F000000) == 0x0B000000) & known
        tail = ok & ((T & 0x0F000000) == 0x0A000000) & known & ((tgt < f) | (tgt >= nxt))
        self.seq = collections.defaultdict(list); self.callers = collections.defaultdict(set)
        thunk = dict(zip(a[tail & (a == f)].tolist(), tgt[tail & (a == f)].tolist()))   # `b f`: a call to it calls f
        for s, t in zip(f[call | tail].tolist(), tgt[call | tail].tolist()):
            if s not in thunk: t = thunk.get(t, t); self.seq[s].append(t); self.callers[t].add(s)
        self.const = collections.defaultdict(set)
        v = ok & ((T & 0x0F3F0E00) == 0x0D1F0A00)           # vldr s / d, [pc, #+-imm]
        imm = 4 * (T & 0xFF); lit = a + 8 + np.where(T & 0x800000, imm, -imm)
        for s, l, d in zip(f[v].tolist(), lit[v].tolist(), (T[v] & 0x100).tolist()):
            self.const[s].add(('f', word(l) | (word(l + 4) << 32 if d else 0)))
        refs = list(strs(T, a, f)); r = (T >> 7) & 0x1E; i8 = T & 0xFF
        for op, sg in ((0x028F0000, 1), (0x024F0000, -1)):   # adr: add / sub rX, pc, #imm
            m = ok & ((T & 0x0FEF0000) == op)
            refs += zip(f[m].tolist(), (a[m] + 8 + sg * (((i8[m] >> r[m]) | (i8[m] << (32 - r[m]))) & 0xFFFFFFFF)).tolist())
        self.glob, self.users = collections.defaultdict(list), collections.defaultdict(set)   # address order
        for s, x in refs:
            t = string(x)
            if t: self.const[s].add(('s', t))
            elif data[0] <= x < data[1] and s not in self.users[x]: self.glob[s].append(x); self.users[x].add(s)


def cstr(mem, base, x):
    """a printable C string of 4+ characters at x, or None"""
    if not base <= x < base + len(mem): return None
    e = mem.find(b'\0', x - base, x - base + 300)
    s = mem[x - base:e] if e >= 0 else b''
    return s if len(s) >= 4 and all(32 <= c < 127 for c in s) else None


def load():
    report = []   # its own pairs from an earlier build stay out
    R = {t: [r for r in rs if not r[3][0].startswith('tools/match4u.py')] for t, rs in gn.rows([]).items()}
    W4 = np.frombuffer(a4u.M, dtype='<u4', count=(a4u.TEXT_END - a4u.B) // 4).astype(np.int64)
    push = a4u.B + 4 * np.nonzero(((W4 & 0xFFFF4000) == 0xE92D4000) | (W4 == 0xE52DE004))[0]

    def strs4(T, a, f):   # ldr rX, =string or =global
        m = ((T >> 28) == 0xE) & ((T & 0x0F7F0000) == 0x051F0000)
        imm = T & 0xFFF; lit = a + 8 + np.where(T & 0x800000, imm, -imm)
        return ((s, a4u.u(l)) for s, l in zip(f[m].tolist(), lit[m].tolist()) if a4u.B <= l < a4u.TEXT_END)
    u4 = Game(W4, a4u.B, set(sym.u4_known_starts()) | set(push.tolist()), a4u.u,
              lambda x: cstr(a4u.M, a4u.B, x), strs4, (a4u.TEXT_END, 0x111d5a4))   # .rodata to .bss end
    TG = np.frombuffer(asm.MEM, dtype='<u4', count=vt.TEXT_END // 4).astype(np.int64)

    def strsg(T, a, f):   # ldr rM, [pc, #imm] ... add rD, pc, rM (or ldr rD, [pc, rM]: a GOT slot)
        out = []
        for k in np.nonzero(((T & 0xFFFF0FF0) == 0xE08F0000) | ((T & 0xFFFF0FF0) == 0xE79F0000))[0].tolist():
            rm = int(T[k]) & 0xF
            for j in range(k - 1, max(k - 16, 0), -1):
                w = int(T[j])
                if (w & 0xFF7FF000) == 0xE51F0000 | rm << 12:
                    lit = 4 * j + 8 + ((w & 0xFFF) if w & 0x800000 else -(w & 0xFFF))
                    x = (4 * k + 8 + asm.u32(lit)) & 0xFFFFFFFF
                    out.append((int(f[k]), vt.u(x) - gn.GU_B if T[k] >> 20 & 1 else x)); break
                if (w >> 12 & 0xF) == rm: break
        return out
    gu = Game(TG, 0, set(asm.starts()) | set(sym.table_only_starts()), asm.u32,
              lambda x: cstr(asm.MEM, 0, x), strsg, (vt.TEXT_END, len(vt.IMG)))
    return R, u4, gu, report


def registries():
    """(D4, V4, DG, VG): {dti: (name, parent, site)} and {dti: [(vtable, slots)]} of both games (as ghidra_names)"""
    report = []; W = np.frombuffer(vt.IMG, dtype='<u4'); got = lambda t: vt.u(t) - gn.GU_B
    import gu_enemy as g
    DG = gn.dti_registry(asm.callers()[g.DTI_CTOR], asm.func_start_push, g.ins, asm.u32, got, asm.MEM, 0, report, 'gu')
    T = np.frombuffer(asm.MEM, dtype='<u4', count=vt.TEXT_END // 4)
    i = np.nonzero(((T[:-2] & 0xFFFFF000) == 0xE59F0000) & (T[1:-1] == 0xE79F0000) & (T[2:] == 0xE12FFF1E))[0]
    gets = {4 * k: got(4 * k + 12 + asm.u32(4 * k + 8 + (int(T[k]) & 0xFFF))) for k in i.tolist()}
    VG = gn.vtables(W, 0, gn.GU_B, vt.TEXT_END, False, {f: d for f, d in gets.items() if d in DG}, report, 'gu')
    W4 = np.frombuffer(a4u.M, dtype='<u4'); T = W4[:(a4u.TEXT_END - a4u.B) // 4].astype(np.int64)
    k = np.nonzero(((T & 0x0F000000) == 0x0B000000) & ((T >> 28) == 0xE))[0]
    sites = (a4u.B + 4 * k)[a4u.B + 4 * k + 8 + 4 * sext24(T[k]) == a4u.DTI_CTOR].tolist()
    D4 = gn.dti_registry(sites, dis4u.func_bounds, dis4u.INS, a4u.u, None, a4u.M, a4u.B, report, '4u')
    i = np.nonzero(((T[:-1] & 0xFFFFF000) == 0xE59F0000) & (T[1:] == 0xE12FFF1E))[0]
    gets = {a4u.B + 4 * k: a4u.u(a4u.B + 4 * k + 8 + (int(T[k]) & 0xFFF)) for k in i.tolist()}
    V4 = gn.vtables(W4, a4u.B, 0, a4u.TEXT_END, True, {f: d for f, d in gets.items() if d in D4}, report, '4u')
    return D4, V4, DG, VG


def new_instance_4u(site):
    """slot 2 of the DTI vtable the 4U static init stores right after the MtDTI ctor call (ldr r1, =vt; str r1, [r0])"""
    for x in range(site + 4, site + 20, 4):
        w = a4u.u(x)
        if (w & 0xFFFFF000) == 0xE59F1000 and any(a4u.u(y) == 0xE5801000 for y in range(x + 4, x + 16, 4)):
            return a4u.u(a4u.u(x + 8 + (w & 0xFFF)) + 8)
    return None


def class_pairs(D4, V4, DG, VG):
    """[(4U dti, GU dti, rating)] of classes with one vtable in each game: the same name and parent name (C), the same
    name only (S: GU moved the class in the tree), a PAIRS monster class (S)"""
    n4 = collections.Counter(n for n, _, _ in D4.values()); ng = collections.Counter(n for n, _, _ in DG.values())
    by4 = {n: d for d, (n, _, _) in D4.items()}; byg = {n: d for d, (n, _, _) in DG.items()}
    par = lambda D, d: D[D[d][1]][0] if D[d][1] in D else None
    one = lambda a, b: len(V4.get(a, ())) == 1 and len(VG.get(b, ())) == 1
    out = [(d, byg[n], 'C' if par(D4, d) == par(DG, byg[n]) else 'S') for n, d in sorted(by4.items())
           if n4[n] == 1 and ng.get(n) == 1 and one(d, byg[n])]
    return out + [(by4[a], byg[b], 'S') for a, b in PAIRS if a in by4 and b in byg and one(by4[a], byg[b])]


def owners(rows):
    """{function: class} of the slot functions ghidra_names names <Class>_vt<k>"""
    return {a: re.match(r'(\w+)_vt\d+$', t).group(1) for k, a, t, src in rows
            if k == 'func' and src == ['vtable'] and re.match(r'\w+_vt\d+$', t)}


def gap_votes(x, y, M, MG):
    """unpaired (4U, GU) callee pairs at the same place of an equal-length run between two paired ones (or an end), or
    the only callee of two such runs of different lengths (a repeated call inlined or not)"""
    tx = [M.get(t, ('4', t)) for t in x]; ty = [t if t in MG else ('g', t) for t in y]
    out = set(); i0 = j0 = 0
    for i, j, n in difflib.SequenceMatcher(None, tx, ty, autojunk=False).get_matching_blocks():
        gx, gy = x[i0:i], y[j0:j]
        if len(gx) != len(gy) and len(set(gx)) == len(set(gy)) == 1: gx, gy = gx[:1], gy[:1]
        if len(gx) == len(gy): out.update((a, b) for a, b in zip(gx, gy) if a not in M and b not in MG)
        i0, j0 = i + n, j + n
    return out


def overlap(X, V, kind, near4, nearg, backg, M, MG):
    """unpaired functions with >= 2 paired neighbours (near: callees or callers) in common and Jaccard >= 0.5 over the
    paired ones; such a candidate also counts the constants both load"""
    for c, ns in near4.items():
        if c in M: continue
        A = {M[t] for t in ns if t in M}
        if len(A) < 2: continue
        cand = collections.Counter(x for t in A if len(backg[t]) <= NEAR for x in backg[t] if x not in MG)
        for x, n in cand.items():
            B = {t for t in nearg[x] if t in MG}
            n = len(A & B)
            if n >= 2 and n * 2 >= len(A | B):
                V[c, x][kind] += n
                k = len(X['u4'].const.get(c, set()) & X['gu'].const.get(x, set()))
                if k > V[c, x]['const']: V[c, x]['const'] = k


def context():
    """everything the rounds read: both games' code, class pairs, slot owners, names"""
    R, u4, gu, report = load()
    D4, V4, DG, VG = registries()
    X = dict(u4=u4, gu=gu, D4=D4, V4=V4, DG=DG, VG=VG, own4=owners(R['mh4u']), owng=owners(R['gu']),
             CP=class_pairs(D4, V4, DG, VG), report=report,
             names={g: {a: t for k, a, t, _ in gn.merge(R[tag], [], tag) if k == 'func'} for g, tag in (('4u', 'mh4u'), ('gu', 'gu'))})
    t4, tg = collections.defaultdict(set), collections.defaultdict(set)
    for G, t in ((u4, t4), (gu, tg)):
        for f, ts in G.const.items():
            for c in ts: t[c].add(f)
    X['const'] = collections.Counter((min(t4[c]), min(tg[c])) for c in t4 if len(t4[c]) == 1 and len(tg.get(c, ())) == 1)
    for k, G, own in (('reg4', u4, X['own4']), ('regg', gu, X['owng'])):   # the class whose slot functions surround f
        ks = np.array(sorted(own), dtype=np.int64); cls = [own[x] for x in ks.tolist()] + [None]
        i = np.searchsorted(ks, G.starts, 'right')
        X[k] = {f: cls[j - 1] for f, j in zip(G.starts.tolist(), i.tolist()) if j and cls[j - 1] == cls[j]}
    X['cpn'] = {(gn.ident(D4[a][0]), gn.ident(DG[b][0])) for a, b, _ in X['CP']}
    X['cp4'], X['cpg'] = {x for x, _ in X['cpn']}, {y for _, y in X['cpn']}
    return X


def apart(X, a, b):
    """a and b sit among the slot functions of two classes that are no class pair, one of which has a counterpart
    (a class's code is one translation unit, emitted together)"""
    r4, rg = X['reg4'].get(a), X['regg'].get(b)
    return r4 and rg and (r4, rg) not in X['cpn'] and (r4 in X['cp4'] or rg in X['cpg'])


def seeds(X):
    """the class pairs' getDTI, DTI-vtable newInstance and own MtObject slots 0..4 -> (M, MG, ev)"""
    D4, V4, DG, VG, own4, owng = (X[k] for k in ('D4', 'V4', 'DG', 'VG', 'own4', 'owng'))
    seed = collections.defaultdict(set)
    newi = {d: new_instance_4u(s) for d, (_, _, s) in D4.items()}
    nn = collections.Counter(newi.values())
    gnew = {t[:-len('_newInstance')]: a for a, t in X['names']['gu'].items() if t.endswith('_newInstance')}
    for d4, dg, r in X['CP']:
        s4, sg = V4[d4][0][1], VG[dg][0][1]
        c4, cg = gn.ident(D4[d4][0]), gn.ident(DG[dg][0])
        for k in range(min(6, len(s4), len(sg))):
            if own4.get(s4[k]) == c4 and owng.get(sg[k]) == cg: seed[s4[k]].add((sg[k], r, 'slot %d' % k))
        if nn[newi[d4]] == 1 and cg in gnew: seed[newi[d4]].add((gnew[cg], r, 'newInstance'))
    M, MG, ev = {}, {}, {}
    claims = collections.Counter(b for s in seed.values() for b, _, _ in s)
    for a, s in sorted(seed.items()):
        (b, *_), *_ = s
        if len({x[0] for x in s}) == 1 and claims[b] == len(s):
            M[a] = b; MG[b] = a; ev[a] = (min(x[1] for x in s), {'class': len(s)}, 0, 0, ', '.join(sorted(x[2] for x in s)))
    X['report'].append('class pairs: %d (%d C); seeds: %d' % (len(X['CP']), sum(r == 'C' for *_, r in X['CP']), len(M)))
    return M, MG, ev


def votes(X, M, MG):
    """{(4U, GU): Counter(kind: votes)} for unpaired functions, from the pairs made so far"""
    D4, V4, DG, VG, own4, owng, u4, gu = (X[k] for k in ('D4', 'V4', 'DG', 'VG', 'own4', 'owng', 'u4', 'gu'))
    V = collections.defaultdict(collections.Counter)
    for (a, b), n in X['const'].items():
        if a not in M and b not in MG: V[a, b]['const'] += n
    fam = collections.defaultdict(list)
    for d4, dg, _ in X['CP']:
        c4, cg = gn.ident(D4[d4][0]), gn.ident(DG[dg][0])
        s4, sg = V4[d4][0][1], VG[dg][0][1]
        fam[D4[d4][1], DG[dg][1]].append((c4, cg, s4, sg))
        for a, b in gap_votes(s4, sg, M, MG):
            if own4.get(a) == c4 and owng.get(b) == cg: V[a, b]['vtable'] += 1
    for cls in fam.values():   # classes with the same parents share the parent's slot layout: pool their slot pairs
        sv = collections.Counter()
        for c4, cg, s4, sg in cls:
            pos = {f: j for j, f in enumerate(sg) if owng.get(f) == cg}
            sv.update((k, pos[M[f]]) for k, f in enumerate(s4) if own4.get(f) == c4 and M.get(f) in pos)
        for (k, j), _ in mutual(sv, 2):
            n = sv[k, j]
            for c4, cg, s4, sg in cls:
                if k < len(s4) and j < len(sg) and own4.get(s4[k]) == c4 and owng.get(sg[j]) == cg and s4[k] not in M \
                        and sg[j] not in MG: V[s4[k], sg[j]]['slotmap'] += n
    for a, b in M.items():
        for p in gap_votes(u4.seq.get(a, []), gu.seq.get(b, []), M, MG): V[p]['calls'] += 1
    overlap(X, V, 'callees', u4.seq, gu.seq, gu.callers, M, MG)
    overlap(X, V, 'callers', u4.callers, gu.callers, gu.seq, M, MG)
    if 'G' not in X: return V
    G, GG, gv = X['G'], X['GG'], collections.Counter()   # globals pair at the same place in paired functions
    for a, b in M.items(): gv.update(gap_votes(u4.glob.get(a, []), gu.glob.get(b, []), G, GG))
    for (g, h), _ in mutual(gv, 1): G[g] = h; GG[h] = g
    overlap(X, V, 'globals', u4.glob, gu.glob, gu.users, {**M, **G}, {**MG, **GG})   # code and data never overlap
    return V


def mutual(score, level):
    """[((a, b), rival)]: a score >= level that is a's best and b's best, each by a strict margin; rival: the larger
    runner-up score"""
    by4, byg = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for (a, b), n in score.items(): by4[a][b] = byg[b][a] = n
    out = []
    for a, c in sorted(by4.items()):
        (b, n), (_, r4) = (c.most_common(2) + [(None, 0)])[:2]
        (a2, _), (_, rg) = (byg[b].most_common(2) + [(None, 0)])[:2]
        if n >= level and n > r4 and a2 == a and n > rg: out.append(((a, b), max(r4, rg)))
    return out


def propagate(X, M, MG, ev, levels=LEVELS):
    rnd = 0
    for glob in (False, True):   # globals join when the rest is done: sooner, their pairs mislead the calls (check)
        if glob: X['G'], X['GG'] = {}, {}
        for level in levels:
            while True:
                rnd += 1
                V = votes(X, M, MG)
                new = mutual({p: sum(k.values()) for p, k in V.items() if not apart(X, *p)}, level)
                for (a, b), rival in new:
                    M[a] = b; MG[b] = a; ev[a] = (None, dict(V[a, b]), rival, rnd, '')
                X['report'].append('round %d (votes >= %d%s): +%d pairs, %d in all' % (
                    rnd, level, ', globals' if glob else '', len(new), len(M)))
                print(X['report'][-1], flush=True)
                if not new: break


def build():
    os.makedirs(OUT, exist_ok=True)
    X = context(); M, MG, ev = seeds(X); propagate(X, M, MG, ev)
    names, report = X['names'], X['report']
    with open(PAIRS_TSV, 'w', encoding='utf-8') as f:
        f.write('# rating\t4u\tgu\tevidence\t4u name\tgu name\n')
        for a in sorted(M):
            r, k, rival, rd, note = ev[a]
            r = r or ('S' if (len(k) >= 2 or 'slotmap' in k) and 2 * rival < sum(k.values()) else 'W')
            e = ', '.join('%s %d' % kv for kv in sorted(k.items())) + (' (%s)' % note if note else '') + \
                (', rival %d' % rival if rival else '') + (', round %d' % rd if rd else '')
            f.write('%s\t%#x\t%#x\t%s\t%s\t%s\n' % (r, a, M[a], e, names['4u'].get(a, ''), names['gu'].get(M[a], '')))
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')


def read_pairs():
    """[(rating, 4U, GU, evidence, 4U name, GU name)] of dump/match4u/pairs.tsv"""
    if not os.path.exists(PAIRS_TSV): sys.exit('match4u: no %s, run `python3 tools/match4u.py build`' % PAIRS_TSV)
    rows = [l.rstrip('\n').split('\t') for l in open(PAIRS_TSV, encoding='utf-8') if not l.startswith('#')]
    return [(r, int(a, 16), int(b, 16), e, n4, ng) for r, a, b, e, n4, ng in rows]


def truth():
    """{name: [(4U, GU)]}: api-map C rows, SLOT_PAIR over the uEnemy and PAIRS classes' own slots, module/game.h
    [0x...] brackets; weaker: api-map S rows, dump/apimap2.pkl"""
    import pickle
    R = gn.rows([]); own4, owng = owners(R['mh4u']), owners(R['gu'])
    D4, V4, DG, VG = registries()
    by4 = {n: d for d, (n, _, _) in D4.items()}; byg = {n: d for d, (n, _, _) in DG.items()}
    slot = []
    for a, b in PAIRS + [('uEnemy', 'uEnemy')]:
        if a not in by4 or b not in byg: continue
        s4, sg = V4[by4[a]][0][1], VG[byg[b]][0][1]
        slot += [(s4[k], sg[j]) for k, j in gn.SLOT_PAIR.items() if k < len(s4) and j < len(sg)
                 and own4.get(s4[k]) == gn.ident(a) and owng.get(sg[j]) == gn.ident(b)]
    sw = [(int(x, 16), int(y, 16)) for u, g, c, _ in gn.api_rows() if c == 'S' and len(u) == len(g) for x, y in zip(u, g)]
    T = {'api C': gn.api_c_pairs(), 'SLOT_PAIR': slot, 'game.h': [(x, g) for g, x, _ in sym.game_h_brackets()], 'api S': sw}
    p = os.path.join(gn.ROOT, 'dump', 'apimap2.pkl')   # tools/apialign2.py, when it was run
    if os.path.exists(p): T['apimap2'] = sorted(pickle.load(open(p, 'rb'))['map'].items())
    return T


def check():
    P = read_pairs(); M = {a: (r, b, e) for r, a, b, e, *_ in P}; MG = {b: a for _, a, b, *_ in P}
    kinds = lambda e: re.findall(r'(class|vtable|slotmap|calls|callees|callers|const|globals) \d+', e)
    for name, gt in truth().items():
        c = collections.Counter(); bad = []
        for x, y in sorted(set(gt)):
            if x in M: r, b, e = M[x]; ok = b == y
            elif y in MG: r, b, e = M[MG[y]]; ok = False
            else: c['not paired'] += 1; continue
            c[r, ok] += 1; c.update((k, ok) for k in kinds(e))
            if not ok: bad.append('4U %#x GU %#x: paired %s (%s %s)' % (x, y, '4U %#x' % MG[y] if x not in M else 'GU %#x' % b, r, e))
        print('%s (%d pairs): %s' % (name, len(set(gt)), ', '.join('%s %s %d' % (k[0], 'ok' if k[1] else 'wrong', n)
              if isinstance(k, tuple) else '%s %d' % (k, n) for k, n in sorted(c.items(), key=str))))
        for b in bad: print('   ', b)
    # slot functions paired without class / vtable evidence: right when their owner classes are a class pair
    R = gn.rows([]); own4, owng = owners(R['mh4u']), owners(R['gu']); D4, V4, DG, VG = registries()
    cp = {(gn.ident(D4[a][0]), gn.ident(DG[b][0])) for a, b, _ in class_pairs(D4, V4, DG, VG)}
    c = collections.Counter()
    for a, (r, b, e) in M.items():
        if a in own4 and b in owng and not set(kinds(e)) & {'class', 'vtable', 'slotmap'} and (
                own4[a] in {x for x, _ in cp} or owng[b] in {y for _, y in cp}):
            ok = (own4[a], owng[b]) in cp; c[r, ok] += 1; c.update((k, ok) for k in kinds(e))
    print('slot owners (%d pairs): %s' % (sum(n for (k, _), n in c.items() if k in 'SW'), ', '.join(
        '%s %s %d' % (k, 'ok' if ok else 'wrong', n) for (k, ok), n in sorted(c.items()))))
    import apialign as al, apialign2 as a2
    B = a2.blocks_4u()
    for cls in ('uEm089', 'uEm025'):
        calls = [t for s in al.seqs4(*B[cls]).values() for t, _ in s]
        print('%s external calls %d: %.0f%% to paired callees, %d of %d distinct callees paired' % (
            cls, len(calls), 100 * sum(t in M for t in calls) / len(calls), len(set(calls) & set(M)), len(set(calls))))


def lookup(game, addrs):
    P = read_pairs(); by = {(a if game == '4u' else b): p for p in P for _, a, b, *_ in [p]}
    for s in addrs:
        x = sym.parse_addr(game, s); f = x if x in by else sym.func_start(game, x)[0]
        if f not in by: print('%s %#x: function %#x has no partner' % (game, x, f)); continue
        r, a, b, e, n4, ng = by[f]
        print('%s %#x%s: 4U %#x %s <-> GU %#x %s | %s: %s' % (game, x, '' if f == x else ' (function %#x)' % f, a, n4 or '-',
                                                          b, ng or '-', r, e))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'build': build()
    elif cmd == 'check': check()
    elif cmd in ('4u', 'gu') and len(sys.argv) > 2: lookup(cmd, sys.argv[2:])
    else: sys.exit(__doc__)
