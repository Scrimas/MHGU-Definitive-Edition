"""arcdiff.py : what differs between two MT Framework arcs (4U v0x13 or GU v0x11), entry by entry.

  arcdiff.py A B [--ranges N]     A / B = an arc file, or a GU RomFS path (/nativeNX/arc/..., read from
                                  tools/paths.py GU_ROMFS); N = byte ranges listed per changed entry (default 8)

Entries are matched by (path, type hash). Per changed entry, by type:
  PEL  per list (efl4u2gu.pel_lists): records paired by id (by index in a list that repeats an id), added / removed
       records, path and +2 byte changes, and the changed bytes of the 160-byte state (offset, old -> new)
  TEX  header (tex.parse): width x height, format, mips, and whether the data after the header differs
  MRL  mrl.read: textures added / removed, materials by name hash added / removed / changed (entry words, block)
  EFL  efl_parse: version, entries, tail records, blocks; with equal block counts the changed blocks in order
  else the changed byte ranges (equal sizes) or the sizes and the first differing offset
Prints only what differs; "no difference" when the entry lists and every entry's bytes are equal.
Library: read_arc(spec) -> [(path, type hash, bytes)] (tools/fxaudit.py, tools/fxsheet.py).
"""
import os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths
sys.path.insert(0, paths.GU_PY)
import arcpack, efl4u2gu, tex

NAMES = {v: k for k, v in efl4u2gu.T.items()}


def read_arc(spec):
    """an arc file, or a GU RomFS path (/nativeNX/...)"""
    if os.path.isfile(spec):
        d = open(spec, 'rb').read()
    elif spec.startswith('/nativeNX/'):
        try:
            d = efl4u2gu.gu_rom().read(spec)
        except KeyError:
            raise SystemExit('not in the GU RomFS (%s): %s' % (paths.GU_ROMFS, spec))
    else:
        raise SystemExit('no such arc: %s (an arc file, or a GU RomFS path /nativeNX/...)' % spec)
    if d[:4] != b'ARC\0':
        raise SystemExit('not an arc: %s' % spec)
    return arcpack.read(d)[1]


def tname(t):
    return NAMES.get(t, '%08x' % t)


def ranges(a, b):
    """[(start, end)] of the differing bytes of two equal-length byte strings"""
    x = (np.frombuffer(a, np.uint8) != np.frombuffer(b, np.uint8)).view(np.int8)
    d = np.diff(np.concatenate(([0], x, [0])))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def byte_diff(a, b, nshow):
    if len(a) != len(b):
        n = min(len(a), len(b))
        r = ranges(a[:n], b[:n])
        return ['size %d -> %d, first difference at %#x' % (len(a), len(b), r[0][0] if r else n)]
    r = ranges(a, b)
    return ['%d changed byte range(s), %d bytes: %s%s' % (len(r), sum(e - s for s, e in r),
            ' '.join('%#x..%#x' % (s, e) for s, e in r[:nshow]), ' ...' if len(r) > nshow else '')]


def pel_records(body, n):
    out, i = [], 0
    for _ in range(n):
        L = body[i]
        out.append((body[i + 1:i + 1 + L].decode('ascii'), body[i + 1 + L:i + 3 + L], body[i + 3 + L:i + 3 + L + 160]))
        i += 3 + L + 160
    return out


def state_diff(a, b):
    return ', '.join('+%#x %s -> %s' % (s, a[s:e].hex(), b[s:e].hex()) for s, e in ranges(a, b))


def pel_diff(a, b, nshow):
    la, lb = efl4u2gu.pel_lists(a), efl4u2gu.pel_lists(b)
    out = ['lists %s -> %s records' % ('/'.join(str(n) for n, _ in la), '/'.join(str(n) for n, _ in lb))]
    for li in range(3):
        ra, rb = pel_records(la[li][1], la[li][0]), pel_records(lb[li][1], lb[li][0])
        ida = [struct.unpack_from('<H', st, 0x30)[0] for _, _, st in ra]
        idb = [struct.unpack_from('<H', st, 0x30)[0] for _, _, st in rb]
        by_id = len(set(ida)) == len(ida) and len(set(idb)) == len(idb)
        ka, kb = (ida, idb) if by_id else (list(range(len(ra))), list(range(len(rb))))
        A, B = dict(zip(ka, ra)), dict(zip(kb, rb))
        key = 'id %d' if by_id else 'record #%d'
        lines = []
        for k in [k for k in ka if k not in B]:
            lines.append('removed %s %s' % (key % k, A[k][0]))
        for k in [k for k in kb if k not in A]:
            lines.append('added %s %s' % (key % k, B[k][0]))
        for k in [k for k in kb if k in A]:
            (pa, ta, sa), (pb, tb, sb) = A[k], B[k]
            if (pa, ta, sa) == (pb, tb, sb):
                continue
            j = struct.unpack_from('<h', sb, 0x32)[0]
            d = ['path %s -> %s' % (pa, pb)] if pa != pb else []
            if ta != tb:
                d.append('+2 bytes %s -> %s' % (ta.hex(), tb.hex()))
            if sa != sb:
                d.append(state_diff(sa, sb))
            lines.append('%s (#%d, joint %d, %s): %s' % (key % k, kb.index(k), j, pb.rsplit('\\', 1)[-1], '; '.join(d)))
        if lines:
            out.append('list %d%s:' % (li, '' if by_id else ' (ids repeat: paired by index)'))
            out += ['  ' + l for l in lines]
    return out


