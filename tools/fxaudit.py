"""fxaudit.py : a port's motion effects (PEL list 1) against the 4U MEF records they come from, by efl4u2gu's rules.

  fxaudit.py 4U_ARC GU_ARC [--pel PATH] [--all]   4U_ARC = the 4U monster arc (dump/romfs/data/emNNN.arc), GU_ARC =
                                                  the built arc (or a GU RomFS path); PATH default
                                                  effect\\pel\\em\\<GU arc name>u; --all lists every paired record
  fxaudit.py --ports [--all]                      every built monsters/*/romfs/nativeNX/arc/enemy/*.arc with its own
                                                  PEL u, its 4U arc derived (below), then a table of the counts

Pairing (build_pel's layout: one list-1 record per MEF record, id and joint kept, EFL path = the MEF group / file):
a list-1 record pairs with the MEF record of its id whose group / file its EFL name gives (emNNN_FFF / qeNNN_FFF ->
NNN, FFF; the joint decides between MEFs). A record whose id and joint match but whose EFL differs (a port that swapped
the EFL, or a GU record sharing the id) is listed apart and not audited; records with no MEF id are GU's own or made
by the port (counted). --ports takes as 4U arc the dump/romfs/data/emNNN.arc, among the em families its list-1 EFLs
name, that pairs the most records (an inference from the data, printed with every candidate's count).

Checks per paired record (the rules: efl4u2gu MEF_LOCAL .. MEF_ROT_MASKS comments, notes/porting-guide.md lessons):
  FOLLOW   a joint record without the ground flag follows its joint in 4U (mef_follows); the GU tail is not a
           follow tail (transform mode 0 / 1)
  PLACED   a joint -1 record (ground flag or not): efl4u2gu's rule places it (PEL_TAIL, mode 2); the tail follows
  ROT      a following joint record without an axis mask: 4U turns it with the body when MEF flag 4 is set, else with
           the joint (PEL +0x38 1 / 0, efl4u2gu mef_rotation); +0x38 differs
  GROUND   ground flag (MEF bit 1) on a joint: 4U keeps it on the ground under the joint every frame, no GU tail does
           (world tail = the port posts it at a point; module tables named *ground* / *gjoint* listing the id are named)
  AXIS     MEF flags 0x40 / 0x80 / 0x100 keep only x / y / z of the rotation; GU +0x3c 0 / 1 / 2 / 3 = x / y / z / all is
           efl4u2gu's reading, its branch not confirmed: shown, not judged
  B0       MEF byte 0 != 0: 4U posts it only while bit b0 of this+0xca8 is set; GU's PSL never tests it, so the port's
           PSL hook must. Gate = a {id, b0} table in a module/*.c array named *b0* (found by that pattern only)
GU transform mode from +0x36 (efl4u2gu, 0x32a548): 4 -> 0, 1 -> 2, 0 -> 1 if +0x38 == 1 else 0, 2 / 3 -> 3 if +0x3e == 6
else 4; 0 / 1 follow, 2 placed once, 3 / 4 a world point (the follow / placed meaning is efl4u2gu's G, from tests).
psl N = PSL entries of the GU arc naming the id in a kind-4 slot (0: no motion posts it through a PSL; code may).
Not checked: list 2 (code posts: 4U applies the MEF flags to motion posts only), the local flag, end modes, offsets.
"""
import collections, glob, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths
import arcdiff, efl4u2gu
from efl4u2gu import T, MEF_GROUND, MEF_BODY, MEF_ROT_MASKS

KIND = {0: 'follows', 1: 'follows', 2: 'placed', 3: 'world', 4: 'world'}
EFL_NAME = re.compile(r'(?:em|qe)(\d{3})_(\d{3})$')
TABLE = re.compile(r'(\w+)\s*\[\s*\](?:\s*\[\s*\d+\s*\])?\s*=\s*\{(.*?)\};', re.S)
ROW = re.compile(r'\{\s*(\d+)\s*,\s*(-?(?:0x[0-9a-fA-F]+|\d+))\b')
AXES = ((0x40, 'x'), (0x80, 'y'), (0x100, 'z'))


def gu_mode(st):
    m = st[0x36]
    if m == 4: return 0
    if m == 1: return 2
    if m == 0: return 1 if st[0x38] == 1 else 0
    if m in (2, 3): return 3 if st[0x3e] == 6 else 4
    return None


def entries(spec):
    return {(p, t): d for p, t, d in arcdiff.read_arc(spec)}


