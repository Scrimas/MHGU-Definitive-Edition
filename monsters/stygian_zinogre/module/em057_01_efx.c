/* em057_01_efx.c: Stygian Zinogre's code-posted effects through GU's effect gateway (notes/plan.md, test 1
 * 2026-10-28: GU Zinogre effects on Stygian). C = confirmed in code, S = strong, G = guess.
 *
 * GU (C, MHGU 1.4): uEm057_00 slot 116 0xf060c4(self, id, req) posts PEL u (this+0xb624) list-2 record rec(id)
 * through 0x6ff74(self, 2, rec, req): ids >= 1000 from the class table 0x16a63f4, the others through uEnemy's 0xa3e98
 * (table 0x159fa1c); req = self+0xb640, whose byte +0xc every caller sets to EN_AREA. Its callers for any variant:
 *   eefda4, charge state change: 1004 in cat 11 for variant 0, else 1005 -> 120 / 90 = em057_00_002 joint 2;
 *   slot 129's start work (eefed0, every action) and ef41xx keep looping effects in this+0xcb08 / 0xcb0c / 0xcb10:
 *   1001 / 1002 / 1003 / 1007 -> 30 / 31 / 32 / 32 = em057_00_000 joint 2, masks 2 / 4 / 1 / 1 (1006 -> 42: no
 *   record); 1008 / 1009 -> 250 / 280: no record;
 *   uEnemy 0xa4274, every 30 s while rageOn, unless this+0xb7d2 == 0 (GU clears it for a G-rank Thunderlord only):
 *   ids 0 / 1 -> 1120 / 1121 = em057_00_011 joint 2;
 *   uFestaEnemy 0xca2b4, only when this+0xb720 is set (G: GU's Hyper state, 139 readers): 47 + k -> 1300.. (1301 =
 *   em057_00_500, Zinogre's own file).
 * 4U (C, MH4U v1.1): the class posts the charge change 0x856f0c ((58, cat 11 ? 14 : 11) = em049_005 / em049_002 at
 * joint 1 / 2, then sound 213 / 210 at that joint, 0x304c34), and the aura controller 0x322f18 (outside the class)
 * keeps one looping effect on the monster, joint 2, for its state: none (0x94d7a8), enraged (rageOn: (58, 17) =
 * em049_011, mask -1), charged (0x90f90c: (58, 9) = em049_000 mask 1), else the slot-51 query 1 answering 1 / 2:
 * em049_000 mask 2 / 4. Zinogre's are (57, 11) / (57, 0) = em048_011 / em048_000, which GU's em057_00_011 /
 * em057_00_000 records copy with the same joint and masks. Its loop sounds 201 / 202 / 203 (0x322d90) are not ported
 * here (sounds batch). 4U has no Hyper.
 * So for Stygian: the charge change takes 4U's file (1004 / 1005 -> 3205 in cat 11, else 3202, PEL list-2 records of
 * build_em057_01_arc.py SHELL_FX) and 4U's sound; the aura is 4U's controller itself (em057_01_efx_frame, every frame
 * from the slot-125 hook), so GU's aura posts (1001 / 1002 / 1003 / 1007 and the enraged ids 0 / 1) answer 0, GU's
 * own "no record" result (its slots then hold 0 and its stops skip them). Test 2026-10-28 (user: "a full ball of
 * effect", fps falling, cleared when the monster changes area): the first version swapped em049_011 into GU's 30 s
 * enraged post, which GU never stops (its em057_00_011 ends by itself; 4U's em049_011 loops until the controller
 * removes it), so one more aura stacked every 30 s. Hyper id 48 -> no effect (logged); GU's common records (cm202 /
 * cm200) stay. Not ported: the controller's loop sounds 201 / 202 / 203 (0x322d90, sounds batch).
 * Point posts (sz_efx_world, C; notes/b5-shells.md 8): 4U posts its shell and ground effects at a point (0xc08628,
 * nothing attached). GU's monster entry 0x6ff74 attaches every post to the monster's model when the request names no
 * target (req+0xd0 = vt+0x130(self), req+0x1c |= 2), so the effect takes the monster's model frame and scale (as
 * Gogmazios' ground effects, 2.5x too big); GU's own point posts (0x179d3c) leave the target empty and go through
 * 0x40978, as 0x53b500 does after filling an unset area (req+0xc = 254) with the unit's. So sz_efx_world calls
 * 0x53b500 itself (the monster's PEL u this+0xb624 and PEL-tied sounds this+0xb628, what 0x6ff74 passes through
 * slot 78 0x6fe48). Request overrides (req+0x14 bit i -> field i of the body; em089_efx.c, 0x179d90): bit 1 rotation
 * in degrees at req+0x30, bit 19 ground flags at req+0x6c. Ground flags = 4U 0xc074b8: (2 << kind) | 1, kind >= 6 ->
 * 3; an EFL element shows when its ground mask (element word 4) meets them (4U 0xafc574; GU keeps the words, its
 * records +0x4c and the request body +0x5c default to -1 = every ground set at once).
 * The posted records need GU's world transform mode (record +0x36 3 / +0x3e 6 = mode 3, efl4u2gu PEL_TAIL_WORLD): the
 * unit setup (effect slot 32 0x32aa44) attaches the root node to the target in modes 0-2 and copies a world position
 * in modes 3 / 4 (C). Test 5 with the attach tail (mode 2) and no target drew them away from the point (user:
 * "shifted towards the left of his body"); GU's own joint -1 code posts use mode 3 (notes/b5-shells.md 8e).
 * Multiplayer: each machine runs these for its own copy (the dispatcher and GU's posts run on every machine, S);
 * effects and sounds are local. */
