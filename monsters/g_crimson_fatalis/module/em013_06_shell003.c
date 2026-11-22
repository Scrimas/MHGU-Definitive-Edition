/* em013_06_shell003.c: the stepfire hit, 4U uShell003 subtype 177 (type 3 via 0x663220; init 0xc544d0, frame 0xc54b04,
 * kill 0xc5598c), and the family of em117's shells (em013_06_shell.h).
 * 4U (C, spec 2026-11-22): em117's slot-48 footstep loop (0x89d600) posts it at the joint of each newly set footstep
 * slot (0x89d940: pos = joint position, area W+0x14c, group 0xffff), then sound 220 at the joint (posted by the
 * caller, not the shell). Subtype 177 takes uShell003's default init / frame path, as Dalamadur's dala_shell003.c
 * blasts, with no effect (0x101dfcc[177] = ff ff) and no sound (0x101e7c4[177] = -1): arming 0x9ab120(shell,
 * 0x101f230, 0x101efbc, 177, a 31, b 2) = HDS GCF_HDS_STEP (window 0 + 20, power 20, type 1, volume 120 = sphere r100
 * on bone 255), angles zero, position = the request's; per frame age += dt, end (state 2) when the attack slot is no
 * longer active (+0x16d: the window's end, one tick after its 20 frames) or age >= 200; kill = the base kill (no
 * effect to release). */
#include "game.h"
#include "util.h"
#include "em013_06_shell.h"

const struct shell_family gcf_shells = {GCF_SHELL_FILE, GCF_SHELL_ROW, "gcfport"};

#define B_STATE   (SHELL_FIELDS + 0x00)   /* u8 0 new, 1 active, 2 done [+0xf1] */
#define B_ARMED   (SHELL_FIELDS + 0x01)
#define B_AREA    (SHELL_FIELDS + 0x02)   /* u8 request area [+0x130] */
#define B_AGE     (SHELL_FIELDS + 0x04)   /* float [+316] */
#define B_SERIAL  (SHELL_FIELDS + 0x08)
#define B_START   (SHELL_FIELDS + 0x0c)   /* float[3] request position */
#define B_SIZE    (SHELL_FIELDS + 0x20)

static shcls_t s_cls;
static uint32_t s_serial;

static void s003_end(void *self, const char *why)
{
    static uint32_t s_n;
    if (++s_n <= 20) logf("gcfport: stepfire %u end at age %d: %s", FIELD(uint32_t, self, B_SERIAL),
                          (int32_t)FIELD(float, self, B_AGE), why);
    FIELD(uint8_t, self, B_STATE) = 2;
    VCALL0(self, GCF_SLOT_KILL);
}

/* slot 79: base set-up + init 0xc544d0 (default case) */
static int s003_setup(void *self, void *param)
{
    if (gcfShellSetup(self, param) != 1) return 0;
    FIELD(uint8_t, self, SH_AREA) = FIELD(uint8_t, self, B_AREA);
    float *pos = GCF_VEC(self, SH_POS), *st = GCF_VEC(self, B_START), *p2 = GCF_VEC(self, SH_POS2);
    for (int i = 0; i < 3; i++) pos[i] = p2[i] = st[i];
    for (int i = 0; i < 3; i++) FIELD(uint32_t, self, SH_ANGLES + 4 * i) = 0;
    FIELD(uint8_t, self, B_STATE) = 1;
    FIELD(float, self, B_AGE) = 0.0f;
    FIELD(uint8_t, self, B_ARMED) = (uint8_t)shell_arm(&gcf_shells, self, GCF_HDS_STEP, 31, 2, 0xffff);
    static uint32_t s_n;
    if (++s_n <= 20)
        logf("gcfport: stepfire %u at %d %d %d area %u hit %u", FIELD(uint32_t, self, B_SERIAL), (int32_t)pos[0],
             (int32_t)pos[1], (int32_t)pos[2], FIELD(uint8_t, self, SH_AREA), FIELD(uint8_t, self, B_ARMED));
    return 1;
}

/* slot 9 = 4U slot 23 0xc54b04 (default path 0xc54b88) */
static void s003_move(void *self)
{
    gcfShellMove(self);
    if (!shell_live(self) || FIELD(uint8_t, self, B_STATE) != 1) return;
    float *age = &FIELD(float, self, B_AGE);
    *age += shell_dt(self);
    if (!FIELD(uint8_t, self, SH_ATK0 + ATK_ACTIVE)) s003_end(self, "attack window over");
    else if (*age >= 200.0f) s003_end(self, "age 200");
}

static void *s003_new(MtDTI *dti) { (void)dti; return shell_new(&s_cls); }
static MtDTI *s003_dti(void *self) { (void)self; return &s_cls.dti; }
static void s003_delete(void *self) { shell_free(&s_cls, self); }

void *gcf_stepfire_post(void *owner, const float *pos, uint32_t area)
{
    if (!pos) return 0;
    if (!s_cls.registered)
        shell_register(&s_cls, &gcf_shells, "uShellGcf003", B_SIZE, s003_new, s003_delete, s003_dti, s003_move,
                       s003_setup, 0);
    void *param = shell_param(&gcf_shells, owner, "stepfire");
    if (!param) return 0;
    void *shell = shell_new(&s_cls);
    if (!shell) { shell_param_free(param); return 0; }
    FIELD(uint8_t, shell, B_AREA) = (uint8_t)area;
    float *st = GCF_VEC(shell, B_START);
    st[0] = pos[0]; st[1] = pos[1]; st[2] = pos[2];
    FIELD(uint32_t, shell, B_SERIAL) = ++s_serial;
    return shell_start(&gcf_shells, shell, param, "stepfire");
}