def mefs_of(arc):
    return [(p, r) for (p, t), d in arc.items() if t == T['MEF'] for r in efl4u2gu.mef_records(d)]


def list1(pel):
    n, body = efl4u2gu.pel_lists(pel)[1]
    return arcdiff.pel_records(body, n)


def psl_ids(arc):
    """{id: number of PSL entries naming it in a kind-4 slot (PEL u list 1)}: efl4u2gu.build_psl's layout"""
    out = collections.Counter()
    for (p, t), d in arc.items():
        if t != T['PSL']:
            continue
        n = struct.unpack_from('<H', d, 6)[0]
        for o in struct.unpack_from('<%dI' % n, d, 8):
            if not o:
                continue
            at = struct.unpack_from('<I', d, o + 8)[0]
            mask, ids, kinds = struct.unpack_from('<I', d, at)[0], struct.unpack_from('<32H', d, at + 4), \
                struct.unpack_from('<32I', d, at + 68)
            out.update({ids[k] for k in range(32) if mask >> k & 1 and kinds[k] == 4})
    return out


def pair(recs, mefs):
    """-> {'path': [(gu rec, (mef path, mef rec))], 'other_efl': [...], 'ambiguous': [gu rec], 'none': [gu rec]}"""
    by_id = collections.defaultdict(list)
    for m in mefs:
        by_id[m[1]['id']].append(m)
    out = collections.defaultdict(list)
    for rec in recs:
        path, _, st = rec
        rid, j = struct.unpack_from('<Hh', st, 0x30)
        g = EFL_NAME.search(path.rsplit('\\', 1)[-1])
        g = g and (int(g.group(1)), int(g.group(2)))
        c = [m for m in by_id.get(rid, ()) if (m[1]['grp'], m[1]['file']) == g]
        if len(c) > 1:
            c = [m for m in c if m[1]['joint'] == j] or c
        how = 'path'
        if not c:
            c, how = [m for m in by_id.get(rid, ()) if m[1]['joint'] == j], 'other_efl'
        if len(c) == 1:
            out[how].append((rec, c[0]))
        else:
            out['ambiguous' if c else 'none'].append(rec)
    return out


def module_tables(mod_dir):
    """{'b0': {id: [(b0, table)]}, 'ground': {id: [table]}} from module/*.c arrays named *b0* / *ground* / *gjoint*
    (a package with two entries can hold one table per entry: every table listing an id is kept)"""
    out = {'b0': collections.defaultdict(list), 'ground': collections.defaultdict(list), 'names': []}
    for fn in sorted(glob.glob(os.path.join(mod_dir, '*.c'))):
        src = open(fn, encoding='utf-8').read()
        for m in TABLE.finditer(src):
            name, body = m.group(1), m.group(2)
            where = '%s %s' % (os.path.basename(fn), name)
            low = name.lower()
            if 'b0' in low:
                for a, b in ROW.findall(body):
                    out['b0'][int(a)].append((int(b, 0), where))
            elif 'ground' in low or 'gjoint' in low:
                for a, _ in ROW.findall(body):
                    out['ground'][int(a)].append(where)
            else:
                continue
            out['names'].append(where)
    return out


def ground_table(r, mod):
    t = mod and mod['ground'].get(r['id'])
    return 'listed in module table %s' % ', '.join(t) if t else 'no module ground table lists it' if mod else \
        'module not searched'


def b0_gate(r, mod):
    """(gated, text)"""
    if not mod:
        return False, 'module not searched'
    g = mod['b0'].get(r['id'], [])
    ok = [w for b, w in g if b == r['b0']]
    return bool(ok), ('gated (%s)' % ', '.join(ok) if ok else
                      ', '.join('%s has b0 %d' % (w, b) for b, w in g) if g else 'no module b0 table lists it')