#include "em057_01.h"
#include "alloc.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

typedef void *(*efx_post_t)(void *self, uint32_t mode, uint32_t rec, void *req);
#define efx_post_u  FN(efx_post_t, 0x6ff74)     /* PEL u list `mode` record, returns the effect or 0 */
typedef void *(*sndPos_t)(void *mgr, uint32_t id, void *owner, const float *pos, uint32_t area, int32_t m2);
#define sndPos      FN(sndPos_t, 0x4efb98)      /* [0x312484] */
typedef void (*efx_stop_t)(void *eff, uint32_t kill);
#define efx_stop    FN(efx_stop_t, 0x32a400)    /* 1: vt+0xa4 and state 2 (kill; GU's slot reset vt118 0xeeebb0) */
#define rageOn      FN(selfInt_t, 0x8172c)      /* [0x954e48] W+0x530 == 1 (dala_parts.c) */

#define REQ         0xb640  /* GU's effect request in the monster; its byte +0xc = the area, set before each post */
/* the aura's handle and state, in GU's type-52 material fields: the material init (vt118 0xeeed88) writes them for a
 * type-52 material only, none in em049's model, and slot 132, their only reader, is skipped for variant 1 (C;
 * em057_01_fix.c); the ctor sets the handle to 0 and the state to -1 (eee8f8 / eee950: test 3 logged "255 -> 0") */
#define AURA_EFX    0xcac4  /* uMHProofEffect * [4U controller +0x3c] */
#define AURA_STATE  0xcacc  /* u32: state 1..4 | area << 8 [4U controller +0x31] */
#define AURA_SNDA   0xcad0  /* float loop-sound timer A [4U controller +64] (type-52 fields too: written by the ctor */
#define AURA_SNDB   0xcad4  /* float timer B [+68]   and the material reset eeecd8 only, read by slot 132 only) */
#define AURA_LINES  60u

static const uint16_t s_aura_rec[5] = {0, 3250, 3225, 3200, 3211};   /* em049_000 masks 2 / 4 / 1, em049_011 */

