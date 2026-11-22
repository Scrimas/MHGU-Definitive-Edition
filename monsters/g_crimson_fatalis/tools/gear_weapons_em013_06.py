"""gear_weapons_em013_06.py : the 8 G-rank Crimson Fatalis weapons GU lacks as records appended to GU's loaded weapon
tables -> data file sections TBLA / TXTA / KIRX of the g_crimson_fatalis entry (gen/*-weapons.sec, tools/portdata.py;
read by module/gear.c). Tables, 4U records and the rules every monster shares: tools/weapons4u.py; this file: its
inputs (as Shrouded Nerscylla's gear_weapons_em070_01.py). Facts: C = read in code / data, S = strong, G = guess.

  gear_weapons_em013_06.py          write the sections (and check module/gear_hooks.txt holds the weapon class hooks)
  gear_weapons_em013_06.py show     print the per-weapon summary, the tables and the hooks; write nothing

Weapons (C, 4U v1.1 exe, 2026-11-22): every 4U weapon whose create or upgrade recipe uses its materials: 9 forged
(create recipes) and 5 upgrades. GU has 6 of them by name (HBG Destiny's Arm, SnS True Ruiner Sword, Lance True Ruiner
Lance, SA True Ruiner's Bane, DB Twinbane Blades, CB True Ruiner Reaver): GU's own, left as they are (additions only).
The 8 GU lacks are each a one-weapon line here, forged from its 4U create recipe (no 4U child: checked):
  GS Flame Fatalis Blade (216), LS Fatalis Fotia (190), GL Hellruin Gunlance (195), Hammer Fatalis Iregard (215),
  HH Fatalis Menace Soul (158), IG Hellruin Glaive (120), LBG Dith Valor (159), Bow Red Heaven Ruiner (177).
Data: affinity, defense, slots, rarity, price, bowgun ammo = the 4U records'. Status 4 = Blast (GU mElement 9,
Dalamadur's spec). Raw and element = the 4U records' on GU's balance (weapons4u.gu_scale, raw to tens), as Shrouded
Nerscylla's and Desert Seltas' (the maintainer's "scale ... to MHGU's level where needed"), a DEVIATION from 4U.
Sharpness: the table is full (C): entries GU holds take its row; the others keep their 4U row in KIRX, mKireType the
nearest GU row (KIRE_NEAR) as the fallback.
Stand-ins (records copied, then every 4U field set): GU's own Crimson Fatalis weapon of each class (C: their recipes
use its materials, GU 1658..1662): GS 120 Fatalis Fireblade, Hammer 114 Fatalis Smasher, LBG 94 Ruiner Recurve, LS
111 Fatalis Scythe, GL 98 Ruiner Gunlance, Bow 91 Bow of Ire & Anguish, HH 97 Fatalis Firelied, IG 69 Ruiner Glaive.
Kinsect (C): the 4U extra -> GU mInsectType as Tidal's (12 Mauldrone for Impact, 1 Culldrone for Cutting).
Recipe items: its renamed materials (items_em013_06.RENAMED) by GU's names; GU lacks B.Gravios Pallium (Menace Soul):
Gravios Pallium, a PACKAGE-SPLIT substitute (gear_em013_06.py: the real item once all packages ship as one).
Models (C): 4U's numbers (allocations.toml weapon_models, free in GU), arcs tools/weapon4u2gu.py (build.py weapons).
Sounds (C): each 4U arc's own set (sound_set_4u, checked): GU's arc of that number when GU ships it, else the 4U
arc's converted.
"""
import os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
sys.path.insert(0, HERE)
import paths
sys.path.insert(0, paths.GU_PY)
import arcpack, gear4u, gear_em013_06, items_em013_06, portdata, weapons4u   # noqa: E402
from gear4u import EXE, EXE_BASE, RomFS, gu_arc, gmd       # noqa: E402

