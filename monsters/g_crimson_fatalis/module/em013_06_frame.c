/* em013_06_frame.c: G-rank Crimson Fatalis' per-frame parts of 4U slot 48 0x89cc6c (em117 only) and the hitzone
 * switch 0x89c2f4 (notes/plan.md 9). C = read in code, S = strong, G = guess; 4U addresses in [].
 * Prominence (GU slot 130 entry 0xd80eec; GU's slot 130 is 4U slot 48's shared motion switch without em117's
 * parts, C): the clock W+0x70 counts down by the motion delta; at 0 the current motion picks a pattern and frame 2
 * of it starts a sequence: the angles and the position are stored, the clock set to 630, and post k (uShell018 6,
 * the marker; its end posts the eruption) goes out once 60 k frames have run, on a grid of the pattern's table
 * 0xe0db0c (columns: distance / yaw; rows 1400 apart), scaled by the size, dropped on the ground. 3 x 3 posts (3 x 2
 * for pattern 5); the next sequence can start when the clock is back at 0. 4U slot 48 runs the shared switch first;
 * here the gate runs before GU's slot 130 body (S: no field of one is read by the other).
 * Stepfire [the footstep loop 0x89d600, C]: each new section of the motion's footstep bit track whose code is 2000..
 * 2003 posts uShell003 177 at joint 40 / 50 / 90 / 80 and sound 220 there (and sets MEF bit 4, which posts em117_1's
 * record of that code). GU moved those tracks into its PSL files; ours carry em117_1's records 2000..2003 on 4U's
 * own bits (build_em013_06_arc.py psl_own), so GU's PSL post of one of them is that new section: the core PSL gate
 * (module/b0gate.c) calls gcf_footstep then (S: one post per section, as GU's dust records).
 * Hitzones (GU 0xd815d0 entry, called by slot 130; GU switches variants 1 / 2 only, C): enraged and not the event
 * quest -> the rage rows (partMeatAlt i, i), else the base rows, for the 8 rows, every frame. */
#include "em013_06.h"
#include "b0gate.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

/* 0xe0db0c: 6 patterns x 3 columns {distance, yaw} (C, read as f32) */
static const float k_grid[6][3][2] = {
    {{1000.0f, 0x2000}, {1000.0f, 0x6000}, {1000.0f, 0xa000}},
    {{1000.0f, 0xe001}, {1000.0f, 0xa000}, {1000.0f, 0x6000}},
    {{1000.0f, 0x2000}, {1000.0f, 0xe001}, {1500.0f, 0x8000}},
    {{1000.0f, 0x2000}, {1000.0f, 0xe001}, {1000.0f, 0}},
    {{1000.0f, 0}, {1000.0f, 0x6000}, {1000.0f, 0xa000}},
    {{1000.0f, 0x2000}, {1000.0f, 0xe001}, {0.0f, 0}},
};

/* the pattern of a motion (jump table 0x89d76c, C); 0xff = none */
static uint8_t pattern(uint32_t m)
{
    switch (m) {
    case 0x205: return 0;
    case 0x206: return 1;
    case 6: case 7: case 8: case 9: case 0xa: case 0xe: case 0xf: case 0x10: case 0x14: case 0x15:
    case 0x219: case 0x223: case 0x224: case 0x227: case 0x230: return 2;
    case 0x216: return 3;
    case 0xb: case 0x217: return 4;
    case 0x21a: return 5;
    default: return 0xff;
    }
}

