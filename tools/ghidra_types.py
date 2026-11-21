"""ghidra_types.py : the monster object's layout the repo already knows -> structures in the seeded Ghidra projects.

  ghidra_types.py collect          write dump/ghidra_types/{gu,mh4u}.tsv + report.txt (nothing applied)
  ghidra_types.py apply [ROOT]     collect, then apply both lists with tools/ghidra/ApplyTypes.java (ROOT replaces
                                   dump/ for a trial copy laid out like dump/: gu/ghidra and mh4u_ghidra)
`ghidra_names.py apply` runs both after its own lists (it creates functions this types; it renames typed functions,
this keeps names).

Structures (category /mhgu-de), flat so the decompiler reads `this->EN_RECORD->REC_HP` or `this->REC_HP`, never
`this->base.rec.REC_HP`:
- GU: uEnemyBase (0xb740), uEnemy (0xca80), uFestaEnemy (0xcac0) and every monster class uEmXXX_YY (its DTI size;
  past the base only EN_WORK at 0xcac0, in the classes whose ctor sets it), EnemyRec (the record, embedded at this+0x1440, pointer EN_RECORD) and EnemyWork
  (record + 96, pointer EN_WORK); the record's fields also sit flat in the object at 0x1440 + offset.
- 4U: uEnemy (0x8d88) and every uEmNNN, EnemyW (W, embedded at this+0xe30, pointers this+0xe28 and this+0x8d88).
Field facts, only from regular forms:
- `#define EN_* / REC_* / MOT_* <number>` in tracked C files: EN_ / MOT_ = this offsets, REC_ = record offsets; module/
  game.h's all, elsewhere those used as an offset (FIELD(T, base, NAME), a macro wrapping FIELD, `rec[NAME]`,
  `base + NAME`: MOT_ also names motion ids). Type = the most used FIELD type at NAME (others reported), else the type
  word opening the define's comment. Uses at NAME + k and literal offsets on a record base: comment-only fields.
- the `[4U W+N]` / `[4U this+N]` bracket on a define line, notes/api-map.md's Q2 table and every notes table headed
  `| 4U | GU |` pairing offsets: 4U fields, and comments on the GU side.
A field gets its name only when confirmed the way ghidra_names.confirmed() rates a define (module/game.h unless marked
S / W / guess, elsewhere (C) / CONFIRMED on the line); a 4U field when its bracket sits on such a line, or its pair is
rated C and the GU offset has a confirmed name. Everything else is an unnamed undefined field carrying the comment.
Conflicts (all reported): a name at several offsets loses it unless one source is rated better (game.h brackets over
notes tables); overlapping facts keep the better rated one, the other goes into its comment; per-class offsets past the
base from per-monster files are left out.
`this` gets its type through a class namespace + __thiscall: the decompiler keeps inferring the other parameters and
the return type (a typed parameter would lock the whole prototype); the qualified name gains `uEmXXX_YY::`. The class
says what the object always is in the code seen, not which class declares the function. Typed, until nothing is added:
- monster vtable slot functions (slots below the base count) the base vtables do not hold, no data word or address
  load outside the monster vtables pointing to them;
- the enemy base classes' own slot functions (ghidra_names.owners(): uEnemyBase / uEnemy / uFestaEnemy_vtK, 4U
  uEnemy_vtK): virtual calls reach them only with an object of at least that class; no data word or address load
  outside the labelled classes' vtables may point to them;
- every other function all of whose references are calls or tail branches made while r0 holds this (walk(), a
  must-dataflow from r0 at entry) in typed functions, with no pointer to it: the action handlers the dispatchers (GU
  slot 125, 4U slot 44) reach through their jump tables, and the shared helpers.
A slot function also needs every call or branch to it made that way. Its classes: its own (the monster classes
holding it, or the base class); a called function gets the union of its callers'. One class -> that class, several ->
the most basic of them (GU uEnemyBase, uEnemy, else uFestaEnemy; 4U uEnemy). Left out: slots returning a struct
through r0 (GU 54, 203, 229: a function there stores at [r0], so this is r1).
Not seen: fields reached any other way, per-class fields, functions Ghidra has none of or that are thunks
(ApplyTypes reports both as skips), this kept on the stack (the walk loses it: fewer functions, never wrong ones), and
4U Thumb code (the runtime helpers at 0x100000-0x104000 and near 0x300c74, reached with blx): a call from it to a
game function would be an unseen reference.
"""
import collections, os, re, sys