NAME = 'g_crimson_fatalis'
STATUS = {4: 9}                          # 4U Blast -> GU mElement 9 (Dalamadur's spec, C)
# GU NN, GU stand-in ID, 4U ID (forged from its create recipe)
LINES = [(0, 120, 216),                  # Flame Fatalis Blade
         (2, 114, 215),                  # Fatalis Iregard
         (6, 94, 159),                   # Dith Valor
         (7, 111, 190),                  # Fatalis Fotia
         (9, 98, 195),                   # Hellruin Gunlance
         (10, 91, 177),                  # Red Heaven Ruiner
         (12, 97, 158),                  # Fatalis Menace Soul
         (13, 69, 120)]                  # Hellruin Glaive
IG_INSECT = {0: 1, 1: 12}                # 4U extra 0 Cutting -> GU Culldrone, 1 Impact -> Mauldrone (Tidal's)
# GU rows nearest its 4U entries (sum of absolute differences, GU rows only: a port's rows exist only with its
# package): mKireType, the fallback; its bars are the 4U rows (KIRX). 4U entry 32 (an HR entry ending at 400, IG) is
# GU row 32 up to that end (GU's rows 0..47 are 4U's entries 0..47, weapons4u): that row
KIRE_NEAR = {97: 97, 98: 128, 99: 121, 32: 32}
BOW = dict(kyoku=None)                   # arc shot: the stand-in's; tame, charges, coatings: the 4U record's
PWL_FIX = []                             # every model's GU motion set has its gNN arc (check_pwl)
GEAR_SRC = os.path.join(ROOT, 'dump/gear_src/weapons/4u/data')
PFX = {0: 'two', 1: 'one', 2: 'ham', 3: 'lan', 4: 'hbg', 6: 'lbg', 7: 'swo', 8: 'axe', 9: 'gun', 10: 'bow',
       11: 'sou', 12: 'hue', 13: 'rod', 14: 'gaxe'}


def sound_set_4u(nn, model):
    """the wave set number of the 4U weapon arc of a model (its waves are named <pfx>NNN_k)"""
    ents = arcpack.read(open(os.path.join(GEAR_SRC, 'pl_%s%03d.arc' % (PFX[nn], model)), 'rb').read())[1]
    sets = {re.match(r'[a-z]+(\d+)_', p.split('\\')[-1]).group(1) for p, t, d in ents if '\\wave\\' in p}
    assert len(sets) == 1, (nn, model, sets)
    return int(sets.pop())


def children_4u(exe, nn, i):
    """child weapon IDs of a 4U weapon (upgrade table record +16, 4 x u16)"""
    ctype = weapons4u.CLASS_INFO[nn][3]
    a = weapons4u.u32(exe, weapons4u.UPGRADE_4U + 4 * (ctype - 7)) + 24 * i - EXE_BASE
    return [c for c in struct.unpack_from('<4H', exe, a + 16) if c]


def model(exe, nn, i):
    return weapons4u.weapon_4u(exe, nn, weapons4u.CLASS_INFO[nn][2], i)['model']


def check_pwl(R, exe):
    """every model's GU motion set (pl_wNN record at the model number) has its gNN arc, no GU model arc exists at our
    numbers, and the models are allocations.toml's"""
    res = gu_arc(R.read('/nativeNX/loc/arc/resident.arc'))
    wm = gear4u.alloc.monster(NAME)['weapon_models']
    for nn, sid, i in LINES:
        m = model(exe, nn, i)
        assert wm['w%02d' % nn] == m, (nn, m, wm)
        pwl = res['weapon\\w%02d\\pwl\\pl_w%02d' % (nn, nn)]
        assert m < struct.unpack_from('<I', pwl, 4)[0], (nn, m)
        g = struct.unpack_from('<I', pwl, 8 + 16 * m)[0]
        assert '/nativeNX/arc/weapon/w%02d/g%02d.arc' % (nn, g) in R.files, (nn, m, g)
        assert '/nativeNX/arc/weapon/w%02d/%03d.arc' % (nn, m) not in R.files, (nn, m)


