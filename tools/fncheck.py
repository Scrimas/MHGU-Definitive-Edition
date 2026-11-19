"""fncheck.py : every FN() call target of the module code against the argument registers its GU function reads.

  python3 tools/fncheck.py [--src ROOT]       ROOT: a checkout to scan instead of this one (module/, monsters/*/module/,
                                              maps/*/module/ *.c / *.h under it)

The FN() typedef is a call's whole contract (porting guide, lessons: Dalamadur's timerUp without its float ran at
whatever s0 held). For each `#define X FN(T, ADDR)` / inline `FN(T, ADDR)` (T a typedef name visible in the file or its
quoted includes, or an inline `RET (*)(ARGS)`), the typedef is laid out under AAPCS-VFP (int / pointer -> next r,
64-bit -> even r pair, float -> lowest free s, double -> lowest free d, back-filling) and the GU function at ADDR
(dump/gu_main/main.asm through tools/gulib/asm.py) is walked from its entry: every path up to a call (bl / blx clobber
r0-r3 and s0-s15), a return, an indirect branch or a trap, following every direct branch (thunks and tail calls
included) and clang's table jumps, with register renames tracked (`mov r3, r2` reads r2) and condition codes (a write
under eq and one under ne define the register; a branch fixes the condition on each side).
  MISSING  the function reads r0-r3 / s0-s15 before writing them on some path, and the typedef never fills that
           register (error; exit status 1)
  info     a declared argument no path reads before its first call / return (it may still be passed on to a callee)
  skip     FN() uses this tool cannot check (non-constant address, unknown type, struct by value, variadic)
Coverage: only what the entry function itself does before its first call; arguments a callee reads through a bl, stack
arguments, values read back from a push (`push {r3, lr}` is not a read: compilers push dead registers to align sp),
instructions the model does not know (`<unknown>` in main.asm, listed as incomplete) and code past an indirect branch
are not seen. No MISSING line means none found this way, not that the typedefs are right.
"""
import glob, os, re, sys

import paths
for _p in (paths.GU_MAIN, os.path.join(paths.GU_CODE, 'main.asm')):
    if not os.path.exists(_p): sys.exit('%s missing: run tools/setup.py (tools/doctor.py lists the inputs)' % _p)
sys.path.insert(0, paths.GU_PY)
import asm  # noqa: E402

ARGS = frozenset(['r%d' % i for i in range(4)] + ['s%d' % i for i in range(16)])

# ---------------------------------------------------------------- C side

def strip_comments(t):
    """comments -> spaces (newlines kept, so offsets keep their line numbers); strings are left alone"""
    out = list(t); i, n = 0, len(t)
    while i < n:
        c = t[i]
        if c in '"\'':
            j = i + 1
            while j < n and t[j] != c:
                j += 2 if t[j] == '\\' else 1
            i = j + 1
        elif t.startswith('//', i):
            while i < n and t[i] != '\n':
                out[i] = ' '; i += 1
        elif t.startswith('/*', i):
            j = t.find('*/', i + 2); j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != '\n': out[k] = ' '
            i = j
        else:
            i += 1
    return ''.join(out)


def close_paren(t, i):
    """index of the ')' matching the '(' at t[i]"""
    d = 0
    for k in range(i, len(t)):
        if t[k] == '(': d += 1
        elif t[k] == ')':
            d -= 1
            if d == 0: return k
    return -1


def split_top(s):
    out, d, cur = [], 0, ''
    for c in s:
        if c in '([{': d += 1
        elif c in ')]}': d -= 1
        if c == ',' and d == 0:
            out.append(cur); cur = ''
        else:
            cur += c
    out.append(cur)
    return [x.strip() for x in out]


