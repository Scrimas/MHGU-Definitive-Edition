"""hagi_em013_06.py : G-rank Crimson Fatalis carve tables from 4U for the em013_06 arc (manifest fields 46-50 =
enemy\\hagi\\hagi_s0..s4_em013_06, tools/build_em013_06_arc.py). Format and 4U tables: tools/hagi4u.py.

  hagi_em013_06.py       print the tables

4U em 117 is G rank only (low and high null, C): its three carve points share one record (body), and it has no shiny
drops (shiny base 0xffff, notes/plan.md 5). Layout = GU em013_01's s4 (C, 2026-11-22: only the body table, every
index byte ff). s4 = G, s0..s3 = GU's filler.
Its materials are GU's own (C: the 4U descriptions equal GU's, CRLF line breaks; GU renamed them "Crimson Fatalis
...").
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core tools
import hagi4u

EM_4U = 117
POINTS = 3
# 4U item -> GU item: Fatalis Flamescale / Flameshell / Flamehorn / Flamewing / Devileye+ = GU Crimson Fatalis Scale /
# Shell / Horn / Wing, Fatalis Devileye+ (checked by name of the description in build_em013_06_arc.py)
ITEMS_4U_GU = {1589: 1658, 1590: 1659, 1591: 1660, 1592: 1661, 1593: 1662}


def files():
    """{manifest field: data} for fields 46..50 (hagi s0..s4)"""
    exe = hagi4u.exe()
    recs = {hagi4u.carve_record_4u(exe, EM_4U, p) for p in range(POINTS)}
    assert len(recs) == 1, '4U em117 carve points no longer share one record'
    low, high, g, _ = hagi4u.record_4u(exe, recs.pop())
    assert low == 0 and high == 0 and g, 'em117 is no longer G rank only'
    body = [(n, c, ITEMS_4U_GU[item]) for n, c, item in hagi4u.table_4u(exe, g)]
    filler = hagi4u.filler()
    return {46: filler, 47: filler, 48: filler, 49: filler, 50: hagi4u.hagi([body], {})}


if __name__ == '__main__':
    hagi4u.show(files())
