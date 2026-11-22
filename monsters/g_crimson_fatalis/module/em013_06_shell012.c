/* em013_06_shell012.c: the heatwave shots, 4U uShell012 subtypes 51 (ahead) / 54 / 55 (sides) and the event quest's
 * 66 / 67 / 68 (type 12 via 0x661f6c; 688 B, vtable 0xe6d7cc: init 0xc61058, frame 0xc61b80, kill 0xc6362c).
 * C = read in code, S = strong, G = guess (spec 2026-11-22).
 * Post (4U 0x899c30, 7/74..76 at its motionCheck frame): offset A, velocity B, acceleration C (local), group 0xffff.
 * Ctor 0xc636d8 (owner = a uEnemy): area = the owner's W+0x14c, position = the owner's W+0x198; angles 0.
 * Init (C): the flight effect (87, 21) = em117_204, mask 1 for 51 / 66, 2 for the others, posted on the shell (flags
 * 0x110, white: no colour change) -> GCF_EFX_HEAT / _SIDE; then position += A turned by Rz(owner z angle W+0x1b0),
 * Rx(x angle W+0x1a8), Ry(yaw W+0x1ac), velocity and acceleration by the yaw only; life 0x10291c8[sub] = 60.0; attack
 * 0x9ab120(0x1028958, 0x1028904, 0x10290b0[sub] = 35 / 37 / 45 / 46, a 31, b 2) = HDS GCF_HDS_HEAT.. (start 0, length
 * 99, capsules on bone 1001: r1400 ahead, r700 sides; type 6, the event's 7); group 0xffff; no init sound; the frame
 * runs in the same tick.
 * Frame (C): owner gone -> 3; life out (0x9aad4c) -> 2 (no impact branch for these subtypes); previous position =
 * position (+0x120, the capsule's second point); the window length = 100 every frame (the record's 99 never runs out);
 * position += v dt + a dt^2 / 2, then v += a dt (0x9ab0a0); no map test and no hit test: they pass through walls and
 * hunters, life 60 is the only end; sound 221 on the shell from a 30-frame timer that fires on the first tick only
 * (the frame adds dt, the timer takes it again): once; angles from the velocity.
 * Kill (C): the effect is not released (S: it ends with its target). In GU the shell must outlive an effect attached to
 * it, so the kill stops it and waits for it (Dalamadur's fireball, at most 300 frames). */
#include "game.h"
#include "util.h"
#include "em013_06_shell.h"

#define H_SUB     (SHELL_FIELDS + 0x00)   /* u8 subtype [+0xfd] */
#define H_STATE   (SHELL_FIELDS + 0x01)   /* u8 0 new, 1 flying, 2 done [+0xf1] */
#define H_ARMED   (SHELL_FIELDS + 0x02)
#define H_DYING   (SHELL_FIELDS + 0x03)   /* u8 1 = killed, waiting for the effect */
#define H_LIFE    (SHELL_FIELDS + 0x04)   /* float [+0x26c] */
#define H_SND_T   (SHELL_FIELDS + 0x08)   /* float [+0x2a8] */
#define H_EFX     (SHELL_FIELDS + 0x0c)   /* void * [+0x274] */
#define H_SERIAL  (SHELL_FIELDS + 0x10)
#define H_DIE_T   (SHELL_FIELDS + 0x14)   /* float frames waited for the effect */
#define H_OFF     (SHELL_FIELDS + 0x18)   /* float[3] A [+0x278] */
#define H_VEL     (SHELL_FIELDS + 0x28)   /* float[3] B [+0x140] */
#define H_ACC     (SHELL_FIELDS + 0x38)   /* float[3] C [+0x150] */
#define H_PREV    (SHELL_FIELDS + 0x48)   /* float[3] [+0x120] */
#define H_SIZE    (SHELL_FIELDS + 0x58)

#define HEAT_LIFE    60.0f    /* 0x10291c8[sub] */
#define SND_HEAT     221u     /* 0x10283a0[sub] */
#define SND_EVERY    30.0f
#define EFX_DIE_MAX  300.0f

static shcls_t s_cls;
static uint32_t s_serial;

static int ahead(uint32_t sub) { return sub == 51 || sub == 66; }
static uint32_t hds_of(uint32_t sub)
{
    return sub == 51 ? GCF_HDS_HEAT : sub == 66 ? GCF_HDS_HEAT_EV : sub >= 66 ? GCF_HDS_HEAT_SIDE_EV : GCF_HDS_HEAT_SIDE;
}