/* post k of the running sequence [0x89c448] */
static void prom_post(void *self, struct gcf *s)
{
    uint32_t n = s->type == 5 ? 2 : 3, k = s->k;
    if (60.0f * (float)k > 630.0f - s->cool) return;
    uint32_t row = k / n, col = k % n;
    float dist = k_grid[s->type][col][0], yaw = k_grid[s->type][col][1];
    if (dist == 0.0f) return;
    float v[3] = { 0.0f, 0.0f, dist + (float)row * 1400.0f }, sc = speedFactor(self);
    gcf_rot_y(v, (uint32_t)((float)s->ang[1] + yaw));
    float pos[4] = { s->pos[0] + v[0] * sc, s->pos[1] + v[1] * sc, s->pos[2] + v[2] * sc, 0.0f };
    uint32_t ang[3] = { s->ang[0], s->ang[1] + (uint32_t)yaw, s->ang[2] };
    uint32_t area = FIELD(uint8_t, self, GCF_EN_AREA);
    uint32_t mask = gcfAreaList(area, FIELD(uint8_t, self, GCF_EN_FLOOR)) == 1 ? 128 : 0;
    uint32_t out[64];
    uint8_t hit = 0;
    void *mgr = GCF_COL_MGR;
    if (mgr) pos[1] = gcfGroundRay(mgr, pos, 0, area, &hit, out, mask);
    void *sh = gcf_marker_post(self, pos, ang);
    static uint32_t s_n;
    if (++s_n <= 40)
        logf("gcfport: prominence %u post %u at %d %d %d (ground %u mask %u) -> %x", s->type, k, (int)pos[0],
             (int)pos[1], (int)pos[2], hit, mask, (uint32_t)sh);
    if (++s->k >= 3 * n) s->prom_run = 0;
}

/* the cooldown, the trigger and the posts [0x89d598..0x89d8e8, then the tail call 0x89c448] */
static void prominence(void *self, struct gcf *s)
{
    if (s->cool == 0.0f && s->prom_on == 1) {
        uint32_t m = curMotion(self);
        s->type = pattern(m);
        if (motionCheck(self, 0, 0, 2.0f, 0.0f) && s->type != 0xff) {
            const uint32_t *a = &FIELD(uint32_t, GCF_REC(self), REC_ANGLES);   /* [this+0x8d20 = W+0x1a8..] (S) */
            const float *p = &FIELD(float, self, 0x40);                       /* [this+0x40] unit position */
            for (int i = 0; i < 3; i++) { s->ang[i] = a[i]; s->pos[i] = p[i]; }
            s->k = 0;
            s->prom_run = 1;
            s->cool = 630.0f;
            static uint32_t s_n;
            if (++s_n <= 20) logf("gcfport: prominence pattern %u starts (motion %x)", s->type, m);
        }
    } else {
        s->cool -= FIELD(float, self, GCF_EN_MDT);
        if (s->cool <= 0.0f) s->cool = 0.0f;
    }
    if (s->prom_run) prom_post(self, s);
}

int em013_06_frame_c(uint32_t *regs)           /* GU slot 130 entry 0xd80eec (r0 = this) */
{
    void *self = (void *)regs[R0];
    if (!gcf_ours(self)) return 0;
    struct gcf *s = gcf_state(self);
    gcf_haze_frame(self, s);                    /* [0x89c1fc, the first call of slot 48] */
    prominence(self, s);
    return 0;
}

int em013_06_meat_c(uint32_t *regs)            /* GU 0xd815d0 entry (r0 = this): replaced for variant 6 */
{
    void *self = (void *)regs[R0];
    if (!gcf_ours(self)) return 0;
    int alt = gcfRageOn(self) == 1 && !gcf_event_quest();
    for (uint32_t i = 0; i < 8; i++) {
        if (alt) partMeatAlt(self, i, i);
        else partMeatBase(self, i);
    }
    return 1;
}

/* [0x89d6a0..0x89d714, em117's branch] */
void gcf_footstep(void *self, uint32_t id)
{
    static const uint8_t k_joint[4] = { 40, 50, 90, 80 };
    if (id < 2000 || id > 2003) return;
    uint32_t j = k_joint[id - 2000], area = FIELD(uint8_t, self, GCF_EN_AREA);
    float pos[4];
    jointPos(self, j, pos);
    pos[3] = 0.0f;
    void *sh = gcf_stepfire_post(self, pos, area);
    void *m = GCF_SND_MGR;
    if (m) gcfSndJoint(m, 220, self, j, area, -2);
    static uint32_t s_n;
    if (++s_n <= 30) logf("gcfport: stepfire %u at joint %u -> %x", id, j, (uint32_t)sh);
}

/* the core PSL gate tells us of our PEL u posts (em117_1's records are all on their own bits: nothing gated) */
const struct b0post em013_06_b0post = { G_CRIMSON_FATALIS_EM_ID, gcf_footstep };
