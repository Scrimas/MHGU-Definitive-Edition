"""build_em013_06_quest.py : G-rank Crimson Fatalis' three 4U quests for MHGU (notes/plan.md 5 and 10), appended to GU's
quest list by the core (module/quest.c quest_group_append; allocations.toml quests + quest_append).

  build_em013_06_quest.py [--hp-table N] [--out DIR] [--only ID]

Writes (default DIR = monsters/g_crimson_fatalis/romfs), per quest: the quest arc, loose questData / questLink and the
5 GMDs (tools/quest4u.py assemble / write).

His 4U quests (C): m11036 "Advanced: A Final Battle Cry" (loc/data quest arcs, guild G3 = star 10) and the events
m60249 "Beyond the Crimson Veil" and m60215 "A Feast for the Departed" (the maintainer's DLC extdata, tools/
extdata4u.py; star 10; m60215 added 2026-11-22 by the maintainer, Phase 1 had missed it): each a single slay on Ingle
Isle (4U stage 9), 35 min, area 1, no subquest, board icon '?' (+0xE8 = 0). Placement (the maintainer, 2026-11-22):
hub G4, the rank of GU's own Crimson Fatalis q11456 (GU's top rank, as 4U's G3 is 4U's).

Sources (C unless marked):
  GU template  q11456 for both (hub G4 slay of Crimson Fatalis 0x10d on stage 19, not urgent): stars / class bytes,
               board, start area, flags, +0x1A, questPlus, GMD unk word, supply box with its delivery groups (4U's two
               quests are multiplayer ones too, Tidal Najarala's rule) and the boss record's restore / byte 8 / size
               table / stamina.
  Money        4U's fee / reward (5800 / 57900, m60215 4900 / 48300), no subquest money; academy points and HRP = the 4U
               reward x the template's ratio, rounded to 10 (Dalamadur's G3 -> G4 rule, build_dalamadur_quest.py).
  Stat rows    the maintainer's ratio rule with GU's floor (2026-11-22): r = the quest's 4U em_nando_tbl value over the
               one of m60211 "Take the Black" (4U's only G3 Fatalis quest, event, 78 / 115 / 87; HP column 0, attack
               column 1), target = q11456's row value x r, the nearest GU row not below it and never below q11456's
               own row (r <= 1 keeps that row). The other row is q11456's.
  Boss record  the stand-in Crimson Fatalis (allocations.toml standin_id 0x10d), swapped to 0x60d at spawn by
               module/main.c; aura 0; size % from 4U (100). The objective names 0x60d (Monoblos' builder).
  Spawn        q11456's own setEmMain b_m19em013_00, unchanged (S): 4U em078's m60126 and the em117 quests spawn at
               the same 4U point (area 1, -3780 / 372 / 2200, rotation 0), and Capcom moved that point for GU's
               Crimson Fatalis (q11456: 226 / -23 / 2647, rotation 171): GU's mapping of 4U's point on its Ingle Isle.
               No small monsters (z_m00d_000), as q11456 and 4U.
  Spawn byte 3 (4U spawn record +0xB): m60249 1, m11036 / m60215 0 (asserted): the event quest's 4U behaviour
               (event shots, permanent rage, no hitzone switch), which the module keys on quests[1]
               (em013_06_state.c gcf_event_quest, notes/plan.md 2 and 9).
  4U quest     text (5 languages; chT / chS from lang/zh_*.toml), minutes, reward rows A / B.
  Rewards      rows A / B from 4U. Row A carries 4U's repel list (flag 4) as a condition-4 group after the slay
               group (quest4u.rem_4u: 4U and GU both draw it instead of the main list when the quest ends by repel,
               C; q11456's row A has one). Slots 3 / 4 = GU's empty row rem_000000 (Stygian Zinogre's rule, issue #8):
               q11456's rem_530074 (Triumph / Horns Coins, condition 3) and rem_230077 (condition 5: 3 more draws on
               a slay, GU 0x38236c, C; 4U has no such bonus) are its own quest's extras. No subquest row (GU's
               rem_000000, as q11456). Items (gu_item): his materials 4U 1589..1592 are GU's 1658..1661 under GU's
               names (C: q11456's rem_230077 is m11036's row A with those IDs, chance for chance), Strong Armor Sphere
               -> King Armor Sphere (Gogmazios' / Dalamadur's substitute, GU has none), the rest by English name; GU
               has no Conqueror's Seal G, Immenseness Ticket S or Crimson Fatalis Ticket (4U 1886, gear Phase 5b):
               left out, their chance to the row's most likely item (quest4u.rem_4u).
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.dirname(HERE)                         # monsters/g_crimson_fatalis
ROOT = os.path.dirname(os.path.dirname(MON))
sys.path.insert(0, os.path.join(ROOT, 'tools'))     # core converters + paths.py
import paths                        # noqa: E402
sys.path.insert(0, paths.GU_PY)
import alloc, arcpack, extdata4u, gear4u, gmd, quest4u   # noqa: E402
from items4u import EXE, EXE_BASE, text_4u   # noqa: E402
from quest4u import (arc_files, text4u, ref, T_SET, T_ESL, T_REM, T_SUPP, T_PLUS,  # noqa: E402
                     REWARD_ROWS_4U, SUB_ROW_4U, STATS_4U, NANDO_4U)
from romfs import RomFS             # noqa: E402

ALLOC = alloc.monster('g_crimson_fatalis')
EM_ID, BOSS_ID = ALLOC['em_id'], ALLOC['standin_id']   # 0x60d; Crimson Fatalis 0x10d, swapped at spawn
EM_4U, EM_4U_REF = 117, 77                               # G-rank Crimson Fatalis; Fatalis (the ratio's reference)
Q4U_DIR = os.path.join(ROOT, 'dump/romfs/loc/data')
STAGE_4U, STAGE = 9, 19             # Ingle Isle
TPL = 11456                         # GU's Crimson Fatalis, hub G4: template, stat base, box, spawn
REF = 60211                         # 4U "Take the Black", G3 Fatalis: the ratio's reference
SLAY_4U = 0x101                     # 4U objective type of all three (no capture); GU's q11456 uses type 1
ICON = alloc.board_byte(alloc.ICON_PAGE2)                # 4U's '?' (module/icons.c), Dalamadur's builder
REM_EMPTY = struct.pack('<fI', 1.0, 1) + bytes(176)     # GU's rem_000000 (184 B, no group; C: q10706)
URGENT = 0x1                        # questData +0x16F bit 0 = an urgent (key) quest (Monoblos' builder)
OTHER_4U_GU = {1589: 1658, 1590: 1659, 1591: 1660, 1592: 1661,   # Flamescale / shell / horn / wing (see above)
               1643: 351}           # Strong Armor Sphere -> King Armor Sphere
NO_GU_4U = {1721, 1724, 1886}       # Conqueror's Seal G, Immenseness Ticket S, Crimson Fatalis Ticket
# k = index in allocations.toml quests, num = 4U quest, event = its 4U spawn byte 3
QUESTS = [dict(k=0, num=11036, event=0), dict(k=1, num=60249, event=1), dict(k=2, num=60215, event=0)]


def quest_4u(num):
    """a 4U quest by number: the ROM's (loc/data/quest00.arc / quest01.arc), else the maintainer's DLC extdata"""
    for arc in ('quest00.arc', 'quest01.arc'):
        f = arc_files(open(os.path.join(Q4U_DIR, arc), 'rb').read())
        if 'loc\\quest\\m%05d' % num in f:
            q = f['loc\\quest\\m%05d' % num][1]
            break
    else:
        q = extdata4u.quest(num)
    assert q[4:8] == b'v005' and struct.unpack_from('<H', q, 0xC0)[0] == num, num
    return q


def spawns_4u(q):
    """4U boss spawn records of the first list, 0x28 B each closed by em 0xffffffff: [(em, area, (x, y, z, rot), +0xB
    spawn byte 3, +0xF)]"""
    rec = struct.unpack_from('<I', q, struct.unpack_from('<I', q, 0x28)[0])[0]
    out = []
    while struct.unpack_from('<I', q, rec)[0] != 0xFFFFFFFF:
        out.append((struct.unpack_from('<I', q, rec)[0], q[rec + 9], struct.unpack_from('<4f', q, rec + 0x10),
                    q[rec + 0xB], q[rec + 0xF]))
        rec += 0x28
    return out


def stat_rows(R, q4, qr, b):
    """(HP, attack, other) rows and the trace (r HP, r attack, rows' values): q4 / qr = the 4U quest / m60211, b = the
    GU base boss record"""
    res = {p: d for p, t, d in arcpack.read(R.read('/nativeNX/loc/arc/resident.arc'))[1]}
    gu = res['enemy\\resident\\em_nando_tbl']
    rows = [struct.unpack_from('<8f', gu, 16 + 32 * k) for k in range((len(gu) - 16) // 32)]
    exe = open(EXE, 'rb').read()
    r4 = lambda row: struct.unpack_from('<8f', exe, NANDO_4U - EXE_BASE + 32 * row)
    s, z = q4[STATS_4U + 3:STATS_4U + 6], qr[STATS_4U + 3:STATS_4U + 6]
    r_hp, r_atk = r4(s[0])[0] / r4(z[0])[0], r4(s[1])[1] / r4(z[1])[1]

    def pick(col, base_row, r):
        if r <= 1: return base_row          # GU's floor
        t = rows[base_row][col] * r         # 1e-3: a table value equal to the target is not below it
        return min((abs(rows[k][col] - t), k) for k in range(len(rows)) if rows[k][col] >= t - 1e-3)[1]
    hp, atk = pick(0, b[4], r_hp), pick(1, b[5], r_atk)
    return (hp, atk, b[6]), (r_hp, r_atk, rows[hp][0], rows[atk][1])


def gu_items(R):
    """gu_item(4U id) -> GU id: OTHER_4U_GU, else by English name (the first id of the name); None for NO_GU_4U (any
    other 4U item without a GU name stops the build)"""
    gu = gmd.gmd_strings(gear4u.gu_arc(R.read('/nativeNX/eng/arc/resident_eng.arc'))['eng\\table\\itemData_eng'])
    by_name = {}
    for i in range(0, len(gu), 2):
        by_name.setdefault(gu[i], i // 2)
    names4 = text_4u('eng')[0]

    def gu_item(k):
        if k in OTHER_4U_GU: return OTHER_4U_GU[k]
        if k in NO_GU_4U:
            print('reward: 4U %d %s has no GU item (left out)' % (k, names4[k]))
            return None
        assert names4[k] in by_name, ('4U item without a GU item', k, names4[k])
        return by_name[names4[k]]
    return gu_item


def build(R, gu_item, out, spec, hp_table=None):
    k, num = spec['k'], spec['num']
    qid = ALLOC['quests'][k]
    sid, m4 = '%07d' % qid, 'm%05d' % num
    q4, qr = quest_4u(num), quest_4u(REF)
    sp, spr = spawns_4u(q4), spawns_4u(qr)
    assert [s[0] for s in sp] == [EM_4U] and [s[0] for s in spr] == [EM_4U_REF], (m4, sp, spr)
    assert sp[0][1] == 1 and sp[0][3] == spec['event'] and not sp[0][4], (m4, 'spawn area / byte 3 / +0xF', sp[0])
    assert q4[0xC4] == STAGE_4U and q4[0xC2] == qr[0xC2] == 10, (m4, 'not a star-10 Ingle Isle quest')
    assert q4[0xCB] == 1 and struct.unpack_from('<IHH', q4, 0xCC) == (SLAY_4U, EM_4U, 1), (m4, 'objective')
    assert struct.unpack_from('<IHH', q4, 0xDC) == (0, 0, 0) and not struct.unpack_from('<I', q4, SUB_ROW_4U)[0], \
        (m4, 'the 4U quest has a subquest')
    assert struct.unpack_from('<H', q4, 0xE8)[0] == 0, (m4, "4U board icon is not '?'")
    tpl = arc_files(R.read('/nativeNX/loc/arc/quest/q%07d.arc' % TPL))

    # --- questData: the template's (rank, board, start area, flags, box groups), then 4U's values
    qd = bytearray(tpl['loc\\quest\\questData\\questData_%07d' % TPL][1])
    assert len(qd) == quest4u.QD_SIZE and qd[0x14] == STAGE and qd[0x1D] == 0, (TPL, 'not on Ingle Isle / clear rule')
    assert qd[0x1F:0x24] == struct.pack('<BHH', 1, BOSS_ID, 1) and qd[0x29:0x2E] == bytes(5), (TPL, 'not a single '
                                                                                                    'slay, no subquest')
    assert not struct.unpack_from('<H', qd, 0x16F)[0] & URGENT, (TPL, 'template is an urgent quest')
    t_fee, _, t_reward, _, t_acad, _, _, t_hrp, _ = struct.unpack_from('<9I', qd, 0x31)
    struct.pack_into('<I', qd, 0x0C, qid)
    qd[0x16] = struct.unpack_from('<I', q4, 0xB4)[0]       # minutes (4U)
    struct.pack_into('<BHH', qd, 0x1F, 1, EM_ID, 1)
    fee, reward, _ = struct.unpack_from('<III', q4, 0xA4)
    r10 = lambda v: int(round(v, -1))
    acad, hrp = r10(reward * t_acad / t_reward), r10(reward * t_hrp / t_reward)
    struct.pack_into('<9I', qd, 0x31, fee, 0, reward, 0, acad, 0, 0, hrp, 0)

    # boss record: the stand-in with the computed rows, the template's other bytes
    b = struct.unpack_from('<HBBBBBBBHBB', qd, 0x64)
    assert b[0] == BOSS_ID and not any(qd[0x64 + 13:0x64 + 65]), (TPL, 'not one Crimson Fatalis record')
    (hp, atk, other), trace = stat_rows(R, q4, qr, b)
    if hp_table is not None: hp = hp_table
    size = struct.unpack_from('<H', q4, STATS_4U)[0]
    struct.pack_into('<HBBBBBBBHBB', qd, 0x64, BOSS_ID, 0, 0, b[3], hp, atk, other, b[7], size, b[9], b[10])
    qd[0xD6:0xDB] = bytes([ICON, 0, 0, 0, 0])
    for i, lang in enumerate(quest4u.QLANGS):
        qd[0xDF + 20 * i:0xDF + 20 * (i + 1)] = ref(quest4u.T_GMD, '%s_%s' % (sid, lang))

    # --- questLink + resources: the template's spawn, small monsters, box and questPlus; 4U's reward rows
    tlink = tpl['loc\\quest\\questLink\\questLink_%07d' % TPL][1]
    # 15 refs: 5 setEmMain, 3 emSetList, 5 rem (A, B, slot 3, slot 4, subquest), supp, questPlus
    tnames = [tlink[8 + 20 * i + 4:8 + 20 * (i + 1)].split(b'\0')[0].decode() for i in range(15)]
    assert tnames[1:5] == ['b_m00em000_00'] * 4 and tnames[12] == 'rem_000000', (TPL, tnames)
    res = [('quest\\boss\\setEmMain\\' + n, T_SET, tpl['quest\\boss\\setEmMain\\' + n][1])
           for n in sorted(set(tnames[:5]))]
    res += [('quest\\zako\\emSetList\\' + n, T_ESL, tpl['quest\\zako\\emSetList\\' + n][1])
            for n in sorted(set(tnames[5:8]))]
    rows = {'rem_%sa' % m4: REWARD_ROWS_4U[0], 'rem_%sb' % m4: REWARD_ROWS_4U[1]}
    rems = {name: quest4u.rem_4u(q4, row, gu_item) for name, row in rows.items()}
    assert not set(rems) & set(tnames), 'reward row names taken by the template'
    assert tpl['quest\\rem\\rem_000000'][1] == REM_EMPTY, "GU's rem_000000 is not the empty row"
    rems['rem_000000'] = REM_EMPTY
    rem = ['rem_%sa' % m4, 'rem_%sb' % m4, 'rem_000000', 'rem_000000', 'rem_000000']
    res += [('quest\\rem\\' + r, T_REM, rems[r]) for r in sorted(set(rem))]
    res.append(('quest\\supp\\supp_' + sid, T_SUPP, tpl['quest\\supp\\' + tnames[13]][1]))
    plus = tnames[14]
    res.append(('quest\\plus\\questPlus_' + plus, T_PLUS, tpl['quest\\plus\\questPlus_' + plus][1]))
    link = tlink[:8] + b''.join(ref(T_SET, n) for n in tnames[:5]) + b''.join(ref(T_ESL, n) for n in tnames[5:8])
    link += b''.join(ref(T_REM, r) for r in rem) + ref(T_SUPP, 'supp_' + sid) + ref(T_PLUS, plus)
    assert len(link) == 308

    # --- text (4U, 5 languages + chT / chS) + arc layout + files (tools/quest4u.py)
    gmds = quest4u.quest_gmds(tpl, TPL, sid, text4u(q4))
    qd = bytes(qd)
    quest4u.write(out, quest4u.assemble(res, link, gmds, qd, sid))
    print('quest %d = 4U %s (tpl q%d): star %d class %d stage %d, %d min, fee %d reward %d (tpl %d / %d) acad %d '
          'hrp %d, objective %s; boss %#x rows %d/%d/%d size %d (r HP %.3f atk %.3f -> %.2f / %.2f; q%d %d/%d/%d); '
          'spawn byte 3 = %d' % (qid, m4, TPL, qd[0x12], qd[0x13], qd[0x14], qd[0x16], fee, reward, t_fee, t_reward,
                                 acad, hrp, qd[0x1F:0x24].hex(' '), BOSS_ID, hp, atk, other, size, *trace, TPL, b[4],
                                 b[5], b[6], sp[0][3]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--hp-table', type=int, help='boss vital (HP) table byte instead of the computed one (shorter '
                                                 'tests)')
    ap.add_argument('--out', default=os.path.join(MON, 'romfs'))
    ap.add_argument('--only', type=int, help='build only this GU quest ID')
    a = ap.parse_args()
    R = RomFS(paths.GU_ROMFS)
    gu_item = gu_items(R)
    for spec in QUESTS:
        if a.only in (None, ALLOC['quests'][spec['k']]):
            build(R, gu_item, a.out, spec, a.hp_table)


if __name__ == '__main__':
    main()
