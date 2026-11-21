"""gate4u.py : which 4U actions let each conditioned motion effect play, per port (MEF byte 0 = a bit of this+0xca8).

  python3 tools/gate4u.py ENTRY [--actions]     ENTRY: an allocations.toml entry of PORTS below, or `all`

4U's motion-effect queue 0x391a60 posts a MEF record with byte 0 (b0) != 0 only while bit b0 of the unit's mask
this+0xca8 is set; the action handlers set bits every frame and the component clears them after the frame's posts
(0x393524). GU's PSL posts the record whenever its motion plays (porting guide, "MEF byte 0 gates the post").
For every b0 record the port's PSLs post, this lists the 4U actions whose motions post it and what each one does
with bit b0:
  always     every path through a running frame (step byte W+0x144 = 1) sets it: 4U plays it there, like GU
  sometimes  only some paths set it: a condition the tool cannot resolve (a state such as Stygian's charge, a frame
             window, a value from memory); GU plays the effect on every path
  never      no path of any step sets it: 4U never plays the effect in that action, GU does
and whether the port's module already gates the record (a module/*.c table named *b0*, as fxaudit finds it).
A bit 4U's shared ground code sets (0x3934b8, by stage and area: 30 / 31), or one the class sets outside its
actions (its own vtable slots but 44, or a mask store in its code no action reaches, e.g. through a function
pointer), gets no verdict. `python3 tools/gate4u.py all > dump/gate4u/report.txt` keeps a report.

How (static, C): each action is the class's vtable slot 44 dispatcher read with the work bytes +0x1ca / +0x1cb
(category / number) known, every category 0..15 and number 0..255, by a forward dataflow pass from r0 = this:
constants, this / W = [this+0xe28] / the em byte W+0x1c0 (also through a pointer this+k: `add r5, r4, #3072; add r5,
r5, #552; ldr r0, [r5]`, the Desert Seltas Queen's 1/31), the flags of compares on known values (so variant and
species tests resolve), jump tables (`cmp; ldrlo pc` / `add pc`), and the bits of `ldr [this, #0xca8]; orr ...;
str [this, #0xca8]` (must = every path, may = some). Direct calls with r0 = this are followed 5 levels deep with
their r1 / r2 when constant or this (a callee's summary joins its caller's paths); motions are the constant r1 of
the setMotion helpers (tools/em089_actions.py's list) and of the wrappers that pass it on. Motion m posts the
records of its 4U LMT event slots (efl4u2gu.lmt_events: bank m >> 8 = the file's `_N` suffix, animation m & 0xff).
Checked: Black Gravios' hand-made table (module/em005_01_fx.c s_mask, from the same 4U code) row for row (7/79 / 80
come out `sometimes`), Stygian Zinogre's known cases (3030 sometimes in 7/109, the charge; 3000 / 3001 in 7/89).
Coverage (what is not seen): a mask store through an indirect call (blx / vtable) or a pointer other than this
(the report lists those the actions reach), a motion chosen at run time (no constant r1) or set outside the
helpers. An action that posts a record through such a motion is not listed: no line means none found this way, and
`never` holds only for what the pass read; read the code before a gate trusts one.
"""
import collections, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths
import a4u, arcpack, dis4u, disp4u, efl4u2gu, fxaudit, xref
from efl4u2gu import T

