/* seltas_hold.c: the Desert Seltas Queen's hold points, where a hunter she holds is placed (0.1.19). C = read in code,
 * S = strong. The maintainer's test of 0.1.18 (and the contributor on 0.1.16): the bar to break free of her pin is
 * nearly empty, the hunter is free at once.
 *
 * 4U (v1.1, C): 0x799e24(this, mode) writes the two 28-byte hold points {u32 joint, f32 x, y, z, u32 rot[3]} of the
 * species' data object (0x91df20 -> 0x688854 by em number, its +0xa0); side = W+0x278 != 1:
 *  - mode 0 (7/73 = 0x7915dc, her tail grab, first step): both = the class table's (joint 144 at (0, 0, -400) and
 *    (0, 80, -400), rotation (0, 0, 0x8000): her tail pincers);
 *  - mode 1 (16/2 = 0x7924a8, her pin, at its attack frame): point [side] = joint 0 at (0, 160, 150) / (0, 120, 100),
 *    or, with her Desert Seltas on her back (W+0x1c9 bit 0), (0, 260, 100) / (0, 240, 30) times his W+444;
 *  - mode 2 (16/5 = 0x792b80, her launch, first step): point [side] = mode 0's;
 *  - mode 3 (16/5 when its hold check passes, step 2 -> 3): point [side] = joint 0 at (0, 0, 800) / (0, 0, 770).
 *  4U runs all four on every machine (no control test there).
 * GU (C): those points are dtbase +0x80 (count +0xbe): 0xb1a28 = 0x713b4 hands them to the hunter's hold code
 * (0x1127d4c), and GU em069_00's two are 4U's mode 0 with z -350 (Capcom's retune). GU's twins of 7/73, 16/2 (0xf9b250)
 * and 16/5 (0xf9b8c0) dropped every call, so her pin held the hunter at her tail pincers and its hold check (0xc7318
 * kind 3) failed. That the pin's hold reads these points and not dtbase +0xac (0x713dc, by the hunter's +0x1051) is S.
 * Offsets (C, twin code): 4U W+0x278 = rec+0x230 (both games' hold checks), W+0x1c9 = rec+0x1bb (the pair's rider
 * clear, 4U 0x78c07c = GU 0xf8dbb8), W+444 = rec+0x1b0 (speedFactor 4U 0x911cb4 = GU 0xbe5d4), the step W+0x144 =
 * rec+0x1a1, the rider [this+0x8d88]+0 = [this+0xcac0]+0. Modes 0 and 2 put back GU's own points as loaded (the
 * species' values, as GU retuned them); modes 1 and 3 take 4U's.
 * Hooks: her action dispatcher 0xf9c8b4 (entry, every frame before the action's handler: modes 0, 1, 2) and 0xf9baf4
 * (entry; GU's twin of 4U 0x798fe0, which 16/5 calls right after its step 2 -> 3 and on each frame of step 3: mode 3).
 * The normal Queen keeps GU's code. All addresses through MAIN / FN. Logs: "dsport: dsq hold". */
#include <stdint.h>
#include "game.h"
#include "util.h"
#include "port.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

#define IS_DSQ(p)    ((p) && FIELD(uint16_t, (p), EN_ID) == DESERT_SELTAS_QUEEN_EM_ID)
#define EN_DTBASE    0x75e8          /* the unit's dtbase object (GU 0x713b4) */
#define DT_HOLD      0x80            /* its hold points */
#define DT_HOLD_N    0xbe            /* u8 their count */
#define EN_PAIR      0xcac0          /* the pair; its +0 = the Desert Seltas on her back */
#define REC_STEP     0x1a1
#define REC_SIDE     0x230
#define REC_RIDER    0x1bb           /* bit 0: her Desert Seltas rides on her */
#define REC_SCALE    0x1b0           /* f32, 4U W+444 */
#define PIN_FRAME    86.0f           /* 16/2's attack frame: GU's literal 0xf9b474 for both of its frame checks */
#define MAX_LOG      40u

typedef int (*atFrame_t)(void *self, float f);
#define atFrame      FN(atFrame_t, 0xb0a30)      /* [0x941dbc] */

struct hold { uint32_t joint; float x, y, z; uint32_t rot[3]; };
_Static_assert(sizeof(struct hold) == 28, "hold");

static struct hold s_gu[2];          /* GU's points as loaded (modes 0 and 2) */
static void *s_gu_of;                /* the dtbase object they were read from */
static void *s_launch_held;          /* mode 3 done in her running 16/5 */

