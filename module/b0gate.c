/* b0gate.c: the 4U condition of ported motion-effect records (notes/porting-guide.md, "MEF byte 0 gates the post";
 * C). 4U's motion-effect queue 0x391a60 posts a MEF record whose byte 0 (b0) is not 0 only while bit b0 of the unit's
 * mask this+0xca8 is set. The action handlers set their bits every frame, and the component clears the mask after
 * the frame's posts (0x393524). GU's PSL posts the record whenever its motion plays, so a mid hook in uFestaEnemy
 * slot 75 0x70028 (the PSL post, every monster's) at 0x70050 (r5 = this, r2 = the PSL entry data, r3 = the slot)
 * skips the post (exit 0x7016c: return 0, GU's own no-post path) when the record's bit is not in the 4U mask of the
 * current action. Each port lists its records, the bits each action sets (tools/gate4u.py finds them in 4U's
 * dispatcher; each row is read in the 4U code before it goes in) and the bits 4U sets outside its actions. GU's own
 * records (other ids) are never touched. Stygian Zinogre's GU class keeps 4U's bits as one number (EN_MOVECLASS),
 * which its own PSL hook tests (em057_01_efx.c). A port whose 4U code is tied to the post of its own records is
 * told of them (s_posts: G-rank Crimson Fatalis' stepfire, whose footstep sections GU keeps only as PSL records). */
#include <stdint.h>
#include "game.h"
#include "util.h"
#include "b0gate.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

#define PSL_KIND    0x44        /* PSL entry data: u32 kind[32] at +0x44, u16 id[32] at +4 */
#define KIND_PEL_U  4

static const struct b0port *const s_ports[] = {
    &em005_01_b0port, &em068_01_b0port, &em069_01_b0port, &em070_01_b0port, &em089_b0port, &em090_00_b0port,
    &em090_01_b0port,
};
static const struct b0post *const s_posts[] = { &em013_06_b0post };

static uint32_t mask4u(const struct b0port *p, const void *self, uint8_t cat, uint8_t num)
{
    uint32_t m = p->extra ? p->extra(self) : 0;
    for (uint32_t i = 0; i < p->nact; i++)
        if (p->act[i].cat == cat && p->act[i].num == num) m |= 1u << p->act[i].bit;
    return m;
}

/* GU 0x70050: 1 = skip the post (exit 0x7016c) */
int b0gate_c(uint32_t *regs)
{
    static uint32_t s_lines;
    const void *self = (const void *)regs[R5];
    const uint8_t *data = (const uint8_t *)regs[R2];
    const struct b0port *p = 0;
    uint32_t slot = regs[R3], id;
    if (!self || !data || slot >= 32) return 0;
    for (uint32_t i = 0; i < sizeof s_posts / sizeof s_posts[0]; i++)
        if (FIELD(uint16_t, self, EN_ID) == s_posts[i]->em &&
            FIELD(uint32_t, data, PSL_KIND + 4 * slot) == KIND_PEL_U)
            s_posts[i]->posted((void *)self, FIELD(uint16_t, data, 4 + 2 * slot));
    for (uint32_t i = 0; i < sizeof s_ports / sizeof s_ports[0]; i++)
        if (FIELD(uint16_t, self, EN_ID) == s_ports[i]->em) p = s_ports[i];
    if (!p || FIELD(uint32_t, data, PSL_KIND + 4 * slot) != KIND_PEL_U) return 0;
    id = FIELD(uint16_t, data, 4 + 2 * slot);
    for (uint32_t i = 0; i < p->nrec; i++) {
        if (p->rec[i].id != id) continue;
        uint8_t cat = FIELD(uint8_t, self, EN_ACT_CAT), num = FIELD(uint8_t, self, EN_ACT_NUM);
        uint32_t on = mask4u(p, self, cat, num) >> p->rec[i].b0 & 1;
        if (++s_lines <= 60)
            logf("%s: effect %u (4U bit %u) in action %u/%u: %s", p->tag, id, p->rec[i].b0, cat, num,
                 on ? "posted" : "skipped (4U condition)");
        return !on;
    }
    return 0;
}