def tex_head(d):
    h = tex.parse(d)
    return '%dx%d fmt %#x mips %d' % (h['width'], h['height'], h['fmt'], h['mips']), h['data']


def tex_diff(a, b, nshow):
    (ha, da), (hb, db) = tex_head(a), tex_head(b)
    return ['header %s%s; data %s' % (ha, '' if ha == hb else ' -> ' + hb, 'same' if da == db else 'differs')]


def mrl_diff(a, b, nshow):
    import mrl
    ra, rb = mrl.read(a), mrl.read(b)
    out = ['version %#x -> %#x, %d -> %d materials, %d -> %d textures' % (
        ra['version'], rb['version'], len(ra['mats']), len(rb['mats']), len(ra['textures']), len(rb['textures']))]
    ta, tb = [p for _, p in ra['textures']], [p for _, p in rb['textures']]
    out += ['texture removed %s' % p for p in ta if p not in tb] + ['texture added %s' % p for p in tb if p not in ta]
    if ta != tb and sorted(ta) == sorted(tb):
        out.append('texture order changed')
    ma, mb = {m['name']: m for m in ra['mats']}, {m['name']: m for m in rb['mats']}
    out += ['material %08x removed' % k for k in ma if k not in mb] + ['material %08x added' % k for k in mb if k not in ma]
    for k in [k for k in mb if k in ma]:
        x, y = ma[k], mb[k]
        w = [i for i in range(15) if x['words'][i] != y['words'][i]]
        d = (['words %s' % w] if w else []) + (['block (%s)' % byte_diff(x['block'], y['block'], nshow)[0]]
                                               if x['block'] != y['block'] else []) + \
            (['animation block'] if x['anim'] != y['anim'] else [])
        if d:
            out.append('material %08x: %s' % (k, '; '.join(d)))
    return out


def efl_diff(a, b, nshow):
    pa, pb = efl4u2gu.efl_parse(a), efl4u2gu.efl_parse(b)
    out = ['version %#x -> %#x, entries %d -> %d, tail %d -> %d, blocks %d -> %d, %d -> %d B' % (
        pa['ver'], pb['ver'], pa['n'], pb['n'], pa['n2'], pb['n2'], len(pa['blocks']), len(pb['blocks']), len(a), len(b))]
    if len(pa['blocks']) != len(pb['blocks']):
        return out
    if a[0x30:pa['first']] != b[0x30:pb['first']]:
        out.append('entry / tail tables differ')
    ch = []
    for i, ((oa, sa, ka), (ob, sb, kb)) in enumerate(zip(pa['blocks'], pb['blocks'])):
        if a[oa:oa + sa] != b[ob:ob + sb]:
            kind = 'unit type %d' % ka[1] if ka and ka[0] == 1 else 'block %s' % (ka,)
            ch.append('#%d %s at %#x, %d -> %d B: %s' % (i, kind, ob, sa, sb, byte_diff(a[oa:oa + sa], b[ob:ob + sb], 3)[0]))
    out.append('%d changed block(s)' % len(ch))
    out += ch[:nshow] + (['...'] if len(ch) > nshow else [])
    return out


DETAIL = {efl4u2gu.T['PEL']: pel_diff, efl4u2gu.T['TEX']: tex_diff, efl4u2gu.T['MRL']: mrl_diff,
          efl4u2gu.T['EFL']: efl_diff}


def main():
    args = sys.argv[1:]
    nshow = 8
    if '--ranges' in args:
        i = args.index('--ranges')
        nshow = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    ea, eb = read_arc(args[0]), read_arc(args[1])
    A, B = {}, {}
    for ents, D, spec in ((ea, A, args[0]), (eb, B, args[1])):
        for p, t, d in ents:
            if (p, t) in D:
                raise SystemExit('%s holds (%s, %s) twice: entries are matched by path and type' % (spec, p, tname(t)))
            D[(p, t)] = d
    print('A %s: %d entries\nB %s: %d entries' % (args[0], len(ea), args[1], len(eb)))
    removed = [k for k in A if k not in B]
    added = [k for k in B if k not in A]
    changed = [k for k in B if k in A and A[k] != B[k]]
    order = [k for k in A if k in B] != [k for k in B if k in A]
    for k in removed:
        print('removed  %s %s (%d B)' % (tname(k[1]), k[0], len(A[k])))
    for k in added:
        print('added    %s %s (%d B)' % (tname(k[1]), k[0], len(B[k])))
    for k in changed:
        print('changed  %s %s' % (tname(k[1]), k[0]))
        try:
            lines = DETAIL.get(k[1], byte_diff)(A[k], B[k], nshow)
        except (AssertionError, SystemExit, struct.error, KeyError) as e:
            # a parser that rejects the file: the raw ranges still say what changed
            lines = ['(%s parser failed: %r)' % (tname(k[1]), e)] + byte_diff(A[k], B[k], nshow)
        for l in lines:
            print('    ' + l)
    if order:
        print('entry order differs')
    print('summary: %d removed, %d added, %d changed, %d same%s' % (
        len(removed), len(added), len(changed), len(B) - len(added) - len(changed), ', order differs' if order else ''))
    if not (removed or added or changed or order):
        print('no difference')


if __name__ == '__main__':
    main()