typedef void *(*unitEfxPost_t)(void *unit, void *pel, uint32_t mode, uint32_t id, void *req, void *tied);
#define unitEfxPost FN(unitEfxPost_t, 0x53b500)
typedef void (*efx_req_t)(void *req);
#define efx_req_ctor FN(efx_req_t, 0x40b10)
#define efx_req_dtor FN(efx_req_t, 0x40b50)
#define PEL_U_OBJ   0xb624  /* the monster's PEL u */
#define PEL_SE_OBJ  0xb628  /* its PEL-tied sounds */
#define REQ_SIZE    0x100u  /* request object ~0xd8 B */
#define REQ_FIELDS  0x14    /* body field-override bits */
#define REQ_ROT     0x30    /* float[4] degrees, bit 1 */
#define REQ_GROUND  0x6c    /* u32 ground flags, bit 19 */
#define REQ_FLAGS   0x1c    /* 1: world position, 2: attach */
#define REQ_POS     0xc0
#define REQ_TARGET  0xd0    /* attach model (0x6ff74 fills vt+0x130(monster) only when 0) */
#define VT_ATTACH   0x130   /* unit slot 76: the attach model getter (this+0xfd0, shells too; em089_efx.c) */
#define EFX_NODE    0x150   /* transform node, position +0x40 (0x32a45c) */

int sz_efx_alive(void *eff)                     /* unit state 1 / 2 (dala_efx.c) */
{
    return eff && (FIELD(uint32_t, eff, 0xc) & 7) - 1 < 2;
}

void sz_efx_finish(void *eff)                   /* 0x32a400 mode 0: asks it to finish (4U 0xc470dc on a one-shot) */
{
    if (sz_efx_alive(eff)) efx_stop(eff, 0);
}

int sz_efx_pos(void *eff, float *out)           /* where GU placed it: node +0x40 (0x32a45c writes it) */
{
    uint8_t *n = sz_efx_alive(eff) ? FIELD(uint8_t *, eff, EFX_NODE) : 0;
    if (!n) return 0;
    for (int i = 0; i < 3; i++) out[i] = FIELD(float, n, 0x40 + 4 * i);
    return 1;
}

uint32_t sz_ground_flags(uint32_t kind)         /* 4U 0xc074b8..0xc07524 */
{
    return (kind < 6 ? 2u << kind : 2u) | 1u;
}

/* point post of PEL u list `list` record `id` (the record needs the world tail, efl4u2gu PEL_TAIL_WORLD) */
static void *efx_point(void *self, uint32_t list, uint32_t id, const float *pos, const float *rot, uint32_t ground)
{
    uint32_t buf[REQ_SIZE / 4 + 4];
    void *req = (void *)(((uint32_t)buf + 15u) & ~15u), *eff;
    if (!self || !pos) return 0;
    if (FIELD(uint8_t, self, EN_ACT_CAT) == 12 && FIELD(uint8_t, self, EN_ACT_NUM) == 255) return 0;   /* 0x6ff94 */
    efx_req_ctor(req);
    FIELD(uint32_t, req, REQ_FLAGS) |= 1u;
    for (int i = 0; i < 3; i++) FIELD(float, req, REQ_POS + 4 * i) = pos[i];
    FIELD(float, req, REQ_POS + 12) = 0.0f;
    if (rot) {
        FIELD(uint32_t, req, REQ_FIELDS) |= 2u;
        for (int i = 0; i < 3; i++) FIELD(float, req, REQ_ROT + 4 * i) = rot[i] * 57.2957795f;
        FIELD(float, req, REQ_ROT + 12) = 0.0f;
    }
    if (ground) {
        FIELD(uint32_t, req, REQ_FIELDS) |= 0x80000u;
        FIELD(uint32_t, req, REQ_GROUND) = ground;
    }
    eff = unitEfxPost(self, FIELD(void *, self, PEL_U_OBJ), list, id, req, FIELD(void *, self, PEL_SE_OBJ));
    efx_req_dtor(req);
    return eff;
}

void *sz_efx_world(void *self, uint32_t id, const float *pos, const float *rot, uint32_t ground)
{
    return efx_point(self, 2, id, pos, rot, ground);
}

/* 4U 0xc08698 with request +0x5c = a shell (an effect that rides the shell): GU shells' own request (0x4a1d34, as
 * em089_efx.c post_full, tested on Gogmazios' flying blobs): attach model = the unit's vt+0x130, flags 1 | 2, world
 * position = the unit's (+0x40), req+4 = the unit, req+0xc = its area; posted through the monster's PEL (0x6ff74) */