static struct hold *holds(void *self)
{
    uint8_t *dt = FIELD(uint8_t *, self, EN_DTBASE);
    if (!dt || FIELD(uint8_t, dt, DT_HOLD_N) < 2 || !FIELD(struct hold *, dt, DT_HOLD)) return 0;
    if (dt != s_gu_of) {             /* first sight of this object: nothing of ours has written it yet */
        s_gu[0] = FIELD(struct hold *, dt, DT_HOLD)[0];
        s_gu[1] = FIELD(struct hold *, dt, DT_HOLD)[1];
        s_gu_of = dt;
    }
    return FIELD(struct hold *, dt, DT_HOLD);
}

static void hold_set(void *self, int mode)
{
    static uint32_t s_n, s_quest;
    struct hold *h = holds(self);
    uint8_t *rec = FIELD(uint8_t *, self, EN_RECORD);
    if (!h || !rec) return;
    int side = FIELD(uint8_t, rec, REC_SIDE) != 1, ride = FIELD(uint8_t, rec, REC_RIDER) & 1;
    if (mode == 0) {
        h[0] = s_gu[0];
        h[1] = s_gu[1];
    } else if (mode == 2) {
        h[side] = s_gu[side];
    } else if (mode == 1) {
        static const float pin[2][2][2] = { { { 160.0f, 150.0f }, { 120.0f, 100.0f } },
                                            { { 260.0f, 100.0f }, { 240.0f, 30.0f } } };
        struct hold p = { 0, 0.0f, pin[ride][side][0], pin[ride][side][1], { 0, 0, 0 } };
        uint8_t *pair = FIELD(uint8_t *, self, EN_PAIR), *rider = pair ? FIELD(uint8_t *, pair, 0) : 0;
        uint8_t *rr = rider ? FIELD(uint8_t *, rider, EN_RECORD) : 0;
        float s = ride && rr ? FIELD(float, rr, REC_SCALE) : 1.0f;
        p.x *= s; p.y *= s; p.z *= s;
        h[side] = p;
    } else {
        struct hold p = { 0, 0.0f, 0.0f, side ? 770.0f : 800.0f, { 0, 0, 0 } };
        h[side] = p;
    }
    if (port_quest_id() != s_quest) { s_quest = port_quest_id(); s_n = 0; }
    if (s_n++ < MAX_LOG)
        logf("dsport: dsq hold mode %d (action %u/%u%s): point %d = joint %u at %d %d %d", mode,
             FIELD(uint8_t, self, EN_ACT_CAT), FIELD(uint8_t, self, EN_ACT_NUM), ride ? ", he rides" : "", side,
             h[side].joint, (int)h[side].x, (int)h[side].y, (int)h[side].z);
}

void seltas_act_log(void *self, int queen);     /* seltas.c: the log of their action changes */

/* 0xf9c8b4 = uEm069_00's action dispatcher (entry, every frame): 0 = on into GU's */
int seltas_dsq_hold_c(uint32_t *regs)
{
    void *self = (void *)regs[R0];
    uint8_t *rec;
    if (!IS_DSQ(self) || !(rec = FIELD(uint8_t *, self, EN_RECORD))) return 0;
    seltas_act_log(self, 1);
    uint32_t cat = FIELD(uint8_t, self, EN_ACT_CAT), num = FIELD(uint8_t, self, EN_ACT_NUM), step = rec[REC_STEP];
    if (cat == 7 && num == 73 && step == 0) hold_set(self, 0);
    else if (cat == 16 && num == 2 && step == 1 && atFrame(self, PIN_FRAME)) hold_set(self, 1);
    else if (cat == 16 && num == 5 && step == 0) { s_launch_held = 0; hold_set(self, 2); }
    return 0;
}

/* 0xf9baf4 (entry): GU's twin of 4U 0x798fe0, called by 16/5 right after its step 2 -> 3 and on each frame of step 3 */
int seltas_dsq_hold3_c(uint32_t *regs)
{
    void *self = (void *)regs[R0];
    uint8_t *rec;
    if (!IS_DSQ(self) || !(rec = FIELD(uint8_t *, self, EN_RECORD)) || s_launch_held == self) return 0;
    if (FIELD(uint8_t, self, EN_ACT_CAT) == 16 && FIELD(uint8_t, self, EN_ACT_NUM) == 5 && rec[REC_STEP] == 3) {
        s_launch_held = self;
        hold_set(self, 3);
    }
    return 0;
}
