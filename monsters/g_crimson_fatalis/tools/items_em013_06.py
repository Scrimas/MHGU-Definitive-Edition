"""items_em013_06.py : G-rank Crimson Fatalis' appended item and break rewards for module/items.c and module/gear.c ->
data file sections TBLA + TXTA (the ticket APPENDED after the Desert Seltas Queen's materials, notes/items-append.md)
and BUI4 (tools/portdata.py, tools/items4u.py).
  items_em013_06.py          write the sections
  items_em013_06.py show     print them only
Items (C, 2026-11-22): its 4U materials 1589..1593 are GU's 1658..1662 under GU's names (RENAMED: GU's Crimson Fatalis
G materials are em117's), so only 4U 1886 Crimson Fatalis Ticket is appended (GU 3063: GU has none; its "EX C.Fatalis
Ticket" 1834 is another item, the one of GU's own GX set). Its GU category: the EX C.Fatalis Ticket's, which has the
same icon (checked).
Break rewards (C): 4U em117's G groups 0..3 (Flamehorn, Devileye+, Flamewing, Flameshell / Flamescale) are GU
Crimson Fatalis' own G record (result.arc bui_s4 em 0x10d: conds 20 / 30 / 40 / 50, the same items and chances), so
the groups map to those conds; 4U groups 4..7 of the em117 index hold Diablos' items (another species' rows): left
out. em117 is G rank only in 4U (no High rows): BUI4.
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
import paths
sys.path.insert(0, paths.GU_PY)
import gear4u, items4u, portdata
from items4u import EXE, LANGS, text_4u
from romfs import RomFS

NAME, EM4U = 'g_crimson_fatalis', 117
# 4U IDs. Order = GU IDs from 3063: never reorder once released (saves keep them).
ITEMS_4U = [1886]   # Crimson Fatalis Ticket
TICKET_GU = 1834    # EX C.Fatalis Ticket: the GU item whose category the ticket takes
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


def category(R, exe):
    d = gear4u.gu_arc(R.read('/nativeNX/loc/arc/resident.arc'))['table\\itemData']
    r = d[8 + 44 * TICKET_GU:8 + 44 * (TICKET_GU + 1)]
    assert r[0x10] == items4u.item_4u(exe, ITEMS_4U[0])[1], ('the ticket icons differ', r[0x10])
    return r[0x1b]


def materials(R=None, exe=None):
    R = R or RomFS(paths.GU_ROMFS)
    exe = exe or open(EXE, 'rb').read()
    check_other(R)
    return items4u.Materials(NAME, [(ITEMS_4U[0], category(R, exe))], (), OTHER_4U_GU, ())


def main():
    R = RomFS(paths.GU_ROMFS)
    exe = open(EXE, 'rb').read()
    text = {lang: text_4u(lang) for lang in LANGS}
    m = materials(R, exe)
    out = list(m.append_sections(exe, text, R))
    brk = items4u.breaks_em(exe, EM4U, BREAK_GROUPS, 3, m.gu_item)
    assert len(brk) == len(BREAK_GROUPS) and all(i is not None for _, es in brk for _, _, i in es), brk
    out.append(items4u.bui_section(brk, items4u.RANK_4U_GU[3]))
    if sys.argv[1:] == ['show']:
        for s in out: print(s.tag, portdata.decode(s.tag, s.bytes()))
        return
    for s in out: print('wrote', portdata.write_section(NAME, s))


if __name__ == '__main__':
    main()
