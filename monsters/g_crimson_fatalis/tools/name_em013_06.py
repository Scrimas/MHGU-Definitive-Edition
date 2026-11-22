"""name_em013_06.py : G-rank Crimson Fatalis' name -> data file section NAME (gen/NAME-ui.sec, tools/portdata.py).

  name_em013_06.py           write the section

The entry is allocations.toml name_entry 223 (the second list's 'dummy3', as Monoblos' name_em007_01.py). 4U names
em117 only "Fatalis" (emName[117]), and GU names all three of its forms "Fatalis" in the five western languages (C:
monsterName 117..119), so the 4U rule (4U emName) would give a second "Fatalis". The maintainer's name instead
(2026-11-22): "Crimson Fatalis (4U)", in each language GU's own word for Crimson Fatalis, the one a Crimson Fatalis
item of GU carries (CRIMSON: itemData 1658 "Crimson Fatalis Scale", or the EX ticket 1834 where the scale's name puts
the words apart, C), plus " (4U)". Chinese (chT, chS): lang/zh_TW.toml / zh_CN.toml [monsters], GU's own 紅龍 /
红龙 (monsterName 118: GU's Chinese text does tell its forms apart) plus a full-width "（4U）" (GU's chS text has no
ASCII parentheses), added by portdata.pack.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
import paths
sys.path.insert(0, paths.GU_PY)
from romfs import RomFS
import alloc, gear4u, gmd, portdata
from items4u import LANGS

NAME = 'g_crimson_fatalis'
# GU's word for Crimson Fatalis per language and the GU item whose name carries it (Scale 1658, EX ticket 1834)
CRIMSON = {'eng': ('Crimson Fatalis', 1658), 'fre': ('Fatalis rouge', 1834), 'ger': ('KarmesinFatalis', 1658),
           'ita': ('Fatalis cremisi', 1658), 'spa': ('Fatalis Carmesí', 1658)}


def main():
    entry = alloc.monster(NAME)['name_entry']
    rom = RomFS(paths.GU_ROMFS)
    names = []
    for lang in LANGS:
        s0 = gmd.gmd_strings(rom.read('/nativeNX/%s/GUI/06_msg/monsterName_%s.gmd' % (lang, lang)))
        assert s0[entry] == 'dummy%d' % (entry - 220), (lang, s0[entry])
        items = gmd.gmd_strings(gear4u.gu_arc(rom.read('/nativeNX/%s/arc/resident_%s.arc' % (lang, lang)))[
            '%s\\table\\itemData_%s' % (lang, lang)])
        word, item = CRIMSON[lang]
        assert word in items[2 * item], (lang, items[2 * item])
        names.append(word + ' (4U)')
    sec = portdata.name_section(NAME, entry, names, rom)
    print('wrote', portdata.write_section(NAME, sec, 'ui'), '(name entry %d = %s)' % (entry, ' / '.join(names)))


if __name__ == '__main__':
    main()
