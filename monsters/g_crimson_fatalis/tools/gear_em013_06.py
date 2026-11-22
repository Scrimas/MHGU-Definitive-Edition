"""gear_em013_06.py : G-rank Crimson Fatalis' armor (4U Wroth and GX Fatalis Crimson, 2 series pairs, 20 pieces, crafted
from its materials in 4U) as records appended to GU's loaded tables -> data file sections TBLA / TXTA / SKIL
(gen/*-armor.sec, tools/portdata.py; module/gear.c). Formats, 4U records and the shared rules: tools/gear4u.py. Weapons:
gear_weapons_em013_06.py. Models: build.py step armor (tools/armor4u2gu.py, Wroth's 20 arcs pl_{m,f}_<part>{410,411});
GX Fatalis Crimson's models 507 / 508 are GU's own arcs.
  gear_em013_06.py          write the sections
  gear_em013_06.py show     print them only
4U data (C, 2026-11-22): the pieces whose 4U create recipes use its materials, per pair the Blademaster piece IDs below
(Gunner = ID + 1), rarity 10: Wroth (models 410 / 411, no GU armor arc has them) and GX Fatalis Crimson (models 507 /
508 + the Crimson Fatalis Ticket, items_em013_06.py; GU ships that look as its own "Fatalis Crimson XR" set with
another recipe and skills: the maintainer chose to port 4U's set beside it, 2026-11-22).
Choices (the earlier ports' rules, listed for review):
  - Templates: Wroth = GU Fatalis Crimson (1074 / 1075, G rank, the same species); GX = GU Fatalis Crimson XR (1078 /
    1079: models 507 / 508, the same look): max level, limit levels, defense table, sound, look.
  - Defense: 4U defense x the GU / 4U ratio of the G-rank elder sets both games have by name at 4U rarity 10 (ANCHORS:
    Kushala X, Akantor X, Ukanlos X; S): 4U's Fatalis G sets are not in GU by name, GU's Fatalis Crimson is 4U's High
    Rank set re-ranked. On GU's balance as the earlier ports.
  - Skills by GU tree name; a 4U tree GU lacks is dropped (DROPPED_TREES), a DEVIATION. 4U Arcana (the GX set's
    tree) is the ported Arcana / Enlightened Blade (tools/gear4u.py arcana, the maintainer's choice 2026-11-22: port
    the skill), whose records this package ships as Gogmazios' does: the first one loaded appends them.
  - Level rows: the templates', unchanged: their monster materials are GU's Crimson Fatalis ones = its own (C:
    items_em013_06.RENAMED), so nothing is swapped (TEMPLATE_WORD None, as Shrouded Nerscylla's).
  - Recipe items: its renamed materials (items_em013_06.RENAMED) by GU's names; items GU lacks -> SUBSTITUTES (the
    maintainer, 2026-11-22: GU stand-ins of the same rarity tier). B.Gravios Pallium is a PACKAGE-SPLIT substitute:
    our Black Gravios package appends the real item, but packages install separately today; when all packages ship
    as one, use the real item.
  - Default dye = 4U's colour index.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
sys.path.insert(0, HERE)
import gear4u, items_em013_06, portdata           # noqa: E402
from gear4u import EXE, RomFS, gu_arc, gmd, text4u   # noqa: E402
NAME = 'g_crimson_fatalis'
# (pair, 4U Blademaster IDs head / body / arms / waist / legs, GU template pair, model pair)
PAIRS = [('Wroth', [698, 702, 686, 686, 694], (1074, 1075), (410, 411)),
         ('GX Fatalis Crimson', [901, 886, 870, 870, 878], (1078, 1079), (507, 508))]
# 4U G-rank elder sets of GU's names: (Blademaster head, Gunner head) -> GU series
ANCHOR_NAMES = [('Kushala Glare X', 'Kushala Snarl X'), ('Akantor Mask X', 'Akantor Fangs X'),
                ('Ukanlos Mask X', 'Ukanlos Fangs X')]
# 4U Constitutn = GU Constitution (4U's 10-character name, the same description, C). 4U Arcana (GX's set tree, +10 =
# Enlightened Blade: Awaken + Element Atk Up + Status Atk Up) is the ported tree 206 / skill 328 Gogmazios' armor has
# (tools/gear4u.py arcana: GU's element and status boosts, GU has no Awaken), its records shipped here too (see there)
TREE_4U_GU = {'Constitutn': 'Constitution'}
DROPPED_TREES = {'FreeElemnt'}           # as the earlier ports: GU has no hidden elements
TEMPLATE_WORD = None                     # the templates' materials are its own (see above)
SUBSTITUTES = {'B.Gravios Pallium': 'Gravios Pallium',          # package-split (see above; Shrouded Nerscylla's rule)
               'Earth Dragonsphire': 'Heavenly Dragonsphire',   # Dah'ren Mohran's (not in GU)
               'Skyblade Drgnsphire': 'Azure Dragonsphire',
               'Dire Blastheart': 'Tigrex Mantle'}              # Molten Tigrex's (not in GU) -> Tigrex's rarest
# 4U name -> GU name of its renamed materials (the recipes name items by GU's English names)
RENAMED = {}


def anchors(t4, gn):
    """([(4U head ID, GU series)], [..]) Blademaster, Gunner"""
    h4 = {n: k for k, n in enumerate(t4['HeadName'])}
    return tuple([(h4[p[g]], gn[p[g]]) for p in ANCHOR_NAMES] for g in range(2))


def defense_map(exe, series, defs, anch):
    """{4U defense: GU defense} of one pair's Blademaster / Gunner defenses `defs`"""
    out = {}
    for g, d4 in enumerate(defs):
        ratios = [series[8 + 127 * gu + 106] / gear4u.armor_4u(exe, 33, k)['defense'] for k, gu in anch[g]]
        out[d4] = int(d4 * sum(ratios) / len(ratios) + 0.5)
    return out


