/* seltas_shots.c: the Desert Seltas' and the Desert Seltas Queen's own 4U shots. C = read in code, S = strong.
 *
 * 4U (C): where the Seltas and Queen classes test the species before a shot, the Desert pair posts its own subtypes
 * (monsters/desert_seltas/tools/shots_seltas.py lists them and asserts their data). GU (C): its twins post the species'
 * shell ids 0x13b / 0x139 / 0x127, and at six places skip the post for a variant (`ldrb [this+0xb5f5]; cmp #0; bne`
 * past it): the Desert Seltas' 7/2 7/13 (0xfd5010), 7/7 7/12 (0xfd5e58), 7/52 7/60 7/63 (0xfd7c78, its mode-0 shot;
 * GU keeps `this` in r10 there, so the function's entry notes the unit), 7/57 7/61 (0xfd8028), 7/58 7/62
 * (0xfd84c8), the Queen's 7/56 (0xf9866c); her 7/9 7/15 7/34 7/79 (0xf96a38) post the normal Queen's three shots for
 * her. The 0.1.1 test: "spit attacks without spit effects".
 * Port: a mid hook at each skip goes on to GU's own post (MID_EXIT = the instruction after the branch) and marks the
 * unit; the Queen's three posts in 0xf96a38 mark it too (the swap is the core's since G-rank Crimson Fatalis shares
 * it: module/shellswap.c, these marks call shellswap_mark). The shell request 0x48c4f0 takes the family's def from its
 * per-id cache [mgr + 0x1c + 4 * id] at 0x48c5e8 and hands it to the new shell (0x4a1c84) (C): for a marked request of
 * 0x13b / 0x139 / 0x127 the cache holds our copy for that one read (GU's def on our PEL and hit data, found by file ID),
 * and gets GU's back at the request's exit 0x48c54c, which every path takes. So only these posts see a copy: a normal
 * Seltas or Queen next to them (quest 11140) keeps GU's family, and GU's kinds, directions and timing stay.
 * The ground splash (0.1.8, C; the contributor on 0.1.7: green splashes and a green puddle where his volley from her
 * back lands): GU's Seltas shell class posts a second shell at a ground hit, 0x13a (em076_00_shell01) from 0xfdca90 (r4
 * = the shell that hit), kind 2 for his volley 7/52 7/60 = GU's green em076_00_002. 4U draws that ground effect inside
 * uShell001 (his kinds 117 / 118: em094_202). A mid hook before that post (0xfdcbe4) marks the shell's owner when he
 * is the Desert Seltas, so the request takes our 0x13a copy (em094_202, no tint; tools/shots_seltas.py).
 * The other ground posts (0.1.10, C; the contributor on 0.1.9: on her back their shots are still green where they land;
 * the 0.1.9 effect log showed two GU defs): GU's Seltas class has a shell callback 0xfc6a30 that posts the unit's shell
 * id this+0xcac8 (0x13a) with a kind from a table (his 7/57 shots took kind 1 = GU's green em076_00_002), requests
 * 0xfc6c08 / 0xfc6df0; and GU's Queen shell class 0xf9dc80 posts 0x128 (em069_00_shell01) kind 2 at a ground or wall
 * hit of her shot (request 0xf9dda4), GU's normal-Queen hit effect. Mid hooks before the three requests mark a Desert
 * owner: his takes our 0x13a copy, hers our 0x128 copy (em095_021 = 4U kind 92's ground and wall effect).
 * Every 0x13a of his (0.1.12, C; the 0.1.11 log, quest 11372: two more of GU's 0x13a kinds 1 / 0 after his shell37
 * shots in 7/57 and 7/2, with no mark before them, so from neither 0xfdca90 nor 0xfc6a30): GU creates every shell
 * inside its request (0x4a1c84 has one caller, 0x48c62c), so a mid hook at the request's start (0x48c4f8, r1 = the
 * request: +0x4 shell id, +0xc owner) marks each 0x13a whose owner is the Desert Seltas, whoever posts it. The owner is
 * looked up among the 10 monster slots before its ID is read (requests also come from hunters and stage objects).
 * Multiplayer: every machine runs these handlers and posts its own shots, as GU's do; the swap is local and lasts one
 * call. All addresses through MAIN / FN. Logs: "mhgu-de: shell swap ds" / "dsq" (module/shellswap.c). */
#include <stdint.h>
#include "game.h"
#include "util.h"
#include "port.h"
#include "shellswap.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

#define IS_DS(p)   ((p) && FIELD(uint16_t, (p), EN_ID) == DESERT_SELTAS_EM_ID)
#define IS_DSQ(p)  ((p) && FIELD(uint16_t, (p), EN_ID) == DESERT_SELTAS_QUEEN_EM_ID)

/* our family copies (tools/shots_seltas.py FAMILIES; the build asserts these file IDs) */
#define FID_DS_37   0x10a1cu   /* GU shell 0x13b, em076_00_shell37 */
#define FID_DS_00   0x10a1du   /* GU shell 0x139, em076_00_shell00 */
#define FID_DS_01   0x10a1eu   /* GU shell 0x13a, em076_00_shell01: the volley's ground splash (0.1.8) */
#define FID_DSQ_00  0x10a59u   /* GU shell 0x127, em069_00_shell00 */
#define FID_DSQ_01  0x10a5au   /* GU shell 0x128, em069_00_shell01: her shots' ground splash (0.1.10) */