TYPEDEF = re.compile(r'\btypedef\s+([\w\s\*]+?)\s*\(\s*\*\s*(\w+)\s*\)\s*\(')
DEFINE = re.compile(r'^[ \t]*#[ \t]*define[ \t]+(\w+)[ \t]+\(?(0x[0-9a-fA-F]+|\d+)[uUlL]*\)?[ \t]*$', re.M)
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]+"([^"]+)"', re.M)
FNUSE = re.compile(r'\bFN\s*\(')
MACRO = re.compile(r'#[ \t]*define[ \t]+(\w+)[ \t]+$')
INLINE_T = re.compile(r'^([\w\s\*]+?)\s*\(\s*\*\s*\)\s*\((.*)\)$', re.S)

_files = {}


def source(path):
    if path not in _files:
        with open(path, encoding='utf-8') as f:
            _files[path] = strip_comments(f.read())
    return _files[path]


def scope(path, incdirs):
    """path and every quoted include it pulls in (own folder first, then the build's -I folders); unresolved ones
    (generated headers, system headers) are left out"""
    out, todo = [], [path]
    while todo:
        p = todo.pop(0)
        if p in out: continue
        out.append(p)
        for name in INCLUDE.findall(source(p)):
            for d in [os.path.dirname(p)] + incdirs:
                q = os.path.join(d, name)
                if os.path.isfile(q):
                    todo.append(os.path.normpath(q)); break
    return out


def typedefs(text):
    out = []
    for m in TYPEDEF.finditer(text):
        e = close_paren(text, m.end() - 1)
        if e < 0 or not re.match(r'\s*;', text[e + 1:]): continue
        out.append((m.group(2), ' '.join(m.group(1).split()), ' '.join(text[m.end():e].split())))
    return out


SCALAR32 = {'int', 'unsigned', 'signed', 'uint32_t', 'int32_t', 'uint16_t', 'int16_t', 'uint8_t', 'int8_t', 'char',
            'short', 'long', 'bool', '_Bool', 'size_t', 'uintptr_t', 'intptr_t'}
SCALAR64 = {'uint64_t', 'int64_t'}
QUALS = {'const', 'volatile', 'register'}


def kind(t, param):
    """'r' / 'r64' / 's' / 'd' / 'void', or None (a type this tool does not lay out)"""
    if '*' in t or '[' in t: return 'r'
    w = [x for x in t.split() if x not in QUALS]
    if param and len(w) > 1 and w[-1] not in SCALAR32 | SCALAR64 | {'float', 'double', 'void'}:
        w = w[:-1]                                  # the parameter's name
    if w == ['void']: return 'void'
    if w == ['float']: return 's'
    if w == ['double']: return 'd'
    if w and w[0] == 'enum': return 'r'
    if set(w) <= SCALAR64 or w in (['long', 'long'], ['unsigned', 'long', 'long']): return 'r64'
    if w and set(w) <= SCALAR32: return 'r'
    return None


def layout(ret, params):
    """registers the AAPCS-VFP call fills, as [(param text, [regs])], or (None, why)"""
    if kind(ret, False) is None: return None, 'return type %r' % ret
    ps = split_top(params)
    if ps == ['void'] or ps == ['']: return [], None
    if '...' in ps: return None, 'variadic'
    out, ncrn, sfree, vfp_stack = [], 0, [True] * 16, False
    for p in ps:
        k = kind(p, True)
        if k in (None, 'void'): return None, 'parameter %r' % p
        regs = []
        if k == 'r':
            if ncrn < 4: regs = ['r%d' % ncrn]
            ncrn = min(ncrn + 1, 4)
        elif k == 'r64':
            ncrn = (ncrn + 1) & ~1
            if ncrn <= 2: regs = ['r%d' % ncrn, 'r%d' % (ncrn + 1)]
            ncrn = min(ncrn + 2, 4)
        else:
            step = 1 if k == 's' else 2
            free = [i for i in range(0, 16, step) if all(sfree[i:i + step])] if not vfp_stack else []
            if free:
                regs = ['s%d' % i for i in range(free[0], free[0] + step)]
                for i in range(free[0], free[0] + step): sfree[i] = False
            else:
                vfp_stack = True                    # AAPCS C.2: one VFP argument on the stack closes the VFP registers
        out.append((p, regs))
    return out, None