import numpy as np

import paths
sys.path.insert(0, paths.GU_PY)
import asm, vt  # noqa: E402
import a4u, dis4u, disp4u, fncheck, gu_enemy, xref  # noqa: E402
from ghidra_names import tracked, confirmed, headless, gu_classes, u4_classes, PROJECTS, ROOT, OUT as NAMES_OUT  # noqa: E402

OUT = os.path.join(ROOT, 'dump', 'ghidra_types')
STARTS = set(asm.starts())
# notes/api-map.md Layout anchors (C), notes/enemy-class.md (CONFIRMED)
# rec_end: the record lies inside uEnemyBase (0xb740, whose ctor 0x6d8ec sets its pointer): an upper bound
# sizes: the enemy base classes above the base, most basic first
GU = dict(base='uFestaEnemy', size=0xcac0, rec=0x1440, rec_end=0xb740, work=96, slots=286, disp=125,
          sizes={'uEnemyBase': 0xb740, 'uEnemy': 0xca80},
          vts=(0x1734798, 0x1734d44), ptr={0x1428: 'EnemyRec', 0xcac0: 'EnemyWork'})
U4 = dict(base='uEnemy', size=0x8d88, rec=0xe30, rec_end=0x8d88, slots=95, disp=44, sizes={}, ptr={0xe28: 'EnemyW', 0x8d88: 'EnemyW'})
VIEWS = ('EnemyRec', 'EnemyWork', 'EnemyW')      # the record / work structures; the rest are objects
U4_PAIR = {0xe28: 0x1428, 0x8d88: 0xcac0}   # 4U this offset -> GU this offset (Layout anchors, C)
CTYPE = {'uint8_t': 'u8', 'int8_t': 's8', 'char': 's8', 'uint16_t': 'u16', 'int16_t': 's16', 'uint32_t': 'u32',
         'int32_t': 's32', 'int': 's32', 'unsigned': 'u32', 'float': 'f32', 'uint64_t': 'u64', 'double': 'f64'}
WORD = {'u8': 'u8', 's8': 's8', 'u16': 'u16', 's16': 's16', 'u32': 'u32', 's32': 's32', 'float': 'f32', 'void': 'ptr'}
SIZE = {'u8': 1, 's8': 1, 'u16': 2, 's16': 2, 'u32': 4, 's32': 4, 'f32': 4, 'ptr': 4, 'u64': 8, 'f64': 8}
DEFINE = re.compile(r'^\s*#\s*define\s+((?:EN|REC|MOT)_\w+)\s+\(?(0x[0-9a-fA-F]+|\d+)[uU]?\)?\s*(?:(?:/\*|//)\s*(.*))?$')
BRACKET = re.compile(r'\[4U ((?:W|this|work)\+(?:0x[0-9a-f]+|\d+)(?:\+(?:0x[0-9a-f]+|\d+))*)')


def ctype(t):
    t = re.sub(r'\b(const|volatile)\b', '', t).strip()
    return 'ptr' if t.endswith('*') else CTYPE.get(t)


def defines():
    """{name: [(value, file, line no, confirmed, comment text, line)]} of the offset defines"""
    out = collections.defaultdict(list)
    for f in tracked('*.c', '*.h'):
        comment = ''
        for n, line in enumerate(open(os.path.join(ROOT, f), encoding='utf-8', errors='replace'), 1):
            m = DEFINE.match(line)
            if m:
                text = (m.group(3) or '').split('*/')[0].strip()
                out[m.group(1)].append((int(m.group(2), 0), f, n, confirmed(f, comment, line), text, line))
            s = line.strip()
            comment = comment + s if s.startswith(('/*', '*', '//', 'typedef')) and not m else ''
    return out