#        entry: (4U arc and its em number, 4U class running it, GU arc of the port); C: the class's slot 44 is the
#        dispatcher its notes name (0x807e5c Black Gravios, 0x7957c4 the Seltas Queen, 0x8a1e6c Dalamadur's tail ...)
PORTS = {'black_gravios': ('em041', 41, 'uEm038', 'em005_01'),
         'dalamadur': ('em024', 24, 'uEm024', 'em090_00'),
         'shah_dalamadur': ('em110', 110, 'uEm024', 'em090_01'),
         'desert_seltas': ('em094', 94, 'uEm025', 'em076_01'),
         'desert_seltas_queen': ('em095', 95, 'uEm026', 'em069_01'),
         'gogmazios': ('em089', 89, 'uEm089', 'em089_00'),
         'monoblos': ('em101', 101, 'uEm101', 'em007_01'),
         'shrouded_nerscylla': ('em096', 96, 'uEm027', 'em070_01'),
         'stygian_zinogre': ('em049', 49, 'uEm048', 'em057_01'),
         'tidal_najarala': ('em093', 93, 'uEm023', 'em068_01'),
         'tigerstripe_zamtrios': ('em092', 92, 'uEm022', 'em067_01')}
SET_MOTION = {0x94e350, 0x9190c4, 0x910c6c, 0x94ef9c, 0x94f440, 0x9200a4}   # tools/em089_actions.py
GROUND_CODE = 0x3934b8
ALL = 0xFFFFFFFF
DEPTH, STEPS = 5, 60000
CONDS = 'eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le'
BASES = sorted('ldrsb ldrsh ldrb ldrh ldrd ldr strb strh strd str push pop movw movt mov mvn orr and bic eor add sub '
               'rsb cmp cmn tst teq lsl lsr asr'.split(), key=len, reverse=True)
MN = re.compile(r'^(%s)(s?)(%s)?(?:\.\w+)?$' % ('|'.join(BASES), CONDS))
BR = re.compile(r'^(b|bl|blx|bx)(%s)?$' % CONDS)
LDM = re.compile(r'^(ldm|stm)(?:ia|ib|da|db|fd|ed|fa|ea)?(%s)?$' % CONDS)
FLAGS = re.compile(r'^(adcs|sbcs|rscs|rsbs|muls|mlas|umulls|smulls|umlals|smlals|rors|rrxs|bics|mvns|ands|orrs|eors|'
                   r'adds|subs|lsls|lsrs|asrs|movs|msr|vmrs|cmp|cmn|tst|teq)')   # other ARM / VFP ops keep NZCV
MEM = re.compile(r'^(r\d+|lr), \[(r\d+|sp|pc)(?:, #(-?(?:0x[0-9a-f]+|\d+)))?\]$')
REGS = ['r%d' % i for i in range(13)] + ['lr']


def imm(s):
    return int(s.lstrip('#'), 0) & ALL


def cond_true(c, f):
    """c under flags f = (N, Z, C, V), each True / False / None; -> True / False / None (unknown)"""
    N, Z, C, V = f
    def lnot(x): return None if x is None else not x
    def land(x, y): return False if x is False or y is False else None if x is None or y is None else True
    def lor(x, y): return True if x is True or y is True else None if x is None or y is None else False
    def eq(x, y): return None if x is None or y is None else x == y
    return {'eq': Z, 'ne': lnot(Z), 'cs': C, 'hs': C, 'cc': lnot(C), 'lo': lnot(C), 'mi': N, 'pl': lnot(N), 'vs': V,
            'vc': lnot(V), 'hi': land(C, lnot(Z)), 'ls': lor(lnot(C), Z), 'ge': eq(N, V), 'lt': lnot(eq(N, V)),
            'gt': land(lnot(Z), eq(N, V)), 'le': lor(Z, lnot(eq(N, V)))}[c]


def sub_flags(a, b):
    r = (a - b) & ALL
    return (bool(r >> 31), r == 0, a >= b, bool(((a ^ b) & (a ^ r)) >> 31))


def add_flags(a, b):
    r = (a + b) & ALL
    return (bool(r >> 31), r == 0, a + b > ALL, bool((~(a ^ b) & (a ^ r)) >> 31 & 1))