def fn_uses(path, incdirs):
    """[(line, macro or None, type text, addr or None, why)] for every FN( in the file (the macro FN itself excluded)"""
    text = source(path)
    td, consts = {}, {}
    for p in reversed(scope(path, incdirs)):
        for name, ret, params in typedefs(source(p)):
            td.setdefault(name, set()).add((ret, params))
        consts.update((k, int(v, 0)) for k, v in DEFINE.findall(source(p)))
    out = []
    for m in FNUSE.finditer(text):
        e = close_paren(text, m.end() - 1)
        line = text.count('\n', 0, m.start()) + 1
        pre = text[text.rfind('\n', 0, m.start()) + 1:m.start()]
        mac = MACRO.match(pre.strip() + ' ') if pre.strip().startswith('#') else None
        args = split_top(text[m.end():e])
        if len(args) != 2 or re.search(r'#\s*define\s*$', pre): continue      # the macro FN's own definition
        t, a = ' '.join(args[0].split()), args[1]
        mm = re.fullmatch(r'(0x[0-9a-fA-F]+|\d+)[uUlL]*', a)
        addr = int(mm.group(1), 0) if mm else consts.get(a)
        sig, why = None, None
        if addr is None: why = 'address %r is not a constant' % a
        elif re.fullmatch(r'\w+', t):
            defs = td.get(t, set())
            if len(defs) == 1: sig = next(iter(defs))
            else: why = 'type %s: %s' % (t, 'not found' if not defs else '%d different typedefs' % len(defs))
        else:
            mi = INLINE_T.match(t)
            if mi: sig = (' '.join(mi.group(1).split()), ' '.join(mi.group(2).split()))
            else: why = 'type %r not parsed' % t
        out.append((line, mac.group(1) if mac else None, t, addr, sig, why))
    return out


# ---------------------------------------------------------------- GU side: which argument registers a function reads

CONDS = {'eq': 'ne', 'ne': 'eq', 'hs': 'lo', 'lo': 'hs', 'mi': 'pl', 'pl': 'mi', 'vs': 'vc', 'vc': 'vs', 'hi': 'ls',
         'ls': 'hi', 'ge': 'lt', 'lt': 'ge', 'gt': 'le', 'le': 'gt'}
ALIAS = {'cs': 'hs', 'cc': 'lo'}
ALU = set('''mov mvn add adc sub sbc rsb rsc and orr eor bic lsl lsr asr ror rrx mul sdiv udiv movw adr uxtb uxth uxtab
 uxtah uxtb16 sxtb sxth sxtab sxtah ubfx sbfx clz rev rev16 revsh rbit pkhbt pkhtb qadd qsub qdadd qdsub smulbb smulbt
 smultb smultt smulwb smulwt smmul smmulr mla mls smlabb smlabt smlatb smlatt smlawb smlawt smmla smmls usat ssat
 vadd vsub vmul vnmul vdiv vabs vneg vsqrt vmov vcvt vcvtr vmax vmin vorr vand veor vbic vorn vmvn vdup vext vpadd
 vpmax vpmin vrecpe vrsqrte vrecps vrsqrts vmovl vmovn vqmovn vshl vshr vcge vcgt vceq vabd vrev64 vcnt vtst'''.split())