def uses():
    """offset uses of the tracked C files: FIELD(T, base, off), a macro `M(b, o)` defined as FIELD(T, b, o), `b[off]` on
    a record (u8) and `b + off`: {(name, k): Counter(type)} for off = NAME + k (type None: no type there), record
    literals {off: Counter(type)} (base REC(...) or a variable set from it), the files of each"""
    named, lit = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    where = collections.defaultdict(set)
    text = {f: fncheck.strip_comments(open(os.path.join(ROOT, f), encoding='utf-8', errors='replace').read())
            for f in tracked('*.c', '*.h')}
    macros = {m.group(1): m.group(4) for t in text.values() for m in re.finditer(     # headers define them for others
        r'#\s*define\s+(\w+)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s+&?\s*FIELD\s*\(\s*([^,]+?)\s*,\s*\2\s*,\s*\3\s*\)', t)}
    for f, t in text.items():
        recs = set(re.findall(r'\b(\w+)\s*=\s*(?:REC\(|FIELD\(\s*uint8_t\s*\*\s*,\s*\w+\s*,\s*EN_RECORD\s*\))', t))
        found = []      # (type, base, offset expression)
        for m in re.finditer(r'\b(FIELD|%s)\s*\(' % '|'.join(macros or ['FIELD']), t):
            args = fncheck.split_top(t[m.end():fncheck.close_paren(t, m.end() - 1)])
            if m.group(1) == 'FIELD' and len(args) == 3: found.append((ctype(args[0]), args[1], args[2]))
            elif m.group(1) != 'FIELD' and len(args) == 2: found.append((ctype(macros[m.group(1)]), args[0], args[1]))
        for m in re.finditer(r'(REC\(\w*\)|\w+)\s*\[\s*([^\]]+)\]', t):
            rec = m.group(1).startswith('REC(') or m.group(1) in recs
            found.append(('u8' if rec else None, 'REC()' if rec else m.group(1), m.group(2)))
        found += [(None, m.group(1), m.group(2)) for m in re.finditer(
            r'(REC\(\w*\)|\w+)\s*\+\s*((?:EN|REC|MOT)_\w+(?:\s*\+\s*(?:0x[0-9a-fA-F]+|\d+))?)\b', t)]
        for typ, base, off in found:
            off = off.replace('(', '').replace(')', '').strip()
            mo = re.fullmatch(r'((?:EN|REC|MOT)_\w+)\s*(?:\+\s*(0x[0-9a-fA-F]+|\d+))?', off)
            mv = re.match(r'((?:EN|REC|MOT)_\w+)\s*\+', off)     # NAME + a variable: the name is an offset, no type
            if mo or mv:
                key = (mo.group(1), int(mo.group(2) or '0', 0)) if mo else (mv.group(1), 0)
                named[key][typ if mo else None] += 1; where[key].add(f)
            elif typ and re.fullmatch(r'0x[0-9a-fA-F]+|\d+', off) and (base.startswith('REC(') or base in recs):
                lit[int(off, 0)][typ] += 1; where[('rec', int(off, 0))].add(f)
    return named, lit, where


def pair_rows():
    """([(4U base, off)], [(GU base, off)], text, rating, source) of notes/api-map.md's Q2 table (4U W+ | meaning | GU
    rec+ | conf) and of every tracked notes table headed `| 4U | GU |` whose two cells are offsets (W+ / this+ /
    work+, rec+ / this+); a cell of anything else (functions, sums, ranges) gives no pair"""
    def offs(cell, kinds, base=None):
        out = []
        for p in cell.replace('**', '').replace('`', '').split('/'):
            m = re.fullmatch(r'\s*(?:(%s)\+)?(0x[0-9a-f]+|\d+)\s*(?:\(([^)]*)\))?\s*' % kinds, p)
            if not m or not (m.group(1) or base): return [], ''
            base = m.group(1) or base
            out.append(('rec' if base in ('W', 'work') else base, int(m.group(2), 0)))
        return out, ' '.join(re.findall(r'\(([^)]*)\)', cell))
    for f in tracked('*.md'):
        head = q2 = None
        for line in open(os.path.join(ROOT, f), encoding='utf-8'):
            if line.startswith('## '): q2 = f == 'notes/api-map.md' and line.startswith('## Q2')
            if not line.startswith('|'):
                head = None; continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if head is None:
                head = q2 or cells[:2] == ['4U', 'GU']; continue
            if not head or len(cells) < 3 or not cells[0].strip('-: '): continue
            if q2:
                u4, d4 = offs(cells[0], 'W', 'W'); gu, dg = offs(cells[2], 'rec', 'rec')
                text, rate = ' '.join(x for x in (cells[1], d4, dg) if x), cells[3]
            else:
                u4, d4 = offs(cells[0], 'W|this|work'); gu, dg = offs(cells[1], 'rec|this')
                text, rate = ' '.join(x for x in [d4, dg] + cells[2:-1] if x), cells[-1]
            r = re.findall(r'\b([CSWG])\b', rate)
            if u4 and gu: yield u4, gu, text, r[0] if len(set(r)) == 1 else 'mixed', f


