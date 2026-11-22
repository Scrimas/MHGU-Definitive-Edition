/* em013_06_alias.c: G-rank Crimson Fatalis (GU Fatalis variant 6) takes GU Crimson's (variant 1) branch where GU's
 * class uEm013_00 switches on variants 0 / 1 / 2 with no case for 6 (notes/plan.md 7). C = read in code, S = strong.
 * 4U (C): these sites have no species test in 4U's uEm077 (its 20 species reads, scan of 0x892000..0x8a0000); its
 * fireball post 0x89e788 tests em 79 only, so em 77 / 78 / 117 post the same uShell001 kinds, and every effect file
 * em117 shares with em078 is byte-identical (build_em013_06_arc.py shared_4u): em117 = Crimson at each site. GU's
 * per-variant split there is its data packaging (one shell family set per variant). The sites:
 *   slot 86 0xd8e32c: the shell family preload (0 -> rows 130..133, 1 -> 134..137, 2 -> 138..142, else none: without
 *     it every Crimson shot of variant 6 is refused for want of a resource) -> exit 0xd8e3fc (rows 134..137);
 *   slot 79 0xd8e044: 7/59 / 7/60 in motions 0x205 / 0x206 set the attack flags this+0x13f4 |= 0x38000 for variant 1
 *     (4U 0x89473c runs those slots for em 78 and em 117 alike) -> exit 0xd8e108;
 *   the shot posts 0xd83144 (0xd831c8: families 131 / 135 / 139), 0xd8519c (0xd851c8), 0xd89134 (0xd89324) and
 *   0xd8775c (0xd89840): variant 1's family. Where the pair after the variant load holds the compare, the variant
 *   register is rewritten (6 -> 1); where it holds the load, the load's offset is pointed at a byte holding 1
 *   (0xd89324, whose pair before the load stores s16 and cannot be skipped); where it is movw + ldrb, the hook exits
 *   to the variant-1 branch.
 * Only a variant-6 uEm013_00 can be ours (GU ships variants 0..2); the ID is checked anyway. */
#include <stdint.h>
#include "game.h"
#include "util.h"
#include "alloc.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

#define EN_VARIANT (EN_ID + 5)

static const uint8_t k_variant1 = 1;

static int ours(uint32_t self)
{
    return self && FIELD(uint16_t, (void *)self, EN_ID) == G_CRIMSON_FATALIS_EM_ID;
}

static void note(const char *site)
{
    static uint32_t s_n;
    if (++s_n <= 20) logf("gcfport: variant 6 takes variant 1's branch at %s", site);
}

int em013_06_preload_c(uint32_t *regs)        /* 0xd8e334 (r4 = this) -> 0xd8e3fc */
{
    if (!ours(regs[R4])) return 0;
    note("the shell preload (slot 86)");
    return 1;
}

int em013_06_flags_c(uint32_t *regs)          /* 0xd8e0f8 (r4 = this) -> 0xd8e108 */
{
    if (!ours(regs[R4])) return 0;
    note("the 7/59 / 7/60 attack flags (slot 79)");
    return 1;
}

int em013_06_shot_d_c(uint32_t *regs)         /* 0xd89840 in 0xd8775c (r4 = this) -> 0xd898f8 */
{
    if (!ours(regs[R4])) return 0;
    note("0xd89840");
    return 1;
}

int em013_06_shot_a_c(uint32_t *regs)         /* 0xd831cc in 0xd83144 (r5 = this, r0 = variant): before cmp r0, #2 */
{
    if (regs[R0] == 6 && ours(regs[R5])) { regs[R0] = 1; note("0xd831c8"); }
    return 0;
}

int em013_06_shot_b_c(uint32_t *regs)         /* 0xd851c4 in 0xd8519c (r4 = this, r0 = variant): before cmp r0, #2 */
{
    if (regs[R0] == 6 && ours(regs[R4])) { regs[R0] = 1; note("0xd851c8"); }
    return 0;
}

int em013_06_shot_c_c(uint32_t *regs)         /* 0xd89320 in 0xd89134 (r5 = this, r0 = 0xb5f5): before ldrb r0, [r5, r0] */
{
    if (!ours(regs[R5]) || FIELD(uint8_t, (void *)regs[R5], EN_VARIANT) != 6) return 0;
    regs[R0] = (uint32_t)&k_variant1 - regs[R5];
    note("0xd89324");
    return 0;
}
