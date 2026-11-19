"""hookcheck.py : static check of every mhgu-de patch site against GU main (dump/gu_main: mem.bin, main.asm).

usage: python3 tools/hookcheck.py        exit 1 when a definite problem (PROBLEM) is found

Sites: module/build.py's HOOKS (module/gear_hooks.txt and every define-conditional addition, each with its
condition, read from build.py's source, so the environment's GOG_DEFINES does not hide any), REPLACE_HOOKS,
MID_EXIT, WORD_PATCHES, LIT_PATCHES and the item bound patches (build.item_patches). A hook patches the word at the
site; its trampoline calls <name>_c, runs `cmp r0, #0`, replays the site and site + 4 (when the call returned 0) and
goes on at site + 8. REPLACE_HOOKS replay nothing (the function is replaced); a MID_EXIT hook jumps to its exit when
the call returned nonzero.
Checks (PROBLEM = definite, exit 1; WARNING = needs a look):
- overlapping windows: a hook covers 8 bytes (site, site + 4), a word / literal / item patch 4
- the displaced pair: what build.py refuses to displace; an instruction reading NZCV (a condition, adc / sbc / rsc,
  rrx, mrs), which sees the trampoline's flags; an `ldr rX, [pc, #imm]` of a literal the IPS patches (the
  trampoline copies the original value)
- flags live across the site: on the path from the site (fallthrough and unconditional b, at most 64 instructions,
  ending at a call, a return or an indirect jump), an instruction reading flags that only the code before the site
  set; on a MID_EXIT path, one reading the trampoline's flags (WARNING: there Z=0 C=1 V=0, N = bit 31 of r0)
- branches into site + 4 from all of main's text (b / bl / b<cond>; build.py only looks +-16 KB): the hook is skipped
  on that path; relocated data words equal to site + 4 (function pointers, absolute jump tables). Not covered:
  pc-relative jump tables of offsets, addresses computed in code (add rX, pc, ...), Thumb blx.
- MID_EXIT / REPLACE_HOOKS names without a hook, and a MID_EXIT exit outside the hook's function (by asm.func_start)
- per hook: the containing function and its names (tools/sym.py: asm.func_start, ghidra_names' rows).
Not checked: whether a mid-function hook without MID_EXIT always returns 0 (its C code), PLUGIN_CHECKED (build.py).
"""
import ast, collections, importlib.util, os, struct, sys

import numpy as np

import paths
sys.path.insert(0, paths.GU_PY)
import asm, vt  # noqa: E402
import ghidra_names as gn, sym  # noqa: E402

BUILD = os.path.join(paths.ROOT, 'module', 'build.py')
TABLES = ('HOOKS', 'REPLACE_HOOKS', 'MID_EXIT')
MUTATORS = {'append', 'extend', 'insert', 'update', 'add', 'pop', 'remove', 'clear', 'setdefault', 'discard'}
SCAN = 64
TEXT_END = vt.TEXT_END
MEM = asm.MEM
COND_READS = {0: 'Z', 1: 'Z', 2: 'C', 3: 'C', 4: 'N', 5: 'N', 6: 'V', 7: 'V', 8: 'CZ', 9: 'CZ', 10: 'NV', 11: 'NV',
              12: 'NVZ', 13: 'NVZ'}
NZCV = frozenset('NZCV')


def u32(a):
    return struct.unpack_from('<I', MEM, a)[0]


def load_build():
    """module/build.py as a module: its import only reads files (no build runs outside __main__)"""
    spec = importlib.util.spec_from_file_location('mhgu_de_build', BUILD)
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    return b


