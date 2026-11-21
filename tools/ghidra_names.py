"""ghidra_names.py : names the repo already knows -> the seeded Ghidra projects (dump/gu/ghidra, dump/mh4u_ghidra).

  ghidra_names.py project [ROOT]  create the missing projects (import, function-start seeds, auto-analysis; ROOT
                                  replaces dump/ for a trial copy)
  ghidra_names.py collect         write dump/ghidra_names/{gu,mh4u}.tsv + report.txt (nothing applied)
  ghidra_names.py apply [ROOT]    collect, then apply both lists with tools/ghidra/ApplyNames.java (in place; ROOT as
                                  for project), then tools/ghidra_types.py's structures
Ghidra: ghidra-analyzeHeadless on PATH, or GHIDRA_HEADLESS = <ghidra>/support/analyzeHeadless.

Only facts that need no judgement:
- GU functions / data named by `#define NAME ... FN(type, 0xADDR)` / `MAIN(0xADDR)` in tracked C files, as names
  only when confirmed: module/game.h is confirmed unless marked (S / W / guess), other files only with (C) or
  CONFIRMED on the define line; the rest becomes a comment "mhgu-de code calls this NAME". A name defined at two
  addresses (two files' local macros) is dropped; an address with several names gets one as the function name
  (module/game.h first, written names before vtable-slot names) and the others as labels.
- 4U names only where notes/api-map.md's framework table pairs the 4U and GU addresses with confidence C.
- The mod's hook sites (module/build.py HOOKS, module/gear_hooks.txt): a comment, no name.
- tools/match4u.py's 4U <-> GU function pairs (dump/match4u/pairs.tsv, read when it exists): a comment on both
  functions naming the counterpart and its rating; a C pair (same-named class's getDTI, newInstance, own MtObject
  slots) also gives a function without a name its counterpart's name.
- Every MtDTI class (name, parent) from the MtDTI ctor calls (GU 0x7aedcc, 4U 0x5bfabc: r0 = DTI, r1 = name, r2 =
  parent), traced by constant propagation, gets `<Class>_vtable` on the one vtable whose slot 5 is a getDTI returning
  its DTI (`::` written `__`; a name with other characters, or repeated, is skipped). A class with several such
  vtables (subclasses without a DTI of their own share its getDTI) gets no label. A slot function f at slot k gets
  `<Owner>_vt<k>`, the owner being where the walk up the DTI tree from every vtable holding f stops: the class whose
  parent's vtable holds something else at k, has no slot k, or is none. It stays a comment saying where it sits
  when another word among the vtables also holds f, the slots differ, a walk meets a class whose vtables disagree
  at k (or has none), a holder's chain does not reach the root, or the walks end at different classes.
- GU `<Class>_ctor`, `_newInstance`, `_dti_vtable`: the DTI vtable stored after the ctor call, whose slot 2
  (newInstance) tail-calls a function that loads the class's vtable.
- No RTTI, no symbol sizes: a vtable ends at the first word that is no slot or that a pointer points at, so a table
  of code pointers right after a vtable that no pointer marks reads as more slots; a class whose own vtable the
  linker dropped, with one DTI-less subclass, would get that subclass's vtable.
- GU functions only a jump table or pointer reaches (tools/sym.py table_only_starts: a push {.., lr} after an
  unconditional return / branch that no branch of the code before reaches): function starts, also among the seeds.
ApplyNames.java renames only functions with Ghidra's own names (FUN_..., analysis labels); a vtable target or
constructor Ghidra missed becomes a function (a vtable slot and a tail-called constructor start one). Every skip
is reported.
"""
import collections, os, re, subprocess, sys

import numpy as np

import paths  # noqa: E402
import a4u, dis4u, gu_enemy as g  # noqa: E402
vt = g.vt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'dump', 'ghidra_names')
GU_B = 0x10000000
GU_BASES = [('uEnemy', 0x1734798), ('uFestaEnemy', 0x1734d44)]   # notes/enemy-class.md, CONFIRMED
# meanings marked C / CONFIRMED in notes/enemy-class.md and notes/api-map.md
GU_SLOT_NOTE = {1: 'deleting dtor', 5: 'getDTI', 125: 'action dispatcher (this+0x73e0 / +0x73e1)',
                127: 'action remap hook (setAction until stable)', 171: 'get *(work+0x24)', 172: 'set *(work+0x24)',
                247: 'end action -> AI think'}