void *sz_efx_on(void *self, uint32_t id, void *unit)
{
    typedef void *(*attach_t)(void *);
    uint32_t buf[REQ_SIZE / 4 + 4];
    void *req = (void *)(((uint32_t)buf + 15u) & ~15u), *eff;
    if (!self || !unit) return 0;
    efx_req_ctor(req);
    FIELD(void *, req, REQ_TARGET) = ((attach_t)((*(uint32_t **)unit)[VT_ATTACH / 4]))(unit);
    FIELD(uint32_t, req, REQ_FLAGS) |= 3u;
    for (int i = 0; i < 3; i++) FIELD(float, req, REQ_POS + 4 * i) = FIELD(float, unit, 0x40 + 4 * i);
    FIELD(float, req, REQ_POS + 12) = 0.0f;
    FIELD(void *, req, 0x4) = unit;
    FIELD(uint8_t, req, 0xc) = FIELD(uint8_t, unit, 0x1054);
    eff = efx_post_u(self, 2, id, req);
    efx_req_dtor(req);
    return eff;
}

/* 4U 0x312484(mgr, id, owner, pos, area, -2) = GU 0x4efb98 (dala_shell.h, C) */
void sz_snd_at(void *self, uint32_t id, const float *pos, uint32_t area)
{
    void *mgr = *(void **)MAIN(SND_MGR);
    if (mgr && self && pos) sndPos(mgr, id, self, pos, area & 0xff, -2);
}

/* 4U aura controller 0x322f18 (C): 0 = none (0x94d7a8: action category 11 or 14, or the death action 12 / 255),
 * 4 = enraged (rageOn), 3 = charged (0x90f90c), else uEm048 slot 51 query 1 (0x857a5c): charge work+0 < 25 -> 0,
 * < 50 -> 1, < 75 -> 2, else 3. GU keeps action, rage, charge flag and work+0 where 4U's code reads them (C:
 * em057_01_start.c, game.h). */
static uint32_t aura_state(void *self)
{
    uint32_t cat = FIELD(uint8_t, self, EN_ACT_CAT), num = FIELD(uint8_t, self, EN_ACT_NUM);
    int32_t c;
    if (cat == 11 || cat == 14 || (cat == 12 && num == 255)) return 0;
    if (rageOn(self)) return 4;
    if (isCharged(self)) return 3;
    c = FIELD(int16_t, WORK(self), 0);
    return c < 25 ? 0 : c < 50 ? 1 : c < 75 ? 2 : 3;
}

/* 4U 0xb0709c(unit, &timer): 1 when the timer is or reaches 0 (then 0), else counts it down by the unit's dt */
static int aura_timer(void *self, uint32_t off)
{
    float *t = &FIELD(float, self, off);
    if (*t > 0.0f) {
        *t -= FIELD(float, self, EN_DT);
        if (*t > 0.0f) return 0;
    }
    *t = 0.0f;
    return 1;
}

/* 4U 0x322d90(controller, state) (C), every frame after the state step: two repeating sounds at joint 2 (0x2fcc50
 * with the unit's area and -2 = sz_snd). Timer A (+64): states 1 / 2 -> 201 every 58, 3 -> 202 every 62, 4 -> 203
 * every 46; timer B (+68): state 2 -> 208, 3 / 4 -> 206, every 48. A timer that runs out in state 0 (or B in state 1)
 * stays at 0 and fires as soon as a state that plays comes. */
static void aura_sounds(void *self, uint32_t st)
{
    static const uint16_t a_id[5] = {0, 201, 201, 202, 203}, b_id[5] = {0, 0, 208, 206, 206};
    static const float a_gap[5] = {0, 58.0f, 58.0f, 62.0f, 46.0f};
    if (aura_timer(self, AURA_SNDA) && a_id[st]) {
        sz_snd(self, a_id[st], 2, 0x322e14);
        FIELD(float, self, AURA_SNDA) = a_gap[st];
    }
    if (aura_timer(self, AURA_SNDB) && b_id[st]) {
        sz_snd(self, b_id[st], 2, 0x322ec8);
        FIELD(float, self, AURA_SNDB) = 48.0f;
    }
}

