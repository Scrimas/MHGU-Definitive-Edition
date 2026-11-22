/* efx.h: code-posted effects of the ports (core, 2026-11-22): a record of the monster's PEL u list 2 posted at a world
 * point or on a unit. The GU calls are the ones Gogmazios' em089_efx.c, Dalamadur's dala_efx.c and Stygian Zinogre's
 * em057_01_efx.c found (C there); those keep their own copies. A record without its PEL entry posts nothing (GU
 * 0x3267d0 finds no id: 0 returned, logged). */
#pragma once
#include <stdint.h>

/* at a world point (request flags 1), rotation in radians or 0, through 0x53b500 without the owner's attach (no model
 * scale of the monster; Stygian's sz_efx_world). The record needs the world tail (efl4u2gu PEL_TAIL_WORLD) */
void *efx_world(void *owner, uint32_t id, const float *pos, const float *rot);
/* on a unit (a shell: attach model vt+0x130, flags 3, its position and area), through 0x6ff74: the record follows it
 * (PEL_TAIL_PREV). The unit must outlive the effect: stop it, then wait for it (Dalamadur's fireball) */
void *efx_on(void *owner, uint32_t id, void *unit);
void efx_finish(void *eff);         /* GU 0x32a400(eff, 0): stop emitting, it ends on its own (4U 0xc470dc) */
void efx_kill(void *eff);           /* GU 0x32a400(eff, 1): at once */
int efx_alive(void *eff);           /* unit state 1 / 2 */