def facts(report):
    """{'gu' / 'mh4u': {'this' / 'rec': [(off, type, name or None, rank, comment)]}}; rank orders overlaps (lower
    wins: confirmed names, module/game.h first)"""
    D, (named, lit, where) = defines(), uses()
    F = {g: {'this': [], 'rec': []} for g in ('gu', 'mh4u')}
    used = {n for n, _ in named}     # elsewhere MOT_ also names motion ids: a use as an offset decides
    gu_name, gu_type = {}, {}      # by GU this offset (record offsets + 0x1440)
    at = lambda b, o: o + GU['rec'] if b == 'rec' else o
    for name, defs in sorted(D.items()):
        if name not in used and not any(d[1] == 'module/game.h' for d in defs): continue
        base = 'rec' if name.startswith('REC_') else 'this'
        vals = {v for v, *_ in defs}
        if len(vals) > 1:
            report.append('conflict, one name at several offsets (comment only): %s %s' % (name, ', '.join(
                '%#x %s:%d' % (v, f, n) for v, f, n, *_ in defs)))
        types = collections.Counter({k: n for k, n in named.get((name, 0), {}).items() if k})
        if len(types) > 1:
            report.append('conflict, several FIELD types for %s: %s (the most used kept)' % (name, dict(types)))
        for v in sorted(vals):
            ds = [d for d in defs if d[0] == v]
            ok = len(vals) == 1 and any(d[3] for d in ds)
            words = [re.match(r'\w*', d[4]).group(0) for d in ds]
            typ = types.most_common(1)[0][0] if types else next((WORD[w] for w in words if w in WORD), None)
            src = ', '.join(sorted({'%s:%d' % (f, n) for _, f, n, *_ in ds}))
            text = '%s (%s, %s) %s' % (name, 'C' if ok else 'not rated C', src, '; '.join(sorted({d[4] for d in ds if d[4]})))
            if base == 'this' and v >= GU['size'] and v not in GU['ptr']:
                report.append('left out, per-class offset past uFestaEnemy: %s %#x (%s)' % (name, v, src)); continue
            F['gu'][base].append((v, typ, name if ok else None, (0 if ok else 3, '1' if 'module/game.h' in src else '2'), text))
            if ok: gu_name[at(base, v)], gu_type[at(base, v)] = name, typ
            for k, ts in sorted((k, ts) for (n, k), ts in named.items() if n == name and k):
                ts = [x for x in ts if x]
                F['gu'][base].append((v + k, ts[0] if ts else None, None, (4, name), 'mhgu-de uses %s + %d%s (%s)' % (
                    name, k, ' as ' + '/'.join(ts) if ts else '', ', '.join(sorted(where[(name, k)])))))
            for d in ds:     # the 4U counterpart in the line's bracket, rated with the line
                b = BRACKET.search(d[5])
                if not b: continue
                kind, nums = b.group(1).split('+', 1)
                F['mh4u']['this' if kind == 'this' else 'rec'].append((
                    sum(int(x, 0) for x in nums.split('+')), typ if ok else None, name if ok else None,
                    (0 if ok else 3, name), 'GU %s %#x (%s, %s:%d) %s' % (name, v, 'C' if ok else 'not rated C', d[1], d[2], d[4])))
    for off, ts in sorted(lit.items()):
        F['gu']['rec'].append((off, ts.most_common(1)[0][0], None, (5, ''), 'mhgu-de reads rec+%#x as %s (%s)' % (
            off, '/'.join(ts), ', '.join(sorted(where[('rec', off)])))))
    for u4, gu, text, rate, f in pair_rows():
        pair = len(u4) == len(gu)
        for k, (b, x) in enumerate(u4):
            y = gu[k] if pair else None
            name = gu_name.get(at(*y)) if rate == 'C' and y else None
            F['mh4u'][b].append((x, gu_type.get(at(*y)) if name else None, name, (1 if name else 3, f), '%s (%s, %s)%s' % (
                text, rate, f, ' = GU %s+%#x' % y if y else '')))
        for k, (b, y) in enumerate(gu):
            F['gu'][b].append((y, None, None, (3, f), '%s (%s, %s)%s' % (text, rate, f, ' = 4U %s+%#x' % (
                'W' if u4[k][0] == 'rec' else 'this', u4[k][1]) if pair else '')))
    for x, y in U4_PAIR.items():
        if y in gu_name:
            F['mh4u']['this'].append((x, 'ptr', gu_name[y], (0, ''), 'GU %s (notes/api-map.md Layout anchors, C)' % gu_name[y]))
    return F


