/* em013_06_shell.h: G-rank Crimson Fatalis' own 4U shells (4U em117) as GU uShellEnemy subclasses on the core shell
 * framework (module/shell.h). Literal translations of the 4U classes; the 4U facts per class are in each file
 * (C = read in code, S = strong, G = guess), from the spec of 2026-11-22 (4U v1.1 addresses):
 *   em013_06_shell018.c  uShell018 subtype 6: the prominence marker (posted by 4U 0x89c448, slot 48)
 *   em013_06_shell037.c  uShell037 kind 8: the eruption it posts at its end
 *   em013_06_shell012.c  uShell012 51 / 54 / 55 (event 66 / 67 / 68): the heatwave shots (4U 0x899c30, 7/74..76)
 *   em013_06_shell003.c  uShell003 177: the stepfire hit at a footstep (4U 0x89d940, slot 48)
 * Their posters (the behaviour hooks) come with Phase 4. Multiplayer: no net test in 4U's posters or classes; GU
 * replays the actions on every machine, so every machine posts its own shells, as Dalamadur's. */
#pragma once
#include <stdint.h>
#include "game.h"
#include "shell.h"
#include "efx.h"

/* the shell family shell\em\em013_06_shell01\em013_06_01 (build_em013_06_arc.py shell_family: GU em013_01_shell01
 * renamed, HDS / HTS from the 4U records); def file ID = the arc's extra 'shell01' (the build asserts it); row 135 =
 * GU's em013_01_shell01, param class EmBase01 (DTI 0x188cb88, the core request's) */
#define GCF_SHELL_FILE 0x10a91u
#define GCF_SHELL_ROW  135u
/* GU Crimson's fireball families 0x86 / 0x87 (em013_01_shell00 / 01) on our PEL, clods hidden (build_em013_06_arc.py
 * CLOD_DEFS; extras 'shell10' / 'shell11', the build asserts them), swapped in by em013_06_alias.c */
#define GCF_CLOD_FILE_10 0x10a92u
#define GCF_CLOD_FILE_11 0x10a93u
extern const struct shell_family gcf_shells;       /* em013_06_shell003.c; log prefix "gcfport" */

/* HDS entries (build_em013_06_arc.py SHELL_HDS, same order) */
enum {
    GCF_HDS_HEAT = 0,          /* uShell012 record 35 (51): capsule r1400, power 20, type 6 */
    GCF_HDS_HEAT_SIDE = 1,     /* record 37 (54 / 55): capsule r700 */
    GCF_HDS_HEAT_EV = 2,       /* record 45 (66): as 35, type 7 */
    GCF_HDS_HEAT_SIDE_EV = 3,  /* record 46 (67 / 68): as 37, type 7 */
    GCF_HDS_ERUPT = 4,         /* uShell037 record 6 (kind 8): window 15 + 60, power 10, type 31, sphere r150 */
    GCF_HDS_STEP = 5,          /* uShell003 177: window 0 + 20, power 20, type 1, sphere r100 on bone 255 */
};

/* PEL u list-2 records (build_em013_06_arc.py CODE_FX) */
enum {
    GCF_EFX_MARKER = 4100,     /* em117_205, all elements, world point (the marker) */
    GCF_EFX_ERUPT = 4101,      /* em117_202 element 0, world point (the eruption's start) */
    GCF_EFX_SCORCH = 4102,     /* em117_202 element 1, world point (its scorch) */
    GCF_EFX_HEAT = 4103,       /* em117_204 element 0 on the shell (51 / 66) */
    GCF_EFX_HEAT_SIDE = 4104,  /* em117_204 element 1 on the shell (54 / 55 / 67 / 68) */
};

/* 4U 0x662160(mgr, owner, 6, &pos, &angles, 0xffff, flag 1) from the prominence: the marker; at its end it posts the
 * eruption (4U 0x6626a4(mgr, owner, 8, &pos, &angles, 0xffff, 0, 0)) */
void *gcf_marker_post(void *owner, const float *pos, const uint32_t *angles);
void *gcf_eruption_post(void *owner, const float *pos, const uint32_t *angles);
/* 4U 0x661f6c(mgr, owner, subtype, &offset, &velocity, &acceleration, 0xffff) from 7/74..76 */
void *gcf_heatwave_post(void *owner, uint32_t subtype, const float *off, const float *vel, const float *acc);
/* 4U 0x663220(mgr, owner, 177, &pos, area, 0xffff) at a footstep joint */
void *gcf_stepfire_post(void *owner, const float *pos, uint32_t area);

/* ---- GU calls the four classes share ---- */
typedef uint32_t (*gcf_map_segment_t)(void *mgr, const float *from, const float *to, uint32_t area, float *out,
                                      void *info, uint32_t mask, uint32_t flags);
#define gcfMapSegment        FN(gcf_map_segment_t, 0x1838fc)   /* = 4U 0x2b96e4 */
typedef uint32_t (*gcf_shell_flags_t)(void *self);
#define gcfColFlags          FN(gcf_shell_flags_t, 0x4a2a8c)   /* = 4U 0x9aad8c */
typedef void (*gcf_shell_fn_t)(void *self);
#define gcfShellMove         FN(gcf_shell_fn_t, 0x4a2304)      /* base slot 9: owner gone -> kill [4U state 3] */
#define gcfShellKill         FN(gcf_shell_fn_t, 0x4a247c)      /* base slot 16 */
typedef int (*gcf_shell_setup_t)(void *self, void *param);
#define gcfShellSetup        FN(gcf_shell_setup_t, 0x43b4bc)   /* uShellEnemy slot 79 */
#define GCF_COL_MGR          (*(void **)MAIN(0x21270e0))
#define GCF_SLOT_KILL        16
#define GCF_EN_AREA          0x1054   /* u8 unit area [4U W+0x14c] */
#define GCF_REC_POS          0x40     /* float x, y, z owner position [4U W+0x198] */
/* attack slot 0 fields beside shell.h's: the start delay [4U slot +0x54 = shell +0x1bc] (S: GU's slot layout is 4U's
 * + 8 there, as ATK_TIME 0x60 = 4U +0x58) */
#define GCF_ATK_DELAY        0x5c

#define GCF_VEC(p, off) (&FIELD(float, p, off))

static inline float gcf_ang_rad(uint32_t a) { return (float)(a & 0xffff) * (6.28318531f / 65536.0f); }
static inline uint32_t gcf_rad_ang(float r) { return (uint32_t)(int32_t)(r * (65536.0f / 6.28318531f)) & 0xffff; }
static inline float gcf_sqrt(float x)
{
    float r;
    __asm__("vsqrt.f32 %0, %1" : "=t"(r) : "t"(x));
    return r;
}
/* 4U 0xaad5b0(&v, a): x' = c x + s z, z' = c z - s x (c, s of the u16 angle) */
static inline void gcf_rot_y(float *v, uint32_t a)
{
    float s = sinf_gu(gcf_ang_rad(a)), c = cosf_gu(gcf_ang_rad(a)), x = c * v[0] + s * v[2], z = c * v[2] - s * v[0];
    v[0] = x; v[2] = z;
}