/* every frame (em057_01_diag.c, slot 125): one aura for the state; a new state removes the old one (4U 0xc470dc,
 * here GU's kill) and posts its own (4U 0xc08698 on the monster, joint 2: the records' joint) and restarts both
 * sound timers at 0 (0x322fe8; not for state 0); then the loop sounds (aura_sounds). Area change (C): 4U's controller
 * skips its frame while the area move runs (W+0x1dd == 1, set by the move 0x68aa58) and posts again once its handle
 * test 0x37ecd4 finds the effect gone, which the area change does in 4U; GU leaves the effect alive in the old area,
 * where it went on drawn on its own (issue #8: "a dragonblight orb stays on the map and moves on its own"), so the
 * area change stops it here, then posts the state's aura in the new area. */
void em057_01_efx_frame(void *self)
{
    static uint32_t s_lines;
    uint32_t st = aura_state(self), area = FIELD(uint8_t, self, EN_AREA), old = FIELD(uint32_t, self, AURA_STATE);
    void *h = FIELD(void *, self, AURA_EFX);
    if (h && !sz_efx_alive(h)) h = 0, old = 0;          /* 4U 0x37ecd4: a dead handle -> state 0, posted again */
    else if (h && (old >> 8) != area) {
        efx_stop(h, 1);                                 /* GU keeps it alive across the area change (issue #8) */
        h = 0, old = 0;
    }
    if (h != FIELD(void *, self, AURA_EFX) || (old & 0xff) != st) {
        if (h) efx_stop(h, 1);
        h = 0;
        if (st) {
            FIELD(uint8_t, self, REQ + 0xc) = (uint8_t)area;
            h = efx_post_u(self, 2, s_aura_rec[st], (uint8_t *)self + REQ);
            FIELD(float, self, AURA_SNDA) = 0.0f;
            FIELD(float, self, AURA_SNDB) = 0.0f;
        }
        FIELD(void *, self, AURA_EFX) = h;
        FIELD(uint32_t, self, AURA_STATE) = st | area << 8;
        if (s_lines < AURA_LINES) {
            s_lines++;
            logf("szport: em057_01 aura %u -> %u (record %u, effect %x, area %u)", old & 0xff, st, s_aura_rec[st],
                 (uint32_t)(uintptr_t)h, area);
        }
    }
    aura_sounds(self, st);
}

/* 4U 0x304c34(mgr, id, owner, joint, area, -2): a point sound at the joint's position now (dala_shell.h, C) */
static void snd_at_joint(void *self, uint32_t id, uint32_t joint)
{
    float p[4];
    jointPos(self, joint, p);
    sz_snd_at(self, id, p, FIELD(uint8_t, self, EN_AREA));
}

/* GU uEm057_00 slot 116 0xf060c4(self, id, req) -> effect or 0 */
int em057_01_efx_c(uint32_t *regs)
{
    static uint8_t s_hyper;
    void *self = (void *)regs[R0];
    uint32_t id = regs[R1], cat11;
    if (!self || FIELD(uint16_t, self, EN_ID) != STYGIAN_ZINOGRE_EM_ID) return 0;
    switch (id) {
    case 1001: case 1002: case 1003: case 1007: case 0: case 1:     /* the aura: em057_01_efx_frame */
        regs[R0] = 0;
        return 1;
    case 1004: case 1005:
        cat11 = FIELD(uint8_t, self, EN_ACT_CAT) == 11;
        regs[R0] = (uint32_t)efx_post_u(self, 2, cat11 ? 3205 : 3202, (void *)regs[R2]);
        snd_at_joint(self, cat11 ? 213 : 210, cat11 ? 1 : 2);
        return 1;
    default:
        if (id < 47 || id >= 1000) return 0;
        if (s_hyper < 4) {
            s_hyper++;
            logf("szport: em057_01 GU Hyper effect id %u (cat %u/%u)%s", id, FIELD(uint8_t, self, EN_ACT_CAT),
                 FIELD(uint8_t, self, EN_ACT_NUM), id == 48 ? ": Zinogre's em057_00_500, not posted" : "");
        }
        if (id != 48) return 0;
        regs[R0] = 0;
        return 1;
    }
}

