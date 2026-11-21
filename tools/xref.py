"""xref.py : whole-exe searches over the disassembly text (4U: dump/mh4u.asm, GU: dump/gu_main/main.asm).

  python3 tools/xref.py {4u|gu} field OFF     every load / store at [base, #OFF], or at [base, rK] with rK set by
                                              `mov / movw rK, #OFF`; grouped by function, R / W and the base shown
  python3 tools/xref.py {4u|gu} em N          compares of em number N with a load of the em-ID field: 4U the byte
                                              W+0x1c0 (W = [this+0xe28], checked), GU the em byte +0xb5f4 and the ID
                                              +0xb5f0 (any variant of N: low byte N); also stores of the constant N
  python3 tools/xref.py {4u|gu} calls ADDR    every bl / b to ADDR, with the r0-r3 / s0-s1 constants set before it

The fields (C): 4U em number at W+0x1c0 (the guide's `cmp W+0x1c0, #89`; react_seltas.py's W+0x1c0 == 26); GU 0x6fb14
stores the 32-bit ID at +0xb5f0, its low byte (em number) at +0xb5f4 and (ID >> 8) & 15 (variant) at +0xb5f5.
Functions: tools/sym.py func_start (known starts, or a push of lr that the code before it never branches past: a
function only a jump table or pointer reaches); a leaf function after another one may still show under it.
Coverage: only the instruction shapes named above. A field reached through another offset (`add rX, this, #K` then
[rX, #OFF - K]) or a register offset set any other way (a pc literal, arithmetic), an em number compared after
arithmetic (`sub; cmp` switches) or held in a table, and calls through pointers or vtables are not found. A register
offset counts when its mov / movw reaches the use on straight code, or is the function's one write of a register
r4 and up. 4U compares after a +0x1c0 load whose base is not shown to be W (the `ldr [x, #0xe28]` on the straight
code before, or the function's one write of that register) are listed apart. A call's constant is shown only when the
last write of its register is an unconditional mov / mvn / movw(+movt) / pc literal / vldr literal / vmov #imm on
straight code (no branch lands in between, no call clobbers it); else nothing is shown for it. No hit means none
found this way.
"""
import os, re, struct, sys

import paths
sys.path.insert(0, paths.GU_PY)
import sym  # noqa: E402  (asm.func_start alone misses the functions only jump tables reach)

CONDS = 'eq|ne|hs|lo|cs|cc|mi|pl|vs|vc|hi|ls|ge|lt|gt|le'
LOADS = set('ldr ldrb ldrh ldrsb ldrsh ldrd ldrex ldrexb ldrexh vldr'.split())
STORES = set('str strb strh strd strex strexb strexh vstr'.split())
BRANCH = re.compile(r'^(bl|blx|b)(%s)?$' % CONDS)
CALLS = re.compile(r'^(bl|blx)(%s)?$' % CONDS)
NOWRITE = re.compile(r'^(cmp|cmn|tst|teq|vcmp|vcmpe|b|bl|blx|bx|push|vpush|pld|pli|nop|vmsr|msr|mcr|%s)(%s)?$' % (
    '|'.join(STORES), CONDS))
LEAVE = re.compile(r'^(b|bx)$|^pop')
LINE4 = re.compile(rb'^ +([0-9a-f]+):\s+(\S+)[ \t]*([^\n]*)$')


class Exe:
    """one game's disassembly: ins(a) -> (mnemonic, operands), scan(needle, rx) over every line, func(a), word(a)"""

    def __init__(self, game):
        self.game = game
        if game == 'gu':
            import asm
            self.asm, self.INS = asm, asm.INS
        else:
            import a4u, dis4u
            self.a4u, self.dis = a4u, dis4u
        self._targets = None

    def ins(self, a):
        if self.game == 'gu':
            m, o = self.INS.get(a, ('?', ''))
            return m, o.split(' <')[0]
        return self.dis.INS(a)

    def scan(self, needle, rx):
        """(addr, mnemonic, operands) of every instruction whose line holds needle and whose operands match rx"""
        r = re.compile(rx)
        if self.game == 'gu':
            for a, (m, o) in self.INS.items():
                if needle in o and r.search(o): yield a, m, o.split(' <')[0]
            return
        mm, n = self.dis._mm, needle.encode()
        i = mm.find(n, 0)      # from the top: without a start, find begins where dis4u's last read left the map
        while i >= 0:
            s = mm.rfind(b'\n', 0, i) + 1
            e = mm.find(b'\n', i)
            x = LINE4.match(mm[s:e])
            if x:
                o = x.group(3).decode('latin-1').split(' @')[0].split(' <')[0].strip()
                if r.search(o): yield int(x.group(1), 16), x.group(2).decode(), o
            i = mm.find(n, e)

    def func(self, a):
        return sym.func_start(self.game, a)[0]

    def word(self, a):
        return self.asm.u32(a) if self.game == 'gu' else self.a4u.u(a)

    def targets(self):
        """every direct branch / call target (where another path can join straight code)"""
        if self._targets is None:
            if self.game == 'gu':
                it = ((m, o) for m, o in self.INS.values() if m[0] == 'b')
            else:
                it = ((m, o) for a, m, o in self.scan('@ imm = #', ''))
            self._targets = {int(o.split()[0], 16) for m, o in it if BRANCH.match(m) and o.startswith('0x')}
        return self._targets


