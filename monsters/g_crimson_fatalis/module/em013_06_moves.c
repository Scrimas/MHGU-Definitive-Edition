/* em013_06_moves.c: G-rank Crimson Fatalis' heatwave, 7/74 / 7/75 / 7/76 [4U 0x899c30(r1 = 0 / 1 / 2), from the
 * cat-7 dispatcher 0x898d90], and the zone it leaves [0x89e990] (notes/plan.md 9). C = read in code, S = strong.
 * GU's uEm013_00 cat-7 dispatcher 0xd8bc74 (its one caller: slot 125's case 7, 0xd8d83c) sends 74..76 to the base
 * "no case" thunk 0xca10c (the action would end the same frame, C). Entry hook there: for us and 74..76 the handler
 * runs and the hook returns to slot 125 (which goes on with its own post-step); everything else goes on into GU's
 * dispatcher. The thunk itself (Tigerstripe's hook) is not touched.
 * The handler, literally (C): step 0: setTargetMode 0, motion 0x23d / 0x23e / 0x23c (blend 4), 7/76 arms attack 46
 * in slot 0. Step 1: at frame 128 (sides) / 284 (ahead) the shot (uShell012 54 / 55 / 51, the event quest 67 / 68 /
 * 66: em013_06_shell012.c) from offset A with velocity B and acceleration C, then the zone; at the motion's end the
 * action ends (vt+0x164 = GU slot 247). No turn, sound or camera shake in the handler (its sounds come from the
 * motion's events and the shots).
 * Zone [0x89e990, C]: one at a time (marker 0xff = free); centre = position + R(yaw)(offset + A), offset 3000 ahead
 * (r 1900) or 3000 to a side (r 900, zone yaw +-0x4000), timer 300 (em013_06_state.c counts it down). */
#include "em013_06.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

void gcf_zone_place(void *self, uint32_t sub, const float *a)
{
    struct gcf *s = gcf_state(self);
    uint8_t *rec = GCF_REC(self);
    uint32_t yaw = FIELD(uint32_t, rec, REC_YAW), zyaw = yaw;
    float v[3] = { 0.0f, 0.0f, 0.0f }, r = 0.0f;
    if (s->zone.marker != 0xff) return;
    if (sub == 0) { v[2] = 3000.0f; r = 1900.0f; }
    else if (sub == 1) { v[0] = 3000.0f; r = 900.0f; zyaw = (yaw + 0x4000) & 0xffff; }
    else if (sub == 2) { v[0] = -3000.0f; r = 900.0f; zyaw = (yaw + 0xc000) & 0xffff; }
    for (int i = 0; i < 3; i++) v[i] += a[i];
    gcf_rot_y(v, yaw);
    const float *p = GCF_VEC(rec, GCF_REC_POS);
    s->zone.marker = 117;
    s->zone.area = FIELD(uint8_t, self, GCF_EN_AREA);
    for (int i = 0; i < 3; i++) s->zone.pt[i] = v[i] + p[i];
    s->zone.yaw = zyaw;
    s->zone.r = r;
    s->zone.timer = 300.0f;
    static uint32_t s_n;
    if (++s_n <= 20)
        logf("gcfport: zone %u at %d %d %d yaw %x r %d (area %u)", sub, (int)s->zone.pt[0], (int)s->zone.pt[1],
             (int)s->zone.pt[2], zyaw, (int)r, s->zone.area);
}

static void heatwave(void *self, uint32_t v)
{
    static const uint16_t k_motion[3] = { 0x23d, 0x23e, 0x23c };
    uint8_t *rec = GCF_REC(self);
    if (rec[REC_STEP0] == 0) {
        rec[REC_STEP0] = 1;
        setTargetMode(self, 0);
        setMotion(self, k_motion[v], 4.0f, 0.0f);
        if (v == 2) gcfAttack(self, 0, 46);
        return;
    }
    if (rec[REC_STEP0] != 1) return;
    if (motionCheck(self, 0, 0, v == 2 ? 284.0f : 128.0f, 0.0f)) {
        int ev = gcf_event_quest();
        float a[4] = { 0.0f, 0.0f, 600.0f, 0.0f }, b[4] = { 10.0f, 0.0f, 0.0f, 0.0f };
        float c[4] = { 3.0f, 0.0f, 0.0f, 0.0f };
        uint32_t sub = ev ? 67 : 54, zone = 1;
        if (v == 1) { b[0] = -10.0f; c[0] = -3.0f; sub = ev ? 68 : 55; zone = 2; }
        if (v == 2) {
            a[2] = 1400.0f; b[0] = 0.0f; b[2] = 10.0f; c[0] = 0.0f; c[2] = 3.0f;
            sub = ev ? 66 : 51; zone = 0;
        }
        void *sh = gcf_heatwave_post(self, sub, a, b, c);
        static uint32_t s_n;
        if (++s_n <= 20) logf("gcfport: 7/%u heatwave shot %u -> %x", 74 + v, sub, (uint32_t)sh);
        gcf_zone_place(self, zone, a);
    }
    if (isMotionEnd(self)) VCALL0(self, SLOT_ACTION_END);
}

int em013_06_act7_c(uint32_t *regs)            /* GU 0xd8bc74 entry (r0 = this): 1 = handled, back to slot 125 */
{
    void *self = (void *)regs[R0];
    if (!gcf_ours(self)) return 0;
    uint32_t num = FIELD(uint8_t, self, EN_ACT_NUM);
    if (num < 74 || num > 76) return 0;
    static uint32_t s_n;
    if (GCF_REC(self)[REC_STEP0] == 0 && ++s_n <= 30) logf("gcfport: 7/%u heatwave starts", num);
    heatwave(self, num - 74);
    return 1;
}
