"""variants_gu.py : where a GU monster class tests its variant / ID, returns early on a variant, and posts shells.

  python3 tools/variants_gu.py CLASS        CLASS as tools/gu_enemy.py classes names it (uEm069_00 = Seltas Queen,
                                            uEm076_00 = Seltas)

A GU class that hosts a 4U subspecies keeps 4U's species tests as tests of the variant byte (porting guide, lessons from
Desert Seltas): a test followed by a return freezes the subspecies (the Seltas Queen's reaction switch), one that
branches past a shell post drops its projectile. Scanned: the class's own vtable functions (the slots that differ from
uFestaEnemy's 286, gu_enemy.py) and the functions only they reach (every bl / b to them comes from those functions,
no data pointer to them), each walked along its control flow (direct branches, conditional ones both ways, clang's
table jumps; a branch to another function start is a tail call). In each, a must-dataflow tracks the registers that
hold the offsets 0xb5f5 / 0xb5f0 (`movw`) or the pointers this+0xb5f5 / +0xb5f0 (`ldrb rX, [rB, rK]!`, `add`):
  read     every load of the variant byte (+0xb5f5) or the 16-bit ID (+0xb5f0), its base (this = r0 at entry and its
           copies) and the instruction that tests the loaded value next
  EXIT     the test is followed by a conditional return, or a conditional branch to a block that only returns
  post     every bl 0x48c4f0 (shell request) with its shell id (the movw stored at param+4 before it), and each variant
           test whose conditional branch jumps past that post ("skipped when ...")
Coverage: functions shared with other classes or the base class, and code reached through pointers / vtable calls,
are not scanned; a field reached any other way (another offset arithmetic, a pointer kept in memory) and a test
after more than plain moves are missed. No line means none found this way, not that the class has none.
"""
import collections, os, re, sys

import paths
import fncheck, xref  # noqa: E402  (fncheck checks main.asm / mem.bin)
_p = os.path.join(paths.GU_CODE, 'img_reloc.pkl')
if not os.path.exists(_p): sys.exit('%s missing: run tools/setup.py (tools/doctor.py lists the inputs)' % _p)
import asm, gu_enemy, vt  # noqa: E402

SHELL_REQUEST = 0x48c4f0
FIELDS = {0xb5f5: 'variant', 0xb5f0: 'ID'}
CORE = ['r%d' % i for i in range(13)]


def ins(a):
    m, o = asm.INS.get(a, ('?', ''))
    return m, o.split(' <')[0]


def walk(f, starts):
    """(succ {addr: [next addrs]}, callees) of the function at f along its control flow"""
    succ, callees, todo = {}, set(), [f]
    while todo:
        a = todo.pop()
        if a in succ or len(succ) > 20000: continue
        e = fncheck.model(a)
        if e is None:
            succ[a] = []; continue
        cc, R, W, flags, flow, target = e
        nxt = [a + 4] if flow is None or cc != 'al' else []
        if flow == 'call':
            if target is not None: callees.add(target)
            nxt = [a + 4]
        elif flow == 'b':
            if target in starts and target != f: callees.add(target)
            else: nxt.append(target)
        elif flow == 'switch':
            nxt = list(target)
        succ[a] = nxt
        todo += nxt
    return succ, callees


def closure(cls, C):
    """{function: label} of the class's own vtable functions and the functions only they reach, and their CFGs"""
    base = gu_enemy.vslots(gu_enemy.UENEMY_VT, 286)
    own = gu_enemy.vslots(C[cls]['vt'], 286)
    shared = set(base)
    for k, c in C.items():
        if k != cls and c['vt']: shared |= set(gu_enemy.vslots(c['vt'], 286))
    label = collections.defaultdict(list)
    for i, (f, b) in enumerate(zip(own, base)):
        if f != b: label[f].append('slot %d' % i)
    starts = set(asm.starts())
    bsites = collections.defaultdict(list)
    for a, (m, o) in asm.INS.items():
        if m[0] == 'b' and o.startswith('0x') and (fncheck.mnemonic(m) or ('',))[0] == 'b':
            bsites[int(o.split()[0], 16)].append(a)
    calls = asm.callers()
    cfg, held = {}, {}
    while True:
        for f in list(label):
            if f not in cfg: cfg[f] = walk(f, starts)
        inside = {a for f in label for a in cfg[f][0]}
        new = []
        for f in list(label):
            for t in cfg[f][1]:
                if t in label or t in shared: continue
                if t not in cfg: cfg[t] = walk(t, starts)
                sites = [s for s in calls.get(t, []) + bsites.get(t, []) if s not in cfg[t][0]]
                if t not in held: held[t] = bool(vt.holders(t))
                if sites and all(s in inside for s in sites) and not held[t]: new.append((t, f))
        if not new: break
        for t, f in new: label[t] = ['callee of %x' % f]
    return label, cfg