class St:
    """dataflow state: regs {reg: ('c', k) | 'this' | 'W' | ('m', must, may)}, flags, mask bits stored (must / may),
    motions set, notes"""
    __slots__ = ('regs', 'flags', 'must', 'may', 'mot', 'notes')

    def __init__(self, regs, flags=(None,) * 4, must=0, may=0, mot=frozenset(), notes=frozenset()):
        self.regs, self.flags, self.must, self.may, self.mot, self.notes = regs, flags, must, may, mot, notes

    def copy(self):
        return St(dict(self.regs), self.flags, self.must, self.may, self.mot, self.notes)

    def key(self):
        return (tuple(sorted(self.regs.items())), self.flags, self.must, self.may, self.mot, self.notes)


def join_val(x, y):
    if x == y: return x
    if isinstance(x, tuple) and isinstance(y, tuple) and x[0] == y[0] == 'm':
        return ('m', x[1] & y[1], x[2] | y[2])
    return None


def join(s, t):
    regs = {r: v for r in s.regs if r in t.regs for v in [join_val(s.regs[r], t.regs[r])] if v is not None}
    return St(regs, tuple(a if a == b else None for a, b in zip(s.flags, t.flags)), s.must & t.must, s.may | t.may,
              s.mot | t.mot, s.notes | t.notes)


def this_off(base, off):
    """(base, offset) of a memory operand, a pointer this+k (('p', k)) read as this with offset k + off"""
    return ('this', base[1] + off) if isinstance(base, tuple) and base[0] == 'p' else (base, off)


def val(s, x):
    """value of operand x (register, #imm, or `reg, lsl #n` on a constant)"""
    x = x.strip()
    if x.startswith('#'): return ('c', imm(x))
    m = re.match(r'^(r\d+|lr), (lsl|lsr|asr) (#\d+|r\d+)$', x)
    if m:
        v = s.regs.get(m.group(1))
        n = ('c', int(m.group(3)[1:])) if m.group(3).startswith('#') else s.regs.get(m.group(3))
        if not (isinstance(v, tuple) and v[0] == 'c' and isinstance(n, tuple) and n[0] == 'c'): return None
        k, n = v[1], n[1] & 0xFF
        return ('c', (k << n if m.group(2) == 'lsl' else k >> n) & ALL if n < 32 else 0)
    return s.regs.get(x)