U4_SLOT_NOTE = {1: 'deleting dtor', 5: 'getDTI', 44: 'action dispatcher (W+0x1ca / +0x1cb)',
                46: 'action remap hook', 78: 'get *(work+0x24)', 79: 'set *(work+0x24)', 89: 'end action -> AI think'}
SLOT_PAIR = {0: 0, 1: 1, 5: 5, 44: 125, 46: 127, 78: 171, 79: 172, 89: 247}   # 4U -> GU, C


def tracked(*globs):
    out = subprocess.run(['git', 'ls-files', *globs], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return out.split()


# (?!\+): `(W+0x7a6e)` in a comment is a 4U record offset, not a rating
UNRATED = re.compile(r'\((?:S|W)\b(?!\+)|\bGUESS\b|\bguess|\bstrong\b|\bweak\b|\bunconfirmed\b')


def confirmed(f, comment, line):
    """module/game.h: confirmed unless marked (its header); elsewhere only a (C) / CONFIRMED on the define line"""
    if UNRATED.search(comment + line): return False
    return f == 'module/game.h' or re.search(r'\(C\b|\bCONFIRMED\b', line) is not None


def gu_defines(report):
    fn = re.compile(r'#define\s+([A-Za-z_]\w*)\b[^\n]*?\bFN\(.*?,\s*(0x[0-9a-fA-F]+)\)')
    data = re.compile(r'#define\s+([A-Za-z_]\w*)\s+[^\n]*?\bMAIN\((0x[0-9a-fA-F]+)\)')
    by_name = collections.defaultdict(set)
    for f in tracked('*.c', '*.h'):
        comment = ''
        for line in open(os.path.join(ROOT, f), encoding='utf-8', errors='replace'):
            m = fn.search(line)
            kind = 'func'
            if not m:
                m = data.search(line); kind = 'label'
            if m: by_name[m.group(1)].add((kind, int(m.group(2), 16), f, confirmed(f, comment, line)))
            s = line.strip()   # the comment block right above the next define (typedefs in between)
            comment = comment + s if s.startswith(('/*', '*', '//', 'typedef')) and not m else ''
    out = []
    for name, defs in sorted(by_name.items()):
        addrs = {(k, a) for k, a, _, _ in defs}
        if len(addrs) != 1:
            report.append('gu define dropped (several addresses): %s %s' % (
                name, ' '.join('%s:%#x' % (f, a) for _, a, f, _ in sorted(defs, key=lambda d: d[1]))))
            continue
        (kind, a), = addrs
        files = sorted({f for _, _, f, _ in defs})
        if any(c for *_, c in defs) and a not in api_rated('SW'): out.append((kind, a, name, files))
        else: out.append(('comment', a, 'mhgu-de code %s this %s (not rated confirmed)' % (
            'calls' if kind == 'func' else 'names', name), files))
    report.append('gu defines: %d confirmed names, %d comments only (rated S / W / guess, or unrated)' % (
        sum(r[0] != 'comment' for r in out), sum(r[0] == 'comment' for r in out)))
    return out


def api_rows():
    """(4U addresses, GU addresses, confidence) of notes/api-map.md's framework table"""
    for line in open(os.path.join(ROOT, 'notes', 'api-map.md'), encoding='utf-8'):
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) >= 5 and cells[3] in ('C', 'S', 'W'):
            yield re.findall(r'0x[0-9a-f]+', cells[0]), re.findall(r'0x[0-9a-f]+', cells[2]), cells[3], cells


def api_rated(confs):
    """GU addresses the table rates with one of confs: a name taken from that mapping is not confirmed"""
    return {int(y, 16) for _, gu, c, _ in api_rows() if c in confs for y in gu}