def layout(fs, size, delta, report, tag):
    """[(off, type, name, comment)] of facts placed at off + delta inside [0, size): best rank first, an overlapping
    fact goes into the comment of the field it overlaps (reported)"""
    placed = []
    for off, typ, name, rank, text in sorted(fs, key=lambda r: r[3]):
        off += delta
        n = SIZE.get(typ, 1)
        if not 0 <= off <= size - n: continue
        hit = [p for p in placed if p[0] < off + n and off < p[0] + SIZE.get(p[1], 1)]
        if hit:
            p = hit[0]
            if (p[2] and name and p[2] != name) or p[0] != off or (typ and p[1] and typ != p[1]):
                report.append('%s overlap at %#x: kept %s, folded %s' % (tag, off, p[3][:80], text[:80]))
            p[3] += ' | ' + text
            continue
        placed.append([off, typ, name, text, rank])
    first = {}
    for p in placed:     # a name at several offsets: the best rated keeps it when it is rated better than the rest
        if not p[2]: continue
        if p[2] not in first: first[p[2]] = p; continue
        q = first[p[2]]
        report.append('%s conflict, %s at %#x and %#x: %s' % (tag, p[2], q[0], p[0], 'kept at %#x' % q[0] if q[4][0] < p[4][0]
                                                               else 'comment only'))
        if q[4][0] == p[4][0]: q[2] = None
        p[2] = None
    return sorted(p[:4] for p in placed)


def structs(F, game, report):
    """{struct: (size, [(off, type, name, comment)])}: the record view, GU's work view, the object view per class"""
    G = GU if game == 'gu' else U4
    this = F[game]['this'] + [(o + G['rec'],) + tuple(r) for o, *r in F[game]['rec']]
    rec = [(o - G['rec'],) + tuple(r) for o, *r in F[game]['this']] + F[game]['rec']
    rname = VIEWS[0] if game == 'gu' else VIEWS[2]
    # the views repeat the object's fields: their overlaps are reported once, by the object view
    out = {rname: (G['rec_end'] - G['rec'], layout(rec, G['rec_end'] - G['rec'], 0, [], ''))}
    if game == 'gu':
        out[VIEWS[1]] = (out[rname][0] - G['work'], layout(rec, out[rname][0] - G['work'], -G['work'], [], ''))
    sizes = {n: (s, False) for n, s in list(G['sizes'].items()) + [(G['base'], G['size'])]}
    sizes.update(classes(game, report))
    obj = layout(this, max(s for s, _ in sizes.values()), 0, report, game + ' object')
    for name, (size, work) in sizes.items():      # past the base only the work pointer, where the ctor sets it
        out[name] = (size, [p for p in obj if p[0] + SIZE.get(p[1], 1) <= size and (p[0] < G['size'] or work)])
    return out


_classes = {}


def classes(game, report):
    """{class: (size, sets the work pointer)} of the monster classes with an object vtable, deriving from the base (GU:
    the ctor calls the uFestaEnemy ctor, gu_enemy.py; 4U: DTI parent uEnemy, one vtable, a4u.py). The work pointer:
    GU a `movw rX, #0xcac0` in the ctor (up to the next known function start), 4U only uEm089 (the anchor's ctor)."""
    if game not in _classes:
        out = {}
        if game == 'gu':
            for name, c in sorted(gu_enemy.classes().items()):
                if not name.startswith('uEm'): continue
                if not c['vt']: report.append('gu class left out (no object vtable, gu_enemy.py): ' + name); continue
                end = min(a for a in STARTS if a > c['ctor'])
                work = any(asm.INS.get(a, ('', ''))[0] == 'movw' and asm.INS[a][1].endswith('#0xcac0')
                           for a in range(c['ctor'], end, 4))
                if not work: report.append('gu class without EN_WORK (its ctor does not set this+0xcac0): ' + name)
                out[name] = (c['size'], c['vt'], work)
        else:
            D, N = a4u.dtis(), a4u.by_name()
            for name, d in sorted(N.items()):
                if not re.fullmatch(r'uEm\d+(_\d+)?', name): continue
                vts = a4u.vtables(d)
                if D[d][1] != N['uEnemy'] or len(vts) != 1:
                    report.append('4u class left out (parent not uEnemy or %d vtables): %s' % (len(vts), name)); continue
                out[name] = (D[d][2], vts[0], name == 'uEm089')
        _classes[game] = out
    return {k: (s, w) for k, (s, _, w) in _classes[game].items()}