def tables(b):
    """hooks [(name, site, condition)], replace {name: condition}, mid {name: (exit, condition)} from build.py's
    source; condition = the source of the enclosing ifs, None = always"""
    src = open(BUILD, encoding='utf-8').read()
    tree = ast.parse(src)
    hooks, replace, mid, read = [], {}, {}, set()

    def table(t):
        if isinstance(t, ast.Subscript): t = t.value
        return t.id if isinstance(t, ast.Name) else None

    def visit(body, cond):
        for st in body:
            if isinstance(st, ast.If):
                c = ast.get_source_segment(src, st.test)
                visit(st.body, c if cond is None else '%s and %s' % (cond, c))
                visit(st.orelse, 'not (%s)' % c if cond is None else '%s and not (%s)' % (cond, c))
                continue
            t = st.targets[0] if isinstance(st, ast.Assign) and len(st.targets) == 1 else \
                st.target if isinstance(st, ast.AugAssign) else None
            n, v = table(t), getattr(st, 'value', None)
            if n == 'HOOKS' and isinstance(v, ast.List):
                hooks.extend((h, a, cond) for h, a in ast.literal_eval(v))
            elif n == 'HOOKS' and '_GEAR_HOOKS' in ast.get_source_segment(src, v):   # read as build.py reads it
                hooks.extend((l.split()[0], int(l.split()[1], 16), cond)
                             for l in open(b._GEAR_HOOKS, encoding='utf-8') if l.strip())
            elif n == 'REPLACE_HOOKS' and isinstance(v, ast.Set):
                replace.update((h, cond) for h in ast.literal_eval(v))
            elif n == 'MID_EXIT' and isinstance(t, ast.Subscript):
                mid[ast.literal_eval(t.slice)] = (ast.literal_eval(v), cond)
            elif n == 'MID_EXIT' and isinstance(v, ast.Dict):
                mid.update((h, (a, cond)) for h, a in ast.literal_eval(v).items())
            else:
                continue
            read.add(id(st))

    visit(tree.body, None)
    for node in ast.walk(tree):   # any other change of the three tables: refuse rather than miss a hook
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AugAssign) else []
        if any(table(t) in TABLES for t in targets) and id(node) not in read or \
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                table(node.func.value) in TABLES and node.func.attr in MUTATORS:
            sys.exit('hookcheck: module/build.py line %d changes %s in a way this tool does not read'
                     % (node.lineno, ast.get_source_segment(src, node).split('\n')[0]))
    return hooks, replace, mid


def dataproc(w):
    """ARM data-processing (not multiply, extra load / store or the miscellaneous space)"""
    if w & 0x0C000000: return False
    if not (w & 0x02000000) and (w & 0x90) == 0x90: return False
    return not (((w >> 23) & 3) == 2 and not (w & 0x00100000))


def reads(w):
    """NZCV flags the instruction reads: its condition, the carry of adc / sbc / rsc / rrx, mrs"""
    if (w >> 28) == 0xF: return set()
    r = set(COND_READS.get(w >> 28, ''))
    if dataproc(w) and ((w >> 21) & 0xF) in (5, 6, 7): r.add('C')
    if dataproc(w) and not (w & 0x02000000) and (w & 0xFF0) == 0x060: r.add('C')    # rrx = ror #0
    if (w & 0x0FBF0FFF) == 0x010F0000: r |= NZCV                                       # mrs rD, apsr
    return r


def writes(w):
    """NZCV flags an unconditional instruction surely writes (a conditional one may not run)"""
    if (w >> 28) != 0xE: return set()
    if dataproc(w) and w & 0x00100000:
        if ((w >> 21) & 0xF) in (2, 3, 4, 5, 6, 7, 10, 11): return set(NZCV)
        imm = w & 0x02000000      # logical ops: C only from a shifter that rotates / shifts by a constant
        return set('NZC') if (imm and w & 0xF00) or (not imm and not (w & 0x10) and w & 0xFF0) else set('NZ')
    if (w & 0x0F0000F0) == 0x00000090 and w & 0x00100000: return set('NZ')          # muls / umulls ...
    if (w & 0x0FB0FFF0) == 0x0120F000 and w & 0x00080000: return set(NZCV)          # msr apsr_f, rM
    if (w & 0x0FB0F000) == 0x0320F000 and w & 0x00080000: return set(NZCV)          # msr apsr_f, #imm
    if (w & 0x0F10F010) == 0x0E10F010: return set(NZCV)                             # vmrs / mrc to APSR_nzcv
    return set()


def is_branch(w):
    return (w >> 28) != 0xF and (w & 0x0E000000) == 0x0A000000


def branch_target(a, w):
    off = w & 0xFFFFFF
    return a + 8 + 4 * (off - 0x1000000 if off & 0x800000 else off)


def leaves(w):
    """writes pc other than by b / bl: bx / blx rM, ldm / pop with pc, ldr pc, data-processing into pc"""
    return (w & 0x0FFFFFD0) == 0x012FFF10 or (w & 0x0E108000) == 0x08108000 or (w & 0x0C10F000) == 0x0410F000 or \
        dataproc(w) and ((w >> 12) & 15) == 15 and ((w >> 21) & 0xF) not in (8, 9, 10, 11)