def armor_specs(R, exe):
    t4 = text4u('eng')
    res = gu_arc(R.read('/nativeNX/loc/arc/resident.arc'))
    lres = gu_arc(R.read('/nativeNX/eng/arc/resident_eng.arc'))
    series = res['table\\armorSeriesData']
    sn = gmd(lres['eng\\table\\armorSeriesData_eng'])
    gn = {sn[10 * i]: i for i in range(len(sn) // 10)}
    gst = gmd(lres['eng\\table\\skillTypeData_eng'])
    gtree = {gst[i]: i // 2 for i in range(0, len(gst), 2)}
    gi = gmd(lres['eng\\table\\itemData_eng'])
    renamed = {t4['itemName'][k]: gi[2 * g] for k, g in items_em013_06.RENAMED.items()}
    anch = anchors(t4, gn)

    def tree(tree4, name):
        if name in DROPPED_TREES: return None
        if tree4 == gear4u.ARCANA_4U: return gear4u.ARCANA_TREE
        return gtree[TREE_4U_GU.get(name, name)]
    specs = []
    for pair, parts, tpl, model in PAIRS:
        recipes = []
        for (part, _), k in zip(gear4u.PARTS, parts):
            r = [(t4['itemName'][it], c) for it, c in gear4u.armor_recipe_4u(exe, part, k)]
            assert r == [(t4['itemName'][it], c) for it, c in gear4u.armor_recipe_4u(exe, part, k + 1)], (pair, part)
            recipes.append([(SUBSTITUTES.get(n, renamed.get(n, n)), c) for n, c in r])
        defs = [gear4u.armor_4u(exe, 33, parts[0] + g)['defense'] for g in range(2)]
        specs.append(dict(template=tpl, model=model, parts=parts, defense=defense_map(exe, series, defs, anch),
                          tree=tree, recipes=recipes, scrap=None, level_swap={}, template_word=TEMPLATE_WORD))
    return specs


def main():
    R = RomFS(gear4u.GU_ROMFS)
    exe = open(EXE, 'rb').read()
    mats = items_em013_06.materials(R, exe)
    specs = armor_specs(R, exe)
    for (pair, *_), s in zip(PAIRS, specs):
        print('%-18s defense %s' % (pair, s['defense']))
    tables, texts = gear4u.armors(NAME, [mats], specs, R, exe)
    t, x, skil = gear4u.arcana(gu_arc(R.read('/nativeNX/loc/arc/resident.arc')))    # GX's set tree
    secs = [portdata.tbla(tables + t), portdata.txta(texts + x), skil]
    if sys.argv[1:] == ['show']:
        for s in secs: print(s.tag, portdata.decode(s.tag, s.bytes()))
        return
    for s in secs: print('wrote', portdata.write_section(NAME, s, 'armor'))


if __name__ == '__main__':
    main()
