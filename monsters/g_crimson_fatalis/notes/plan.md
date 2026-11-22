# G-rank Crimson Fatalis (4U em117): port plan

C = confirmed in code or data, S = strong, G = guess. 4U = MH4U v1.1 EUR code.bin addresses, GU = MHGU 1.4 main offsets.
Phase 1 (static study) done 2026-11-22 on branch wip/g-crimson-fatalis; IDs in allocations.toml (g_crimson_fatalis).
W = the 4U enemy record [this+0xe28]; em117's state lives in it (this+0x8d88 holds the same pointer, C: the
constructor 0x89f12c and spawn setup 0x893cfc store [this+0xe28] there).

## 1. What it is

- 4U: em117, emName "Fatalis" like em077 (Fatalis), em078 (Crimson), em079 (White). One class, uEm077 (DTI 0x10b7a28,
  vtable 0xe69ca4), runs all four (C). Its arc em117.arc has its own model (enemy\em117\mod\em117 + 5 textures), sounds
  (snd_em117, call em117, em117_se_heatwave / _L / _R / _after, _prominence_se / _voice, _stepfire, _flyby,
  _meteorite_fall / _break / _break_2, _explosion_spark, vo_reverb), MEF em117_1, EFLs em117_200 / 202..205 and effect
  textures em117_001 / 003, theme bgm_em117.mca; it shares em077's motions (mot em077_0..3, camera e077_cam) and AI
  table (em077_cmd: the four arcs carry byte-identical copies), and em078's EFLs 002 / 006 / 007 / 008 / 016 (C).
- GU: ships the trio as em013 variants 0 / 1 / 2 (Fatalis, Crimson, White; arcs em013_00..02, class uEm013_00,
  vtable 0x17acaf4, shells uShellEm013_0V_00 / 01 / 02 / 51), G4 hub quests 11454 / 11456 / 11457 (C). GU's Crimson
  (em013_01) is 4U's em078: the same sound set, none of em117's files (C).
- GU's class keeps 4U's em117 tests as **variant 6** (C): slot 133 0xd8185c `cmp #6; cmpne #1` = 4U slot 51 0x89e29c /
  0x89e2a4 `cmp #78` / `cmp #117`; also 0xd84b24, 0xd84d20 (the 7/0-family handler), 0xd8db70 (slot 132), and GU's
  selector g0 s3 still sends variant 6 to selector 10 (section 3). GU never registers 0x60d and ships no em013_06 arc.
  Our ID: 0x60d, on GU's class (package.toml gu_class).
- Arena: Ingle Isle, 4U stage 9 = GU stage 19, GU's own (GU's Crimson q11456 is there): no map package (C).
- Size record: 4110.6 cm, no crowns (4U 0xf32008, as em077 / em078) (C).

## 2. 4U's em117 code (14 compares of W+0x1c0 with 117, 0x892b94..0x89e990) and GU's side