def flag_reader(a, unset):
    """the first instruction on the path from a (fallthrough, unconditional b) reading a flag of unset before the path
    writes it: (address, flags), or (None, why the walk stopped)"""
    unset = set(unset)
    for _ in range(SCAN):
        if not 0 <= a < TEXT_END: return None, 'left the text'
        w = u32(a)
        r = reads(w) & unset
        if r: return a, ''.join(sorted(r))
        unset -= writes(w)
        if not unset: return None, 'flags rewritten at %x' % a
        if (w >> 28) == 0xE and is_branch(w):
            if w & 0x01000000: return None, 'call at %x' % a       # AAPCS: no flags survive a call
            a = branch_target(a, w); continue
        if (w >> 28) == 0xE and leaves(w): return None, 'path ends at %x' % a
        a += 4
    return None, 'undecided after %d instructions' % SCAN


def dis(a):
    return '%x: %s %s' % ((a,) + asm.INS.get(a, ('?', '')))


def func_name(start):
    """the confirmed name of a function start, else its first comment that is not a hook's, else '-'"""
    rows = sym.knowledge()['gu'].get(start, [])
    for k, t, _ in rows:
        if k == 'func': return t
    for k, t, _ in rows:
        if k == 'comment' and not t.startswith('mhgu-de hook'): return '(comment: %s)' % t
    return '-'


