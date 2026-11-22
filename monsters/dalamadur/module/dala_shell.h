/* dala_shell.h: Dalamadur's attack shells (goal D5) as GU uShellEnemy subclasses on the core's shell framework
 * (module/shell.h; until 2026-11-22 dala_shell.c held it). C = read in code, S = strong, G = guess.
 *
 * 4U shell types posted by the classes uEm024 (head, 0x76c700..0x776290) and uEm083 (tail, 0x89fab8..0x8a3160) and by
 * their shells (scan of every bl into the shell manager 0x660000..0x664000, C):
 *   head 0x76dda8 -> 0x66242c type 29 (meteor, dala_meteor.c)
 *   head 0x772714 (in 0x77250c) -> 0x661bec type 1 uShell001 kinds 24 / 25 / 88 / 89 (fireball, dala_shell001.c)
 *   head 0x7711f8 / 0x775e70 -> 0x6620c4 type 16 uShell016 subtypes 21 / 39 (mouth beam, dala_shell016.c)
 *   tail 0x8a064c (7.0) -> 0x661d18 type 5 uShell005 subtype 4 (tremor column, dala_shell005.c)
 *   uShell029 0xc7d540.. -> 0x663220 -> 0x661c5c type 3 uShell003 113 / 126 / 160 / 162 (meteor blast) and 0x6626e8
 *   type 38 uShell038 (meteor scale, dala_shell038.c); uShell001 impacts -> uShell003 114 / 161 or 0x661ea0 type 9
 *   uShell009 1 / 2, which posts uShell003 112 / 159 (dala_shell003.c).
 * The tail range's other posts (0x89e4b4..0x89f984) belong to uEm081 (its ctor at 0x89fa2c stores vtable
 * 0xe69e28, C). Multiplayer: no W+0x1d9 (net owner) test in either class range except 0x77543c (Shah effect
 * reset 0x7753f4, not a shell site) and none in the shell classes (C); 4U's shell manager 0x660e88 creates the
 * shell locally (0x660fe0 unit add, no net send, as dala_meteor.c found). GU replays each action on every machine,
 * so every machine posts its own shells, as 4U. */
#pragma once
#include <stdint.h>
#include "game.h"
#include "shell.h"

/* Dalamadur's shell family shell\em\em090_00_shell00\em090_00_00 (build_dalamadur_arc.py shell_family: a copy of
 * Kushala's family 00 with HDS / HTS from the 4U inline records). Def file ID = em090_00's extra 'shell00' (the
 * build asserts it); row id param+4 = 175 as Kushala's and Gogmazios' family. */
#define DALA_SHELL_FILE 0x107a6u
#define DALA_SHELL_ID   175u
extern const struct shell_family dala_shells;       /* dala_shell.c: the family above, log prefix "dalaport" */
#define DALA_SH_FIELDS  SHELL_FIELDS

/* HDS entries of the family (build_dalamadur_arc.py SHELL_HDS; 4U record in brackets; byte-identical 4U records
 * fold onto one entry, the build checks it) */
enum {
    DALA_HDS_METEOR = 0,     /* 0..5 = uShell029 records 0x102dff0 + 40 i; kinds 0..7 use u32 table 0x102e0e0 */
    DALA_HDS_S001_HI = 6,    /* uShell001 record 64 (kind 24; kind 89's record 82 is identical) */
    DALA_HDS_S001_LO = 7,    /* record 62 (kind 25; kind 88's 81 is identical) */
    DALA_HDS_S003_112 = 8,   /* uShell003 records = subtype: 112 (= 159) */
    DALA_HDS_S003_113 = 9,   /* 113 (= 160) */
    DALA_HDS_S003_114 = 10,  /* 114 (= 161) */
    DALA_HDS_S003_126 = 11,  /* 126 (= 162) */
    DALA_HDS_S016_14 = 12,   /* uShell016 record 14 (subtype 21; 39's record 34 is identical) */
    DALA_HDS_S016_18 = 13,   /* record 18 (21 from owner frame 380; 39's 35 is identical) */
    DALA_HDS_S005_4 = 14,    /* uShell005 record 4 */
};

/* ---- the shells (one file each) ---- */
/* dala_shell001.c: 4U 0x77250c(this, kind, lim, ang, flag) = the head's aim (joint 5 toward target slot 0, clamped)
 * + 0x773e00's spawn data + the post; and the fireball itself (uShell001 kinds 24 / 25 / 88 / 89) */
void dala_head_fireball(void *self, uint32_t kind, uint32_t lim, uint32_t ang, uint32_t flag);
void *dala_shell001_post(void *owner, uint32_t kind, const float *pos, uint32_t pitch, uint32_t yaw);
/* dala_shell003.c: 4U 0x663220 (uShell003 blast: subtypes 112..114 / 126 / 159..162) and 0x661ea0 (uShell009
 * burn sequence: subtypes 1 / 2) */
void *dala_shell003_post(void *owner, uint32_t subtype, const float *pos, uint32_t area, uint32_t group);
void *dala_shell009_post(void *owner, uint32_t subtype, const float *pos, uint32_t area, uint32_t group,
                         const uint32_t *angles);
/* dala_shell016.c: 4U 0x6620c4 with {joint 5, (0, -273, 751), x 0xe39, y 0}, subtype 21 / Shah 39, length 12000 */
void *dala_shell016_post(void *owner, uint32_t subtype, uint32_t joint, const float *off, uint32_t xang,
                         uint32_t yang, float length);
/* dala_shell005.c: 4U 0x661d18(mgr, owner, &pos, subtype, 0xffff, scale) (tail 7.0: subtype 4) */
void *dala_shell005_post(void *owner, uint32_t subtype, const float *pos, float scale);
/* dala_shell038.c: 4U 0x6626e8(mgr, owner, kind 0 / Shah 1, area, &pos, yaw, ground byte): the meteor scale and its
 * mining point (the ground byte = the kobj the meteor hit: not passed, see the file) */
void *dala_shell038_post(void *owner, uint32_t kind, const float *pos, uint32_t area, uint32_t yaw);
uint32_t dala_shell038_alive(void);   /* scales alive now (DALA_TEST_MINING: one at a time, as 4U's 7200-frame gap) */
