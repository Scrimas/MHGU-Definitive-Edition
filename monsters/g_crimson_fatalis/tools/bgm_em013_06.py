"""bgm_em013_06.py : G-rank Crimson Fatalis' theme (4U battle theme bgm_em117) -> a GU Opus stream + its own battle STQR.

  bgm_em013_06.py      write monsters/g_crimson_fatalis/romfs/nativeNX/sound/bgm/battle/wav/bgm_em013_06_Fatalis.opus
                       and dump/converted/g_crimson_fatalis/bgm_em013_06.stqr (packed into em013_06 as
                       sound\\bgm\\battle\\bgm_em013_06 by build_em013_06_arc.py)

4U (C): sound/bgm/battle/wav/bgm_em117.mca, one stream (no phase 2), its level from 4U bgm_bat.stq. GU level = 4U
level + the median delta of the battle-theme anchors (tools/snd_bgm.py levels), as for Gogmazios and Dalamadur.
Sequence id: allocations.toml bgm_ids (0x904).
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import alloc, snd_bgm

SRC = 'sound/bgm/battle/wav/bgm_em117.mca'
STQR = os.path.join(ROOT, 'dump/converted/g_crimson_fatalis/bgm_em013_06.stqr')
PATH = 'sound\\bgm\\battle\\wav\\bgm_em013_06_Fatalis'


def main():
    ids = tuple(alloc.monster('g_crimson_fatalis')['bgm_ids'])
    assert len(ids) == 1, 'one theme, one sequence id'
    log = []
    med, db4 = snd_bgm.levels(log)
    name = SRC.split('/')[-1][:-4]
    assert name in db4, '4U bgm_bat.stq has no sequence for ' + name
    opus, ns, ls, le, _ = snd_bgm.convert_track(snd_bgm.extract([SRC])[SRC], log)
    out = os.path.join(MON, 'romfs/nativeNX', PATH.replace('\\', '/') + '.opus')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'wb').write(opus)
    log.append('%s: 4U %+.1f dB -> GU %+.2f dB' % (PATH, db4[name], db4[name] + med))
    os.makedirs(os.path.dirname(STQR), exist_ok=True)
    snd_bgm.build_battle_stqr([(PATH, len(opus), ns, ls, le, ids[0], db4[name] + med)], log, STQR, 'em013_06')
    for l in log: print(l)


if __name__ == '__main__':
    main()