def main():
    b = load_build()
    hooks, replace, mid = tables(b)
    if sorted((n, a) for n, a, _ in hooks) != sorted(gn.hooks()):   # two readers of one file must agree
        sys.exit('hookcheck: build.py HOOKS read here and by ghidra_names.hooks() differ: %s'
                 % sorted(set((n, a) for n, a, _ in hooks) ^ set(gn.hooks())))
    problems, warnings = [], []
    on = lambda c: c is None or bool(eval(c, vars(b)))   # build.py's own expression, in build.py's namespace
    if [(n, a) for n, a, c in hooks if on(c)] != b.HOOKS or {n for n, c in replace.items() if on(c)} != b.REPLACE_HOOKS \
            or {n: a for n, (a, c) in mid.items() if on(c)} != b.MID_EXIT:   # the source read vs the import, as now
        sys.exit('hookcheck: the tables read from build.py differ from the imported build.py\'s')
    names = [n for n, _, _ in hooks]
    for n in sorted({n for n in names if names.count(n) > 1}):
        problems.append('hook %s is listed %d times' % (n, names.count(n)))
    for n in sorted(set(replace) - set(names)): warnings.append('REPLACE_HOOKS names %s, which is no hook' % n)
    for n in sorted(set(mid) - set(names)): warnings.append('MID_EXIT names %s, which is no hook' % n)
    for n in sorted(set(mid) & set(replace)): problems.append('%s is in both REPLACE_HOOKS and MID_EXIT' % n)

    words = [(s, 'word patch %x' % s) for s, _, _ in b.WORD_PATCHES]
    words += [(lit, 'literal patch %x (%s)' % (lit, sym_)) for lit, _, sym_ in b.LIT_PATCHES]
    words += [(s, 'item bound patch %x' % s) for s, _, _ in b.item_patches(MEM)]
    wins = sorted([(a, a + 8, 'hook %s %x' % (n, a)) for n, a, _ in hooks] + [(a, a + 4, t) for a, t in words])
    for i, (s0, e0, t0) in enumerate(wins):
        for s1, e1, t1 in wins[i + 1:]:
            if s1 >= e0: break
            problems.append('overlap: %s and %s' % (t0, t1))
    patched = {a: t for a, t in words}

    # every b / bl of main's text and every relocated data word, against the sites' second words
    w = np.frombuffer(MEM, dtype='<u4', count=TEXT_END // 4)
    src = np.nonzero(((w & 0x0E000000) == 0x0A000000) & ((w >> 28) != 0xF))[0]
    off = (w[src] & 0xFFFFFF).astype(np.int64)
    off[off >= 0x800000] -= 0x1000000
    tgt = src.astype(np.int64) * 4 + 8 + off * 4
    second = np.array(sorted({a + 4 for _, a, _ in hooks}), dtype=np.int64)
    into = {}
    for k in np.nonzero(np.isin(tgt, second))[0]:
        into.setdefault(int(tgt[k]), []).append(int(src[k]) * 4)
    img = np.frombuffer(vt.IMG, dtype='<u4')
    ptr = {}
    for k in np.nonzero(np.isin(img, second + vt.B))[0]:
        ptr.setdefault(int(img[k]) - vt.B, []).append(int(k) * 4)

    rows, walks = [], collections.Counter()
    for n, site, cond in hooks:
        tag = 'hook %s %x' % (n, site)
        if site % 4 or not 0 <= site < TEXT_END or site not in asm.INS:
            problems.append('%s: not an instruction of main\'s text' % tag); continue
        hit = b.branch_into(MEM, site)       # build.py's own +-16 KB look must be a subset of the full scan
        near = [x for x in into.get(site + 4, []) if abs(x - site) < 0x4000]
        if (hit is None) != (not near) or hit is not None and hit not in near:
            sys.exit('hookcheck: %s: build.branch_into says %s, the scan %s' % (tag, hit, near))
        for x in into.get(site + 4, []):
            problems.append('%s: %s branches into site + 4: the hook is skipped on that path' % (tag, dis(x)))
        for x in ptr.get(site + 4, []):
            problems.append('%s: data word at %x = main + %x (site + 4): a pointer into the patch' % (tag, x, site + 4))
        mode = 'REPLACE' if n in replace else 'MID_EXIT -> %x' % mid[n][0] if n in mid else 'replay'
        if n not in replace:
            for k in range(2):
                a = site + 4 * k; x = u32(a)
                if (x & 0xFF000000) == 0xEB000000: continue                   # bl: replayed through ip
                if b.is_ldr_pc_lit(x):
                    lit = a + 8 + ((x & 0xFFF) if x & (1 << 23) else -(x & 0xFFF))
                    if lit in patched:
                        problems.append('%s: displaced %s reads literal %x, which the %s rewrites: the trampoline '
                                        'copies the original' % (tag, dis(a), lit, patched[lit]))
                elif not b.displaced_ok(x):
                    problems.append('%s: displaced %s cannot be displaced (build.py refuses it)' % (tag, dis(a)))
            a, why = flag_reader(site, NZCV)
            if a is not None and a < site + 8:
                problems.append('%s: displaced %s reads %s, which the trampoline\'s cmp r0, #0 set' % (tag, dis(a), why))
            elif a is not None:
                problems.append('%s: %s reads %s set before the site: the trampoline\'s cmp r0, #0 replaced them'
                                % (tag, dis(a), why))
            else:
                walks[why.split(' at ')[0]] += 1
                if why.startswith(('undecided', 'left')): warnings.append('%s: flag walk %s' % (tag, why))
        if n in mid:
            ex = mid[n][0]
            if sym.func_start('gu', ex)[0] != sym.func_start('gu', site)[0]:
                warnings.append('%s: MID_EXIT %x lies in function %x, the site in %x' % (
                    tag, ex, sym.func_start('gu', ex)[0], sym.func_start('gu', site)[0]))
            a, why = flag_reader(ex, NZCV)
            if a is not None:
                warnings.append('%s: MID_EXIT path %s reads %s of the trampoline (r0 != 0: ne, cs, vc)' % (tag, dis(a), why))
            else:
                walks['exit: ' + why.split(' at ')[0]] += 1
                if why.startswith(('undecided', 'left')): warnings.append('%s: MID_EXIT flag walk %s' % (tag, why))
        s = sym.func_start('gu', site)[0]
        rows.append((n, site, mode, s, cond))

    print('hookcheck: %d hooks (%d under a condition), %d word patches, %d literal patches, %d item bound patches'
          % (len(hooks), sum(c is not None for *_, c in hooks), len(b.WORD_PATCHES), len(b.LIT_PATCHES),
             len(b.item_patches(MEM))))
    print('branch scan: %d b / bl in main\'s text, %d hits on a site + 4; %d data words point at one' % (
        len(src), sum(len(v) for v in into.values()), sum(len(v) for v in ptr.values())))
    print('flag walks without a reader, by how they ended:', ', '.join('%s %d' % kv for kv in sorted(walks.items())))
    print('\nhooks: name, site, mode, function (name, start +offset), displaced pair, condition (now on / off)')
    for n, site, mode, s, cond in rows:
        print('  %-24s %7x  %-17s %s %x+%#x  | %s ; %s%s' % (
            n, site, mode, func_name(s), s, site - s,
            ' '.join(asm.INS[site]), ' '.join(asm.INS.get(site + 4, ('?', ''))),
            '' if cond is None else '  | if %s (now %s)' % (cond, 'on' if on(cond) else 'off')))
    print('\n%d PROBLEM, %d WARNING' % (len(problems), len(warnings)))
    for p in problems: print('PROBLEM ' + p)
    for x in warnings: print('WARNING ' + x)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