def audit(rec, mef, mod, psl):
    path, _, st = rec
    r = mef[1]
    f, j = r['flags'], r['joint']
    mode = gu_mode(st)
    kind = KIND.get(mode, '+0x36 %d unknown' % st[0x36])
    tags, notes = [], []
    if j >= 0 and not f & MEF_GROUND:
        if kind != 'follows':
            tags.append('FOLLOW')
        elif not f & MEF_ROT_MASKS and st[0x38] != (1 if f & MEF_BODY else 0):
            tags.append('ROT')
    elif j >= 0:
        tags.append('GROUND')
        notes.append('world tail; ' + ground_table(r, mod) if kind == 'world' else
                     '%s at the joint: the known deviation (no GU tail keeps it on the ground)' % kind)
    else:
        if kind == 'follows':
            tags.append('PLACED')
        elif kind == 'world':
            notes.append('world tail; ' + ground_table(r, mod))
        if f & MEF_GROUND:
            notes.append('ground flag, no joint (efl4u2gu: placed)')
    if f & MEF_ROT_MASKS:
        tags.append('AXIS')
        notes.append('4U keeps %s of the %s rotation; GU +0x38 %d +0x3c %d' % (
            '/'.join(a for b, a in AXES if f & b), 'body' if f & MEF_BODY else 'joint', st[0x38], st[0x3c]))
    if r['b0']:
        tags.append('B0')
        notes.append('b0 %d: %s' % (r['b0'], b0_gate(r, mod)[1]))
    want = 'follows' if j >= 0 and not f & MEF_GROUND else 'ground' if j >= 0 else 'placed'
    line = 'id %-5d %-10s %-8s MEF joint %3d flags %#05x b0 %d | 4U %-7s rot %-5s | GU joint %3d mode %s (%s) ' \
           '+0x38 %d | psl %d' % (
               r['id'], path.rsplit('\\', 1)[-1], mef[0].rsplit('\\', 1)[-1], j, f, r['b0'], want,
               'body' if f & MEF_BODY else 'joint', struct.unpack_from('<h', st, 0x32)[0], mode, kind, st[0x38],
               psl[r['id']])
    return tags, line + (' | ' + ' '.join(tags) if tags else '') + ''.join('\n      ' + n for n in notes)


def run(arc4u, arcgu, pel_path, mod_dir, show_all):
    """audit one PEL; prints, returns the counts"""
    A4, G = entries(arc4u), entries(arcgu)
    if (pel_path, T['PEL']) not in G:
        raise SystemExit('%s has no PEL %s (give it with --pel)' % (arcgu, pel_path))
    mefs = mefs_of(A4)
    if not mefs:
        raise SystemExit('%s holds no MEF' % arc4u)
    recs = list1(G[(pel_path, T['PEL'])])
    pr = pair(recs, mefs)
    mod = module_tables(mod_dir) if mod_dir else None
    psl = psl_ids(G)
    print('4U %s | GU %s %s: %d list-1 records' % (arc4u, arcgu, pel_path, len(recs)))
    print('  module tables: %s' % (', '.join(mod['names']) or 'none named *b0* / *ground* / *gjoint*' if mod else
                                   'not searched (GU arc not under monsters/<package>/)'))
    used = collections.Counter(m[0] for _, m in pr['path'])
    for p in sorted({m[0] for m in mefs}):
        print('  MEF %s: %d of %d records paired' % (p, used[p], sum(1 for m in mefs if m[0] == p)))
    cnt = collections.Counter()
    for rec, mef in pr['path']:
        tags, line = audit(rec, mef, mod, psl)
        cnt.update(tags)
        cnt['no_psl'] += not psl[mef[1]['id']]
        r, st = mef[1], rec[2]
        if r['joint'] >= 0 and not r['flags'] & (MEF_GROUND | MEF_ROT_MASKS) and KIND.get(gu_mode(st)) == 'follows':
            cnt['rot_checked'] += 1
        if 'GROUND' in tags and r['joint'] >= 0:
            cnt['ground_joint_' + KIND.get(gu_mode(st), 'unknown')] += 1
        if 'B0' in tags:
            cnt['b0_gated' if b0_gate(r, mod)[0] else 'b0_ungated'] += 1
            cnt['b0_ungated_posted'] += not b0_gate(r, mod)[0] and psl[r['id']] > 0
        if tags or show_all:
            print('  ' + line)
    for rec, mef in pr['other_efl']:
        st = rec[2]
        print('  id %d %s: id + joint match MEF %s %s (group %d file %d), EFL differs: not audited (GU mode %s; %s)' % (
            struct.unpack_from('<H', st, 0x30)[0], rec[0], mef[0].rsplit('\\', 1)[-1], mef[1]['id'], mef[1]['grp'],
            mef[1]['file'], gu_mode(st), ground_table(mef[1], mod)))
    for rec in pr['ambiguous']:
        print('  id %d %s: several MEF records fit: not audited' % (struct.unpack_from('<H', rec[2], 0x30)[0], rec[0]))
    ids = [struct.unpack_from('<H', st, 0x30)[0] for _, _, st in pr['none']]
    cnt.update(paired=len(pr['path']), other_efl=len(pr['other_efl']), ambiguous=len(pr['ambiguous']), none=len(ids))
    print('  no MEF record: %d (GU\'s own or port-made)%s' % (len(ids), (': ids ' + ' '.join(map(str, ids))) if ids else ''))
    print('  summary: paired %d (no PSL slot names %d) | FOLLOW %d | PLACED %d | ROT %d of %d checked | GROUND %d '
          '(world %d, placed %d, follows %d) | AXIS %d | B0 %d (gated %d, in no *b0* table %d, of those in a PSL slot %d) | '
          'other EFL %d | ambiguous %d' % (
              cnt['paired'], cnt['no_psl'], cnt['FOLLOW'], cnt['PLACED'], cnt['ROT'], cnt['rot_checked'],
              cnt['GROUND'], cnt['ground_joint_world'], cnt['ground_joint_placed'], cnt['ground_joint_follows'],
              cnt['AXIS'], cnt['B0'], cnt['b0_gated'], cnt['b0_ungated'], cnt['b0_ungated_posted'],
              cnt['other_efl'], cnt['ambiguous']))
    return cnt


