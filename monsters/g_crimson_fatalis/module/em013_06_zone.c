/* em013_06_zone.c: G-rank Crimson Fatalis' heat zone against the local hunter and its heat haze (notes/plan.md 9).
 * C = read in code, S = strong, G = guess; 4U addresses in [], GU twins from the 2026-11-22 study.
 * Hunter [0x687280 -> 0x89ebdc, then the player tick 0xb30050, C]: while the zone is on and the local hunter is in
 * its area: a capsule from centre + R(yaw)(0, 0, 3000) to centre - R(yaw)(0, 0, 3000 - r / 3), radius r, against
 * the hunter's position; inside: the haze on (timer 300), flag word |= 0x1000, and every 11 frames of the hunter's
 * clock 2 HP (0xb1ac40(player, -2), skipped under the damage lock 0xb34880). No skill, item or effect test: Cool
 * Drinks and Heat Res do not protect. GU dropped that branch (its hunter tick 0x2a49c0 keeps only the circle zones of
 * 0x6a008); here it runs from our slot 119 for the local hunter, which gives 4U's result on every machine (4U: the
 * local player only, each machine its own) (S). GU twins: the HP change with Guts / faint = 0x2f0c9c, its wrapper
 * 0x2f4930(h, delta) with the damage lock 0x27c9d8 first (C; GU's poison and heat call it); flag word h+0x2850 (C,
 * bit 0x1000: S, a damage-over-time mark the hunter update copies and clears every frame); the hunter's clock h+28
 * (C); our own 11-frame timer (4U P+0x74 has no free GU twin, GU's heat timer h+0x2888 is GU's own). 4U P+0x7fe = 1
 * (only stops the hot-area drain inside the zone, 0xb1aa14) has no GU twin: Ingle Isle is not a hot stage (S).
 * The tick gates h+0x2506 != 256 and !(h+0x274a & 0x20) are GU's hunter tick's entry tests, taken as the 4U tick's (G).
 * Haze [0x893f44 spawn, 0x89c1fc per frame, C]: 4U makes a uMhHazeFilter at every Fatalis' spawn, hidden; the zone
 * hit shows it and restarts its 300-frame timer; the strength fades in by 4.25 x dt per frame to 255 while the timer
 * runs, then out to 0, then the filter is hidden. GU's uHazeFilter (newInstance 0x8c090c, 0xc0 bytes) is the
 * framework's shader filter: no colour; its strength is mHazeScale +0x8c / +0x90 (default 0.05), set here to HAZE_MAX x
 * strength / 255 (G); it goes on unit line 29 with mask 0x10 as sEffect's own filters (0xb92618) (S); 4U's draw bits
 * +4 0x400 / 0x800 = cUnit +0xc 0x400 / 0x800 (S: both cUnits start from the same flags constant 0xf4ff9). 4U's
 * delete of the filter was not traced: ours is killed with the monster (uEm013_00 destructors, port-only), as
 * Dalamadur's effects. */
#include "em013_06.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

typedef void *(*gcf_new_t)(void);
#define hazeNew       FN(gcf_new_t, 0x8c090c)
typedef void (*gcf_unit_add_t)(void *mgr, uint32_t line, void *unit, uint64_t mask);
#define unitAdd       FN(gcf_unit_add_t, 0xc067ec)
#define SUNIT         (*(void **)MAIN(0x2126f48))
#define UNIT_FLAGS    0xc
#define UNIT_KILL     16
#define HAZE_SCALE    0x8c          /* f32 x 2 mHazeScale */
#define HAZE_MAX      0.025f        /* mHazeScale at full strength: half GU's default 0.05, which the maintainer found
                                       too strong in test 1 (2026-11-22; the mapping is a guess, G) */
#define HAZE_DRAW     0xc00u
typedef int (*gcf_is_local_t)(void *h);
#define isLocal       FN(gcf_is_local_t, 0x27bcd0)
typedef int (*gcf_hp_add_t)(void *h, int32_t delta);
#define hunterHp      FN(gcf_hp_add_t, 0x2f4930)   /* 1 = the hunter fainted */
#define H_FLAGS       0x2850        /* [P+0x1f8] */
#define H_AREA        0x1054
#define H_POS         0x40

static int haze_alive(void *h) { return h && (FIELD(uint32_t, h, UNIT_FLAGS) & 7) - 1 < 2; }

static void haze_scale(struct gcf *s)
{
    if (!haze_alive(s->haze)) return;
    float v = HAZE_MAX * (float)s->haze_a / 255.0f;
    FIELD(float, s->haze, HAZE_SCALE) = v;
    FIELD(float, s->haze, HAZE_SCALE + 4) = v;
}