/* 4U frame 0xc61b80 after the owner test; 1 = done */
static int h_step(void *self, void *owner)
{
    float *life = &FIELD(float, self, H_LIFE);
    shell_timer(self, life);
    if (*life <= 0.0f) return 1;
    float *pos = GCF_VEC(self, SH_POS), *prev = GCF_VEC(self, H_PREV), *p2 = GCF_VEC(self, SH_POS2);
    float *vel = GCF_VEC(self, H_VEL), *acc = GCF_VEC(self, H_ACC);
    for (int i = 0; i < 3; i++) prev[i] = p2[i] = pos[i];
    FIELD(float, self, SH_ATK0 + ATK_TIME) = 100.0f;
    float dt = shell_dt(self), h = dt * dt * 0.5f;                    /* 0x9ab0a0 */
    for (int i = 0; i < 3; i++) { pos[i] += vel[i] * dt + acc[i] * h; vel[i] += acc[i] * dt; }
    float *st = &FIELD(float, self, H_SND_T);
    *st += dt;                                                        /* 0xc624dc */
    if (shell_timer(self, st)) {                                      /* 0xc62e84 */
        *st = SND_EVERY;
        shell_snd_obj(owner, SND_HEAT, self, FIELD(uint8_t, self, SH_AREA));
    }
    float hz = gcf_sqrt(vel[0] * vel[0] + vel[2] * vel[2]);          /* 0xc62514 */
    FIELD(uint32_t, self, SH_ANGLES) = gcf_rad_ang(atan2f_gu(-vel[1], hz));
    FIELD(uint32_t, self, SH_ANGLES + 4) = gcf_rad_ang(atan2f_gu(vel[0], vel[2]));
    FIELD(uint32_t, self, SH_ANGLES + 8) = gcf_rad_ang(atan2f_gu(-vel[0], vel[1]));
    return 0;
}

/* slot 16: deferred kill while the attached effect lives */
static void h_slot_kill(void *self)
{
    void *e = FIELD(void *, self, H_EFX);
    if (e && !efx_alive(e)) FIELD(void *, self, H_EFX) = e = 0;
    if (!e) { FIELD(uint8_t, self, H_DYING) = 0; gcfShellKill(self); return; }
    if (FIELD(uint8_t, self, H_DYING)) return;
    FIELD(uint8_t, self, H_DYING) = 1;
    FIELD(uint8_t, self, H_STATE) = 2;
    FIELD(float, self, H_DIE_T) = 0.0f;
    shell_slots_off(self);
    efx_finish(e);
}

static void h_dying(void *self)
{
    void *e = FIELD(void *, self, H_EFX);
    float *t = &FIELD(float, self, H_DIE_T);
    *t += shell_dt(self);
    if (efx_alive(e) && *t >= EFX_DIE_MAX && *t < EFX_DIE_MAX + 1000.0f) {
        efx_kill(e);
        *t = EFX_DIE_MAX + 1000.0f;           /* one more frame for the effect's own kill */
        return;
    }
    if (efx_alive(e) && *t < EFX_DIE_MAX + 1000.0f + 30.0f) return;
    FIELD(void *, self, H_EFX) = 0;
    FIELD(uint8_t, self, H_DYING) = 0;
    gcfShellKill(self);
}

