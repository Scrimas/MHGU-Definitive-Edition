"""ghidra_names.py : names the repo already knows -> the seeded Ghidra projects (dump/gu/ghidra, dump/mh4u_ghidra).

  ghidra_names.py project [ROOT]  create the missing projects (import, function-start seeds, auto-analysis; ROOT
                                  replaces dump/ for a trial copy)
  ghidra_names.py collect         write dump/ghidra_names/{gu,mh4u}.tsv + report.txt (nothing applied)
  ghidra_names.py apply           collect, then apply both lists with tools/ghidra/ApplyNames.java (in place)
Ghidra: ghidra-analyzeHeadless on PATH, or GHIDRA_HEADLESS = <ghidra>/support/analyzeHeadless.

Only facts that need no judgement:
- GU functions / data named by `#define NAME ... FN(type, 0xADDR)` / `MAIN(0xADDR)` in tracked C files, as names
  only when confirmed: module/game.h is confirmed unless marked (S / W / guess), other files only with (C) or
  CONFIRMED on the define line; the rest becomes a comment "mhgu-de code calls this NAME". A name defined at two
  addresses (two files' local macros) is dropped; an address with several names gets one as the function name
  (module/game.h first, written names before vtable-slot names) and the others as labels.
- 4U names only where notes/api-map.md's framework table pairs the 4U and GU addresses with confidence C.
- The mod's hook sites (module/build.py HOOKS, module/gear_hooks.txt): a comment, no name.
- Monster class vtables (GU tools/gu_enemy.py, 4U tools/a4u.py), kept only when the class's getDTI (slot 5)
  returns the class's own DTI. Every monster class derives directly from the base (GU uFestaEnemy, 4U uEnemy).
  A slot function only one monster class's vtable holds gets `<class>_vt<N>`; one in the base vtables, or in
  several classes, gets a comment saying where it sits. Slots past the base class's count are left alone.
- GU functions only a jump table or pointer reaches (tools/sym.py table_only_starts: a push {.., lr} after an
  unconditional return / branch that no branch of the code before reaches): function starts, also among the seeds.
ApplyNames.java renames only functions with Ghidra's own names (FUN_..., analysis labels); a vtable target or
constructor Ghidra missed becomes a function (a vtable slot and a tail-called constructor start one). Every skip
is reported.
"""
import collections, os, re, subprocess, sys

import paths  # noqa: E402
import a4u, gu_enemy as g  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'dump', 'ghidra_names')
GU_B = 0x10000000
GU_BASES = [('uEnemy', 0x1734798), ('uFestaEnemy', 0x1734d44)]   # notes/enemy-class.md, CONFIRMED
GU_SLOTS = 286
U4_SLOTS = 95       # 4U monster vtables are 97 words apart: 2 header words + 95 slots
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


UNRATED = re.compile(r'\((?:S|W)\b|\bGUESS\b|\bguess|\bstrong\b|\bweak\b|\bunconfirmed\b')


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


def place(classes, slots, ancestors, bases, report, tag):
    """classes: {name: [slot fn]}; -> name / comment rows for the slot functions. A function the base vtables
    hold only gets a comment: it may come from an engine class further down (uMHchar, uModel ...)."""
    where = collections.defaultdict(list)
    for c, fns in classes.items():
        for k, f in enumerate(fns[:slots]):
            if f: where[f].append((c, k))
    rows = []
    for f, pl in sorted(where.items()):
        ks = {k for _, k in pl}; cs = {c for c, _ in pl}
        owner = [c for c in cs if all(o == c or c in ancestors(o) for o in cs)]
        if len(ks) == 1 and len(owner) == 1 and owner[0] not in bases:
            rows.append(('func', f, '%s_vt%d' % (owner[0], ks.pop()), ['vtable']))
        elif len(ks) == 1 and len(owner) == 1:
            rows.append(('comment', f, 'slot %d of the %s vtable (and its subclasses)' % (ks.pop(), owner[0]), ['vtable']))
        else:
            txt = ', '.join('%s[%d]' % p for p in sorted(pl)[:12]) + (' +%d more' % (len(pl) - 12) if len(pl) > 12 else '')
            rows.append(('comment', f, 'vtable slot of: ' + txt, ['vtable']))
    rows += [('entry', f, '-', ['vtable']) for f in sorted(where)]
    report.append('%s slot functions: %d named, %d in base vtables (comment), %d shared (comment)' % (
        tag, sum(r[0] == 'func' for r in rows), sum(r[2].startswith('slot ') for r in rows),
        sum(r[2].startswith('vtable slot of') for r in rows)))
    return rows