class Ana:
    """one port's 4U class: summaries of functions under a (entry, r1) context"""

    def __init__(self, em):
        self.em, self.memo, self.work, self.seen = em, {}, {}, set()      # seen: mask stores some walk reached

    def action(self, disp, work):
        """summary of the dispatcher run with these work bytes (+0x1ca / +0x1cb ...): the action, handler included"""
        self.work = work
        return self.walk(disp, St({'r0': 'this'}), 0)

    def summary(self, f, args, depth):
        """(must, may, motions, notes) of function f called with r0 = this, args = (r1, r2): each ('c', k), 'this'
        or None (unknown)"""
        # a summary that read no work byte (+0x1ca / +0x1cb ...: 'uses work') holds for every action
        key, wkey = (f, args, depth), (f, args, depth, tuple(sorted(self.work.items())))
        for k in (wkey, key):
            if k in self.memo: return self.memo[k]
        self.memo[wkey] = (0, ALL, frozenset(), frozenset({'recursion'}))      # a cycle reads as unknown
        regs = {'r0': 'this'}
        for r, v in zip(('r1', 'r2'), args):
            if v is not None: regs[r] = v
        res = self.walk(f, St(regs), depth)
        del self.memo[wkey]
        self.memo[wkey if 'uses work' in res[3] else key] = res
        return res

    def call(self, s, t, depth):
        """apply a direct call to t on state s (in place)"""
        if t in SET_MOTION:
            v = s.regs.get('r1')
            s.mot = s.mot | {v[1] if isinstance(v, tuple) and v[0] == 'c' else -1}
        elif s.regs.get('r0') == 'this' and depth < DEPTH:
            args = tuple(v if v == 'this' or isinstance(v, tuple) and v[0] == 'c' else None
                         for v in (s.regs.get('r1'), s.regs.get('r2')))
            must, may, mot, notes = self.summary(t, args, depth + 1)
            s.must, s.may, s.mot, s.notes = s.must | must, s.may | may, s.mot | mot, s.notes | notes
            if depth == 0:
                r1 = args[0]
                s.notes = s.notes | {'call %x r1 %s' % (t, r1[1] if isinstance(r1, tuple) else r1 or '?')}
        for r in ('r0', 'r1', 'r2', 'r3', 'r12'): s.regs.pop(r, None)
        s.flags = (None,) * 4

    def walk(self, f, s0, depth):
        states, work, exits, steps = {f: s0}, [f], [], 0
        while work:
            a = work.pop()
            steps += 1
            if steps > STEPS:
                return 0, ALL, frozenset(), frozenset({'incomplete %#x' % f})
            s = states[a]
            for nxt, t in self.step(a, s, depth):
                if nxt is None:
                    exits.append(t); continue
                if nxt in states:
                    j = join(states[nxt], t)
                    if j.key() == states[nxt].key(): continue
                    states[nxt] = j
                else:
                    states[nxt] = t
                work.append(nxt)
        if not exits: return 0, 0, frozenset(), frozenset()
        must = exits[0].must
        for e in exits[1:]: must &= e.must
        may, mot, notes = 0, frozenset(), frozenset()
        for e in exits: may, mot, notes = may | e.may, mot | e.mot, notes | e.notes
        return must, may, mot, notes

    def step(self, a, s, depth):
        """[(next address or None = exit, state)]"""
        m, o = dis4u.INS(a)
        o = o.split(' @')[0].split(' <')[0].strip()
        ops = xref.split_ops(o)
        b = BR.match(m)
        if b:
            c = b.group(2)
            ok = cond_true(c, s.flags) if c else True
            out = [] if ok is True else [(a + 4, s)]
            if ok is False: return out
            t = s.copy()
            if b.group(1) == 'bx':
                return out + [(None, t)]                                     # return or tail jump
            if b.group(1) == 'blx':
                t.notes = t.notes | {'indirect call'}
                for r in ('r0', 'r1', 'r2', 'r3', 'r12'): t.regs.pop(r, None)
                t.flags = (None,) * 4
                return out + [(a + 4, t)]
            tg = int(o.split()[0], 16)
            if b.group(1) == 'bl':
                self.call(t, tg, depth)
                return out + [(a + 4, t)]
            if disp4u.is_func_start(tg):                                     # tail call
                self.call(t, tg, depth)
                return out + [(None, t)]
            return out + [(tg, t)]
        mm = MN.match(m)
        lm = LDM.match(m)
        cond = (mm.group(3) if mm else lm.group(2) if lm else None)
        ok = cond_true(cond, s.flags) if cond else True
        if ok is False: return [(a + 4, s)]
        t = s.copy()
        res = self.exec(a, m, o, ops, mm, lm, t, depth)
        if res == 'exit':
            out = [(None, t)]
        elif isinstance(res, list):
            out = [(x, t) for x in res]
        else:
            out = [(a + 4, t)]
        if ok is None:                                                       # may or may not run
            out = out + [(a + 4, s)]
        return out

    def exec(self, a, m, o, ops, mm, lm, t, depth):
        """execute on t; -> None (fall through), 'exit', or [successors] (jump table)"""
        if lm or (mm and mm.group(1) == 'pop'):
            if re.search(r'\bpc\b', o) and (lm is None or lm.group(1) == 'ldm'):
                return 'exit'
        if mm:
            base, sflag = mm.group(1), mm.group(2)
            if ops and ops[0] == 'pc':
                return self.pc_write(a, base, ops, t)
            if base in ('cmp', 'cmn', 'tst', 'teq'):
                x, y = val(t, ops[0]), val(t, ops[1])
                if isinstance(x, tuple) and x[0] == 'c' and isinstance(y, tuple) and y[0] == 'c':
                    p, q = x[1], y[1]
                    if base == 'cmp': t.flags = sub_flags(p, q)
                    elif base == 'cmn': t.flags = add_flags(p, q)
                    else:
                        r = p & q if base == 'tst' else p ^ q
                        t.flags = (bool(r >> 31), r == 0, t.flags[2], t.flags[3])
                else:
                    t.flags = (None,) * 4
                return None
            if base in ('ldr', 'ldrb') and len(ops) == 2:
                mem = MEM.match(o)
                if mem and mem.group(1) in REGS:
                    rb, off = this_off(t.regs.get(mem.group(2)), int(mem.group(3) or '0', 0))
                    v = None
                    if rb == 'this' and off == 0xca8 and base == 'ldr': v = ('m', 0, 0)
                    elif rb == 'this' and off == 0xe28 and base == 'ldr': v = 'W'
                    elif rb == 'W' and off == 0x1c0 and base == 'ldrb': v = ('c', self.em)
                    elif rb == 'W' and off in self.work and base == 'ldrb':
                        v, t.notes = ('c', self.work[off]), t.notes | {'uses work'}
                    elif mem.group(2) == 'pc' and base == 'ldr': v = ('c', a4u.u(a + 8 + off))
                    t.regs.pop(mem.group(1), None)
                    if v is not None: t.regs[mem.group(1)] = v
                    return None
            if base == 'str' and len(ops) == 2:
                mem = MEM.match(o)
                rb, off = this_off(t.regs.get(mem.group(2)), int(mem.group(3) or '0', 0)) if mem else (None, 0)
                if mem and (int(mem.group(3) or '0', 0) == 0xca8 or rb == 'this' and off == 0xca8) \
                        and mem.group(2) != 'sp':
                    self.seen.add(a)
                    if rb == 'this' and off == 0xca8:
                        v = t.regs.get(mem.group(1))
                        if isinstance(v, tuple) and v[0] == 'm': t.must, t.may = t.must | v[1], t.may | v[2]
                        elif isinstance(v, tuple) and v[0] == 'c': t.must, t.may = t.must | v[1], t.may | v[1]
                        else: t.may, t.notes = ALL, t.notes | {'mask store of an unknown value at %#x' % a}
                    else:
                        t.notes = t.notes | {'+0xca8 store through a pointer not this at %#x' % a}
                    return None
            if base in ('mov', 'movw', 'mvn') and len(ops) == 2 and ops[0] in REGS:
                v = val(t, ops[1])
                if base == 'mvn': v = ('c', ~v[1] & ALL) if isinstance(v, tuple) and v[0] == 'c' else None
                t.regs.pop(ops[0], None)
                if v is not None: t.regs[ops[0]] = v
                if sflag: t.flags = (None,) * 4
                return None
            if base in ('orr', 'and', 'bic', 'eor', 'add', 'sub', 'lsl', 'lsr') and len(ops) == 3 and ops[0] in REGS:
                x, y = val(t, ops[1]), val(t, ops[2])
                v = None
                if isinstance(x, tuple) and x[0] == 'm' and base in ('orr', 'bic'):
                    if isinstance(y, tuple) and y[0] == 'c':
                        k = y[1]
                        v = ('m', x[1] | k, x[2] | k) if base == 'orr' else ('m', x[1] & ~k, x[2] & ~k)
                    elif base == 'orr':
                        v = ('m', x[1], ALL)
                elif base in ('add', 'sub') and (x == 'this' or isinstance(x, tuple) and x[0] == 'p') \
                        and isinstance(y, tuple) and y[0] == 'c':
                    k = this_off(x, 0)[1]                 # `add r5, r4, #3072; add r5, r5, #552`: this+0xe28
                    v = ('p', k + y[1] if base == 'add' else k - y[1])
                elif isinstance(x, tuple) and x[0] == 'c' and isinstance(y, tuple) and y[0] == 'c':
                    p, q = x[1], y[1]
                    v = ('c', {'orr': p | q, 'and': p & q, 'bic': p & ~q, 'eor': p ^ q, 'add': p + q, 'sub': p - q,
                               'lsl': p << (q & 31), 'lsr': p >> (q & 31)}[base] & ALL)
                t.regs.pop(ops[0], None)
                if v is not None: t.regs[ops[0]] = v
                if sflag: t.flags = (None,) * 4
                return None
        for r in REGS:                                                       # anything else: forget what it writes
            if r in t.regs and xref.writes(m, o, r): del t.regs[r]
        if (mm and mm.group(2)) or FLAGS.match(m):
            t.flags = (None,) * 4
        return None

    def pc_write(self, a, base, ops, t):
        """`add pc, pc, rX, lsl #2` (a table of branches after it) / `ldr pc, [pc, rX, lsl #2]` (a table of words)"""
        if base == 'ldr' and ops[1:] == ['[sp]', '#4']:
            return 'exit'                                                    # pop {pc}
        if base == 'add' and len(ops) == 3 and ops[1] == 'pc' and re.match(r'^(r\d+), lsl #2$', ops[2]):
            k = t.regs.get(ops[2].split(',')[0])
            if isinstance(k, tuple) and k[0] == 'c': return [a + 8 + 4 * k[1]]
            out, x = [], a + 8
            while BR.match(dis4u.INS(x)[0]) and dis4u.INS(x)[0] == 'b':
                out.append(x); x += 4
            return out + [a + 4]
        mt = re.match(r'^\[pc, (r\d+), lsl #2\]$', ops[1]) if base == 'ldr' and len(ops) == 2 else None
        if mt:                                       # `cmp rX, #N; ldrlo pc, [pc, rX, lsl #2]; b default; N words`
            k = t.regs.get(mt.group(1))
            if isinstance(k, tuple) and k[0] == 'c': return [a4u.u(a + 8 + 4 * k[1])]
            pm, po = dis4u.INS(a - 4)
            pn = re.match(r'^%s, #(\d+)$' % mt.group(1), po.split(' @')[0].strip()) if pm == 'cmp' else None
            if pn:
                return [a4u.u(a + 8 + 4 * j) for j in range(int(pn.group(1)))] + [a + 4]
        t.notes = t.notes | {'pc write %#x not followed' % a}
        return 'exit'