def package_module(arcgu):
    rel = os.path.relpath(os.path.abspath(arcgu), os.path.join(paths.ROOT, 'monsters'))
    return None if rel.startswith('..') else os.path.join(paths.ROOT, 'monsters', rel.split(os.sep)[0], 'module')


def ports(show_all):
    rows = []
    for arc in sorted(glob.glob(os.path.join(paths.ROOT, 'monsters', '*', 'romfs', 'nativeNX', 'arc', 'enemy', '*.arc'))):
        stem = os.path.splitext(os.path.basename(arc))[0]
        pel = 'effect\\pel\\em\\%su' % stem
        G = entries(arc)
        rel = os.path.relpath(arc, paths.ROOT)
        if (pel, T['PEL']) not in G:
            print('%s: no PEL %s, skipped\n' % (rel, pel))
            continue
        recs = list1(G[(pel, T['PEL'])])
        fams = sorted({m for p, _, _ in recs for m in re.findall(r'\\efl\\em\\(em\d{3})\\', p)})
        score = {}
        for fam in fams:
            a4 = os.path.join(paths.ROOT, 'dump', 'romfs', 'data', fam + '.arc')
            if os.path.isfile(a4):
                score[a4] = len(pair(recs, mefs_of(entries(a4)))['path'])
        if not score:
            print('%s: no 4U arc for the em families %s, skipped\n' % (rel, fams))
            continue
        best = max(score, key=score.get)
        print('%s: 4U arc by pairing count: %s' % (rel, ', '.join('%s %d' % (os.path.basename(a), n)
                                                                  for a, n in sorted(score.items()))))
        rows.append((rel.split(os.sep)[1], stem, os.path.basename(best),
                     run(os.path.relpath(best, paths.ROOT), rel, pel, package_module(arc), show_all)))
        print()
    print('ROT = records / checked; GROUND = world / placed / follows tails; B0 = gated / in no *b0* module table (of those in a PSL '
          'slot; a gate written another way is not seen); other = id + joint match, EFL differs (not audited)')
    print('%-22s %-9s %-10s %6s %6s %6s %7s %8s %5s %11s %5s' % ('package', 'arc', '4U arc', 'paired', 'FOLLOW',
                                                               'PLACED', 'ROT', 'GROUND', 'AXIS', 'B0', 'other'))
    for pkg, stem, a4, c in rows:
        print('%-22s %-9s %-10s %6d %6d %6d %7s %8s %5d %11s %5d' % (
            pkg, stem, a4, c['paired'], c['FOLLOW'], c['PLACED'], '%d/%d' % (c['ROT'], c['rot_checked']),
            '%d/%d/%d' % (c['ground_joint_world'], c['ground_joint_placed'], c['ground_joint_follows']), c['AXIS'],
            '%d/%d (%d)' % (c['b0_gated'], c['b0_ungated'], c['b0_ungated_posted']), c['other_efl']))


def main():
    args = sys.argv[1:]
    show_all = '--all' in args
    args = [a for a in args if a != '--all']
    if args == ['--ports']:
        return ports(show_all)
    pel = None
    if '--pel' in args:
        i = args.index('--pel')
        pel = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    pel = pel or 'effect\\pel\\em\\%su' % os.path.splitext(os.path.basename(args[1]))[0]
    run(args[0], args[1], pel, package_module(args[1]), show_all)


if __name__ == '__main__':
    main()