def num(s):
    return int(s, 0)


def memop(m):
    """the load / store mnemonic of m without its condition, or None"""
    core = m.split('.')[0]
    for c in (core, core[:-2] if re.search(r'(%s)$' % CONDS, core) else None):
        if c in LOADS or c in STORES: return c
    return None


def split_ops(o):
    return [x.strip() for x in re.split(r',(?![^\[{]*[\]}])', o)] if o else []


def writes(m, o, reg):
    """does the instruction (maybe) write core register reg? Errs on yes"""
    core = m.split('.')[0]
    ops = split_ops(o)
    if CALLS.match(core): return reg in ('r0', 'r1', 'r2', 'r3', 'r12')
    for i, x in enumerate(ops):
        if re.match(r'\[%s\b' % reg, x) and (x.endswith('!') or i < len(ops) - 1): return True   # base writeback
    if ops and ops[0] == reg + '!': return True
    if NOWRITE.match(core): return False
    if re.search(r'\{[^}]*\b%s\b' % reg, o): return not core.startswith(('stm', 'vstm'))
    dests = ops[:2] if re.match(r'(ldrd|ldrexd|umull|smull|umlal|smlal|vmov)', core) else ops[:1]
    return reg in dests


def swrites(m, o, reg):
    """does the instruction (maybe) write VFP register reg (s0..s15), also through its d / q alias? Errs on yes"""
    core = m.split('.')[0]
    if CALLS.match(core): return True
    if re.match(r'^(vstr|vstm|vpush|vcmp|vcmpe|vmrs|vmsr|vst)', core) or not core.startswith('v'): return False
    n = int(reg[1:])
    alias = r'\b(%s|d%d|q%d)\b' % (reg, n // 2, n // 4)
    if re.match(r'^(vldm|vpop|vld\d)', core): return re.search(r'\{[^}]*' + alias, o) is not None
    return re.match(alias, split_ops(o)[0] if o else '') is not None or (
        core == 'vmov' and len(split_ops(o)) == 4 and re.match(alias, split_ops(o)[1]) is not None)


def const_before(X, site, reg, back=24):
    """value of reg (r0-r3: int, s0 / s1: float) at site, or None"""
    T = X.targets()
    hi = None
    for k in range(1, back):
        a = site - 4 * k
        if a + 4 in T: return None                               # another path joins between here and the call
        m, o = X.ins(a)
        if m in ('?', '<unknown>'): return None
        if reg[0] == 's':
            if not swrites(m, o, reg): continue
            mm = re.match(r'^%s, \[pc, #(-?0x[0-9a-f]+|-?\d+)\]$' % reg, o)
            if m == 'vldr' and mm: return struct.unpack('<f', struct.pack('<I', X.word(a + 8 + num(mm.group(1)))))[0]
            mm = re.match(r'^%s, #(\S+)$' % reg, o)
            return float(mm.group(1)) if m == 'vmov.f32' and mm else None
        if not writes(m, o, reg): continue
        mm = re.match(r'^%s, #(-?0x[0-9a-f]+|-?\d+)$' % reg, o)
        if m == 'movt' and mm and hi is None:
            hi = num(mm.group(1)); continue
        if m in ('mov', 'mvn', 'movw') and mm:
            v = num(mm.group(1)) & 0xffffffff
            if hi is not None: return hi << 16 | v if m == 'movw' else None
            return ~v & 0xffffffff if m == 'mvn' else v
        if hi is not None: return None
        mm = re.match(r'^%s, \[pc, #(-?0x[0-9a-f]+|-?\d+)\]$' % reg, o)
        if m == 'ldr' and mm: return X.word(a + 8 + num(mm.group(1)))
        mm = re.match(r'^%s, pc, #(-?0x[0-9a-f]+|-?\d+)$' % reg, o)
        if m == 'add' and mm: return (a + 8 + num(mm.group(1))) & 0xffffffff
        if X.game == 'gu' and m in ('add', 'ldr') and re.match(r'^%s, (pc, r\d+|\[pc, r\d+\])$' % reg, o):
            import gu
            r = gu.pcref(a)
            return r[0] if r else None
        mm = re.match(r'^%s, (r\d+)$' % reg, o)
        if m == 'mov' and mm: return const_before(X, a, mm.group(1), back - k)
        return None
    return None


def only_write(X, use, reg):
    """(addr, mnemonic, operands) of the one write of reg between its function's start and use, or None (none, or
    more than one: compilers keep offsets and W in one register across a function's loops)"""
    f, found, a = X.func(use), None, use - 4
    while a >= f and a > use - 4 * 4000:
        m, o = X.ins(a)
        ret = re.match(r'^(pop|ldm)', m) and re.search(r'\bpc\b', o)       # a return's pop reaches nothing after it
        if writes(m, o, reg) and not ret:
            if found is not None: return None
            found = (a, m, o)
        a -= 4
    return found


def reaches(X, d, use, reg):
    """does the write of reg at d (no other write of it up to use in address order) hold at use? Yes on straight code;
    across a branch target only when it is the function's one write of reg before use (r4 and up: r0-r3 may bring
    the caller's argument along another path)"""
    if not any(b in X.targets() for b in range(d + 4, use + 4, 4)): return True
    if reg in ('r0', 'r1', 'r2', 'r3'): return False
    w = only_write(X, use, reg)
    return w is not None and w[0] == d


def mem_hits(X, off):
    """[(addr, mnemonic, operands, base, how)] of loads / stores of [base, #off] and [base, rK] with rK = off"""
    out = set()
    for t in ('#0x%x]' % off, '#%d]' % off):
        for a, m, o in X.scan(t, r'\[\w+, %s' % re.escape(t)):
            base = re.search(r'\[(\w+),', o).group(1)
            if memop(m) and base != 'pc': out.add((a, m, o, base, ''))
    for t in ('#0x%x' % off, '#%d' % off):
        for a, m, o in X.scan(t, r'^r\d+, %s$' % t):
            if m not in ('mov', 'movw'): continue
            rk = o.split(',')[0]
            for k in range(1, 64):
                b = a + 4 * k
                m2, o2 = X.ins(b)
                mm = re.search(r'\[(\w+), %s\]' % rk, o2)
                if memop(m2) and mm and reaches(X, a, b, rk):
                    out.add((b, m2, o2, mm.group(1), '%s set at %x' % (rk, a)))
                if writes(m2, o2, rk) or m2.startswith('bx') or (m2.startswith('pop') and 'pc' in o2): break
    return sorted(out)


def cmd_field(X, off):
    hits = mem_hits(X, off)
    byf = {}
    for h in hits: byf.setdefault(X.func(h[0]), []).append(h)
    for f in sorted(byf):
        print('fn %x' % f)
        for a, m, o, base, how in byf[f]:
            print('  %s %x: %-8s %-34s base %s%s' % ('R' if memop(m) in LOADS else 'W', a, m, o, base,
                                                    '  (' + how + ')' if how else ''))
    print('%d accesses of +0x%x in %d functions (shapes and limits: see the docstring)' % (len(hits), off, len(byf)))


def follow_cmp(X, a, rx, n, low_byte):
    """compares of rx with n after the load at a, until rx is rewritten or the path leaves"""
    out = []
    for k in range(1, 9):
        b = a + 4 * k
        m, o = X.ins(b)
        core = m.split('.')[0]
        if re.match(r'^(cmp|teq)(%s)?$' % CONDS, core):
            mm = re.match(r'^%s, #(0x[0-9a-f]+|\d+)$' % rx, o)
            mr = re.match(r'^%s, (r\d+)$' % rx, o)
            v = num(mm.group(1)) if mm else const_before(X, b, mr.group(1)) if mr else None
            if v is not None and (v == n or (low_byte and v & 0xff == n and v < 0x1000)): out.append((b, m, o, v))
        if writes(m, o, rx) or LEAVE.match(core) or CALLS.match(core): break
    return out


def w_base(X, a, base):
    """address of the `ldr base, [x, #0xe28]` (W) that set base before a, on the straight code or as the function's
    only write of base before a; else None"""
    T = X.targets()
    for k in range(1, 32):
        b = a - 4 * k
        if b + 4 in T: break
        m, o = X.ins(b)
        if writes(m, o, base):
            return b if m == 'ldr' and re.match(r'^%s, \[\w+, #0xe28\]$' % base, o) else None
    w = only_write(X, a, base) if base not in ('r0', 'r1', 'r2', 'r3') else None   # r0-r3 die at every call
    return w[0] if w and w[1] == 'ldr' and re.match(r'^%s, \[\w+, #0xe28\]$' % base, w[2]) else None


def cmd_em(X, n):
    rows, other, skipped = [], [], 0
    fields = [(0x1c0, 'em')] if X.game == '4u' else [(0xb5f4, 'em'), (0xb5f0, 'id')]
    for off, what in fields:
        for a, m, o, base, how in mem_hits(X, off):
            out = rows
            if X.game == '4u':
                wb = w_base(X, a, base)
                if wb is None:
                    skipped += 1; out = other                    # +0x1c0 of something not shown to be W
                how = 'W from %x' % wb if wb is not None else 'base %s' % base
            rx = split_ops(o)[0]
            if memop(m) in LOADS:
                for b, m2, o2, v in follow_cmp(X, a, rx, n, what == 'id'):
                    out.append((X.func(a), b, '%-8s %-14s (= %#x) after %x %s %s  %s' % (m2, o2, v, a, m, o, how)))
            elif const_before(X, a, rx) == n:
                out.append((X.func(a), a, 'store of %d: %s %s  %s' % (n, m, o, how)))
    for f, b, t in sorted(rows):
        print('fn %-8x %x: %s' % (f, b, t))
    if other:
        print('not shown to be the em byte (base not loaded from [x, #0xe28] in the function):')
        for f, b, t in sorted(other):
            print('  fn %-8x %x: %s' % (f, b, t))
    print('%d compares / stores of em %d (%s)%s' % (
        len(rows), n, 'ldrb [W, #0x1c0], W = [this, #0xe28]' if X.game == '4u' else
        'em byte +0xb5f4; ID +0xb5f0 with low byte %d' % n,
        '; %d loads of +0x1c0 without such a W, %d of them compared with %d (listed apart)' % (skipped, len(other), n)
        if X.game == '4u' else ''))


def cmd_calls(X, addr):
    t, n = '0x%x' % addr, 0
    for a, m, o in X.scan(t, r'^%s\b' % t):
        if not BRANCH.match(m) or o.split()[0] != t: continue
        vals = []
        for r in ('r0', 'r1', 'r2', 'r3', 's0', 's1'):
            v = const_before(X, a, r)
            if v is not None: vals.append('%s=%s' % (r, ('%g' % v) if r[0] == 's' else hex(v)))
        print('fn %-8x %x: %-5s %s' % (X.func(a), a, m, ' '.join(vals) or '-'))
        n += 1
    print('%d direct calls / branches to %s (constants: see the docstring)' % (n, t))


def main(argv):
    if len(argv) != 3 or argv[0] not in ('4u', 'gu') or argv[1] not in ('field', 'em', 'calls'):
        sys.exit(__doc__)
    try:
        v = int(argv[2], 0)
    except ValueError:
        sys.exit('xref: %r is not a number' % argv[2])
    need = [os.path.join(paths.DUMP, 'mh4u.asm'), os.path.join(paths.DUMP, 'exefs_v11', 'mem.bin')] if argv[0] == '4u' \
        else [os.path.join(paths.GU_CODE, 'main.asm'), paths.GU_MAIN]
    for p in need:
        if not os.path.exists(p): sys.exit('xref: %s missing (CONTRIBUTING.md, inputs; tools/doctor.py)' % p)
    {'field': cmd_field, 'em': cmd_em, 'calls': cmd_calls}[argv[1]](Exe(argv[0]), v)


if __name__ == '__main__':
    main(sys.argv[1:])