def action_table(cls, em):
    """(dispatcher, {(cat, num): summary}) of the class's slot 44 dispatcher, every category / number. Two runs: the
    step byte W+0x144 unknown (every step: motions, the bits some path sets) and at 1 (a running frame past the
    handler's set-up step 0: the bits every path sets); the summary = (must of the second, may, motions, notes of
    the first)."""
    vt = a4u.vtables(a4u.by_name()[cls])
    assert len(vt) == 1, (cls, vt)
    disp = a4u.u(vt[0] + 4 * 44)
    A = Ana(em)
    out = {}
    for cat in range(16):
        for num in range(256):
            any_step = A.action(disp, {0x1ca: cat, 0x1cb: num})
            running = A.action(disp, {0x1ca: cat, 0x1cb: num, 0x144: 1})
            out[(cat, num)] = (running[0] & any_step[1],) + any_step[1:]
    return disp, out, A, vt[0]


def class_starts(base):
    """the lowest own slot function (near its slot 44) of every 4U monster class: where the next class's code begins"""
    out = []
    for name, dti in a4u.by_name().items():
        if not name.startswith('uEm'): continue
        for vt in a4u.vtables(dti):
            own = [a4u.u(vt + 4 * k) for k in range(95) if a4u.u(vt + 4 * k) not in (0, a4u.u(base + 4 * k))]
            near = [f for f in own if abs(f - a4u.u(vt + 4 * 44)) < 0x40000]
            if len(own) > 20 and near: out.append(min(near))
    return out