def api_c_pairs():
    """(4U, GU) address pairs from the C rows of notes/api-map.md's framework table."""
    pairs = []
    for u4, gu, c, cells in api_rows():
        if c == 'C' and u4 and len(u4) == len(gu) and re.fullmatch(r'[0-9a-fx \->]+', cells[0] + cells[2].replace(' ', '')):
            pairs += [(int(x, 16), int(y, 16)) for x, y in zip(u4, gu)]
    return pairs


def hooks():
    src = open(os.path.join(ROOT, 'module', 'build.py'), encoding='utf-8').read()
    out = []
    for m in re.finditer(r'HOOKS\s*\+?=\s*\[', src):
        i, depth = m.end(), 1
        while depth:
            depth += (src[i] == '[') - (src[i] == ']'); i += 1
        out += [(n, int(a, 16)) for n, a in re.findall(r"\('([A-Za-z0-9_]+)',\s*(0x[0-9A-Fa-f]+)\)", src[m.end():i])]
    for l in open(os.path.join(ROOT, 'module', 'gear_hooks.txt'), encoding='utf-8'):
        if l.strip(): out.append((l.split()[0], int(l.split()[1], 16)))
    return out


IMM = r'#(-?(?:0x[0-9a-f]+|\d+)(?:, #\d+)?)'   # objdump writes some immediates as `#value, #rotation`
SETS = re.compile(r'(r\d+), (?:\[pc, %s\]|\[pc, (r\d+)\]|pc, (r\d+)|pc, %s|(r\d+)|%s|(r\d+), %s)$' % (IMM, IMM, IMM, IMM))
NO_WRITE = re.compile(r'(?:str|stm|vstr|vstm|push|vpush|cmp|cmn|tst|teq)\w*$')


def imm(s):
    v, _, r = s.partition(', #')
    v, r = int(v, 0), int(r or 0)
    return (v >> r | v << (32 - r)) & 0xFFFFFFFF if r else v


def call_args(ins, word, got, start, sites):
    """{site: (r0, r1, r2)} at the bl sites of the function at start: forward constant propagation (states meet where
    forward branches land; the code after an unconditional branch is a literal pool until a branch lands in it; a
    backward branch ends the walk). ins(a) -> (mnemonic, operands), word(a) -> literal, got(a) -> GOT entry or None."""
    out = {}; st = {}; pend = collections.defaultdict(list); a = start
    while a <= sites[-1]:
        if a in pend:
            ss = pend.pop(a) + ([st] if st is not None else [])
            st = {r: v for r, v in ss[0].items() if all(s.get(r) == v for s in ss)}
        m, o = ins(a)
        if st is None: pass
        elif re.fullmatch(r'b(?:eq|ne|cs|cc|hs|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)?', m):
            t = int(o.split()[0], 16)
            if t <= a: break
            pend[t].append(st); st = None if m == 'b' else dict(st)
        elif m in ('bl', 'blx'):
            if a in sites: out[a] = tuple(st.get(r) for r in ('r0', 'r1', 'r2'))
            for r in ('r0', 'r1', 'r2', 'r3', 'r12', 'lr'): st.pop(r, None)
        elif m == 'bx' or m in ('pop', 'ldm') and 'pc' in o: st = None
        else:
            mm = SETS.match(o) if m in ('ldr', 'add', 'sub', 'mov', 'movw') else None
            lit, ry, rz, pci, rs, i, rb, bi = mm.groups()[1:] if mm else (None,) * 8
            v = (word(a + 8 + imm(lit)) if m == 'ldr' and lit else
                 got(a + 8 + st[ry]) if m == 'ldr' and got and ry in st else
                 a + 8 + st[rz] if m == 'add' and rz in st else a + 8 + imm(pci) if m == 'add' and pci else
                 st[rs] if m == 'mov' and rs in st else imm(i) if m in ('mov', 'movw') and i else
                 st[rb] + (imm(bi) if m == 'add' else -imm(bi)) if m in ('add', 'sub') and rb in st else None)
            if v is not None: st[mm.group(1)] = v & 0xFFFFFFFF
            elif not (NO_WRITE.match(m) and '!' not in o and '], ' not in o):
                for r in re.findall(r'\b(r\d+|lr)\b', o): st.pop(r, None)
        a += 4
    return out


