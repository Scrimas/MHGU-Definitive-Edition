/* em013_06_shell037.c: the prominence eruption, 4U uShell037 kind 8 (type 37 via 0x6626a4; 672 B, vtable 0xe6e2bc:
 * init 0xc836a8, frame 0xc83eb8, kill 0xc84568). C = read in code, S = strong, G = guess (spec 2026-11-22).
 * Post (the marker's end, 0xc72b94): kind 8, position = the marker's, angles = the marker's, group 0xffff, ctor bytes
 * +0x26c = 0 and +0xf3 = 0; area = the owner's W+0x14c.
 * Init (C): (the stage tests 0x6c5e88 / 0x6c3b94 that can drop it, G: area / stage-object tests: not ported) no table
 * effect for kind 8; angles x / z = 0, the yaw kept; ground snap: 0x2b96e4 between y - 500 and y + 500 (mask 16), its
 * result NOT tested: y = hit y + volume 8's +0x14 (-50.0); the origin +0x120 = that point; speed 0x102f7c0[+0xf3 + 16]
 * = 1650.0; life 0x102f79c[8] = 60.0; attack 0x9ab120(records 0x102f830, volumes 0x102f808, record 0x102f998[8] = 6,
 * a 31, b 2) = HDS GCF_HDS_ERUPT (start delay 15, length 60, power 10, type 31, volume 4: sphere r150 on bone 1001,
 * which GU tests along the capsule origin -> position); group 0xffff (its own serial); a world post of (87, 19) =
 * em117_202 at (x, y + 50, z) with rotation (0, yaw, 0), mask 1 (GCF_EFX_ERUPT, handle dropped); no sound; the frame
 * runs in the same tick.
 * Frame (C): owner gone -> 3; life out -> 2. Once the attack's start delay is over: e = 60 - the window left; r = e /
 * 60; r > 0 -> cur = 1650 r; d = 3 cur while e <= 20, else 1650; position = origin + (0, 0, d) turned by Rx(x angle),
 * Ry(yaw), Rz(z angle): the eruption slides out along its yaw up to 1650 (no rise; y stays). The window end (+0x16d
 * cleared) would end it (never for kind 8: 60 < 15 + 60). Sound 216 on the shell every 30 frames from init (once in
 * its life). The scorch: once e > 16, a latch is set and a ray from y - 500 to y + 150 (mask 16) at the current
 * position; a hit -> world post of (87, 19) mask 2 (GCF_EFX_SCORCH) at (x, hit y, z), no rotation (a miss: none).
 * Kill (C): no effect handle of its own for kind 8 (both posts are fire-and-forget). The 4U request flags of the two
 * posts (0x83 / 0x20) are not mapped (G: GU has no counterpart field known). */
#include "game.h"
#include "util.h"
#include "em013_06_shell.h"

#define E_STATE   (SHELL_FIELDS + 0x00)   /* u8 0 new, 1 alive, 2 done [+0xf1] */
#define E_ARMED   (SHELL_FIELDS + 0x01)
#define E_LATCH   (SHELL_FIELDS + 0x02)   /* u8 scorch done [+0x280 = 65535.0] */
#define E_LIFE    (SHELL_FIELDS + 0x04)   /* float [+0x270] */
#define E_SPEED   (SHELL_FIELDS + 0x08)   /* float [+0x278] */
#define E_CUR     (SHELL_FIELDS + 0x0c)   /* float [+0x27c] */
#define E_SND_T   (SHELL_FIELDS + 0x10)   /* float [+0x274] */
#define E_SERIAL  (SHELL_FIELDS + 0x14)
#define E_START   (SHELL_FIELDS + 0x18)   /* float[3] request position */
#define E_ANG     (SHELL_FIELDS + 0x28)   /* u32[3] request angles */
#define E_SIZE    (SHELL_FIELDS + 0x38)

#define ERUPT_LEN    60.0f    /* record 6's s16 +2 (the window length) */
#define ERUPT_SPEED  1650.0f  /* 0x102f7c0[16] */
#define ERUPT_LIFE   60.0f    /* 0x102f79c[8] */
#define VOL8_Y       -50.0f   /* volume 8 (0x102fa5c) +0x14 */
#define SND_ERUPT    216u     /* 0x102f708 */
#define SND_EVERY    30.0f    /* 0x102f704 */