def outside_bits(A, vt):
    """{bit: [where]} 4U may set outside the actions: the class's own vtable slots (not uEnemy's) but 44, and the
    mask stores in the class's code no action walk reached (their `orr #bits` before the store; unknown value = every
    bit). The class's code = from its lowest own slot function to its highest + 0x8000, among those within 0x40000 of
    the dispatcher (other own slots are shared intermediate classes' functions)."""
    base = a4u.vtables(a4u.by_name()['uEnemy'])[0]
    own = {k: a4u.u(vt + 4 * k) for k in range(95) if a4u.u(vt + 4 * k) != a4u.u(base + 4 * k)}
    out = collections.defaultdict(list)
    A.work = {}
    for k, f in sorted(own.items()):
        if k == 44 or not f: continue
        for b in bits(A.summary(f, (None, None), 1)[1]): out[b].append('slot %d %x' % (k, f))
    near = [f for f in own.values() if f and abs(f - own[44]) < 0x40000]
    lo, hi = min(near), max(near) + 0x8000
    hi = min([hi] + [b for b in class_starts(base) if b > max(near)])
    for a, m, o in xref.Exe('4u').scan('#0xca8]', r'^r\d+, \[r\d+, #0xca8\]$'):
        if not (lo <= a < hi and m.startswith('str')) or a in A.seen: continue
        reg, k, x = o.split(',')[0], 0, a - 4
        while x > a - 48:
            mx, ox = dis4u.INS(x)
            ox = ox.split(' @')[0].strip()
            mo = re.match(r'^%s, %s, #(-?\d+|0x[0-9a-f]+)$' % (reg, reg), ox)
            if mx.startswith('orr') and mo: k |= imm(mo.group(1))
            elif mx.startswith('ldr') and ox.startswith(reg + ', [') and '#0xca8]' in ox: break
            elif xref.writes(mx, ox, reg): k = ALL; break
            x -= 4
        for b in bits(k or ALL): out[b].append('store %x' % a)
    return out