def dti_registry(sites, start, ins, word, got, mem, base, report, tag):
    """{dti: (name, parent dti (0 = root), site)} from the MtDTI ctor calls (r0 = DTI, r1 = name, r2 = parent); a call
    whose arguments do not trace, or a second call for one DTI, is reported"""
    by = collections.defaultdict(list)
    for s in sorted(sites): by[start(s)].append(s)
    D = {}; bad = []
    for f, ss in by.items():
        args = call_args(ins, word, got, f, ss)
        for s in ss:
            d, n, p = args.get(s, (None,) * 3)
            e = mem.find(b'\0', n - base) if n is not None and base <= n < base + len(mem) else -1
            if d is None or p is None or e < 0 or d in D: bad.append(s); continue
            D[d] = (mem[n - base:e].decode('latin-1'), p, s)
    report.append('%s DTI registry: %d classes from %d MtDTI ctor calls; arguments not traced at %d: %s' % (
        tag, len(D), len(sites), len(bad), ' '.join(map(hex, bad))))
    return D


def vtables(W, base, rel, te, zero, gets, report, tag):
    """{dti: [(vtable, [slot fn])]}: the vtables whose slot 5 is a getDTI returning that DTI. A vtable is two zero
    header words, then slots (code addresses; 4U also 0, its pure virtuals), and an object pointer must point at it (GU:
    a GOT word at the header, 4U: a word at slot 0, the vptr the ctor stores). It ends before the first word that is no
    slot, that a pointer points at, or that starts two zero words a pointer points past (the next vtable's header);
    trailing zeros are dropped. W: the words of the image from address base, rel: what a code pointer adds (GU B)."""
    v = W.astype(np.int64) - rel
    data = (te - base) // 4
    slot = (v >= base) & (v < te) | (W == 0) & zero
    p = v[data:] if rel else v      # 4U: the pointers in literal pools too
    refd = set(p[(p >= te) & (p < base + 4 * len(W))].tolist())
    point = -8 if rel else 0
    out = collections.defaultdict(list); bad = collections.Counter()
    for i in (data + np.nonzero(np.isin(v[data:], list(gets)))[0]).tolist():
        j = i - 5; a = base + 4 * j
        if not (W[j - 2] == W[j - 1] == 0 and slot[j:j + 5].all()): bad['no header 5 words before'] += 1; continue
        if a + point not in refd: bad['nothing points at it'] += 1; continue
        n = 1
        while slot[j + n] and a + 4 * n not in refd and not (a + 4 * n + 8 in refd and W[j + n] == W[j + n + 1] == 0):
            n += 1
        sl = [int(x) for x in v[j:j + n]]
        while not sl[-1]: sl.pop()
        out[gets[int(v[i])]].append((a, sl))
    report.append('%s getDTI words not read as slot 5 of a vtable: %s' % (tag, dict(bad)))
    return out


def ident(name):
    """a DTI name as a Ghidra name: nested classes' '::' as '__'; templates and other characters: None"""
    s = name.replace('::', '__')
    return s if re.fullmatch(r'[A-Za-z_]\w*', s) else None