def tags_at(f, succ):
    """must-dataflow: {addr: frozenset((reg, tag))} before each instruction; tags 'K<off>' = the offset constant,
    'P<off>' / 'P<off>T' = base + offset (T: base was this), 'T' = this (r0 at entry and its copies)"""
    preds = collections.defaultdict(list)
    for a, ns in succ.items():
        for n in ns: preds[n].append(a)
    IN, OUT = {f: frozenset({('r0', 'T')})}, {}
    todo = [f]
    while todo:
        a = todo.pop()
        if a not in succ: continue
        if a != f:
            ps = [OUT[p] for p in preds[a] if p in OUT]
            if not ps: continue
            IN[a] = frozenset.intersection(*ps)
        out = transfer(a, IN[a])
        if OUT.get(a) != out:
            OUT[a] = out
            todo += succ[a]
    return IN


def transfer(a, st):
    m, o = ins(a)
    d = dict(st)
    gen = {}
    p = fncheck.mnemonic(m)
    cond = p is None or p[1] != 'al'
    mm = re.match(r'^(r\d+), #(0x[0-9a-f]+)$', o)
    if m == 'movw' and mm and int(mm.group(2), 16) in FIELDS: gen[mm.group(1)] = 'K%x' % int(mm.group(2), 16)
    mm = re.match(r'^(r\d+), \[(r\d+), (r\d+)\]!$', o)
    if mm and xref.memop(m) and not cond and d.get(mm.group(3), '').startswith('K') and mm.group(1) != mm.group(2):
        gen[mm.group(2)] = 'P' + d[mm.group(3)][1:] + ('T' if d.get(mm.group(2)) == 'T' else '')
    mm = re.match(r'^(r\d+), (r\d+), (r\d+)$', o)
    if m == 'add' and mm:
        for b, k in ((mm.group(2), mm.group(3)), (mm.group(3), mm.group(2))):
            if d.get(k, '').startswith('K'): gen[mm.group(1)] = 'P' + d[k][1:] + ('T' if d.get(b) == 'T' else '')
    mm = re.match(r'^(r\d+), (r\d+)$', o)
    if m == 'mov' and mm and mm.group(2) in d: gen[mm.group(1)] = d[mm.group(2)]
    for r in CORE:
        if r in d and xref.writes(m, o, r): del d[r]
    if not cond: d.update(gen)
    return frozenset(d.items())


def field_load(a, st):
    """(field offset, loaded register, base text) when the instruction at a loads the variant / ID through a tracked
    register, else None"""
    m, o = ins(a)
    if xref.memop(m) not in xref.LOADS: return None
    d = dict(st)
    mm = re.match(r'^(r\d+), \[(r\d+), (r\d+)\]!?$', o)
    if mm and d.get(mm.group(3), '').startswith('K'):
        return int(d[mm.group(3)][1:], 16), mm.group(1), 'this' if d.get(mm.group(2)) == 'T' else mm.group(2)
    mm = re.match(r'^(r\d+), \[(r\d+)(?:, #(-?\d+|-?0x[0-9a-f]+))?\]$', o)
    if mm and d.get(mm.group(2), '').startswith('P'):
        t = d[mm.group(2)]
        off = int(t[1:].rstrip('T'), 16) + (int(mm.group(3), 0) if mm.group(3) else 0)
        if off in FIELDS: return off, mm.group(1), 'this' if t.endswith('T') else 'base %s' % mm.group(2)
    return None


def returns_only(t):
    """does the block at t only return (moves / sp adjust / vpop, then a return)?"""
    for k in range(5):
        e = fncheck.model(t + 4 * k)
        if e is None: return False
        cc, R, W, flags, flow, target = e
        if flow == 'ret' and cc == 'al': return True
        m, o = ins(t + 4 * k)
        if flow is not None or cc != 'al' or not re.match(r'^(mov|movw|mvn|add|vpop|vmov)', m) or \
                (m == 'add' and not o.startswith('sp')):
            return False
    return False