RMW = set('movt bfi bfc vmla vmls vnmla vnmls vfma vfms vfnma vfnms vbsl vbit vbif vsli vsri'.split())
PAIR_W = {'umull', 'smull'}
PAIR_RW = set('umlal smlal umaal smlalbb smlalbt smlaltb smlaltt smlald smlsld'.split())
SWAP = set('vzip vuzp vtrn vswp'.split())
CMP = set('cmp cmn tst teq vcmp vcmpe'.split())
LOAD = set('ldr ldrb ldrh ldrsb ldrsh ldrex ldrexb ldrexh vldr ldrd ldrexd'.split())
STORE = set('str strb strh vstr strd pld pli'.split())
STREX = set('strex strexb strexh strexd'.split())
LDM = set('ldm ldmia ldmib ldmda ldmdb pop vldmia vldmdb vpop vld1 vld2 vld3 vld4'.split())
STM = set('stm stmia stmib stmda stmdb push vstmia vstmdb vpush vst1 vst2 vst3 vst4'.split())
SYS = set('vmrs vmsr mrs msr mrc mcr'.split())
TRAP = set('svc udf bkpt hlt'.split())
NOP = set('nop dmb dsb isb clrex'.split())
BRANCH = {'b', 'bl', 'blx', 'bx'}
KNOWN = ALU | RMW | PAIR_W | PAIR_RW | SWAP | CMP | LOAD | STORE | STREX | LDM | STM | SYS | TRAP | NOP | BRANCH
SFLAG = ALU | PAIR_W | PAIR_RW
REG = re.compile(r'\b([rsdq])(\d+)\b(\[(\d*)\])?')


def mnemonic(m):
    """'vmovgt.f32' -> ('vmov', 'gt', False, 'f32'); None for a mnemonic the model does not know"""
    core, _, dt = m.partition('.')
    for cand, cc in ((core, 'al'), (core[:-2], ALIAS.get(core[-2:], core[-2:]))):
        if cc != 'al' and cc not in CONDS: continue
        if cand in KNOWN: return cand, cc, False, dt
        if cand.endswith('s') and cand[:-1] in SFLAG: return cand[:-1], cc, True, dt
    return None


