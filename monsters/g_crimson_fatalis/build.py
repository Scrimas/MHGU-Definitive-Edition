"""build.py : rebuild every G-rank Crimson Fatalis output from the dumps (game data: the outputs are gitignored, never
published).

  python3 monsters/g_crimson_fatalis/build.py [STEP ...]      default: every step, in order (--list: the steps)

Outputs (monsters/g_crimson_fatalis/): romfs/ (converted RomFS = its assets package: the monster arc em013_06, the
  theme's opus stream), gen/g_crimson_fatalis.bin (its data file, packed from the gen/*.sec sections,
  tools/portdata.py), tools/em013_06_manifest.json.
Inputs: dump/romfs (4U em117.arc, em078.arc, em_data.arc, quest00 / 01.arc), dump/extdata_4u (the maintainer's 4U
  event quests, tools/extdata4u.py), dump/exefs_v11 (4U code: shell records), dump/base (4U ROM: the theme, core
  effect arcs, Ingle Isle area colour), dump/m19_unpacked/m19a03 (reference area-colour file), dump/gear_src (4U
  armor / weapon arcs) and the GU inputs of tools/paths.py. Work files in dump/converted/em117/ and
  dump/converted/g_crimson_fatalis/. One line per step on stdout, the step's own output in $BUILD_LOGS/<step>.log
  (tools/steps.py).
"""
import os, sys
MON = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(MON, '..', '..', 'tools'))
from steps import DUMP, py, armor, weapon, main

T = os.path.join(MON, 'tools')
ROMFS = os.path.join(MON, 'romfs')
# Wroth 410 / 411 (tools/gear_em013_06.py)
ARMOR = (410, 411)
# class, 4U arc prefix, model (tools/gear_weapons_em013_06.py). No sound arcs: each 4U arc holds a sound set GU ships
# (checked there)
WEAPONS = (('00', 'two', '108'), ('02', 'ham', '109'), ('06', 'lbg', '059'), ('07', 'swo', '091'), ('09', 'gun', '093'),
           ('10', 'bow', '086'), ('12', 'hue', '079'), ('13', 'rod', '044'))


def dt():     # dtbase / dttune of 4U em078 and em117 on GU em013_01 (tools/dt_convert.py, needs unicorn: the .venv)
    return [py('tools/dt_convert.py', 'build', em, 'em013_01', os.path.join(DUMP, 'converted', 'em117', 'dt_' + em),
               venv=True) for em in ('em078', 'em117')]


def weapons():
    for c, pf, m in WEAPONS:
        yield weapon(ROMFS, int(c), pf + m, m, '--alpha-test-4u', '--anim-4u', '--shield-bone0', '--opaque-4u')


STEPS = [
    ('dt', 'dump/converted/em117/dt_em0NN/', dt),
    ('bgm', 'theme opus + dump/converted/g_crimson_fatalis STQR', lambda: [py(os.path.join(T, 'bgm_em013_06.py'))]),
    ('arc', 'monster arc (carves, shell family) + manifest + FILE', lambda: [py(os.path.join(T, 'build_em013_06_arc.py'))]),
    ('name', 'NAME ("Crimson Fatalis (4U)", GU\'s words, 5 languages)',
     lambda: [py(os.path.join(T, 'name_em013_06.py'))]),
    ('items', 'BUI4 (break rewards)', lambda: [py(os.path.join(T, 'items_em013_06.py'))]),
    ('gear', 'armor records (Wroth)', lambda: [py(os.path.join(T, 'gear_em013_06.py'))]),
    ('armor', 'armor model arcs (Wroth, 20)', lambda: armor(ROMFS, ARMOR)),
    ('weapons', 'weapon model arcs (8)', weapons),
    ('gearw', 'weapon table records (8 one-weapon lines)', lambda: [py(os.path.join(T, 'gear_weapons_em013_06.py'))]),
    ('quest', '11498 11499 11497 (4U m11036 m60249 m60215)',
     lambda: [py(os.path.join(T, 'build_em013_06_quest.py'), flags=('-I', '-B'))]),
    ('pack', 'gen/*.sec -> gen/g_crimson_fatalis.bin', lambda: [py('tools/portdata.py', 'pack', 'g_crimson_fatalis')]),
]

if __name__ == '__main__':
    main('g_crimson_fatalis', STEPS)