| 4U | role | em117 does | GU twin | GU kept? |
|---|---|---|---|---|
| 0x893cfc slot 39 | spawn setup | 0x89ed3c (White's setup), then rage materials: types 0x33 / 0x34 with an animation start at the end of "Angry_End" (glow off, W+0x17 = 0); its zone record (below) joins the stage list 0x684b00(*0xf32004, W+0x38); W+0x6d = 1, W+0x6e = 0, W+0x70 = cooldown (constructor too) | 0xd808f0 slot 118 (`cmp #2` only) | no (S) |
| 0x894050 slot 40 | state frame | spawn byte 3 == 1: 0x934508 every frame = W+0x538 = 1 (permanent rage, below); zone timer: W+0x38 != 0xff -> timerDown(W+0x60), at 0 -> 0xff | 0xd81a08 slot 119 (no variant read); 0x934508 = GU 0xbd100 (S) | no (S) |
| 0x89cc6c slot 48 | per frame | the **prominence** sequence and the **stepfire** (below) | 0xd80eec slot 130 (no variant 6 read) | no (S) |
| 0x89c1fc (slot 48 head) | zone visual | W+0x30 set: fades the object at W+0x2c (byte +0x57 by 4.25 x dt per frame) in while the W+0x34 timer (300) runs, then out, then clears its flags 0x400 / 0x800 | none | no (S) |
| 0x89de60 slot 50 | parts frame | when part 7's count reaches 2: parts of kind 52 (word +0x18 bits 22..29) get hit bits +0x14 (as the species' kind 50, but 228 << 14 once W+0x16 is set); rage glow: "Angry_Start" / "Angry_End" through 0x89e670 and 0x89e8a0 (Crimson em078 has a 6-step glow, White 2 steps) | 0xd8d8f8 slot 132: `cmp #6 -> 0xd8dc64`, parts of kind 50 / 1 with a material: "Angry_Start" when enraged (state +0x36 = 3), "Angry_End" when calm | the glow yes (C); the kind-52 bits no (S) |
| 0x89e25c slot 51 | AI_COND | param 1 (range): em 78 / 117 limits 900 / 1200 (rage) vs 2700 / 1800; param 2: W+0x70 > 0 (prominence cooling down); param 3: W+0x20 in {1, 3, 5} | 0xd817f0 slot 133 `cmp #6; cmpne #1` | yes (C) |
| 0x89c2f4 | hitzone / part switch x8 | enraged and spawn byte 3 != 1 -> 0x93415c(this, 0..7), else 0x936ea8 | 0xd815d0 (`variant - 1` test: Crimson / White) | no (S) |
| 0x89473c (7/0, 7/19, 7/59, 7/60) | attacks | Crimson's attack slots (em 78 or 117) | 0xd84aa0 / 0xd84a2c `cmp #6; cmpne #1` | yes (C) |
| 0x892b94 (cat 11/1) | reaction, motion 0x311 | em 78 / 117: while W+0x5f8 bit 0x40 (0x9306d0), clears this+0xd38 | GU 0xd8d454 (GU's 11/0, motion 0x311): no species branch, also not for GU's Crimson | no (C) |
| 0x899c30 (7/74..76) | heatwave shots | motions 0x23d / 0x23e / 0x23c; at motionCheck: uShell012 subtype 54 / 55 / 51 via 0x661f6c (event quest: 67 / 68 / 66); then 0x89e990 places the zone; end at isMotionEnd | GU cat 7 numbers 74..76 -> no-case thunk 0xca10c | no (C) |
| 0x89e990 | zone placement (em117 only) | if W+0x38 == 0xff: marker 0x75, area = W+0x14c, point = shot point + 3000 ahead (subtype 0) / left / right (1 / 2, yaw +-0x4000) rotated by the yaw, +0x54 yaw, +0x5c 1900 (ahead) / 900 (sides), +0x60 timer 300, +0x64 0 | none | no (C) |

**Prominence** (slot 48, C): W+0x6d is set to 1 by the constructor and the spawn setup and never cleared. While W+0x70
(f32 cooldown) > 0 it counts down by the frame delta (this+0xd58). At 0, the current motion picks a pattern type in
W+0x74 (0x205 -> 0, 0x206 -> 1, 0x216 -> 3, 0x217 / 0xb -> 4, 0x21a -> 5; 6, 7, 8, 9, 0xa, 0xe..0x10, 0x14, 0x15,
0x219, 0x223, 0x224, 0x227, 0x230 -> 2; others 0xff = none); at that motion's motionCheck(this, 0) it stores the
point (this+0x8d20), the yaw (this+0x40..), area (W+0x1d2), W+0x75 = 0, W+0x6e = 1 (running) and W+0x70 = 630. While
running, 0x89c448 posts eruption k = W+0x75 once 630 - W+0x70 >= 60 k: n = 3 columns (2 for type 5), row k / n,
column k % n; table 0xe0db0c (6 types x 3 {f32 distance, f32 yaw u16}: distances 1000 / 1500, yaws 0x2000 .. 0xe001)
-> offset (0, 0, distance + 1400 x row) turned by the stored yaw + the column yaw (0xaad5b0), scaled by 0x911cb4,
on the ground under it (0x2bad24); post uShell018 subtype 6 there (0x662160, flag byte 1). After 3n posts W+0x6e = 0.
A second table (0xe0db9c, 8 x 3) is copied but never read; the byte-3 compare before the divide is dead (C, asm).
- uShell018 (632 B, vtable 0xe6da6c, init 0xc72504, frame 0xc7277c) is a timed marker. Subtype 6: effect (87, 22) =
  em117_205 for 30 frames, no attack; at its end (flag byte 1) it posts uShell037 kind 8 (0x6626a4 -> event 37) at its
  point (C). Fatalis' other uShell018 posts are subtype 4 (em079_006, 60 frames -> uShell003 152 = em079_007, White's).