void gcf_haze_open(void *self, struct gcf *s)
{
    void *mgr = SUNIT;
    if (s->haze || !mgr) return;
    void *h = hazeNew();
    if (h) {
        unitAdd(mgr, 29, h, 0x10);
        FIELD(uint32_t, h, UNIT_FLAGS) &= ~HAZE_DRAW;
    }
    s->haze = h;
    s->haze_on = 0;
    s->haze_a = 0;
    haze_scale(s);
    logf("gcfport: %x heat haze filter %x", (uint32_t)self, (uint32_t)h);
}

void gcf_haze_frame(void *self, struct gcf *s)
{
    if (!s->haze_on) return;
    float d = FIELD(float, self, EN_DT) * 4.25f;
    if (!timerDown(self, &s->haze_t, 1.0f)) {
        if (s->haze_a >= 255) return;
        s->haze_a = (int32_t)((float)s->haze_a + d);
        if (s->haze_a > 255) s->haze_a = 255;
    } else if (s->haze_a > 0) {
        s->haze_a = (int32_t)((float)s->haze_a - d);
        if (s->haze_a < 0) s->haze_a = 0;
    } else {
        if (haze_alive(s->haze)) FIELD(uint32_t, s->haze, UNIT_FLAGS) &= ~HAZE_DRAW;
        s->haze_on = 0;
        s->haze_t = 300.0f;
    }
    haze_scale(s);
}

/* point h within r of the zone's segment [0x89ebdc -> 0x20d1a0] */
static int in_zone(const struct gcf_zone *z, const float *h)
{
    float f[3] = { 0.0f, 0.0f, 3000.0f }, b[3] = { 0.0f, 0.0f, 3000.0f - z->r * 0.33333334f };
    gcf_rot_y(f, z->yaw);
    gcf_rot_y(b, z->yaw);
    float p0[3], d[3], w[3], dd = 0.0f, wd = 0.0f, d2 = 0.0f;
    for (int i = 0; i < 3; i++) {
        p0[i] = z->pt[i] + f[i];
        d[i] = (z->pt[i] - b[i]) - p0[i];
        w[i] = h[i] - p0[i];
        dd += d[i] * d[i];
        wd += w[i] * d[i];
    }
    float t = dd > 0.0f ? wd / dd : 0.0f;
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    for (int i = 0; i < 3; i++) {
        float c = w[i] - t * d[i];
        d2 += c * c;
    }
    return d2 <= z->r * z->r;
}

static void *local_hunter(void)
{
    void *root = *(void **)PLAYER_ROOT;
    void *pl = root ? FIELD(void *, root, 0x58) : 0;
    if (!pl || !FIELD(void *, pl, 0x498) || !FIELD(void *, pl, 0x494) || isLocal(pl) != 1) return 0;
    return pl;
}

void gcf_zone_hunter(void *self, struct gcf *s)
{
    if (s->zone.marker == 0xff) return;
    void *h = local_hunter();
    if (!h || FIELD(uint16_t, h, 0x2506) == 256 || (FIELD(uint8_t, h, 0x274a) & 0x20)) return;
    if (FIELD(uint8_t, h, H_AREA) != s->zone.area || !in_zone(&s->zone, &FIELD(float, h, H_POS))) return;
    if (haze_alive(s->haze)) FIELD(uint32_t, s->haze, UNIT_FLAGS) |= HAZE_DRAW;
    s->haze_on = 1;
    s->haze_t = 300.0f;
    FIELD(uint32_t, h, H_FLAGS) |= 0x1000;
    s->heat_t -= FIELD(float, h, EN_DT);
    if (s->heat_t > 0.0f) return;
    s->heat_t = 11.0f;
    int fainted = hunterHp(h, -2);
    static uint32_t s_n;
    if (++s_n <= 30) logf("gcfport: %x zone heat -2 on the local hunter (fainted %d)", (uint32_t)self, fainted);
}

/* uEm013_00 slot 0 0xd807f0 / slot 1 0xd80844 entry (r0 = this): no filter outlives the monster (port-only) */
static int release(uint32_t *regs)
{
    struct gcf *s = gcf_ours((void *)regs[R0]) ? gcf_find((void *)regs[R0]) : 0;
    if (!s) return 0;
    if (haze_alive(s->haze)) VCALL0(s->haze, UNIT_KILL);
    logf("gcfport: %x deleted, heat haze filter %x killed", regs[R0], (uint32_t)s->haze);
    s->haze = 0;
    s->self = 0;
    return 0;
}
int em013_06_dtor_c(uint32_t *regs) { return release(regs); }
int em013_06_delete_c(uint32_t *regs) { return release(regs); }
