"""items_em013_06.py : G-rank Crimson Fatalis' break rewards for module/items.c -> data file section BUI4
(tools/portdata.py, tools/items4u.py), and its 4U items -> GU items for the gear and quest tools.
  items_em013_06.py          write the section
  items_em013_06.py show     print it only
Items (C, 2026-11-22): its 4U materials 1589..1593 are GU's 1658..1662 under GU's names (RENAMED: GU's Crimson Fatalis
G materials are em117's), so no item is appended. 4U 1886 Crimson Fatalis Ticket is left out (the maintainer,
2026-11-22): its one use is 4U's GX Fatalis Crimson set, which GU already ships as its own (series 1076 / 1077, crafted
with GU's EX C.Fatalis Ticket; notes/plan.md 12).
Break rewards (C): 4U em117's G groups 0..3 (Flamehorn, Devileye+, Flamewing, Flameshell / Flamescale) are GU
Crimson Fatalis' own G record (result.arc bui_s4 em 0x10d: conds 20 / 30 / 40 / 50, the same items and chances), so
the groups map to those conds; 4U groups 4..7 of the em117 index hold Diablos' items (another species' rows): left
out. em117 is G rank only in 4U (no High rows): BUI4.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
import paths
sys.path.insert(0, paths.GU_PY)
import gear4u, items4u, portdata
from items4u import EXE, text_4u
from romfs import RomFS

NAME, EM4U = 'g_crimson_fatalis', 117
# the other 4U items of its break table and gear -> GU items: renamed (RENAMED) or of the same English name
RENAMED = {1589: 1658,   # Fatalis Flamescale -> Crimson Fatalis Scale
           1590: 1659,   # Fatalis Flameshell -> Crimson Fatalis Shell
           1591: 1660,   # Fatalis Flamehorn -> Crimson Fatalis Horn
           1592: 1661}   # Fatalis Flamewing -> Crimson Fatalis Wing
OTHER_4U_GU = {**RENAMED, 1593: 1662}   # Fatalis Devileye+ (the same name)
BREAK_GROUPS = [(0, 20), (1, 30), (2, 40), (3, 50)]     # (4U group, GU cond): horn, eye, wing, back (GU Crimson's)


def check_other(R):
    """RENAMED pairs: GU's names are 4U's with 'Fatalis Flame<part>' -> 'Crimson Fatalis <Part>'; the rest: the same
    English name in both games"""
    gn = gear4u.gmd(gear4u.gu_arc(R.read('/nativeNX/eng/arc/resident_eng.arc'))['eng\\table\\itemData_eng'])
    n4 = text_4u('eng')[0]
    for k, g in OTHER_4U_GU.items():
        want = 'Crimson Fatalis ' + n4[k][len('Fatalis Flame'):].capitalize() if k in RENAMED else n4[k]
        assert gn[2 * g] == want, (k, n4[k], g, gn[2 * g])


def materials(R=None):
    R = R or RomFS(paths.GU_ROMFS)
    check_other(R)
    return items4u.Materials(NAME, [], (), OTHER_4U_GU, ())


def main():
    R = RomFS(paths.GU_ROMFS)
    exe = open(EXE, 'rb').read()
    m = materials(R)
    brk = items4u.breaks_em(exe, EM4U, BREAK_GROUPS, 3, m.gu_item)
    assert len(brk) == len(BREAK_GROUPS) and all(i is not None for _, es in brk for _, _, i in es), brk
    out = [items4u.bui_section(brk, items4u.RANK_4U_GU[3])]
    if sys.argv[1:] == ['show']:
        for s in out: print(s.tag, portdata.decode(s.tag, s.bytes()))
        return
    for s in out: print('wrote', portdata.write_section(NAME, s))


if __name__ == '__main__':
    main()
