"""aiclosure.py : the native actions (`00 cat num`) each AI table (EMC) starts, side by side, and the ones only some
tables start.

  python3 tools/aiclosure.py TABLE TABLE [...]
      TABLE = an .arc file (4U: dump/romfs/data/emNNN.arc; a built port: monsters/<pkg>/romfs/nativeNX/arc/enemy/
              emNNN_VV.arc) or gu:NAME for GU's RomFS arc nativeNX/arc/enemy/NAME.arc; every EMC entry of an arc is
              one table
  e.g. aiclosure.py dump/romfs/data/em095.arc dump/romfs/data/em026.arc gu:em069_00 \\
           monsters/desert_seltas/romfs/nativeNX/arc/enemy/em069_01.arc

The porting guide (lessons from Desert Seltas): GU keeps the code of actions only a subspecies' 4U table starts, but no
GU table reaches it; test those first. Scripts are cut into instructions by the game's own length table (GU main
0x1732c8c, 167 ops, tools/emc.py LEN_TABLE; 4U 0xffe9f4, 146 ops, bound at 0x93555c `cmp r0, #146`, equal to GU's
first 146): a byte < 0x80 = its argument count, 0x8n..0xBn = block ops (`00` opens with n bytes, `01` a case, else 1).
A 4U arc (ARC version 0x13) is read with 4U's table, a GU or port arc (0x11) with GU's. An action inside a 4U em switch
(op 0x46: one 4U table can serve two species) or a GU variant switch (op 0x92) is shown with its case, e.g.
`g20 s0(em 94)`; the only / lacks lists do not split by case. Every `00 cat num` of every
group counts, so the list is what each table can start, not what one fight reaches (conditions, ranks and GU class
code that picks scripts by number decide that). Actions the engine or class code requests on its own (reactions,
death: categories 10 / 11 from GU code) are in no table. A script that does not cut cleanly (an op past the table
before its end) is reported; its rest is not read.
"""
import os, sys

import paths
sys.path.insert(0, paths.GU_PY)
import arcpack, emc  # noqa: E402

LEN_GU = (emc.LEN_TABLE, emc.LEN_COUNT)
LEN_4U = (0xffe9f4 - 0x100000, 146)                 # offset in dump/exefs_v11/mem.bin (flat from 0x100000)
# the switch blocks a subspecies' actions sit in: 4U 0x46 on the em number (0x951ff0, build_dalamadur_arc.py), GU
# 0x92 on the variant (build_seltas_arc.py); `op 00` opens, `op 01 v` = case v, `op 02` = else, `op ff` ends
SWITCH = {0x13: (0x46, 'em'), 0x11: (0x92, 'variant')}


def tokens(s, lens):
    """(instructions, rest): rest is the script past an op outside the table, unless that op is its last byte"""
    out, i = [], 0
    while i < len(s):
        op = s[i]
        if op >= len(lens):
            return out, (s[i:] if i < len(s) - 1 else b'')
        v = lens[op]
        if v >= 0x80 and i + 1 == len(s): return out, s[i:]
        n = 1 + v if v < 0x80 else 2 + (v & 0xf) if s[i + 1] == 0 else 2 + (v >> 4) - 7 if s[i + 1] == 1 else 2
        if i + n > len(s): return out, s[i:]
        out.append(s[i:i + n]); i += n
    return out, b''


def tables(arg, rom):
    """[(label, ARC version, EMC bytes)] of one TABLE argument"""
    if arg.startswith('gu:'):
        p = '/nativeNX/arc/enemy/%s.arc' % arg[3:]
        if p not in rom().files: sys.exit('aiclosure: GU RomFS has no %s' % p)
        d = rom().read(p)
    else:
        if not os.path.isfile(arg): sys.exit('aiclosure: no file %s' % arg)
        with open(arg, 'rb') as f: d = f.read()
    if d[:4] != b'ARC\0': sys.exit('aiclosure: %s is not an ARC file' % arg)
    ver, ents = arcpack.read(d)
    out = [('%s %s' % (arg, p), ver, x) for p, t, x in ents if x[:4] == b'EMC\0']
    if not out: sys.exit('aiclosure: %s holds no EMC (AI table)' % arg)
    return out