typedef void *(*shell_owner_t)(void *shell);
#define shellOwner FN(shell_owner_t, 0x4a1b6c)   /* the unit that posted a shell (GU's own getter; 0 = none) */
static void *s_site3;           /* 0xfd7c78's unit, noted by its callers: the Desert Seltas or 0 */

/* the swap (module/shellswap.c): their copies by GU shell id; every 0x13a of his takes his, whoever posts it */
static uint32_t ds_fid(uint32_t id)
{
    return id == 0x13b ? FID_DS_37 : id == 0x139 ? FID_DS_00 : id == 0x13a ? FID_DS_01 : 0;
}
static uint32_t dsq_fid(uint32_t id) { return id == 0x127 ? FID_DSQ_00 : id == 0x128 ? FID_DSQ_01 : 0; }
static int ds_any(uint32_t id) { return id == 0x13a; }
const struct shellswap em076_01_shellswap = { DESERT_SELTAS_EM_ID, "ds", ds_fid, ds_any };
const struct shellswap em069_01_shellswap = { DESERT_SELTAS_QUEEN_EM_ID, "dsq", dsq_fid, 0 };


/* ---- the skips: 1 = on to GU's post (MID_EXIT), 0 = GU's test as it is ---- */
static int skip_ds(uint32_t *regs)
{
    void *self = (void *)regs[R4];
    if (!IS_DS(self)) return 0;
    shellswap_mark(self);
    return 1;
}
int seltas_shot_a_c(uint32_t *regs) { return skip_ds(regs); }   /* 0xfd531c, 0xfd5010 7/2 7/13 (r4 = this) */
int seltas_shot_b_c(uint32_t *regs) { return skip_ds(regs); }   /* 0xfd6130, 0xfd5e58 7/7 7/12 */
int seltas_shot_d_c(uint32_t *regs) { return skip_ds(regs); }   /* 0xfd8240, 0xfd8028 7/57 7/61 */
int seltas_shot_e_c(uint32_t *regs) { return skip_ds(regs); }   /* 0xfd86e4, 0xfd84c8 7/58 7/62 */

/* 0xfd7c78(this, mode) keeps this in r10 at its test: its entry notes the unit (r0 = this). Only mode 0 reaches the
 * test (0xfd7e08 `beq 0xfd7f30`); modes 1 / 2 post 4U's shared kinds 90 / 91 for both species (C). */
int seltas_shot_c0_c(uint32_t *regs) { s_site3 = IS_DS((void *)regs[R0]) ? (void *)regs[R0] : 0; return 0; }
int seltas_shot_c_c(uint32_t *regs)                               /* 0xfd7f30, its mode-0 shot */
{
    (void)regs;
    void *self = s_site3;
    s_site3 = 0;
    if (!self) return 0;
    shellswap_mark(self);
    return 1;
}

int seltas_shot_q_c(uint32_t *regs)                               /* 0xf987d0, 0xf9866c 7/56 (r4 = this) */
{
    void *self = (void *)regs[R4];
    if (!IS_DSQ(self)) return 0;
    shellswap_mark(self);
    return 1;
}
/* 0xf96a38 (7/9 7/15 7/34 7/79): GU posts the normal Queen's three shots for her; mark each (r4 = this) */
static int mark_dsq(uint32_t *regs) { if (IS_DSQ((void *)regs[R4])) shellswap_mark((void *)regs[R4]); return 0; }
int seltas_shot_q1_c(uint32_t *regs) { return mark_dsq(regs); }   /* 0xf96bc4 */
int seltas_shot_q2_c(uint32_t *regs) { return mark_dsq(regs); }   /* 0xf96c74 */
int seltas_shot_q3_c(uint32_t *regs) { return mark_dsq(regs); }   /* 0xf96d24 */

/* 0xfdcbe4: GU's shell class at a ground hit, right before it posts the splash 0x13a (r4 = the shell that hit) */
int seltas_shot_g_c(uint32_t *regs)
{
    void *owner = regs[R4] ? shellOwner((void *)regs[R4]) : 0;
    if (IS_DS(owner)) shellswap_mark(owner);
    return 0;
}

/* 0xfc6c00 / 0xfc6de0: GU's Seltas shell callback 0xfc6a30, right before its requests 0xfc6c08 / 0xfc6df0 (r1 = the
 * request: +0x4 shell id = the unit's this+0xcac8, +0xc owner = the shot's owner, 0x4a1b6c) */
static int mark_child(uint32_t *regs)
{
    uint8_t *req = (uint8_t *)regs[R1];
    void *owner = req ? FIELD(void *, req, 0xc) : 0;
    if (IS_DS(owner) && FIELD(uint32_t, req, 0x4) == 0x13a) shellswap_mark(owner);
    return 0;
}
int seltas_shot_g2_c(uint32_t *regs) { return mark_child(regs); }
int seltas_shot_g3_c(uint32_t *regs) { return mark_child(regs); }

/* 0xf9dd9c: GU's Queen shell class 0xf9dc80 at a ground / wall hit, right before it posts 0x128 (r4 = the shell) */
int seltas_shot_qg_c(uint32_t *regs)
{
    void *owner = regs[R4] ? shellOwner((void *)regs[R4]) : 0;
    if (IS_DSQ(owner)) shellswap_mark(owner);
    return 0;
}