def ground_bits():
    """bits 4U's shared ground code ors into the mask (0x3934b8, up to its first return)"""
    out, a = 0, GROUND_CODE
    for _ in range(64):
        m, o = dis4u.INS(a)
        mo = re.match(r'^r\d+, r\d+, #(-?\d+|0x[0-9a-f]+)$', o.split(' @')[0].strip())
        if m.startswith('orr') and mo: out |= imm(mo.group(1))
        if m.startswith('pop') and 'pc' in o: break
        a += 4
    assert out, 'no ground bits found at %#x' % GROUND_CODE
    return out


def motions_posting(arc4u):
    """{MEF id: {motion}} from the 4U arc's LMT event slots; {MEF id: b0} from its MEFs"""
    _, ents = arcpack.read(open(arc4u, 'rb').read())
    post, b0 = collections.defaultdict(set), {}
    for p, th, d in ents:
        if th == T['MEF']:
            for r in efl4u2gu.mef_records(d):
                if r['b0']: b0[r['id']] = r['b0']
        mo = re.search(r'\\mot\\em\d+_(\d+)$', p)
        if th == T['LMT'] and mo:
            for ev in efl4u2gu.lmt_events(d):
                if ev and ev[2]:
                    for k, rid in enumerate(ev[2]):
                        if rid: post[rid].add(int(mo.group(1)) << 8 | ev[0])
    return post, b0


def bits(x):
    return [k for k in range(32) if x >> k & 1]