/* slot 79: base set-up, the ctor 0xc636d8 fields, init 0xc61058 and its slot-23 tail call */
static int h_setup(void *self, void *param)
{
    if (gcfShellSetup(self, param) != 1) return 0;
    void *owner = FIELD(void *, param, 0xc);
    uint8_t *rec = FIELD(uint8_t *, owner, EN_RECORD);
    uint32_t sub = FIELD(uint8_t, self, H_SUB);
    FIELD(uint8_t, self, SH_AREA) = FIELD(uint8_t, owner, GCF_EN_AREA);
    float *pos = GCF_VEC(self, SH_POS), *p2 = GCF_VEC(self, SH_POS2), *prev = GCF_VEC(self, H_PREV);
    for (int i = 0; i < 3; i++) pos[i] = FIELD(float, rec, GCF_REC_POS + 4 * i);
    for (int i = 0; i < 3; i++) FIELD(uint32_t, self, SH_ANGLES + 4 * i) = 0;
    /* 0xc619b0..0xc61a80: A by Rz, Rx, then Ry of the owner's angles; B and C by the yaw only */
    uint32_t ax = FIELD(uint32_t, rec, REC_ANGLES), ay = FIELD(uint32_t, rec, REC_ANGLES + 4),
             az = FIELD(uint32_t, rec, REC_ANGLES + 8);
    const float *a = GCF_VEC(self, H_OFF);
    float sx = sinf_gu(gcf_ang_rad(ax)), cx = cosf_gu(gcf_ang_rad(ax)), sz = sinf_gu(gcf_ang_rad(az)),
          cz = cosf_gu(gcf_ang_rad(az));
    float x1 = cz * a[0] - sz * a[1], y1 = sz * a[0] + cz * a[1];
    float v[3] = {x1, cx * y1 - sx * a[2], sx * y1 + cx * a[2]};
    gcf_rot_y(v, ay);
    for (int i = 0; i < 3; i++) pos[i] += v[i];
    for (int i = 0; i < 3; i++) prev[i] = p2[i] = pos[i];
    gcf_rot_y(GCF_VEC(self, H_VEL), ay);
    gcf_rot_y(GCF_VEC(self, H_ACC), ay);
    FIELD(float, self, H_LIFE) = HEAT_LIFE;
    FIELD(uint8_t, self, H_ARMED) = (uint8_t)shell_arm(&gcf_shells, self, hds_of(sub), 31, 2, 0xffff);
    FIELD(float, self, H_SND_T) = 0.0f;
    /* 4U posts the effect before placing the shell; GU's first effect update reads the shell: post once it is placed
     * (as Dalamadur's fireball) */
    FIELD(void *, self, H_EFX) = efx_on(owner, ahead(sub) ? GCF_EFX_HEAT : GCF_EFX_HEAT_SIDE, self);
    FIELD(uint8_t, self, H_STATE) = 1;
    static uint32_t s_n;
    if (++s_n <= 30)
        logf("gcfport: heatwave %u sub %u at %d %d %d yaw %x area %u hit %u efx %x", FIELD(uint32_t, self, H_SERIAL), sub,
             (int32_t)pos[0], (int32_t)pos[1], (int32_t)pos[2], ay & 0xffff, FIELD(uint8_t, self, SH_AREA),
             FIELD(uint8_t, self, H_ARMED), (uint32_t)FIELD(void *, self, H_EFX));
    if (h_step(self, owner)) FIELD(uint8_t, self, H_STATE) = 2;
    return 1;
}

/* slot 9 = 4U slot 23 */
static void h_move(void *self)
{
    if (FIELD(void *, self, H_EFX) && !efx_alive(FIELD(void *, self, H_EFX))) FIELD(void *, self, H_EFX) = 0;
    gcfShellMove(self);                       /* owner gone -> kill (4U state 3) */
    if (FIELD(uint8_t, self, H_DYING)) { h_dying(self); return; }
    if (!shell_live(self)) return;
    if (FIELD(uint8_t, self, H_STATE) == 2) { VCALL0(self, GCF_SLOT_KILL); return; }
    if (FIELD(uint8_t, self, H_STATE) != 1) return;
    void *owner = shell_owner(self);
    if (owner && h_step(self, owner)) FIELD(uint8_t, self, H_STATE) = 2;
}

static void *h_new(MtDTI *dti) { (void)dti; return shell_new(&s_cls); }
static MtDTI *h_dti(void *self) { (void)self; return &s_cls.dti; }

static void h_delete(void *self)
{
    efx_kill(FIELD(void *, self, H_EFX));          /* deleted without our kill (area / quest teardown) */
    FIELD(void *, self, H_EFX) = 0;
    shell_free(&s_cls, self);
}

void *gcf_heatwave_post(void *owner, uint32_t subtype, const float *off, const float *vel, const float *acc)
{
    if (subtype != 51 && subtype != 54 && subtype != 55 && (subtype < 66 || subtype > 68)) {
        static uint32_t s_n;
        if (++s_n <= 10) logf("gcfport: heatwave subtype %u is not em117's: dropped", subtype);
        return 0;
    }
    if (!off || !vel || !acc) return 0;
    if (!s_cls.registered)
        shell_register(&s_cls, &gcf_shells, "uShellGcf012", H_SIZE, h_new, h_delete, h_dti, h_move, h_setup,
                       h_slot_kill);
    void *param = shell_param(&gcf_shells, owner, "heatwave");
    if (!param) return 0;
    void *shell = shell_new(&s_cls);
    if (!shell) { shell_param_free(param); return 0; }
    FIELD(uint8_t, shell, H_SUB) = (uint8_t)subtype;
    for (int i = 0; i < 3; i++) {
        FIELD(float, shell, H_OFF + 4 * i) = off[i];
        FIELD(float, shell, H_VEL + 4 * i) = vel[i];
        FIELD(float, shell, H_ACC + 4 * i) = acc[i];
    }
    FIELD(uint32_t, shell, H_SERIAL) = ++s_serial;
    return shell_start(&gcf_shells, shell, param, "heatwave");
}