CLOBBER = frozenset(['r0', 'r1', 'r2', 'r3', 'r12'])
REGS = frozenset(['r%d' % i for i in range(13)] + ['lr'])


def ins(game, a):
    m, o = asm.INS.get(a, ('?', '')) if game == 'gu' else dis4u.INS(a)
    return m, o.split(' @')[0].split(' <')[0].strip()


def is_start(game, a):
    if game == 'mh4u': return disp4u.is_func_start(a)
    m, o = ins(game, a)
    return a in STARTS or m == 'push' and 'lr' in o


def table(game, a, m, ops):
    """targets of a jump table at a (GU clang `add pc, rA, rB`, fncheck.jump_table; 4U `ldrCC pc, [pc, rX, lsl #2]`
    after `cmp rX, #N`, `addCC pc, pc, rX, lsl #2` before a row of b), else None"""
    if game == 'gu':
        return fncheck.jump_table(a, ops[1], ops[2]) if m == 'add' and len(ops) == 3 else None
    mt = re.fullmatch(r'\[pc, (r\d+), lsl #2\]', ops[1]) if m.startswith('ldr') and len(ops) == 2 else None
    pm, po = ins(game, a - 4)
    pn = re.fullmatch(r'%s, #(\d+)' % mt.group(1), po) if mt and pm == 'cmp' else None
    if pn: return [a4u.u(a + 8 + 4 * j) for j in range(int(pn.group(1)))]
    if m.startswith('add') and ops[1:2] == ['pc'] and re.fullmatch(r'r\d+, lsl #2', ops[2] if len(ops) > 2 else ''):
        out, x = [], a + 8
        while ins(game, x)[0] == 'b':
            out.append(x); x += 4
        return out
    return None


def walk(game, f, R):
    """must-dataflow of the registers holding this (r0 at entry) along f's control flow: ({target: [site]} of the
    tail branches, {target: [site]} of the calls made while r0 holds this, whether f may store at [this]). A branch
    to a function start or to an address something calls is a tail; an unconditional call followed by one does not
    return. A second pass starts each foreign entry with nothing known: an address the first pass reached that a
    call, a pointer or a branch from code it did not reach also enters (code reached through a missed jump table, a
    shared tail, a 4U leaf function, a fall-through into the next function). An instruction the disassembler cannot
    read (GU: ARMv8 VFP forms such as vsel), svc and mrc end what is known."""
    entry = lambda t: is_start(game, t) or any(k == 'bl' for k, _ in R.get(t, ()))

    def flow(pin):
        state, todo, rows = dict.fromkeys(pin, frozenset()), [f, *pin], set()
        state[f], tails, calls, put = frozenset(['r0']), collections.defaultdict(list), collections.defaultdict(list), False
        for _ in range(200000):
            if not todo: return state, rows, tails, calls, put
            a = todo.pop(); s = state[a]
            m, o = ins(game, a)
            if m == '?': continue
            ops, b, out = xref.split_ops(o), xref.BRANCH.match(m), []
            if m.startswith(('str', 'vst', 'stm')):
                x = re.search(r'\[(r\d+)(?::\d+)?(?:, #0)?\]', o) if '[' in o else re.match(r'(r\d+)', o)
                put = put or bool(x and x.group(1) in s)
            if m.startswith(('<', 'svc', 'mrc', 'mrrc')): out.append((a + 4, frozenset()))
            elif b:
                t = int(o.split()[0], 16) if o.startswith('0x') else None      # None: blx rX
                if b.group(1) != 'b':
                    if 'r0' in s and t is not None: calls[t].append(a)
                    if b.group(2) or not entry(a + 4): out.append((a + 4, s - CLOBBER))
                elif entry(t) and t != f:
                    if 'r0' in s: tails[t].append(a)
                else: out.append((t, s))
                if b.group(1) == 'b' and b.group(2): out.append((a + 4, s))
            elif m.startswith('bx') or xref.writes(m, o, 'pc'):
                ts = table(game, a, m, ops) or []
                if game == 'mh4u' and m.startswith('ldr'): rows.update(range(a + 8, a + 8 + 4 * len(ts), 4))
                out = [(t, s) for t in ts]
                if re.fullmatch(r'(?:bx|pop|ldr|add|mov|ldm\w\w)(%s)' % xref.CONDS, m): out.append((a + 4, s))
            elif m == 'mov' and len(ops) == 2 and ops[1] in REGS and ops[0] in REGS:
                out.append((a + 4, s | {ops[0]} if ops[1] in s else s - {ops[0]}))
            else:
                out.append((a + 4, frozenset(r for r in s if not xref.writes(m, o, r))))
            for x, t in out:
                if x not in state or state[x] & t != state[x]:
                    state[x] = t if x not in state else state[x] & t
                    todo.append(x)
        return None
    w = flow(())
    if w is None: return None
    seen = set(w[0]) | w[1]      # 4U jump table words are part of f
    pin = [x for x in w[0] if x != f and any(k == 'bl' or k == 'data' and s not in w[1] or s not in seen
                                             for k, s in R.get(x, ()))]
    w = flow(pin) if pin else w
    return w and w[2:]