def owners(D, V, counts, links, report, tag):
    """rows for every class linked to one vtable and every function its slots hold. A function f at slot k is named
    <owner>_vt<k> when every word among the vtables holding f is slot k of a found vtable, and walking up the DTI tree from every
    holder while the parent's vtable holds f at k ends at the same class (its parent holds something else there, has
    no slot k, or it is the root). A class with several vtables (subclasses without a DTI of their own share its
    getDTI) holds f only when all of them do; mixed, or no vtable, refuses. Every holder's chain must reach the root.
    links gets {vtable: (class, slot count)} of the labelled classes."""
    N = collections.Counter(ident(n) for n, _, _ in D.values())
    name = {d: ident(n) if N[ident(n)] == 1 else None for d, (n, _, _) in D.items()}
    rows = []; why = collections.Counter()
    for d, (n, _, _) in sorted(D.items(), key=lambda x: x[1][0]):
        k = 'none' if d not in V else 'several' if len(V[d]) > 1 else 'name' if not name[d] else None
        if k: why[k] += 1; report.append('%s class not labelled (%s): %s' % (tag, {
            'none': 'no getDTI found, or none at slot 5 of a vtable', 'several': '%d vtables hold its getDTI at slot 5' % len(
                V.get(d, ())), 'name': 'not a Ghidra name, or repeated'}[k], n))
        else:
            rows.append(('label', V[d][0][0], name[d] + '_vtable', ['tools/gu_enemy.py' if tag == 'gu' else 'tools/a4u.py']))
            links[V[d][0][0]] = (name[d], len(V[d][0][1]))
    report.append('%s classes: %d in the registry, %d labelled; not labelled: %s' % (tag, len(D), len(rows), dict(why)))

    def holds(d, k, f):
        h = {k < len(sl) and sl[k] == f for _, sl in V.get(d, ())}
        return h.pop() if len(h) == 1 else None    # None: no vtable, or they differ

    def rooted(d):
        seen = set()
        while d and d in D and d not in seen: seen.add(d); d = D[d][1]
        return d == 0
    where = collections.defaultdict(list)
    for d, vs in V.items():
        for a, sl in vs:
            for k, f in enumerate(sl):
                if f: where[f].append((d, a, k))
    why = collections.Counter()
    for f, pl in sorted(where.items()):
        ks = {k for _, _, k in pl}; k = min(ks); top = set(); r = None
        if counts.get(f, 0) != len(pl): r = 'also held by other words among the vtables'
        elif len(ks) > 1: r = 'at several slots'
        for d, _, _ in pl:
            if r: break
            if not rooted(d): r = 'a holder\'s DTI chain does not reach the root'; break
            if not holds(d, k, f): r = 'held by only some of the vtables of a class'; break
            while D[d][1] and holds(D[d][1], k, f): d = D[d][1]
            if D[d][1] and holds(D[d][1], k, f) is None: r = 'parent vtables unknown or mixed at that slot'
            top.add(d)
        if not r and len(top) > 1: r = 'introduced by several classes'
        o = top.pop() if len(top) == 1 else None
        if not r and not name[o]: r = 'owner has no usable name'
        if r:
            why[r] += 1
            pl = sorted(('%s(%#x)' % (D[d][0], a) if len(V[d]) > 1 else D[d][0], k) for d, a, k in pl)
            rows.append(('comment', f, 'vtable slot of: ' + ', '.join('%s[%d]' % p for p in pl[:12]) + (
                ' +%d more' % (len(pl) - 12) if len(pl) > 12 else ''), ['vtable']))
        else: rows.append(('func', f, '%s_vt%d' % (name[o], k), ['vtable']))
    rows += [('entry', f, '-', ['vtable']) for f in sorted(where)]
    report.append('%s slot functions: %d named, %d comments: %s' % (
        tag, sum(r[0] == 'func' for r in rows), sum(why.values()), dict(why)))
    return rows, name


