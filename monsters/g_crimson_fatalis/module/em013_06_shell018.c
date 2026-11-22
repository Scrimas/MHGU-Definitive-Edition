/* em013_06_shell018.c: the prominence marker, 4U uShell018 subtype 6 (type 18 via 0x662160; 632 B, vtable 0xe6da6c:
 * init 0xc72504, frame 0xc7277c, kill 0xc72dac). C = read in code, S = strong, G = guess (spec 2026-11-22).
 * Post (0x89c730 in the prominence 0x89c448): position = the eruption point on the ground, angles = (W+0x78, W+0x7c +
 * the column's yaw, W+0x80) raw u32, group 0xffff, flag byte +0x276 = 1. Ctor 0xc72dd8: area = the owner's W+0x14c.
 * Init (C): the effect (87, 22) = em117_205 posted with the default mask (all elements); no attack (0x102c390[6] =
 * -1); life 0x102c344[6] = 30.0; no sound; with the flag set it is not attached to the shell; then the frame runs in
 * the same tick. Frame (C): owner gone -> state 3; life out (0x9aad4c) -> state 2 and, with the flag, the eruption
 * (uShell037 kind 8) at the marker's position with its angles; else the effect is put at the shell's position with
 * rotation (x, y angles, 0) every frame: the marker never moves, so here it is posted once there with that rotation
 * (GCF_EFX_MARKER, a world-point record). The area draw flag (shell / effect +4 bit 0x800 by the area shown) is left
 * to GU (G). Kill (C): the effect is released (0xc470dc) -> efx_finish. */
#include "game.h"
#include "util.h"
#include "em013_06_shell.h"

#define M_STATE   (SHELL_FIELDS + 0x00)   /* u8 0 new, 1 alive, 2 done [+0xf1] */
#define M_LIFE    (SHELL_FIELDS + 0x04)   /* float [+0x13c] */
#define M_EFX     (SHELL_FIELDS + 0x08)   /* void * [+0x26c] */
#define M_SERIAL  (SHELL_FIELDS + 0x0c)
#define M_START   (SHELL_FIELDS + 0x10)   /* float[3] request position */
#define M_ANG     (SHELL_FIELDS + 0x20)   /* u32[3] request angles [+0x110..] */
#define M_SIZE    (SHELL_FIELDS + 0x30)

static shcls_t s_cls;
static uint32_t s_serial;

/* 4U frame 0xc7277c after the owner test; 1 = done */
static int m_step(void *self, void *owner)
{
    if (!shell_timer(self, &FIELD(float, self, M_LIFE))) return 0;
    void *e = gcf_eruption_post(owner, GCF_VEC(self, SH_POS), &FIELD(uint32_t, self, M_ANG));
    static uint32_t s_n;
    if (++s_n <= 30) logf("gcfport: marker %u out: eruption %x", FIELD(uint32_t, self, M_SERIAL), (uint32_t)e);
    return 1;
}

/* slot 16 = 4U slot 24 0xc72dac */
static void m_slot_kill(void *self)
{
    efx_finish(FIELD(void *, self, M_EFX));
    FIELD(void *, self, M_EFX) = 0;
    gcfShellKill(self);
}

/* slot 79: base set-up, the ctor 0xc72dd8 fields, init 0xc72504 and its slot-23 tail call */
static int m_setup(void *self, void *param)
{
    if (gcfShellSetup(self, param) != 1) return 0;
    void *owner = FIELD(void *, param, 0xc);
    FIELD(uint8_t, self, SH_AREA) = FIELD(uint8_t, owner, GCF_EN_AREA);
    float *pos = GCF_VEC(self, SH_POS), *st = GCF_VEC(self, M_START), *p2 = GCF_VEC(self, SH_POS2);
    for (int i = 0; i < 3; i++) pos[i] = p2[i] = st[i];
    for (int i = 0; i < 3; i++) FIELD(uint32_t, self, SH_ANGLES + 4 * i) = FIELD(uint32_t, self, M_ANG + 4 * i);
    /* 4U converts the full u32 (radians = a * 2 pi / 65536): the yaw sum may pass 0xffff, the same angle */
    float rot[3] = {(float)FIELD(uint32_t, self, M_ANG) * (6.28318531f / 65536.0f),
                    (float)FIELD(uint32_t, self, M_ANG + 4) * (6.28318531f / 65536.0f), 0.0f};
    FIELD(void *, self, M_EFX) = efx_world(owner, GCF_EFX_MARKER, pos, rot);
    FIELD(float, self, M_LIFE) = 30.0f;
    FIELD(uint8_t, self, M_STATE) = 1;
    static uint32_t s_n;
    if (++s_n <= 30)
        logf("gcfport: marker %u at %d %d %d yaw %x area %u efx %x", FIELD(uint32_t, self, M_SERIAL), (int32_t)pos[0],
             (int32_t)pos[1], (int32_t)pos[2], FIELD(uint32_t, self, M_ANG + 4), FIELD(uint8_t, self, SH_AREA),
             (uint32_t)FIELD(void *, self, M_EFX));
    if (m_step(self, owner)) FIELD(uint8_t, self, M_STATE) = 2;
    return 1;
}

/* slot 9 = 4U slot 23 */
static void m_move(void *self)
{
    if (FIELD(void *, self, M_EFX) && !efx_alive(FIELD(void *, self, M_EFX))) FIELD(void *, self, M_EFX) = 0;
    gcfShellMove(self);
    if (!shell_live(self)) return;
    if (FIELD(uint8_t, self, M_STATE) == 2) { VCALL0(self, GCF_SLOT_KILL); return; }
    if (FIELD(uint8_t, self, M_STATE) != 1) return;
    void *owner = shell_owner(self);
    if (owner && m_step(self, owner)) FIELD(uint8_t, self, M_STATE) = 2;
}

static void *m_new(MtDTI *dti) { (void)dti; return shell_new(&s_cls); }
static MtDTI *m_dti(void *self) { (void)self; return &s_cls.dti; }

static void m_delete(void *self)
{
    efx_kill(FIELD(void *, self, M_EFX));          /* deleted without our kill (area / quest teardown) */
    FIELD(void *, self, M_EFX) = 0;
    shell_free(&s_cls, self);
}

void *gcf_marker_post(void *owner, const float *pos, const uint32_t *angles)
{
    if (!pos || !angles) return 0;
    if (!s_cls.registered)
        shell_register(&s_cls, &gcf_shells, "uShellGcf018", M_SIZE, m_new, m_delete, m_dti, m_move, m_setup,
                       m_slot_kill);
    void *param = shell_param(&gcf_shells, owner, "marker");
    if (!param) return 0;
    void *shell = shell_new(&s_cls);
    if (!shell) { shell_param_free(param); return 0; }
    float *st = GCF_VEC(shell, M_START);
    st[0] = pos[0]; st[1] = pos[1]; st[2] = pos[2];
    for (int i = 0; i < 3; i++) FIELD(uint32_t, shell, M_ANG + 4 * i) = angles[i];
    FIELD(uint32_t, shell, M_SERIAL) = ++s_serial;
    return shell_start(&gcf_shells, shell, param, "marker");
}