static shcls_t s_cls;
static uint32_t s_serial;

static uint32_t ground_ray(void *self, const float *pos, float below, float above, float *out)
{
    float from[4] = {pos[0], pos[1] - below, pos[2], 0.0f}, to[4] = {pos[0], pos[1] + above, pos[2], 0.0f};
    void *col = GCF_COL_MGR;
    return col ? gcfMapSegment(col, from, to, FIELD(uint8_t, self, SH_AREA), out, 0, 16, gcfColFlags(self)) : 0;
}

/* 4U frame 0xc83eb8 after the owner test; 1 = done */
static int e_step(void *self, void *owner)
{
    float *life = &FIELD(float, self, E_LIFE);
    shell_timer(self, life);
    if (*life <= 0.0f) return 1;
    float *pos = GCF_VEC(self, SH_POS), *org = GCF_VEC(self, SH_POS2);
    float left = FIELD(float, self, SH_ATK0 + ATK_TIME), e = ERUPT_LEN - left;
    if (FIELD(float, self, SH_ATK0 + GCF_ATK_DELAY) <= 0.0f) {      /* 0xc84064: only once the delay is over */
        float r = e / ERUPT_LEN;
        if (r > 0.0f) FIELD(float, self, E_CUR) = FIELD(float, self, E_SPEED) * r;
        float d = e <= 20.0f ? FIELD(float, self, E_CUR) * 3.0f : FIELD(float, self, E_SPEED);
        uint32_t ax = FIELD(uint32_t, self, SH_ANGLES), ay = FIELD(uint32_t, self, SH_ANGLES + 4),
                 az = FIELD(uint32_t, self, SH_ANGLES + 8);
        float sx = sinf_gu(gcf_ang_rad(ax)), cx = cosf_gu(gcf_ang_rad(ax)), sy = sinf_gu(gcf_ang_rad(ay)),
              cy = cosf_gu(gcf_ang_rad(ay)), sz = sinf_gu(gcf_ang_rad(az)), cz = cosf_gu(gcf_ang_rad(az));
        float y1 = -sx * d, z1 = cx * d, x2 = sy * z1, z2 = cy * z1;   /* 0xc840d8..0xc84188 */
        pos[0] = org[0] + cz * x2 - sz * y1;
        pos[1] = org[1] + sz * x2 + cz * y1;
        pos[2] = org[2] + z2;
    }
    if (!FIELD(uint8_t, self, SH_ATK0 + ATK_ACTIVE)) {                /* 0xc8423c: the window's end */
        static uint32_t s_n;
        if (++s_n <= 10) logf("gcfport: eruption %u: attack window over", FIELD(uint32_t, self, E_SERIAL));
        return 1;
    }
    float *st = &FIELD(float, self, E_SND_T);
    *st += shell_dt(self);
    if (*st >= SND_EVERY) {
        *st = 0.0f;
        shell_snd_obj(owner, SND_ERUPT, self, FIELD(uint8_t, self, SH_AREA));
    }
    if (e > 16.0f && !FIELD(uint8_t, self, E_LATCH)) {               /* 0xc842c8: the scorch, once */
        FIELD(uint8_t, self, E_LATCH) = 1;
        float out[4] = {0.0f, 0.0f, 0.0f, 0.0f};
        uint32_t hit = ground_ray(self, pos, 500.0f, 150.0f, out);
        if (hit) {
            float p[3] = {pos[0], out[1], pos[2]};
            efx_world(owner, GCF_EFX_SCORCH, p, 0);
        }
        static uint32_t s_n;
        if (++s_n <= 30)
            logf("gcfport: eruption %u scorch at %d %d %d (ground %s), delay %d", FIELD(uint32_t, self, E_SERIAL),
                 (int32_t)pos[0], (int32_t)out[1], (int32_t)pos[2], hit ? "hit" : "missed: none",
                 (int32_t)FIELD(float, self, SH_ATK0 + GCF_ATK_DELAY));
    }
    return 0;
}