def sound_arcs(R):
    """[(class, model)] whose 4U sound set GU does not ship: build.py step weapons converts them (tools/wsnd4u2gu.py)"""
    exe = open(EXE, 'rb').read()
    out = []
    for nn, sid, i in LINES:
        m = model(exe, nn, i)
        s = sound_set_4u(nn, m)
        if '/nativeNX/arc/weapon/w%02d/snd/%03d.arc' % (nn, s) not in R.files:
            assert s == m, (nn, m, s)
            out.append((nn, m))
    return out


def spec(R):
    exe = open(EXE, 'rb').read()
    t4 = gear4u.text4u('eng')
    res = gu_arc(R.read('/nativeNX/loc/arc/resident.arc'))
    lres = gu_arc(R.read('/nativeNX/eng/arc/resident_eng.arc'))
    gi = gmd(lres['eng\\table\\itemData_eng'])
    subs = {t4['itemName'][k]: gi[2 * g] for k, g in items_em013_06.RENAMED.items()}
    subs.update(gear_em013_06.SUBSTITUTES)
    classes, kire = [], []
    for nn, sid, i in LINES:
        short, txt, ptab, _ = weapons4u.CLASS_INFO[nn]
        if nn != 13:                                     # IG rows hold no child IDs
            assert not children_4u(exe, nn, i), (nn, i, children_4u(exe, nn, i))
        w = weapons4u.weapon_4u(exe, nn, ptab, i)
        c = dict(nn=nn, standin=sid, ids4u=(i,))
        c['raw_scale'], c['elem_scale'] = weapons4u.gu_scale(nn, res, lres, t4, exe)
        print('scale %-6s raw x %.3f, element x %.3f' % (short, c['raw_scale'], c['elem_scale']))
        s = sound_set_4u(nn, w['model'])
        if s != w['model']: c['srqr'] = s                # 4U's arc holds another weapon's set: GU's arc of that number
        if nn == 10: c['bow'] = BOW
        if nn == 13: c.update(insect=IG_INSECT[w['extra']], insect_4u=w['extra'])
        classes.append(c)
        if 'sharp' in w and w['sharp'] not in kire: kire.append(w['sharp'])
    return dict(name=NAME, materials=items_em013_06.materials(R), classes=classes, status=STATUS, kire_4u=kire,
                kire_reuse=True, kire_near=KIRE_NEAR, pwl_fix=PWL_FIX, substitutes=subs)


def main():
    R = RomFS(gear4u.GU_ROMFS)
    check_pwl(R, open(EXE, 'rb').read())
    s = spec(R)
    exact = []                                           # the KIRE_NEAR weapons' own 4U rows (KIRX)
    tables, texts, hooks, summary, log, kire = weapons4u.build(s, exact)
    secs, hk = weapons4u.sections(tables, texts, hooks, s['pwl_fix'], exact)
    have = set(open(weapons4u.OUT_HOOKS).read().split())
    missing = [l for l in hk.splitlines() if not set(l.split()) <= have]
    weapons4u.show(summary, log, kire, tables, hooks, s['status'])
    for nn, wid, level, row, slash in exact:
        print('own sharpness w%02d %3d Lv%d: 4U %s, GU row %d the fallback' % (nn, wid, level, slash, row))
    for short, i, name, b, r, mats, k in summary:        # elements (weapons4u.show prints statuses only)
        if 'mElement' in b:
            print('element %-6s %3d %-24s %d:%d' % (short, i, name, b['mElement'], r['mElementValue'] * 10))
    print('sound arcs to convert:', sound_arcs(R))
    print('hooks missing from module/gear_hooks.txt:', missing or 'none')
    if sys.argv[1:] == ['show']:
        return
    assert not missing, 'module/gear_hooks.txt lacks %s: run tools/weapons4u.write_hooks' % missing
    for sec in secs: print('wrote', portdata.write_section(NAME, sec, 'weapons'))


if __name__ == '__main__':
    main()