def gu_classes(report):
    def u(a): return g.vt.u(a) - GU_B
    def dti_at_site(site):
        for k in range(1, 10):
            m, o = g.ins(site - 4 * k)
            if m in ('ldr', 'add') and (o.startswith('r0, [pc, r') or o.startswith('r0, pc, r')):
                return g.got_at(site - 4 * k)
        return None
    def getdti(f):
        m0, o0 = g.ins(f); m1, o1 = g.ins(f + 4); m2, _ = g.ins(f + 8)
        if (m0, m1, m2) == ('ldr', 'ldr', 'bx') and o0.startswith('r0, [pc, #') and o1 == 'r0, [pc, r0]':
            return g.got_at(f + 4)
        return None
    C = g.classes(); rows = []; classes = {}
    for b, v in GU_BASES: classes[b] = [u(v + 4 * k) for k in range(GU_SLOTS)]
    for name, c in sorted(C.items()):
        if not name.startswith('uEm'): continue
        if not c['vt']:
            report.append('gu class skipped (no object vtable found): ' + name); continue
        dti = dti_at_site(c['site']); slots = [u(c['vt'] + 4 * k) for k in range(GU_SLOTS)]
        if dti is None or getdti(slots[5]) != dti:
            report.append('gu class skipped (getDTI does not return its DTI): ' + name); continue
        classes[name] = slots
        rows += [('label', c['vt'], name + '_vtable', ['tools/gu_enemy.py']),
                 ('label', c['dti_vt'], name + '_dti_vtable', ['tools/gu_enemy.py']),
                 ('func', c['newinst'], name + '_newInstance', ['tools/gu_enemy.py']),
                 ('entry', c['ctor'], '-', ['tools/gu_enemy.py']),
                 ('func', c['ctor'], name + '_ctor', ['tools/gu_enemy.py'])]
    rows += [('label', v, b + '_vtable', ['notes/enemy-class.md']) for b, v in GU_BASES]
    anc = lambda c: ['uFestaEnemy', 'uEnemy'] if c.startswith('uEm') else (['uEnemy'] if c == 'uFestaEnemy' else [])
    rows += place(classes, GU_SLOTS, anc, {b for b, _ in GU_BASES}, report, 'gu')
    for c, fns in classes.items():
        for k, note in GU_SLOT_NOTE.items():
            rows.append(('comment', fns[k], 'slot %d: %s' % (k, note), ['notes/enemy-class.md', 'notes/api-map.md']))
    report.append('gu classes kept: %d' % (len(classes) - len(GU_BASES)))
    return rows, classes


def u4_classes(report):
    D = a4u.dtis(); N = a4u.by_name(); rows = []; classes = {}
    for name in ['uEnemy'] + sorted(n for n in N if re.fullmatch(r'uEm\d+(_\d+)?', n)):
        d = N[name]; vts = a4u.vtables(d); gets = a4u.getdti_funcs(d)
        if len(vts) != 1 or len(gets) != 1:
            report.append('4u class skipped (%d vtables, %d getDTI): %s' % (len(vts), len(gets), name)); continue
        v = vts[0]; slots = [a4u.u(v + 4 * k) for k in range(U4_SLOTS)]
        if slots[5] != gets[0] or not all(s == 0 or a4u.B <= s < a4u.TEXT_END for s in slots):
            report.append('4u class skipped (slot 5 / slot range check): ' + name); continue
        classes[name] = slots
        rows.append(('label', v, name + '_vtable', ['tools/a4u.py']))
    anc = lambda c: a4u.chain(N[c])[1:]
    rows += place(classes, U4_SLOTS, anc, {'uEnemy'}, report, '4u')
    for c, fns in classes.items():
        for k, note in U4_SLOT_NOTE.items():
            if fns[k]:
                rows.append(('comment', fns[k], 'slot %d: %s%s' % (k, note, ' (GU slot %d)' % SLOT_PAIR[k] if k in SLOT_PAIR else ''),
                             ['notes/enemy-class.md', 'notes/api-map.md']))
    report.append('4u classes kept: %d' % (len(classes) - 1))
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
    for r in out:
        if r[0] in ('func', 'label') and r[2] in bad: continue
        key = r[:3]
        if key not in seen: seen.add(key); final.append(r)
    return sorted(final, key=lambda r: (r[1], r[0], r[2]))


def rows(report):
    """{'gu' / 'mh4u': [(kind, address, text, sources)]} before merge(): what collect() writes (tools/sym.py reads
    them too)"""
    gu_rows = list(gu_defines(report))
    gu_name = {a: n for k, a, n, _ in gu_rows if k == 'func'}
    u4_rows = []
    for x, y in api_c_pairs():
        if y in gu_name: u4_rows.append(('func', x, gu_name[y], ['notes/api-map.md (C)']))
        else: report.append('api-map C pair without a GU name: 4U %#x GU %#x' % (x, y))
    gu_rows += [('comment', a, 'mhgu-de hook ' + n, ['module/build.py']) for n, a in hooks()]
    cr, _ = gu_classes(report); gu_rows += cr
    u4_rows += u4_classes(report)
    return {'gu': gu_rows, 'mh4u': u4_rows}


def collect():
    import sym      # here: sym imports this module
    os.makedirs(OUT, exist_ok=True); report = []
    R = rows(report)
    R['gu'] += [('entry', a, '-', ['tools/sym.py table_only_starts']) for a in sym.table_only_starts()]
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


def apply():
    for tag, (pdir, name, elf) in PROJECTS.items():
        headless(tag, 'apply', [os.path.join(paths.DUMP, pdir), name, '-process', os.path.basename(elf),
                       '-noanalysis', '-scriptPath', os.path.join(ROOT, 'tools', 'ghidra'), '-postScript',
                       'ApplyNames.java', os.path.join(OUT, tag + '.tsv'), os.path.join(OUT, tag + '.applied.txt')])
        print(open(os.path.join(OUT, tag + '.applied.txt'), encoding='utf-8').readline().strip())


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'collect'
    if cmd == 'project':
        project(sys.argv[2] if len(sys.argv) > 2 else paths.DUMP); sys.exit()
    collect()
    if cmd == 'apply': apply()