def refs(game):
    """{function: [(kind, site)]} every way code or data reaches a function: 'bl' / 'b' sites, 'data' words (GU: the
    relocated image past .text and pc-relative `add rX, pc, rY` address loads; 4U: any aligned word)"""
    out = collections.defaultdict(list)
    if game == 'gu':
        for a, (m, o) in asm.INS.items():
            b = xref.BRANCH.match(m)
            if b and o.startswith('0x'): out[int(o.split()[0], 16)].append(('b' if b.group(1) == 'b' else 'bl', a))
            elif m == 'add' and ', pc, r' in o:
                t = gu_enemy.got_at(a)
                if t is not None: out[t].append(('data', a))
        w = np.frombuffer(vt.IMG, dtype='<u4', count=(len(vt.IMG) - vt.TEXT_END) // 4, offset=vt.TEXT_END) - vt.B
        for k in np.nonzero(w < vt.TEXT_END)[0]:
            out[int(w[k])].append(('data', vt.TEXT_END + 4 * int(k)))
        return out
    for a, m, o in xref.Exe('4u').scan('@ imm = #', ''):
        b = xref.BRANCH.match(m)
        if b and o.startswith('0x'): out[int(o.split()[0], 16)].append(('b' if b.group(1) == 'b' else 'bl', a))
    w = np.frombuffer(a4u.M, dtype='<u4')
    for k in np.nonzero((w >= a4u.B) & (w < a4u.TEXT_END))[0]:
        out[int(w[k])].append(('data', a4u.B + 4 * int(k)))
    return out


def functions(game, report):
    """[(function, struct, rule)] of the functions that certainly take a monster in r0"""
    G = GU if game == 'gu' else U4
    slot = (lambda v, k: vt.u(v + 4 * k) - vt.B) if game == 'gu' else (lambda v, k: a4u.u(v + 4 * k))
    vts = G['vts'] if game == 'gu' else tuple(a4u.vtables(a4u.by_name()['uEnemy']))
    base = {slot(v, k) for v in vts for k in range(G['slots'])}
    classes(game, report)
    own, words, disp, held = collections.defaultdict(set), set(), set(), {(slot(v, k), k) for v in vts for k in range(G['slots'])}
    for name, (_, v, _) in _classes[game].items():
        for k in range(G['slots']):
            f = slot(v, k); words.add(v + 4 * k); held.add((f, k))
            if f and f not in base:
                own[f].add(name)
                if k == G['disp']: disp.add(f)
    links, chain = {}, list(G['sizes']) + [G['base']]
    names = (gu_classes if game == 'gu' else u4_classes)([], links)    # its report lines are ghidra_names.py's
    vwords = {v + 4 * j for v, (_, n) in links.items() for j in range(n)}
    at = collections.defaultdict(set)
    for f, k in held: at[f].add(k)
    seed = {f: (cs, words, at[f], 'vtable slot (%s)' % ('dispatcher' if f in disp else 'own')) for f, cs in own.items()}
    for r in names:
        m = re.fullmatch(r'(%s)_vt(\d+)' % '|'.join(chain), r[2]) if r[0] == 'func' else None
        if m: seed[r[1]] = ({m.group(1)}, vwords, {int(m.group(2))}, 'vtable slot (%s)' % m.group(1))
    R, W = refs(game), {}
    for f, _ in held:
        if f: W[f] = walk(game, f, R)
    sret = sorted({k for f, k in held if k > 1 and f and W[f] and W[f][2]})
    report.append('%s slots returning a struct through r0 (a function there stores at [r0], this is r1): %s' % (game, sret))
    seed = {f: s for f, s in seed.items() if not s[2] & set(sret)}
    sites = {'b': collections.defaultdict(list), 'bl': collections.defaultdict(list)}
    out, typed, todo = [], {}, []
    while True:      # walk todo, then type every function all of whose references are allowed, until none is left
        for f in todo:
            if W.setdefault(f, walk(game, f, R)) is None:
                report.append('%s walk of %#x stopped (step limit)' % (game, f)); continue
            for k, part in zip(('b', 'bl'), W[f]):
                for t, ss in part.items(): sites[k][t] += [(f, x) for x in ss]
        todo = []
        for t in sorted((set(sites['b']) | set(sites['bl']) | set(seed)) - set(typed)):
            cs, ok, _, rule = seed.get(t, (set(), (), (), None))
            ss = sites['b'].get(t, []) + sites['bl'].get(t, [])
            if (ss or cs) and all(x in {y for _, y in sites[k].get(t, [])} if k != 'data' else x in ok for k, x in R.get(t, [])):
                typed[t] = cs.union(*(typed[f] for f, _ in ss)); todo.append(t)
                tail = 'tail branch with this from %s' % ('the dispatcher' if {f for f, _ in ss} & disp else 'a typed function')
                out.append((t, typed[t], rule or (tail if all(k == 'b' for k, _ in R.get(t, [])) else 'call with this')))
        if not todo: break
    report.append('%s slot functions left out (a pointer outside their vtables, or a call / branch without this from '
                  'untyped code): %d of %d' % (game, len(set(seed) - set(typed)), len(seed)))
    report.append('%s targets reached with this left out (also reached another way): %d' % (
        game, len((set(sites['b']) | set(sites['bl'])) - set(typed))))
    return [(f, next(iter(cs)) if len(cs) == 1 else next(c for c in chain if c in cs or c == G['base']), rule)
            for f, cs, rule in out]


def collect():
    os.makedirs(OUT, exist_ok=True); report = []
    F = facts(report)
    for game in ('gu', 'mh4u'):
        G = GU if game == 'gu' else U4
        S, rows = structs(F, game, report), []
        for name, (size, fields) in S.items():     # record / work views first: the objects point to them
            rows.append(('struct', name, '%#x' % size, 'mhgu-de: %s, generated by tools/ghidra_types.py' % name))
            for off, typ, fname, text in fields:
                if not fname: t = 'undef%d' % SIZE.get(typ, 1)
                elif name not in VIEWS and off in G['ptr']: t = 'ptr:' + G['ptr'][off]
                else: t = typ or 'undef1'
                rows.append(('field', name, '%#x' % off, t, fname or '-', re.sub(r'\s+', ' ', text)))
        fns = functions(game, report)
        rows += [('this', '%#x' % f, cls, rule) for f, cls, rule in fns]
        with open(os.path.join(OUT, game + '.tsv'), 'w', encoding='utf-8') as f:
            f.writelines('\t'.join(r) + '\n' for r in rows)
        fields = {(p[0], p[2]) for n, (_, fs) in S.items() if n not in VIEWS for p in fs}
        report.append('%s: %d structures; object fields %d named, %d comment only; %d functions typed: %s' % (
            game, len(S), sum(1 for _, n in fields if n), sum(1 for _, n in fields if not n), len(fns),
            dict(collections.Counter(r for _, _, r in fns))))
    report = list(dict.fromkeys(report))
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(l for l in report if re.search(r'structures|struct through|left out \(', l)))


def apply(root):
    os.makedirs(NAMES_OUT, exist_ok=True)      # headless() keeps its logs there (<tag>.types.log)
    for tag, (pdir, name, elf) in PROJECTS.items():
        headless(tag, 'types', [os.path.join(root, pdir), name, '-process', os.path.basename(elf), '-noanalysis',
                                '-scriptPath', os.path.join(ROOT, 'tools', 'ghidra'), '-postScript', 'ApplyTypes.java',
                                os.path.join(OUT, tag + '.tsv'), os.path.join(OUT, tag + '.applied.txt')])
        print(open(os.path.join(OUT, tag + '.applied.txt'), encoding='utf-8').readline().strip())


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'collect'
    if cmd not in ('collect', 'apply'): sys.exit(__doc__)
    collect()
    if cmd == 'apply': apply(sys.argv[2] if len(sys.argv) > 2 else paths.DUMP)
