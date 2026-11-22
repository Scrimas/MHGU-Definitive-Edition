/* efx.c: code-posted effects of the ports (efx.h). */
#include "game.h"
#include "util.h"
#include "efx.h"

typedef void *(*efx_post_t)(void *self, uint32_t mode, uint32_t id, void *req);
#define efx_post_u   FN(efx_post_t, 0x6ff74)     /* PEL u (this+0xb624) list `mode`, owner attach; effect or 0 */
typedef void *(*unit_efx_post_t)(void *unit, void *pel, uint32_t mode, uint32_t id, void *req, void *tied);
#define unitEfxPost  FN(unit_efx_post_t, 0x53b500)
typedef void (*efx_req_t)(void *req);
#define efx_req_ctor FN(efx_req_t, 0x40b10)
#define efx_req_dtor FN(efx_req_t, 0x40b50)
typedef void (*efx_stop_t)(void *eff, uint32_t now);
#define efx_stop     FN(efx_stop_t, 0x32a400)

#define LIST_CODE    2u       /* PEL list 2 = code posts */
#define PEL_U_OBJ    0xb624   /* the monster's PEL u */
#define PEL_SE_OBJ   0xb628   /* its PEL-tied sounds */
#define REQ_SIZE     0x100u   /* request object ~0xd8 B */
#define REQ_FIELDS   0x14     /* body field-override bits */
#define REQ_ROT      0x30     /* float[4] degrees, bit 1 */
#define REQ_FLAGS    0x1c     /* 1: world position, 2: attach */
#define REQ_POS      0xc0
#define REQ_TARGET   0xd0     /* attach model */
#define VT_ATTACH    0x130    /* unit slot 76: the attach model getter (monsters and shells) */
#define UNIT_AREA    0x1054   /* u8 map area of a monster / shell */

static void post_log(uint32_t id, const char *how, void *eff)
{
    static uint32_t s_n;
    if (++s_n <= 60) logf("mhgu-de: efx post id %u %s -> %x%s", id, how, (uint32_t)eff,
                          eff ? "" : " (no PEL list-2 record: the arc builder's code records)");
}

void *efx_world(void *owner, uint32_t id, const float *pos, const float *rot)
{
    uint32_t buf[REQ_SIZE / 4 + 4];
    void *req = (void *)(((uint32_t)buf + 15u) & ~15u);
    if (!owner || !pos) return 0;
    if (FIELD(uint8_t, owner, EN_ACT_CAT) == 12 && FIELD(uint8_t, owner, EN_ACT_NUM) == 255) return 0;   /* 0x6ff94 */
    efx_req_ctor(req);
    FIELD(uint32_t, req, REQ_FLAGS) |= 1u;
    for (int i = 0; i < 3; i++) FIELD(float, req, REQ_POS + 4 * i) = pos[i];
    FIELD(float, req, REQ_POS + 12) = 0.0f;
    if (rot) {
        FIELD(uint32_t, req, REQ_FIELDS) |= 2u;
        for (int i = 0; i < 3; i++) FIELD(float, req, REQ_ROT + 4 * i) = rot[i] * 57.2957795f;
        FIELD(float, req, REQ_ROT + 12) = 0.0f;
    }
    void *eff = unitEfxPost(owner, FIELD(void *, owner, PEL_U_OBJ), LIST_CODE, id, req, FIELD(void *, owner, PEL_SE_OBJ));
    efx_req_dtor(req);
    post_log(id, "at a point", eff);
    return eff;
}

void *efx_on(void *owner, uint32_t id, void *unit)
{
    uint32_t buf[REQ_SIZE / 4 + 4];
    void *req = (void *)(((uint32_t)buf + 15u) & ~15u);
    if (!owner || !unit) return 0;
    efx_req_ctor(req);
    typedef void *(*attach_t)(void *);
    FIELD(void *, req, REQ_TARGET) = ((attach_t)((*(uint32_t **)unit)[VT_ATTACH / 4]))(unit);
    FIELD(uint32_t, req, REQ_FLAGS) |= 3u;
    for (int i = 0; i < 3; i++) FIELD(float, req, REQ_POS + 4 * i) = FIELD(float, unit, 0x40 + 4 * i);
    FIELD(float, req, REQ_POS + 12) = 0.0f;
    FIELD(void *, req, 0x4) = unit;
    FIELD(uint8_t, req, 0xc) = FIELD(uint8_t, unit, UNIT_AREA);
    void *eff = efx_post_u(owner, LIST_CODE, id, req);
    efx_req_dtor(req);
    post_log(id, "on a unit", eff);
    return eff;
}

void efx_finish(void *eff)
{
    if (efx_alive(eff)) efx_stop(eff, 0);
}

void efx_kill(void *eff)
{
    if (efx_alive(eff)) efx_stop(eff, 1);
}

int efx_alive(void *eff)
{
    return eff && (FIELD(uint32_t, eff, 0xc) & 7) - 1 < 2;
}