- uShell037 (672 B, vtable 0xe6e2bc, init 0xc836a8, frame 0xc83eb8) kinds 0..7 are 4U em009 / em010's gas and beams;
  **kind 8 = the eruption** (C): snaps to the ground (0x2b96e4, +-500), a ground effect (87, 19) = em117_202 at init
  and a scorch (the same) 16 frames later, rises (speeds 0x102f7c0: 1650 / 350), record 6 of 0x102f830 (window 15 + 60,
  power 10, attack type 31) on volumes 0x102f808, sound 216 (0x102f6a8), life 60. Never ported (no repo file names it).

**Stepfire** (slot 48, C): each newly set footstep bit of the motion (part codes 2000..2003 -> joints 40 / 50 / 90 /
80) gives em117 (only) this+0xca8 bit 4 (MEF b0 4) instead of the species' bit 3 (the dust), a uShell003 subtype 177 at
that joint (0x663220: default init path, no effect, window 0 + 20, power 20, type 1, volume 120) and sound 0xdc at the
joint (0x2fcc50). uShell003's default path is ported (monsters/dalamadur/module/dala_shell003.c).

The zone and the hunter (C): the stage list (mgr+0x30c, 6 slots; Dalamadur's Shah uses it too) is read by the heat tick
0xb2f73c at 0xb30050 through 0x687280: a record of the hunter's area with marker 0x75 is tested by 0x89ebdc: a segment
from point - R(0, 0, 3000 - r / 3) to point + R(0, 0, 3000) (R = the record's yaw) against the hunter (0x20d1a0),
the local player only (0xaf79a4). Inside: player +0x1f8 |= 0x1000, every 11 frames 0xb1ac40(player, -2, 0) (the heat
damage), and the zone visual above (W+0x30 = 1, W+0x34 = 300). Unlike Shah's branch there is no skill 218 / effect 47
test, so Heat Cancel / Cool Drinks don't protect (S). GU: Dalamadur already counts its zones as heat in GU's heat tick
through its hook dala_heat_zone (GU 0x6a160, monsters/dalamadur/module/dala_head25.c); a second user makes that site a
core dispatcher (porting guide).

**Heatwave shots** (uShell012 0x1027488 / 0x10278d8 / 0x10290b0 -> 0x1028958, C): subtypes 51 (ahead) and 54 / 55
(sides) fly with (87, 21) = em117_204 (mask 1 ahead, 2 sides), no impact effect; records 35 (ahead) / 37 (sides) differ
only in byte +0x19 (15 / 17, the volume). The event subtypes 66 / 67 / 68 use records 45 / 46 = 35 / 37 with byte +6
(attack type) 7 instead of 6. No other uEm077 code posts uShell012 (Fatalis' fireballs are uShell001, 0x661bec).

Spawn byte 3 (4U spawn record +0xB -> W+0x797e; GU keeps the Hyper flag there, rec+0x5cb6) (C): m11036 = 0,
m60249 = 1. So the event quest uses the event shot subtypes, never switches its parts on rage, and never calms down
once enraged (0x936664: when the rage timer W+0x52c runs out with W+0x538 set, it is reset to 1.0); return 4U's value
from code for 11499 (Gogmazios' way).

## 3. AI (C)

- em077_cmd's selector g0 s3 switches on the species (op 0x46): em 78 -> selector 6, em 79 -> 8 / 9, **em 117 -> 10**,
  else (em 77) 4 / 5 (op 0x20 = go to selector). GU's g0 s3 is the same on the variant (op 0x92): 1 -> 6, 2 -> 8 / 9,
  **6 -> 10**, else 4 / 5. Only selector 10 itself is GU's stub (`a6 ff`).
- GU's em013_00_cmdtbl (all three variants; 15 / 147 scripts against 4U's 12 / 125) replaced exactly 4U's selector
  g0 s10 and g1 s26, s27, s107, s113, s115, s118, s119 with that stub. g0 s10 calls s113 / s118 / s119 (the heatwave:
  AI_COND 0 case 1 -> 1/7, then conditions 0x15 / 0x40 and a side test, op 0x2e, pick 7/74, 7/75 or 7/76) among its
  shared scripts.
- s26 / s27 (7/25 7/26), s107 (3/11 3/17 7/20) and s115 (7/71 7/72) are reached by no script (no `14 nn` call) and no
  uEm077 code (its 26 / 27 / 107 immediates are attack indices, 0x914dfc = attack(this, slot, index)) (S): cut content
  in 4U for every form, not ported. em117's meteor sounds have no attack found yet that plays them (G: the cut s115).
- GU's cat 7 dispatch (0xd8bc74, 87 cases) sends 25..29, 31..33, 74..76 to the no-case thunk; 7/20, 7/71, 7/72 keep a
  handler (C). The port needs 7/74..76 only (0x899c30).
- Port: our arc's cmdtbl = GU's table with 4U's g0 s10, s113, s118 and s119 put back (GU ops where GU changed the
  language: area moves; tools/emc.py build, Tigerstripe's cmdtbl()).

## 4. Assets (C unless noted)

- Motions: GU's em013_00 banks hold every motion of 4U's em077 banks (plus 0x234): take GU's, no motion work.
- Model: em117's own (mod4u2gu, tex, MRL from GU em013_01's Capcom templates); rage materials 0x33 / 0x34 with
  "Angry_Start" / "Angry_End" animations, the names GU's variant-6 branch plays (CBMaterialConstant: Capcom's constant
  template, Desert Seltas' lesson).
- Effects: em117_200 / 202..205 + MEF em117_1 (efl4u2gu; its b0 = 4 records are the stepfire, b0gate extra() bit),
  em078's EFLs from GU's em013_01 conversions where GU has them.
- Shells (new GU uShellEnemy classes, as module/em089_shell*.c): uShell012 51 / 54 / 55 (+ 66..68) heatwave shots,
  uShell018 6 marker + uShell037 8 eruption, uShell003 177 stepfire (dala_shell003.c's default path). Hit entries from
  the 4U records above (the HDS rule, monsters/desert_seltas/tools/shots_seltas.py).
- Sounds: snd_em117 bank and call (snd4u2gu); theme bgm_em117.mca -> Opus + STQR (snd_bgm, BGM ID 0x904).
- Data: dtbase / dttune / bodydata / attackdata from 4U em117's emd / etd against GU em013_01's (dt_convert), area files
  for stage 19 from em013_01.

## 5. Content (decided 2026-11-22 unless open)

- Name "Crimson Fatalis (4U)" (the maintainer). No Hunter's Notes entry: GU has one Fatalis entry (120) for its three.
- Quests: m11036 "Advanced: A Final Battle Cry" (guild G3, fee 5800, reward 57900, 35 min, rows 71 / 115 / 85) -> 11498;
  event m60249 "Beyond the Crimson Veil" (G3, the same fee / reward, rows 78 / 119 / 87, Crimson Fatalis Ticket) ->
  11499; both hub G4 after GU's q11456. Stats: the maintainer's ratio rule with GU's floor: em117 over em077 at 4U
  G3 (event over event: m60249 / m60211 78 / 115 / 87), applied to q11456's rows 100 / 115 / 98, never below them.
- Materials: 4U 1589..1593 (Fatalis Flamescale, Flameshell, Flamehorn, Flamewing, Devileye+) are GU's 1658..1662
  (Crimson Fatalis Scale, Shell, Horn, Wing, Fatalis Devileye+): the same text, renamed (C).
- Carves (C, 4U G rank): 3 points, all Flamescale 30 / Flameshell 62 / Flamehorn 8 %. No shiny drops (as em077).
  Breaks: 4 groups, Flamehorn 100 %, Devileye+ 100 %, Flamewing 100 %, Flameshell 70 / Flamescale 30 % (em077's
  layout; GU part conditions to match in Phase 4).
- Quest rewards (C): m11036 row A Flamescale 22 / Flameshell 35 / Flamewing 12 / Flamehorn 18 / Devileye+ 10 /
  Purecrystal x2 3 %; row B Conqueror's Seal G, Lrg ElderDragon Bone x2, Elder Dragon Blood x2, spheres, charms,
  Adamant / Sovereign Orb. m60249 row A Crimson Fatalis Ticket 5 % + the materials; row B (flags 0x8003) Immenseness
  Ticket S, spheres, charms, orbs. No subquest rows. 4U items without a GU item are dropped by quest4u.rem_4u (the
  ticket depends on the gear decision).
- Gear (open, Phase 5b): 4U's Wroth set (Blademaster / Gunner) and 4U's GX Fatalis Crimson (4U ticket 1886, which GU
  lacks: GU's "EX C.Fatalis Ticket" is another item) are not in GU; GU has its own Fatalis Crimson, XR and GX sets.
  Weapons: GU has 6 of em117's by name (Destiny's Arm, True Ruiner Sword / Lance / Bane / Reaver, Twinbane Blades);
  8 it lacks: Flame Fatalis Blade, Fatalis Fotia, Hellruin Gunlance, Fatalis Iregard, Fatalis Menace Soul, Hellruin
  Glaive, Dith Valor, Red Heaven Ruiner.

## 6. Left for the build phases (small, read when the code is written)

1. What the W+0x2c object is (G: a heat-haze overlay; set up in slot 39) and whether GU has one.
2. this+0xd38, cleared in 11/1 (GU dropped it for its own Crimson too): what it holds before porting it.
3. The kind-52 part bits of slot 50 against em117's part rows (emdata4u.part_rows) and GU's kinds (GU tests 50 / 1).
4. The GU items for quest row B (Conqueror's Seal G, Immenseness Ticket S, Purecrystal, ...) at the quest build.
5. Whether GU's slot-132 variant-6 branch (0xd8dc64) plays "Angry_Start" / "Angry_End" on every material or only on
   types 50 / 1: em117's three additive rage layers (m51 / m52) carry the animations too (Phase 2 MRL).

## 7. Phase 2: assets (done 2026-11-22, static checks only; `python3 monsters/g_crimson_fatalis/build.py`)

Steps: dt (tools/dt_convert.py of em078 and em117 on donor em013_01), bgm (tools/bgm_em013_06.py), arc
(tools/build_em013_06_arc.py), pack. Arc em013_06.arc: 600 entries, 19.0 MB; own file IDs 0x10a80..0x10a91 (16 manifest
fields + extras bgm_stqr 0x10a90, shell01 0x10a91). The builder's docstring and asserts hold the rules; the facts:
- Shared with em078 (C, asserted): the 30 files em117.arc ships under em077 / em078 paths are byte-identical to
  em078.arc's; attackdata / hitsize / bodydata equal. So GU em013_01's files stay for all of them.
- Data (C): dtbase = both conversions = GU's (kept). dttune: the two conversions differ only at +0x38 (HP base, etd word
  4: 8000 -> 8500); GU's file = the em078 conversion + 13 retuned bytes elsewhere; ours = GU's + that word.
- Model: 8 materials (GU's 5 by the same names + 3 additive rage layers m51 / m52, template 'light' as Stygian's
  IAFilter2 lights); all 7 non-eye materials carry 4U's "Angry_Start" / "Angry_End" (name hashes checked), converted.
  Mesh groups = GU em013_01's (asserted), so GU's parts states (XFS) stay as they are. Normal maps (S): em117's
  NM_MIRRORs are half the albedo's height and cover its whole UV range (the wing's NM alpha correlates 0.43 with the
  albedo squashed 2x, 0.09 / 0.13 with either half); the specular mask (+A) = their alpha, rows doubled. GU's own
  Crimson textures are Capcom's HD repaint (no correlation with 4U's): no Capcom rule to copy.
- Sound: 4U call em117 + bank snd_em117 (snd4u2gu), common-bank requests from GU em013_01.
- AI: GU em013_00's table + 4U g0 s10, g1 s113 s118 s119 (asserted: no 4U-only op, every called script equal in both
  tables); natives 1/7 1/12 2/1 7/74 7/75 7/76.