def report(entry, show_actions):
    arc, em, cls, gu = PORTS[entry]
    arc4u = os.path.join(paths.DUMP, 'romfs', 'data', arc + '.arc')
    gu_arc = os.path.join(paths.monster(entry), 'romfs', 'nativeNX', 'arc', 'enemy', gu + '.arc')
    for p in (arc4u, gu_arc):
        if not os.path.isfile(p): sys.exit('gate4u: %s missing (tools/setup.py, the monster\'s build.py)' % p)
    disp, summ, A, vt = action_table(cls, em)
    outside = outside_bits(A, vt)
    acts = {k: sorted(n[5:] for n in s[3] if n.startswith('call ')) for k, s in summ.items()}
    acts = {k: v for k, v in acts.items() if v}
    post, b0 = motions_posting(arc4u)
    played = collections.defaultdict(set)                 # motion -> actions
    for k, (must, may, mot, notes) in summ.items():
        for mo in mot: played[mo].add(k)
    gated = fxaudit.module_tables(os.path.join(paths.monster(entry), 'module'))['b0']
    psl = fxaudit.psl_ids(fxaudit.entries(gu_arc))
    ground = ground_bits()
    print('%s: 4U %s (em %d) class %s, dispatcher %#x: %d category / number pairs reach a call; GU %s' % (
        entry, arc, em, cls, disp, len(acts), gu))
    if show_actions:
        for (c, n), calls in sorted(acts.items()):
            must, may, mot, notes = summ[(c, n)]
            other = sorted(x for x in notes if not x.startswith('call '))
            print('  action %d/%d  calls %s  bits always %s, sometimes %s  motions %s%s' % (
                c, n, ', '.join(calls), bits(must) or '-', bits(may & ~must) or '-',
                ' '.join('%x' % x if x >= 0 else '?' for x in sorted(mot)) or '-',
                ('  (' + '; '.join(other) + ')') if other else ''))
    rows = collections.Counter()
    for rid in sorted(r for r in b0 if psl.get(r)):
        k = b0[rid]
        gate = ', '.join('%s b0 %d' % (w, x) for x, w in gated.get(rid, [])) or 'no *b0* table lists it'
        mots = sorted(post.get(rid, ()))
        line = '  record %d  b0 %d  posted by %s  [%s]' % (rid, k, ' '.join('%x' % x for x in mots) or 'no motion',
                                                            gate)
        if ground >> k & 1:
            print(line + '\n      bit %d is a ground bit (0x3934b8, stage / area): not set by an action' % k)
            rows['ground'] += 1
            continue
        if outside.get(k):
            where = outside[k]
            print(line + '\n      bit %d is also set outside the actions (%s%s): no verdict' % (
                k, ', '.join(where[:6]), ' ...' if len(where) > 6 else ''))
            rows['outside'] += 1
            continue
        verdicts = collections.defaultdict(list)
        for mo in mots:
            for act in sorted(played.get(mo, ())):
                must, may = summ[act][0], summ[act][1]
                v = 'always' if must >> k & 1 else 'sometimes' if may >> k & 1 else 'never'
                verdicts[v].append('%d/%d' % act)
        print(line)
        if not verdicts:
            print('      no action found playing its motions'); rows['no action'] += 1
        for v in ('never', 'sometimes', 'always'):
            if verdicts[v]:
                print('      %-9s %s' % (v, ' '.join(sorted(set(verdicts[v]), key=lambda s: tuple(map(int, s.split('/')))))))
                rows[v] += 1
    print('  %d conditioned records posted by the port\'s PSLs: %s (a record counts once per verdict it has)' % (
        sum(1 for r in b0 if psl.get(r)), dict(rows)))
    unseen = sorted({n.rsplit(' ', 1)[1] for s in summ.values() for n in s[3] if 'pointer not this' in n})
    if unseen:
        print('  mask stores the actions reach through a pointer other than this (their bits are not counted: read '
              'them before trusting a `never`): %s' % ' '.join(unseen))
    print('  coverage: see the docstring; `never` = no path the pass read sets the bit\n')


def main(argv):
    if not argv or argv[0] not in list(PORTS) + ['all']:
        sys.exit(__doc__.split('\n\n')[1] + '\n\nentries: ' + ', '.join(PORTS))
    for e in (PORTS if argv[0] == 'all' else [argv[0]]):
        report(e, '--actions' in argv)


if __name__ == '__main__':
    main(sys.argv[1:])