/* slot 79: base set-up, the ctor 0xc8459c fields, init 0xc836a8 (kind 8) and its slot-23 tail call */
static int e_setup(void *self, void *param)
{
    if (gcfShellSetup(self, param) != 1) return 0;
    void *owner = FIELD(void *, param, 0xc);
    FIELD(uint8_t, self, SH_AREA) = FIELD(uint8_t, owner, GCF_EN_AREA);
    float *pos = GCF_VEC(self, SH_POS), *st = GCF_VEC(self, E_START), *org = GCF_VEC(self, SH_POS2);
    for (int i = 0; i < 3; i++) pos[i] = st[i];
    FIELD(uint32_t, self, SH_ANGLES) = 0;                                       /* 0xc83c94: x and z angles 0 */
    FIELD(uint32_t, self, SH_ANGLES + 4) = FIELD(uint32_t, self, E_ANG + 4);
    FIELD(uint32_t, self, SH_ANGLES + 8) = 0;
    float out[4] = {pos[0], pos[1], pos[2], 0.0f};                 /* 4U ignores the result (its stack on a miss, G) */
    uint32_t hit = ground_ray(self, pos, 500.0f, 500.0f, out);
    pos[1] = out[1] + VOL8_Y;
    for (int i = 0; i < 3; i++) org[i] = pos[i];
    FIELD(float, self, E_SPEED) = ERUPT_SPEED;
    FIELD(float, self, E_CUR) = 0.0f;
    FIELD(float, self, E_LIFE) = ERUPT_LIFE;
    FIELD(uint8_t, self, E_ARMED) = (uint8_t)shell_arm(&gcf_shells, self, GCF_HDS_ERUPT, 31, 2, 0xffff);
    FIELD(float, self, E_SND_T) = 0.0f;
    FIELD(uint8_t, self, E_LATCH) = 0;
    float p[3] = {pos[0], pos[1] + 50.0f, pos[2]}, rot[3] = {0.0f, gcf_ang_rad(FIELD(uint32_t, self, SH_ANGLES + 4)), 0.0f};
    void *eff = efx_world(owner, GCF_EFX_ERUPT, p, rot);
    FIELD(uint8_t, self, E_STATE) = 1;
    static uint32_t s_n;
    if (++s_n <= 30)
        logf("gcfport: eruption %u at %d %d %d (ground %s) yaw %x area %u hit %u efx %x delay %d window %d",
             FIELD(uint32_t, self, E_SERIAL), (int32_t)pos[0], (int32_t)pos[1], (int32_t)pos[2], hit ? "hit" : "missed",
             FIELD(uint32_t, self, SH_ANGLES + 4), FIELD(uint8_t, self, SH_AREA), FIELD(uint8_t, self, E_ARMED),
             (uint32_t)eff, (int32_t)FIELD(float, self, SH_ATK0 + GCF_ATK_DELAY),
             (int32_t)FIELD(float, self, SH_ATK0 + ATK_TIME));
    if (e_step(self, owner)) FIELD(uint8_t, self, E_STATE) = 2;
    return 1;
}

/* slot 9 = 4U slot 23 */
static void e_move(void *self)
{
    gcfShellMove(self);
    if (!shell_live(self)) return;
    if (FIELD(uint8_t, self, E_STATE) == 2) { VCALL0(self, GCF_SLOT_KILL); return; }
    if (FIELD(uint8_t, self, E_STATE) != 1) return;
    void *owner = shell_owner(self);
    if (owner && e_step(self, owner)) FIELD(uint8_t, self, E_STATE) = 2;
}

static void *e_new(MtDTI *dti) { (void)dti; return shell_new(&s_cls); }
static MtDTI *e_dti(void *self) { (void)self; return &s_cls.dti; }
static void e_delete(void *self) { shell_free(&s_cls, self); }

void *gcf_eruption_post(void *owner, const float *pos, const uint32_t *angles)
{
    if (!pos || !angles) return 0;
    if (!s_cls.registered)
        shell_register(&s_cls, &gcf_shells, "uShellGcf037", E_SIZE, e_new, e_delete, e_dti, e_move, e_setup, 0);
    void *param = shell_param(&gcf_shells, owner, "eruption");
    if (!param) return 0;
    void *shell = shell_new(&s_cls);
    if (!shell) { shell_param_free(param); return 0; }
    float *st = GCF_VEC(shell, E_START);
    st[0] = pos[0]; st[1] = pos[1]; st[2] = pos[2];
    for (int i = 0; i < 3; i++) FIELD(uint32_t, shell, E_ANG + 4 * i) = angles[i];
    FIELD(uint32_t, shell, E_SERIAL) = ++s_serial;
    return shell_start(&gcf_shells, shell, param, "eruption");
}