/* Ground sets of the motion-synced records (issue #6; C unless marked): 4U's motion post (0x391b50 -> 0xc09908, enemy
 * branch) takes the ground kind from the monster's ground record W+0x5f0 (attribute word +8, sz_effect_c094e8's bits)
 * and the effect keeps the EFL elements whose ground word meets sz_ground_flags(kind). GU's PEL records and requests
 * default to -1 = every set at once; here the sets are em049_018 (MEF 3000 / 3001: 0x22, 0x54, lava 0x8, 3001 also
 * 0x7e) and em049_007 (3008: 0x22, 0x54, 0x8, 0x76). Hook on GU 0x70028 (uEm057_00 slot 75 = uFestaEnemy's, the
 * PSL post (this, list, PSL entry data, slot, req), req = its fifth argument = regs[8], the caller's stack: GU's PSL
 * player builds a fresh request per post, 0x53b7e0). GU's twin of W+0x5f0 is not identified: the ray of the slams
 * (0x183ad0, mask 64) down through the ground under the monster (rec+0x5b4) (S). */
typedef float (*groundRay_t)(void *mgr, const float *from, const float *to, uint32_t area, uint8_t *hit, void *out,
                             uint32_t mask);
#define groundRay    FN(groundRay_t, 0x183ad0)  /* [0x2bad24] */
#define COLL_MGR     (*(void **)MAIN(0x21270e0)) /* its manager [*0x10574fc] */
#define REC_GROUND_Y 0x5b4

/* MEF byte 0 of Stygian's records (4U em048_0 + em049_1, = build_em057_01_arc.py MEF_B0; C): 4U's motion-effect queue
 * 0x391a60 posts a record with b0 != 0 only when bit b0 of its unit's mask (enemy: this+0xca8, the bits its action
 * handlers set every frame, cleared after the frame's posts 0x393524) is set; the 1000-range records have b0 0. GU
 * keeps that per-action state as one number, EN_MOVECLASS (bit k -> k, cleared every frame 0x6f5a4), set by the
 * twins of every 4U handler that sets a bit (2026-11-19: 4U uEm048 bits 1-7 / 9 in 23 handlers; GU's kept ones store
 * the same numbers, e.g. 7/109 efbb04 = 4U 0x84f138: 1 while charged; the ported ones in em057_01_mv_*.c), but its PSL /
 * PEL carry no such condition, so the PSL hook applies 4U's rule (issue #8: the uncharged tail swipe 7/109 posted
 * the charged bolts 3030, the back slam 0x227 both 3000 (b0 6, uncharged) and 3001 (b0 7, charged)). Zinogre's roar
 * records 42 / 43 (em048_0, motion 0x314, b0 5): 4U 0x847274(k) sets bit 5 for k = 0, 2-5 (1/9 1/38, 1/37, 1/39 1/42
 * 1/43), not for k = 1 (1/34), and 1/2 (0x852fd8) plays 0x314 with no mask (tools/gate4u.py); GU ef45e0 stores 5 for
 * r1 0 / 2 only (1/34 = r1 1), its 1/2 (ef51a8) none, and em057_01_mv_f.c 5 for 1/39 1/42 1/43 (C). */
static const uint16_t s_mef_b0[][2] = {
    {42, 5}, {43, 5}, {3000, 6}, {3001, 7}, {3019, 2}, {3020, 3}, {3021, 3}, {3022, 3}, {3023, 4}, {3027, 4}, {3028, 4},
    {3029, 1}, {3030, 1}, {3031, 1}, {3033, 1}, {3040, 9}, {3041, 9},
};

static uint32_t mef_b0(uint32_t id)
{
    for (uint32_t i = 0; i < sizeof s_mef_b0 / sizeof s_mef_b0[0]; i++)
        if (s_mef_b0[i][0] == id) return s_mef_b0[i][1];
    return 0;
}