def main(argv):
    if len(argv) < 2: sys.exit(__doc__)
    cache = {}

    def rom():
        if 'rom' not in cache:
            if not os.path.exists(paths.GU_ROMFS): sys.exit('aiclosure: %s missing (tools/doctor.py)' % paths.GU_ROMFS)
            from romfs import RomFS
            cache['rom'] = RomFS(paths.GU_ROMFS)
        return cache['rom']

    for p in (paths.GU_MAIN, os.path.join(paths.DUMP, 'exefs_v11', 'mem.bin')):
        if not os.path.exists(p): sys.exit('aiclosure: %s missing (its length table; tools/doctor.py)' % p)
    with open(paths.GU_MAIN, 'rb') as f: g = f.read()
    with open(os.path.join(paths.DUMP, 'exefs_v11', 'mem.bin'), 'rb') as f: m4 = f.read()
    lens = {0x11: g[LEN_GU[0]:sum(LEN_GU)], 0x13: m4[LEN_4U[0]:sum(LEN_4U)]}
    T = [t for a in argv for t in tables(a, rom)]
    where, bad = [], []
    for k, (label, ver, d) in enumerate(T):
        if ver not in lens: sys.exit('aiclosure: %s: ARC version %#x is neither GU (0x11) nor 4U (0x13)' % (label, ver))
        w = {}
        for gi, grp in enumerate(emc.parse(d)[1]):
            for si, s in enumerate(grp):
                ins, rest = tokens(s, lens[ver])
                if rest: bad.append('%s: g%d s%d: op %#x at byte %d is past the length table' % (
                    chr(65 + k), gi, si, rest[0], len(s) - len(rest)))
                cases = []                       # open species / variant switches: [(name, current case)]
                for t in ins:
                    if t[0] == SWITCH[ver][0]:
                        if t[1] == 0: cases.append([SWITCH[ver][1], None])
                        elif t[1] == 1 and cases: cases[-1][1] = '%d' % t[2]
                        elif t[1] == 2 and cases: cases[-1][1] = 'else'
                        elif t[1] == 0xff and cases: cases.pop()
                    if t[0] == 0 and len(t) == 3:
                        w.setdefault((t[1], t[2]), []).append('g%d s%d%s' % (gi, si, ''.join(
                            '(%s %s)' % tuple(c) for c in cases)))
        where.append(w)
    for k, (label, ver, d) in enumerate(T):
        print('%s = %s (%s, %d native actions)' % (chr(65 + k), label, '4U' if ver == 0x13 else 'GU', len(where[k])))
    acts = sorted(set().union(*where))
    names = ''.join(chr(65 + k) for k in range(len(T)))
    print('action  %s  scripts' % names)
    for a in acts:
        have = ''.join(chr(65 + k) if a in w else '.' for k, w in enumerate(where))
        print('%3d/%-3d %s  %s' % (a[0], a[1], have, '; '.join(
            '%s: %s' % (chr(65 + k), ' '.join(w[a][:6]) + (' ...' if len(w[a]) > 6 else ''))
            for k, w in enumerate(where) if a in w)))
    for k, w in enumerate(where):
        only = [a for a in acts if a in w and not any(a in x for j, x in enumerate(where) if j != k)]
        missing = [a for a in acts if a not in w]
        print('%s only: %s' % (chr(65 + k), ' '.join('%d/%d' % a for a in only) or '-'))
        print('%s lacks: %s' % (chr(65 + k), ' '.join('%d/%d' % a for a in missing) or '-'))
    for b in bad: print('not cut cleanly: ' + b)
    print('%d tables, %d distinct native actions. Every `00 cat num` of every script counts (see the docstring: what '
          'a table can start, not what a fight reaches)' % (len(T), len(acts)))


if __name__ == '__main__':
    main(sys.argv[1:])