- Carves: s4 = 4U G table (Flamescale 30 / Flameshell 62 / Flamehorn 8 -> GU 1658 / 1659 / 1660: the 4U descriptions
  equal GU's, C), s0..s3 filler.
- Effects (the maintainer's choice, 2026-11-22: GU's look + em117's own): PEL u = GU em013_01u + em117_1's 7 records
  (list 1) + 5 code records 4100..4104 for the new shells (list 2). PSLs = GU's with (a) the foot dust (PEL c 0..3,
  cm202_020) out only where the motion's 4U records on that foot are all MEF b0 3 (4U 0x89d600 never sets bit 3 for
  em 117; GU dust standing for 4U's ungated records 10..26, or with no 4U record, stays), (b) em117_1's stepfire
  2000..2003 (b0 4 = the rising edge of their own slots for em 117, so no gate) and heatwave casts 2004..2006 (bank 2
  motions 60..62) in at 4U's frames, 23 motions. Area colour: 4U Ingle Isle m09a01 soil.
- BGM: 4U bgm_em117.mca (one looping stream, 4U 0.0 dB -> GU -1.48 dB by the anchors), own STQR (sequence 0x904).
- Shell family em013_06_shell01 (GU em013_01_shell01 renamed, def PEL -> em013_06u) with 6 HDS / HTS entries from 4U by
  the em089 rule: heatwave 35 / 37 (event 45 / 46: attack type 7 instead of 6), volumes 15 / 17 (bone 1001, r1400 /
  r700); eruption uShell037 record 6 (window 15 + 60, power 10, type 31, volume 4: bone 1001, r150: a capsule from the
  ground point to the rising shell); stepfire uShell003 177 (window 0 + 20, power 20, volume 120: bone 255, r100).
  HTS +4: 4U's kept (Capcom set it per volume, no rule).

New in Phase 2 for the module (C):
- GU's slot 86 (0xd8e32c) preloads the shell families per variant (0 -> rows 130..133, 1 -> 134..137, 2 -> 138..142)
  and returns for any other: variant 6 would have none. And four shot sites switch on 0 / 1 / 2 with no case for 6
  (0xd831c8 in 0xd83144, 0xd851c8, 0xd89328, 0xd89848), as does slot 79 (0xd8e09c / 0xd8e100: flags). 4U has no species
  test at their twins (its fireball post 0x89e788 tests em 79 only: em 77 / 78 / 117 post the same uShell001 kinds), so
  variant 6 takes variant 1's branch there (module alias hooks).
- BGM: the core's bgm_select matches em types (u8: 13 = every Fatalis); our registration needs the full ID 0x60d.