def holder_counts(W, base, rel, te, V):
    """{code address: number of words holding it in the span the vtables V take (outside it, 4U tables hold plain
    numbers that equal code addresses, GU's GOT holds the address-taken functions)}"""
    lo = min(a for vs in V.values() for a, _ in vs); hi = max(a + 4 * len(sl) for vs in V.values() for a, sl in vs)
    w = W[(lo - base) // 4:(hi - base) // 4].astype(np.int64) - rel
    u, c = np.unique(w[(w >= base) & (w < te)], return_counts=True)
    return dict(zip(u.tolist(), c.tolist()))


def gu_classes(report, links):
    W = np.frombuffer(vt.IMG, dtype='<u4')
    got = lambda t: vt.u(t) - GU_B
    D = dti_registry(g.asm.callers()[g.DTI_CTOR], g.asm.func_start_push, g.ins, g.asm.u32, got, g.asm.MEM, 0, report, 'gu')
    T = np.frombuffer(g.asm.MEM, dtype='<u4', count=vt.TEXT_END // 4)
    i = np.nonzero(((T[:-2] & 0xFFFFF000) == 0xE59F0000) & (T[1:-1] == 0xE79F0000) & (T[2:] == 0xE12FFF1E))[0]
    gets = {4 * k: got(4 * k + 12 + g.asm.u32(4 * k + 8 + (int(T[k]) & 0xFFF))) for k in i.tolist()}   # ldr; ldr [pc, r0]; bx lr
    V = vtables(W, 0, GU_B, vt.TEXT_END, False, {f: d for f, d in gets.items() if d in D}, report, 'gu')
    rows = [('label', v, b + '_vtable', ['notes/enemy-class.md']) for b, v in GU_BASES]
    cr, name = owners(D, V, holder_counts(W, 0, GU_B, vt.TEXT_END, V), links, report, 'gu')
    for d, (n, _, site) in sorted(D.items()):
        if len(V.get(d, ())) != 1 or not name[d]: continue
        (v, fns), = V[d]
        if n in ('uEnemy', 'uFestaEnemy') or re.fullmatch(r'uEm\d{3}_\d{2}', n):
            rows += [('comment', fns[k], 'slot %d: %s' % (k, note), ['notes/enemy-class.md', 'notes/api-map.md'])
                     for k, note in GU_SLOT_NOTE.items() if k < len(fns)]
        # the DTI vtable stored after the ctor call; its slot 2 (newInstance) tail-calls the ctor, which stores the vtable
        _, dvt = g.next_got(site + 4)
        newi = vt.u(dvt + 16) - GU_B if dvt is not None else None
        ctor = next((int(o.split()[0], 16) for b, m, o in g.asm.func(newi, 30) if m == 'b'), None) if newi else None
        if ctor is None or not any(m == 'ldr' and ', [pc, r' in o and g.got_at(b) == v - 8 for b, m, o in g.asm.func(ctor, 60)):
            continue
        rows += [('label', dvt + 8, name[d] + '_dti_vtable', ['tools/gu_enemy.py']),
                 ('func', newi, name[d] + '_newInstance', ['tools/gu_enemy.py']),
                 ('entry', ctor, '-', ['tools/gu_enemy.py']), ('func', ctor, name[d] + '_ctor', ['tools/gu_enemy.py'])]
    report.append('gu ctors named: %d' % sum(r[2].endswith('_ctor') for r in rows))
    return rows + cr


def u4_classes(report, links):
    W = np.frombuffer(a4u.M, dtype='<u4'); te = (a4u.TEXT_END - a4u.B) // 4
    T = W[:te].astype(np.int64)
    k = np.nonzero(((T & 0x0F000000) == 0x0B000000) & ((T >> 28) == 0xE))[0]
    off = T[k] & 0xFFFFFF; off[off >= 0x800000] -= 0x1000000
    sites = (a4u.B + 4 * k)[a4u.B + 4 * k + 8 + 4 * off == a4u.DTI_CTOR].tolist()
    D = dti_registry(sites, dis4u.func_bounds, dis4u.INS, a4u.u, None, a4u.M, a4u.B, report, '4u')
    i = np.nonzero(((T[:-1] & 0xFFFFF000) == 0xE59F0000) & (T[1:] == 0xE12FFF1E))[0]
    gets = {a4u.B + 4 * k: a4u.u(a4u.B + 4 * k + 8 + (int(T[k]) & 0xFFF)) for k in i.tolist()}   # ldr r0, =dti; bx lr
    V = vtables(W, a4u.B, 0, a4u.TEXT_END, True, {f: d for f, d in gets.items() if d in D}, report, '4u')
    rows, name = owners(D, V, holder_counts(W, a4u.B, 0, a4u.TEXT_END, V), links, report, '4u')
    for d, (n, _, _) in D.items():
        if len(V.get(d, ())) == 1 and name[d] and (n == 'uEnemy' or re.fullmatch(r'uEm\d+(_\d+)?', n)):
            fns = V[d][0][1]
            rows += [('comment', fns[k], 'slot %d: %s%s' % (k, note, ' (GU slot %d)' % SLOT_PAIR[k] if k in SLOT_PAIR else ''),
                      ['notes/enemy-class.md', 'notes/api-map.md']) for k, note in U4_SLOT_NOTE.items() if k < len(fns) and fns[k]]
    return rows


def merge(rows, report, tag):
    """one function name per address (module/game.h first), the rest as labels; a name at two addresses dropped"""
    funcs = collections.defaultdict(list); out = []
    for r in rows:
        (funcs[r[1]] if r[0] == 'func' else out).append(r)
    named = collections.defaultdict(set)
    for a, rs in funcs.items():
        rs.sort(key=lambda r: ('module/game.h' not in r[3], r[3] == ['vtable'], r[2]))
        out.append(rs[0]); out += [('label',) + tuple(r[1:]) for r in rs[1:] if r[2] != rs[0][2]]
    for r in out:
        if r[0] in ('func', 'label'): named[r[2]].add(r[1])
    bad = {n for n, a in named.items() if len(a) > 1}
    for n in sorted(bad): report.append('%s name dropped (several addresses): %s %s' % (tag, n, sorted(map(hex, named[n]))))
    seen = set(); final = []
    for r in sorted(out, key=lambda r: r[3] == ['vtable']):   # a repeated row keeps the source that is not 'vtable'
        if r[0] in ('func', 'label') and r[2] in bad: continue
        key = r[:3]
        if key not in seen: seen.add(key); final.append(r)
    return sorted(final, key=lambda r: (r[1], r[0], r[2]))


MATCH = os.path.join(ROOT, 'dump', 'match4u', 'pairs.tsv')


def match_rows(report, gu_rows, u4_rows):
    """(GU rows, 4U rows) from tools/match4u.py's pair list, when built: every pair a comment on both functions naming
    the counterpart, its rating and its name; a C pair also carries the counterpart's name where the function has
    none and the name is not taken in its game"""
    if not os.path.exists(MATCH):
        report.append('match4u: no %s (python3 tools/match4u.py build makes it): no counterpart rows' % MATCH)
        return [], []
    R = {'gu': gu_rows, 'mh4u': u4_rows}
    name = {t: {a: n for k, a, n, _ in merge([r for r in rs if r[0] == 'func'], [], t) if k == 'func'} for t, rs in R.items()}
    taken = {t: {r[2] for r in rs if r[0] in ('func', 'label')} for t, rs in R.items()}
    out = {'gu': [], 'mh4u': []}; n = collections.Counter()
    for line in open(MATCH, encoding='utf-8'):
        if line.startswith('#'): continue
        r, a, b = line.split('\t')[:3]; n[r] += 1
        for t, x, y, o, game in (('mh4u', int(a, 16), int(b, 16), 'gu', 'GU'), ('gu', int(b, 16), int(a, 16), 'mh4u', '4U')):
            nm = name[o].get(y)
            if r == 'C' and nm and x not in name[t] and nm not in taken[t]:
                out[t].append(('func', x, nm, ['tools/match4u.py (C)'])); taken[t].add(nm); n['C names to ' + t] += 1
            out[t].append(('comment', x, '%s counterpart %#x (%s)%s' % (game, y, r, ': ' + nm if nm else ''), ['tools/match4u.py']))
    report.append('match4u pairs: %s' % dict(n))
    return out['gu'], out['mh4u']


def rows(report, vtables=None):
    """{'gu' / 'mh4u': [(kind, address, text, sources)]} before merge(): what collect() writes (tools/sym.py reads
    them too). vtables, if given, gets {'gu' / 'mh4u': {vtable: (class, slot count)}} of the labelled classes."""
    vtables = {} if vtables is None else vtables
    vtables.update(gu={}, mh4u={})
    gu_rows = list(gu_defines(report))
    gu_name = {a: n for k, a, n, _ in gu_rows if k == 'func'}
    u4_rows = []
    for x, y in api_c_pairs():
        if y in gu_name: u4_rows.append(('func', x, gu_name[y], ['notes/api-map.md (C)']))
        else: report.append('api-map C pair without a GU name: 4U %#x GU %#x' % (x, y))
    gu_rows += [('comment', a, 'mhgu-de hook ' + n, ['module/build.py']) for n, a in hooks()]
    gu_rows += gu_classes(report, vtables['gu'])
    u4_rows += u4_classes(report, vtables['mh4u'])
    mg, m4 = match_rows(report, gu_rows, u4_rows)
    return {'gu': gu_rows + mg, 'mh4u': u4_rows + m4}


def collect():
    import sym      # here: sym imports this module
    os.makedirs(OUT, exist_ok=True); report = []
    R = rows(report)
    R['gu'][:0] = [('entry', a, '-', ['tools/sym.py table_only_starts']) for a in sym.table_only_starts()]
    for tag, rs in R.items():
        rs = merge(rs, report, tag)
        with open(os.path.join(OUT, tag + '.tsv'), 'w', encoding='utf-8') as f:
            for k, a, t, src in rs:
                f.write('%s\t%#x\t%s\t%s\n' % (k, a, t, ','.join(src)))
        report.append('%s rows: %s' % (tag, dict(collections.Counter(r[0] for r in rs))))
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(l for l in report if 'rows' in l or 'kept' in l or 'slot functions' in l))


#     tag: (project dir under dump/, project name, program = ELF under dump/)
PROJECTS = {'gu': (os.path.join('gu', 'ghidra'), 'gu', os.path.join('gu_main', 'main32.elf')),
            'mh4u': ('mh4u_ghidra', 'mh4u', 'mh4u_v11.elf')}


def headless(tag, step, args):
    log = os.path.join(OUT, '%s.%s.log' % (tag, step))
    cmd = [os.environ.get('GHIDRA_HEADLESS') or 'ghidra-analyzeHeadless'] + args
    with open(log, 'w', encoding='utf-8') as lf:
        st = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT).returncode
    if st: sys.exit('ghidra_names: %s failed (%d), see %s' % (tag, st, log))