/* Ground records on a joint (C, 4U 0x392130 + 0xc4838c, read 2026-11-19): MEF flag 2 (ground) -> effect +0x274 bit
 * 0, flag 4 -> bit 2. With both on a joint record, the effect's per-frame slot 6 puts it at the joint's world position
 * plus the monster's rotation applied to the record offset, y = the ground under the monster (owner type 3 = enemy:
 * W+0x624 = GU rec+0x5b4, S), rotation = the monster's angles + the record's (degrees), of which MEF flag 0x40 / 0x80
 * / 0x100 keeps only x / y / z; the ground flag keeps that running every frame (0xc47eac: state 3). The records
 * (= build_em057_01_arc.py GROUND_JOINT): Zinogre's em048_0 dust on the feet, chin and tail and the tail swipe's
 * em048_008 (14, joint 143, heading only), and Stygian's charged bolts 3029 (charge run 0x219, joint 2) and 3030
 * (tail swipe 0x21a, joint 1). GU's PSL post attaches them to the model (efl4u2gu PEL_TAIL: placed once at the joint,
 * in its frame and at its height; issue #8 tests 2026-11-19: the bolts "don't render at the correct position", the
 * tail swipe's effect "vertically instead of horizontally"), so the hook posts them itself at 4U's point (their
 * list-1 records carry the world tail, no joint, offset or rotation) and em057_01_ground_fx_frame moves them every
 * frame with GU's live setters (as Gogmazios' em089_efx.c). The offset turns as 4U's front point 0x858130, Ry(yaw)
 * Rx(pitch) Rz(roll) (S: the owner matrix's order is not read). Not ported: the monster's size (4U: the scale of its
 * world matrix, also on the effect through MEF flag 0x20). */
typedef void (*efx_set_pos_t)(void *eff, const float *pos, int32_t k);
#define efx_set_pos  FN(efx_set_pos_t, 0x32a45c)   /* writes the node's position */
typedef void (*efx_set_rot_t)(void *xf, const float *rot);
#define efx_set_rot  FN(efx_set_rot_t, 0x8a7dc4)   /* node rotation (x, y, z) in radians */