def test_after(a, rx):
    """(test addr, text, exit) of the first instruction testing rx after the load at a, exit = (addr, how) or None"""
    for k in range(1, 7):
        b = a + 4 * k
        m, o = ins(b)
        core = m.split('.')[0]
        if re.match(r'^(cmp|cmn|tst|teq|sub|subs|and|ands)(%s)?$' % xref.CONDS, core) and \
                re.search(r'\b%s\b' % rx, ', '.join(xref.split_ops(o)[1:] if core.startswith(('sub', 'and')) else
                                                     xref.split_ops(o))):
            ex = None
            for j in (1, 2):
                c = b + 4 * j
                e = fncheck.model(c)
                if e is None: break
                cc, R, W, flags, flow, target = e
                if flow == 'ret' and cc != 'al': ex = (c, 'returns when %s' % cc)
                elif flow == 'b' and cc != 'al' and returns_only(target): ex = (c, 'branches when %s to a return' % cc)
                if ex or flow is not None or flags: break
            return b, '%s %s' % (m, o), ex
        if xref.writes(m, o, rx) or fncheck.model(b) is None or fncheck.model(b)[4] is not None: return None
    return None


def shell_id(site):
    """the movw constant stored at [param, #4] (str / stmib) in the instructions before the request, or None"""
    for k in range(1, 48):
        a = site - 4 * k
        m, o = ins(a)
        if fncheck.model(a) and fncheck.model(a)[4] == 'call' and fncheck.model(a)[5] == SHELL_REQUEST: return None
        mm = re.match(r'^(r\d+), #(0x[0-9a-f]+|\d+)$', o)
        if m == 'movw' and mm:
            r = mm.group(1)
            for j in range(1, k):
                m2, o2 = ins(a + 4 * j)
                if re.match(r'^%s, \[r\d+, #0x4\]$' % r, o2) and m2 == 'str' or \
                        m2 == 'stmib' and re.match(r'^r\d+, \{%s\b' % r, o2):
                    return int(mm.group(2), 0)
                if xref.writes(m2, o2, r): break
    return None


def main(argv):
    if len(argv) != 1: sys.exit(__doc__)
    C = gu_enemy.classes()
    cls = argv[0]
    if cls not in C or not C[cls]['vt']: sys.exit('variants_gu: no class %r (gu_enemy.py classes lists them)' % cls)
    label, cfg = closure(cls, C)
    reads, posts = {}, {}                     # by address: an instruction several scanned functions reach is one line
    for f in sorted(label):
        succ = cfg[f][0]
        IN = tags_at(f, succ)
        tests = []
        for a in sorted(IN):
            fl = field_load(a, IN[a])
            if fl:
                off, rx, base = fl
                t = test_after(a, rx)
                reads.setdefault(a, (f, off, base, t))
                if off == 0xb5f5 and t: tests.append((a, t))
            e = fncheck.model(a)
            if e and e[4] == 'call' and e[5] == SHELL_REQUEST: posts.setdefault(a, (f, shell_id(a), set()))
        for p, (pf, sid, skips) in posts.items():
            if p not in succ: continue
            for a, (b, text, ex) in tests:
                for j in (1, 2):
                    e = fncheck.model(b + 4 * j)
                    if e and e[4] == 'b' and e[0] != 'al' and b + 4 * j < p < e[5]:
                        skips.add('%x %s; %x b%s %x' % (a, text, b + 4 * j, e[0], e[5]))
                        break
                    if e is None or e[4] is not None: break
    print('%s: vtable %#x, %d own slots, %d class-only callees, %d functions scanned (fn = the function holding the '
          'instruction, via = the scanned function whose control flow reaches it)' % (
              cls, C[cls]['vt'], sum(1 for v in label.values() if v[0].startswith('slot')),
              sum(1 for v in label.values() if v[0].startswith('callee')), len(label)))
    print('reads of the variant (+0xb5f5) / ID (+0xb5f0):')
    for a, (f, off, base, t) in sorted(reads.items()):
        test = '%x %s' % (t[0], t[1]) if t else '-'
        ex = '  EXIT %x %s' % t[2] if t and t[2] else ''
        print('  fn %-8x via %-18s %x %-7s %-9s -> %s%s' % (xref.sym.func_start('gu', a)[0], ','.join(label[f]), a, FIELDS[off],
                                                           base, test, ex))
    print('shell posts (bl %#x):' % SHELL_REQUEST)
    for a, (f, sid, skips) in sorted(posts.items()):
        print('  fn %-8x via %-18s %x shell %s%s' % (xref.sym.func_start('gu', a)[0], ','.join(label[f]), a,
                                                    '%#x' % sid if sid is not None else '?',
                                                    ''.join('\n      skipped when: ' + s for s in sorted(skips))))
    n_exit = sum(1 for r in reads.values() if r[3] and r[3][2])
    print('%d variant / ID reads (%d EXIT), %d shell posts (%d with a variant test jumping past them). Coverage: see '
          'the docstring; no line means none found this way.' % (len(reads), n_exit, len(posts),
                                                                 sum(1 for p in posts.values() if p[2])))


if __name__ == '__main__':
    main(sys.argv[1:])
