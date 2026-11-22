/* em013_06.h: G-rank Crimson Fatalis' behaviour on GU's uEm013_00 (variant 6): the 4U em117 parts GU's class lacks,
 * from the 4U spec of 2026-11-22 (notes/plan.md 9; C = read in code, S = strong, G = guess). 4U W = [this+0xe28];
 * GU keeps em117's state nowhere, so ours lives in struct gcf (em013_06_state.c), one per unit and quest.
 *   em013_06_state.c   spawn setup (4U slot 39), state frame (slot 40), the m51 / m52 rage layers, the theme
 *   em013_06_frame.c   slot 48's prominence and stepfire, the hitzone switch
 *   em013_06_moves.c   7/74..76 (the heatwave) and the zone placement
 *   em013_06_zone.c    the zone against the local hunter, the heat haze
 * Multiplayer: no net test in any of these 4U paths; GU replays actions on every machine, so each machine runs them
 * for its own copy of the monster (as 4U). */
#pragma once
#include <stdint.h>
#include "game.h"
#include "util.h"
#include "alloc.h"
#include "em013_06_shell.h"

#define GCF_BGM_STQR 0x10a90u      /* our STQR = the arc's extra 'bgm_stqr' (build_em013_06_arc.py asserts it) */

#define GCF_REC(self)    FIELD(uint8_t *, self, EN_RECORD)
#define GCF_EN_WORK      0xcac0    /* uEm013_00 work block pointer: +0x36 the rage glow state (0 calm, 3 enraged) */
#define GCF_EN_FLOOR     0x1065    /* u8 floor id of the unit [4U W+0x5f5] (S: both feed the area list test) */
#define GCF_EN_MDT       0x13b8    /* f32 motion delta [4U this+0xd58 = layer-0 speed x this+20] (C, Monoblos'
                                      em007_01_mv_i.c: GU's yaw update and spinWindow read it) */

/* the 4U em117 record fields we keep (4U offsets in brackets) */
struct gcf_zone {                  /* the zone record [W+0x38 .. W+0x64] */
    uint8_t marker;                /* 0xff off, 117 on [W+0x38] */
    uint8_t area;                  /* [W+0x39] */
    float pt[3];                   /* centre [W+0x40] */
    uint32_t yaw;                  /* [W+0x54] */
    float r, timer;                /* radius [W+0x5c], frames left [W+0x60] */
};
struct gcf {
    void *self;
    uint32_t quest;
    uint8_t prom_on;               /* [W+0x6d] 1 from the spawn setup, never cleared */
    uint8_t prom_run;              /* [W+0x6e] a sequence is posting */
    uint8_t type;                  /* [W+0x74] pattern 0..5, 0xff none */
    uint8_t k;                     /* [W+0x75] posts done */
    float cool;                    /* [W+0x70] sequence clock / cooldown, counts down by mdt */
    uint32_t ang[3];               /* [W+0x78] angles at the trigger (yaw [W+0x7c]) */
    float pos[3];                  /* [W+0x88] position at the trigger */
    uint8_t glow;                  /* GU's glow state last seen (port: the m51 / m52 layers follow it) */
    struct gcf_zone zone;
    void *haze;                    /* the heat haze filter [W+0x2c] (GU uHazeFilter) */
    uint8_t haze_on;               /* [W+0x30] */
    int32_t haze_a;                /* its strength 0..255 [the alpha byte +0x57] */
    float haze_t;                  /* [W+0x34] */
    float heat_t;                  /* the local hunter's 11-frame heat timer [4U player work +0x74] */
    uint8_t rage_seen;             /* test 2 log: rec+0x518 last seen (0 = calm, as at the spawn) */
};

struct gcf *gcf_state(void *self);
struct gcf *gcf_find(const void *self);    /* this unit's state, or 0 (no new one) */
int gcf_ours(const void *self);
int gcf_event_quest(void);         /* the event quest 11499 (4U spawn byte 3 = 1 [W+0x797e]) runs */
void gcf_zone_place(void *self, uint32_t sub, const float *a);    /* em013_06_moves.c [0x89e990] */
void gcf_footstep(void *self, uint32_t id);                       /* em013_06_frame.c, from the core PSL gate */
void gcf_haze_open(void *self, struct gcf *s);                    /* em013_06_zone.c: spawn */
void gcf_haze_frame(void *self, struct gcf *s);                   /* slot 130 [0x89c1fc] */
void gcf_zone_hunter(void *self, struct gcf *s);                  /* slot 119 [0x89ebdc + 0xb30050] */

/* GU calls (4U counterparts in brackets) */
typedef int (*gcf_self_int_t)(void *self);
#define gcfRageOn     FN(gcf_self_int_t, 0x8172c)    /* rec+0x518 == 1 [0x954e48: W+0x530 == 1] (C) */
typedef void (*gcf_self_t)(void *self);
#define gcfRageLock   FN(gcf_self_t, 0xbd100)        /* rec+0x520 = 1 [0x934508: W+0x538 = 1] (C) */
typedef void (*gcf_attack_t)(void *self, uint32_t slot, uint32_t index);
#define gcfAttack     FN(gcf_attack_t, 0x7df94)      /* attackEx with param 0 [0x914dfc] */
typedef void *(*gcf_mat_get_t)(void *self, uint32_t i);
#define gcfMatGet     FN(gcf_mat_get_t, 0x890adc)    /* material i < this+0xfc [0x1a4814, i < this+0xf8] */
typedef int (*gcf_anim_find_t)(void *set, const char *name);
#define gcfAnimFind   FN(gcf_anim_find_t, 0xb0bb0c)  /* [0xcfba14] */
typedef void (*gcf_anim_play_t)(void *mat, uint32_t slot, uint32_t index);
#define gcfAnimPlay   FN(gcf_anim_play_t, 0xb0cab0)  /* [0x636b64] */
#define gcfMatDirty   FN(gcf_self_t, 0x88ecc0)       /* [0x1a64c0] */
typedef float (*gcf_ground_ray_t)(void *mgr, const float *from, const float *to, uint32_t area, uint8_t *hit,
                                  void *out, uint32_t mask);
#define gcfGroundRay  FN(gcf_ground_ray_t, 0x183ad0) /* [0x2bad24] (to = 0: straight down) */
typedef uint32_t (*gcf_area_list_t)(uint32_t area, uint32_t id);
#define gcfAreaList   FN(gcf_area_list_t, 0x497cc)   /* 1 id absent from the area's list, 2 present [0x6c1570] (S) */
typedef void *(*gcf_snd_joint_t)(void *mgr, uint32_t id, void *owner, uint32_t joint, uint32_t area, int32_t m2);
#define gcfSndJoint   FN(gcf_snd_joint_t, 0x4efd74)  /* [0x2fcc50] */
#define GCF_SND_MGR   (*(void **)MAIN(0x1896f5c))    /* [*0xfccd6c] */