static const struct {
    uint16_t id, flags;                         /* the 4U record's id and MEF flags */
    uint8_t joint;
    float off[3], rot[3];                       /* its offset and rotation (degrees) */
} k_gjoint[] = {
    {0, 0x226, 40, {-100.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {1, 0x226, 13, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {2, 0x226, 9, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {3, 0x226, 201, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {4, 0x226, 201, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {11, 0x226, 90, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {12, 0x226, 80, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {14, 0x2a6, 143, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {23, 0x226, 50, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {24, 0x226, 40, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f}},
    {3029, 0x226, 2, {0.0f, 0.0f, 360.0f}, {0.0f, 0.0f, 0.0f}},
    {3030, 0x226, 1, {1.0f, 0.0f, 130.0f}, {10.0f, 0.0f, 0.0f}},
};

static struct {
    void *self, *eff;
    uint32_t row;
} s_gjoint[16];                                 /* full: the effect stays where it was posted */

static void gjoint_place(void *self, uint32_t row, float *pos, float *rot)
{
    const uint8_t *rec = REC(self);
    const float *o = k_gjoint[row].off;
    uint32_t f = k_gjoint[row].flags;
    float a[3], s[3], c[3], x, y;
    for (int i = 0; i < 3; i++) {
        a[i] = (float)(RU(rec, REC_ANGLES + 4 * i) & 0xffff) * 0x1.921fb6p-14f;
        s[i] = sinf_gu(a[i]);
        c[i] = cosf_gu(a[i]);
    }
    x = o[0] * c[2] - o[1] * s[2];              /* Rz(roll) */
    y = o[0] * s[2] + o[1] * c[2];
    float v[3] = {x, 0.0f, y * s[0] + o[2] * c[0]};   /* Rx(pitch); its y is the ground's */
    rot_y(v, RU(rec, REC_ANGLES + 4));
    jointPos(self, k_gjoint[row].joint, pos);
    pos[0] += v[0];
    pos[1] = RF(rec, REC_GROUND_Y);
    pos[2] += v[2];
    pos[3] = 0.0f;
    for (int i = 0; i < 3; i++) rot[i] = a[i] + k_gjoint[row].rot[i] * 0.017453293f;
    if (f & 0x40) rot[1] = rot[2] = 0.0f;       /* 4U +0x274 0x80 / 0x100 / 0x200 (0x392130) */
    if (f & 0x80) rot[2] = rot[0] = 0.0f;
    if (f & 0x100) rot[1] = rot[0] = 0.0f;
    rot[3] = 0.0f;
}

void em057_01_ground_fx_frame(void *self)
{
    for (uint32_t i = 0; i < sizeof s_gjoint / sizeof s_gjoint[0]; i++) {
        float p[4] __attribute__((aligned(16))), r[4] __attribute__((aligned(16)));
        void *eff = s_gjoint[i].eff, *xf;
        if (s_gjoint[i].self != self) continue;
        if (!sz_efx_alive(eff)) {
            s_gjoint[i].self = s_gjoint[i].eff = 0;
            continue;
        }
        gjoint_place(self, s_gjoint[i].row, p, r);
        efx_set_pos(eff, p, 0);
        xf = FIELD(void *, eff, EFX_NODE);
        if (xf) efx_set_rot(xf, r);
    }
}

static void *gjoint_post(void *self, uint32_t list, uint32_t row, uint32_t ground)
{
    float p[4], r[4];
    void *eff;
    gjoint_place(self, row, p, r);
    eff = efx_point(self, list, k_gjoint[row].id, p, r, ground);
    for (uint32_t i = 0; eff && i < sizeof s_gjoint / sizeof s_gjoint[0]; i++) {
        if (s_gjoint[i].self && sz_efx_alive(s_gjoint[i].eff)) continue;
        s_gjoint[i].self = self;
        s_gjoint[i].eff = eff;
        s_gjoint[i].row = row;
        break;
    }
    return eff;
}

int em057_01_psl_c(uint32_t *regs)
{
    void *self = (void *)regs[R0], *req = (void *)regs[8];
    if (!self || !req || FIELD(uint16_t, self, EN_ID) != STYGIAN_ZINOGRE_EM_ID) return 0;
    /* PSL entry data = {u32 mask, u16 ids[32], u32 kinds[32], ..} (tools/efl4u2gu.py build_psl), slot = regs[3] */
    const uint8_t *ent = (const uint8_t *)regs[2];
    uint32_t id = ent && regs[3] < 32 ? FIELD(uint16_t, ent, 4 + 2 * regs[3]) : 0, b0 = mef_b0(id);
    if (b0 && FIELD(uint8_t, self, EN_MOVECLASS) != b0) {
        regs[R0] = 0;                                   /* no effect, GU's own "no record" result */
        return 1;
    }
    uint8_t *rec = REC(self);
    uint32_t out[16] = { 0 };
    uint8_t hit = 0;
    float gy = FIELD(float, rec, REC_GROUND_Y);
    float from[4] = { FIELD(float, rec, REC_POS_X), gy + 100.0f, FIELD(float, rec, REC_POS_Z), 0.0f };
    float to[4] = { from[0], gy - 300.0f, from[2], 0.0f };
    void *mgr = COLL_MGR;
    if (mgr) groundRay(mgr, from, to, FIELD(uint8_t, self, EN_AREA), &hit, out, 64);
    uint32_t kind = sz_effect_c094e8(self, hit ? out[2] : 0, 0x391e3c);
    for (uint32_t row = 0; row < sizeof k_gjoint / sizeof k_gjoint[0]; row++) {
        if (k_gjoint[row].id != id) continue;
        regs[R0] = (uint32_t)gjoint_post(self, regs[R1], row, sz_ground_flags(kind));
        return 1;
    }
    FIELD(uint32_t, req, REQ_FIELDS) |= 0x80000u;
    FIELD(uint32_t, req, REQ_GROUND) = sz_ground_flags(kind);
    return 0;
}