def regs(text, dt=''):
    """argument registers named in an operand text, lanes resolved (d0[1] of a .32 op = s1)"""
    size = int(re.search(r'(\d+)$', dt).group(1)) if re.search(r'\d+$', dt) else 32
    out = set()
    for t, n, lane, k in REG.findall(text):
        n = int(n)
        if t == 'r' and n < 4: out.add('r%d' % n)
        elif t == 's' and n < 16: out.add('s%d' % n)
        elif t == 'd' and n < 8:
            if lane and k != '' and size < 64: out.add('s%d' % (2 * n + int(k) * size // 32))
            else: out |= {'s%d' % (2 * n), 's%d' % (2 * n + 1)}
        elif t == 'q' and n < 4: out |= {'s%d' % i for i in range(4 * n, 4 * n + 4)}
    return out


def mem_wb(ops):
    """(address registers, base register if written back) of a load / store's operands after the data registers"""
    rest = ', '.join(ops)
    m = re.search(r'\[([^\]]*)\](!?)(.*)$', rest)
    if not m: return regs(rest), None
    base = regs(m.group(1).split(',')[0])
    wb = m.group(2) == '!' or m.group(3).strip().startswith(',')
    return regs(m.group(1)) | regs(m.group(3)), (base if wb else None)


def armv8_fp(w):
    """main.asm's `<unknown>` for ARMv8 vsel / vmaxnm / vminnm (GU's motion checks use vsel): (mnemonic, operands)"""
    if (w >> 23) not in (0x1fc, 0x1fd) or (w >> 9) & 7 != 5 or w & 0x10 or ((w >> 23) == 0x1fd and (w >> 20) & 3):
        return None
    sz = (w >> 8) & 1
    f = (lambda v, x: 'd%d' % (x << 4 | v)) if sz else (lambda v, x: 's%d' % (v << 1 | x))
    d, n, m = f(w >> 12 & 15, w >> 22 & 1), f(w >> 16 & 15, w >> 7 & 1), f(w & 15, w >> 5 & 1)
    return 'vmax' if (w >> 23) == 0x1fd else 'vmov', '%s, %s, %s' % (d, n, m)   # both: d written, n and m read


def jump_table(a, ra, rb):
    """targets of clang's table jump at a (motionCheck's kind switch): `cmp rK, #N; bhi; ...; add rB, pc, #imm;
    ldr rA, [rX, rB]; add pc, rA, rB`, N + 1 words of offsets from the table start; None for any other shape"""
    base = n = None; ldr = bhi = False
    for k in range(1, 10):
        m, o = asm.INS.get(a - 4 * k, ('', ''))
        mm = re.fullmatch(re.escape(rb) + r', pc, #(\d+)', o)
        if m == 'add' and mm and base is None: base = a - 4 * k + 8 + int(mm.group(1))
        if m == 'ldr' and re.fullmatch(re.escape(ra) + r', \[r\d+, ' + re.escape(rb) + r'\]', o): ldr = True
        if m == 'bhi': bhi = True
        mm = re.fullmatch(r'r\d+, #(\d+)', o)
        if m == 'cmp' and mm:
            n = int(mm.group(1)); break
    if base is None or n is None or not (ldr and bhi): return None
    out = [(base + asm.u32(base + 4 * i)) & 0xffffffff for i in range(n + 1)]
    return out if all(t in asm.INS for t in out) else None


_model = {}


def model(a):
    """(cc, reads, writes, flags, flow, target) of the instruction at a, flow in None / 'b' / 'call' / 'ret' / 'ind' /
    'trap'; None when the model does not know the instruction"""
    if a in _model: return _model[a]
    m, o = asm.INS.get(a, ('?', ''))
    if m == '<unknown>': m, o = armv8_fp(asm.u32(a)) or (m, o)
    p = mnemonic(m)
    if p is None:
        _model[a] = None; return None
    base, cc, s, dt = p
    o = o.split(' <')[0]
    ops = split_top(o) if o else []
    R, W, flags, flow, target = set(), set(), s, None, None
    first = ops[0] if ops else ''
    if base in BRANCH:
        if base == 'bx':
            R = regs(first); flow = 'ret' if first == 'lr' else 'ind'
        elif re.match(r'0x[0-9a-f]+$', first):
            target = int(first, 16); flow = 'b' if base == 'b' else 'call'
        else:
            R = regs(first); flow = 'call'
    elif base in TRAP:
        flow = 'trap'
    elif base in NOP:
        pass
    elif base in CMP:
        R = regs(o, dt); flags = base[0] != 'v'                   # vcmp sets FPSCR; vmrs copies it to APSR
    elif base in SYS:
        if base == 'vmrs' and first == 'APSR_nzcv': flags = True
        elif base in ('vmrs', 'mrs'): W = regs(first)
        elif base == 'mrc': W = regs(ops[2])
        elif base == 'mcr': R = regs(ops[2])
        else:
            R = regs(', '.join(ops[1:])); flags = base == 'msr' and re.match(r'(apsr|cpsr)', first, re.I) is not None
    elif base in LOAD:
        n = 2 if base in ('ldrd', 'ldrexd') else 1
        R, wb = mem_wb(ops[n:])
        W = regs(', '.join(ops[:n]), dt) | (wb or set())
        if first == 'pc': flow = 'ret' if re.match(r'\[sp\], #4$', ', '.join(ops[1:])) else 'ind'
    elif base in STORE or base in STREX:
        lo = 1 if base in STREX else 0
        n = lo + (2 if base in ('strd', 'strexd') else 0 if base in ('pld', 'pli') else 1)
        R, wb = mem_wb(ops[n:])
        R = R | regs(', '.join(ops[lo:n]), dt)
        W = regs(', '.join(ops[:lo])) | (wb or set())
    elif base in LDM or base in STM:
        lst = next((x for x in ops if x.startswith('{')), '')
        lst = re.sub(r'\b([rsd])(\d+)-[rsd]?(\d+)', lambda x: ', '.join(
            '%s%d' % (x.group(1), i) for i in range(int(x.group(2)), int(x.group(3)) + 1)), lst)
        addr = [x for x in ops if not x.startswith('{')]
        R, wb = mem_wb(addr) if base.startswith(('vld', 'vst')) else (regs(', '.join(addr)), None)
        if addr and addr[0].endswith('!'): wb = regs(addr[0])
        W = wb or set()
        if base in LDM:
            W = W | regs(lst, dt)
            if re.search(r'\bpc\b', lst): flow = 'ret' if base == 'pop' or (addr and addr[0] == 'sp!') else 'ind'
        elif base not in ('push', 'vpush'):              # push of r0-r3 / d0-d7 only pads or saves: not a use
            R = R | regs(lst, dt)
    elif base in PAIR_W:
        W, R = regs(', '.join(ops[:2])), regs(', '.join(ops[2:]))
    elif base in PAIR_RW:
        W, R = regs(', '.join(ops[:2])), regs(o)
    elif base in SWAP:
        R = W = regs(o, dt)
    elif base in RMW:
        R, W = regs(o, dt), regs(first, dt)
    else:                                                # ALU: first operand written, the rest read
        n = 2 if base == 'vmov' and (len(ops) == 4 or (len(ops) == 3 and first.startswith('r'))) else 1
        W, R = regs(', '.join(ops[:n]), dt), regs(', '.join(ops[n:]), dt)
        if base in ('eor', 'sub', 'veor') and len(ops) == 3 and ops[0] == ops[1] == ops[2]:
            R = set()                                    # x ^ x, x - x: zeroing, not a use
        if first == 'pc':
            target = jump_table(a, ops[1], ops[2]) if base == 'add' and cc == 'al' and len(ops) == 3 else None
            flow = 'switch' if target else 'ret' if o == 'pc, lr' else 'ind'
    _model[a] = (cc, frozenset(R), frozenset(W), flags, flow, target)
    return _model[a]


_scans = {}


def scan(entry, limit=200000):
    """{reg: (addr, conditional)} of argument registers read before written, [(flow, addr)] path ends,
    [addr] instructions the model does not know (paths stop there)"""
    if entry in _scans: return _scans[entry]
    reads, ends, unknown = {}, [], []
    seen, todo = set(), [(entry, ARGS, None, frozenset(), None)]

    def go(a, undef, known, cw, pend):
        # `cmp; ldrne r2; cmpne r2, #0; beq`: past the beq (ne known) the cmpne ran, so did every write under ne before it
        if pend and known == pend[0]: undef, pend = undef - pend[1], None
        todo.append((a, undef, known, cw, pend))
    while todo:
        st = todo.pop()
        if st in seen: continue
        seen.add(st)
        if len(seen) > limit:
            unknown.append(None); break
        a, undef, known, cw, pend = st
        e = model(a)
        if e is None:
            unknown.append(a); continue
        cc, R, W, flags, flow, target = e
        run = 'always' if cc == 'al' or cc == known else 'never' if CONDS.get(cc) == known else 'maybe'
        if run == 'never':
            go(a + 4, undef, known, cw, pend); continue
        for r in R & undef:
            if run == 'maybe' and (r, cc) in cw: continue        # read of its own conditional write
            if r not in reads or (reads[r][1] and run == 'always'):
                reads[r] = (a, run == 'maybe')
        undef, cw = set(undef), set(cw)
        for r in W & undef:
            if run == 'always' or (r, CONDS[cc]) in cw: undef.discard(r)
            else: cw.add((r, cc))
        if flags:
            if run == 'maybe':                                     # flags now: the old ones (cc false) or new ones
                p = frozenset(r for r, c in cw if c == cc) | (pend[1] if pend and pend[0] == cc else frozenset())
                pend = (cc, p & undef)
            else:
                pend = None
            known, cw = None, set()
        undef, cw = frozenset(undef), frozenset(cw)
        nk = CONDS[cc] if run == 'maybe' else known                # the instruction did not run: its condition failed
        if flow is None:
            go(a + 4, undef, known, cw, pend)
        elif flow == 'b':
            go(target, undef, cc if run == 'maybe' else known, cw, pend)
            if run == 'maybe': go(a + 4, undef, nk, cw, pend)
        elif flow == 'switch':
            for t in target: go(t, undef, known, cw, pend)
        else:
            ends.append((flow, a))
            if run == 'maybe': go(a + 4, undef, nk, cw, pend)
    _scans[entry] = (reads, ends, unknown)
    return _scans[entry]


def ins_text(a):
    m, o = asm.INS.get(a, ('?', ''))
    return '%x: %s %s' % (a, m, o.split(' <')[0])


# ---------------------------------------------------------------- report

def main(argv):
    root = paths.ROOT
    if argv[:1] == ['--src']:
        if len(argv) < 2 or not os.path.isdir(argv[1]): sys.exit('fncheck: --src needs a folder')
        root = os.path.abspath(argv[1]); argv = argv[2:]
    if argv: sys.exit(__doc__)
    mods = sorted(glob.glob(os.path.join(root, 'monsters', '*', 'module'))) + \
        sorted(glob.glob(os.path.join(root, 'maps', '*', 'module')))
    incdirs = [os.path.join(root, 'module')] + mods
    files = [f for d in incdirs for f in sorted(glob.glob(os.path.join(d, '*.[ch]')))]
    if not files: sys.exit('fncheck: no module sources under %s' % root)
    sites = {}
    for f in files:
        for line, mac, t, addr, sig, why in fn_uses(f, incdirs):
            k = (os.path.relpath(f, root), mac, t, addr, sig, why)
            sites.setdefault(k, []).append(line)
    n_missing = n_info = n_skip = n_inc = 0
    out_m, out_i, out_s = [], [], []
    for (f, mac, t, addr, sig, why), lines in sorted(sites.items(), key=lambda x: (x[0][3] or 0, x[0][0], x[1])):
        where = '%s:%s' % (f, ','.join(map(str, lines)))
        name = mac or 'FN(%s)' % t
        if why is None:
            lay, why = layout(*sig)
        if why is not None:
            out_s.append('skip     %-9s %-18s %s  (%s)' % ('0x%x' % addr if addr is not None else '?', name, where, why))
            n_skip += 1; continue
        if not 0 < addr < 0x13f1dec or addr % 4:
            out_s.append('skip     0x%-7x %-18s %s  (not a code address)' % (addr, name, where)); n_skip += 1; continue
        filled = {r for _, rs in lay for r in rs}
        reads, ends, unknown = scan(addr)
        inc = ''
        if unknown or any(fl == 'ind' for fl, _ in ends):
            n_inc += 1
            inc = '  [incomplete: %s]' % ', '.join(
                ['path limit' if u is None else 'unmodelled %s' % ins_text(u) for u in sorted(set(unknown), key=str)[:3]] +
                ['indirect branch %x' % x for x in sorted({x for fl, x in ends if fl == 'ind'})][:3])
        missing = sorted(set(reads) - filled, key=lambda r: (r[0], int(r[1:])))
        sigtxt = '%s (*)(%s)' % sig
        if missing:
            n_missing += len(missing)
            out_m.append('MISSING  0x%-7x %-18s %s  %s  fills %s%s' % (addr, name, where, sigtxt,
                                                                    ' '.join(sorted(filled)) or '-', inc))
            for r in missing:
                ra, cond = reads[r]
                out_m.append('         reads %-3s before writing it: %s%s' % (r, ins_text(ra), ' (conditional)' if cond else ''))
        unread = [(p, rs) for p, rs in lay if rs and not any(r in reads for r in rs)]
        if unread:
            n_info += 1
            out_i.append('info     0x%-7x %-18s %s  unread: %s%s' % (
                addr, name, where, '; '.join('%s (%s)' % (p, '/'.join(rs)) for p, rs in unread), inc))
    print('\n'.join(out_m + out_i + out_s))
    print('fncheck: %d FN() sites in %d sources: %d MISSING argument registers, %d sites with unread declared '
          'arguments, %d skipped, %d walks incomplete. Coverage: reads before the first call / return of the entry '
          'function only (see the docstring); no MISSING line means none found this way.' % (
              len(sites), len(files), n_missing, n_info, n_skip, n_inc))
    return 1 if n_missing else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