def seeds(tag):
    """function starts the auto-analysis cannot find (stripped C++: vtable / table-only functions)"""
    if tag == 'gu':
        import sym  # here: sym imports this module
        return sorted(set(g.asm.starts()) | set(sym.table_only_starts()))
    push = re.compile(r'^ +([0-9a-f]+):\s+(?:push|stmdb\s+sp!,)\s+\{([^}]*)\}')
    return sorted({int(m.group(1), 16) for l in open(os.path.join(paths.DUMP, 'mh4u.asm'), errors='replace')
                   for m in [push.match(l)] if m and 'lr' in m.group(2)})


def project(root):
    """import + seed + analyse the projects that do not exist yet (several minutes each)"""
    os.makedirs(OUT, exist_ok=True)
    for tag, (pdir, name, elf) in PROJECTS.items():
        pdir = os.path.join(root, pdir)
        if os.path.exists(os.path.join(pdir, name + '.gpr')):
            print('%s: %s exists' % (tag, pdir)); continue
        os.makedirs(pdir, exist_ok=True)
        tsv = os.path.join(OUT, tag + '.seeds.tsv')
        with open(tsv, 'w', encoding='utf-8') as f:
            f.writelines('entry\t%#x\t-\tseed\n' % a for a in seeds(tag))
        headless(tag, 'project', [pdir, name, '-import', os.path.join(paths.DUMP, elf), '-scriptPath',
                       os.path.join(ROOT, 'tools', 'ghidra'), '-preScript', 'ApplyNames.java', tsv,
                       os.path.join(OUT, tag + '.seeds.applied.txt')])
        print('%s: %s' % (tag, open(os.path.join(OUT, tag + '.seeds.applied.txt'), encoding='utf-8').readline().strip()))


def apply(root):
    for tag, (pdir, name, elf) in PROJECTS.items():
        headless(tag, 'apply', [os.path.join(root, pdir), name, '-process', os.path.basename(elf),
                       '-noanalysis', '-scriptPath', os.path.join(ROOT, 'tools', 'ghidra'), '-postScript',
                       'ApplyNames.java', os.path.join(OUT, tag + '.tsv'), os.path.join(OUT, tag + '.applied.txt')])
        print(open(os.path.join(OUT, tag + '.applied.txt'), encoding='utf-8').readline().strip())


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'collect'
    if cmd == 'project':
        project(sys.argv[2] if len(sys.argv) > 2 else paths.DUMP); sys.exit()
    collect()
    if cmd == 'apply':
        root = sys.argv[2] if len(sys.argv) > 2 else paths.DUMP
        apply(root)
        import ghidra_types     # here: ghidra_types imports this module; after apply, which creates functions it types
        ghidra_types.collect(); ghidra_types.apply(root)
