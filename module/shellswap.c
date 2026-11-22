/* shellswap.c: a port's own copies of GU shell families, swapped into GU's shell request for its posts only.
 * C = read in code, S = strong.
 *
 * GU caches a shell family's def per shell id for every monster (0x48c388), so a port's changed def under GU's path
 * would reach GU's own monster too. The shell request 0x48c4f0 takes the def from that cache [mgr + 0x1c + 4 * id]
 * at 0x48c5e8 and hands it to the new shell (0x4a1c84, its one caller 0x48c62c) (C): for a marked request the cache
 * holds the port's copy (found by file ID) for that one read and gets GU's back at the request's exit 0x48c54c, which
 * every path takes. A request is marked by its owner's class hooks (shellswap_mark: Desert Seltas / Queen, whose
 * copies are for some posts only) or here at the request's start 0x48c4f8 (r1 = the request: +0x4 shell id, +0xc
 * owner) when the owner's port takes every post of that id (struct shellswap any). The owner is looked up among the
 * 10 monster slots before its ID is read (requests also come from hunters and stage objects).
 * Users: Desert Seltas / Queen (monsters/desert_seltas/module/seltas_shots.c, its copies by tools/shots_seltas.py),
 * G-rank Crimson Fatalis (monsters/g_crimson_fatalis/module/em013_06_alias.c: GU Crimson's fireball families with the
 * clods hidden). Multiplayer: every machine runs GU's handlers and posts its own shells; the swap is local and lasts
 * one call. Log: "mhgu-de: shell swap". */
#include <stdint.h>
#include "game.h"
#include "util.h"
#include "port.h"
#include "shellswap.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

static const struct shellswap *const s_ports[] = { &em076_01_shellswap, &em069_01_shellswap, &em013_06_shellswap };
#define NPORTS (sizeof s_ports / sizeof s_ports[0])
#define MAX_LOG 60u

typedef void *(*file_res_t)(void *unused, uint32_t file_id);
#define fileResource FN(file_res_t, 0x152960)
#define ENEMY_MGR 0x1851fe0u            /* the enemy manager (module/main.c) */
typedef uint8_t *(*enemy_at_t)(void *mgr, uint32_t k);
#define enemyAt FN(enemy_at_t, 0x5ceb4) /* the k-th of the 10 monster slots, or 0 */

static void *s_mark;            /* the unit whose next shell request takes its copy */
static uint32_t *s_slot, s_saved;

static const struct shellswap *port_of(void *owner)
{
    if (!owner) return 0;
    for (uint32_t i = 0; i < NPORTS; i++)
        if (FIELD(uint16_t, owner, EN_ID) == s_ports[i]->em) return s_ports[i];
    return 0;
}

static void note(const struct shellswap *p, const char *what, uint32_t id, uint32_t fid)
{
    static uint32_t s_n, s_quest;
    if (port_quest_id() != s_quest) { s_quest = port_quest_id(); s_n = 0; }
    if (s_n++ < MAX_LOG)
        logf("mhgu-de: shell swap %s%s: GU shell 0x%x%s (file 0x%x)", p->tag, what, id,
             fid ? " with its own family" : " (no copy)", fid);
}

void shellswap_mark(void *owner) { s_mark = owner; }

static int is_monster(void *p)
{
    void *mgr = *(void **)MAIN(ENEMY_MGR);
    for (uint32_t k = 0; mgr && k < 10; k++) if ((void *)enemyAt(mgr, k) == p) return 1;
    return 0;
}

int shellswap_any_c(uint32_t *regs)         /* 0x48c4f8, the request's start after its entry (r1 = the request) */
{
    uint8_t *req = (uint8_t *)regs[R1];
    if (!req) return 0;
    void *owner = FIELD(void *, req, 0xc);
    if (!owner || !is_monster(owner)) return 0;
    const struct shellswap *p = port_of(owner);
    if (p && p->any && p->any(FIELD(uint32_t, req, 0x4))) s_mark = owner;
    return 0;
}

int shellswap_req_c(uint32_t *regs)         /* 0x48c5e4, before the cache read: r1 = shell id, r4 = the manager */
{
    void *owner = s_mark;
    if (!owner) return 0;
    s_mark = 0;
    const struct shellswap *p = port_of(owner);
    if (!p) return 0;
    uint32_t id = regs[R1], fid = p->fid(id);
    if (!fid) { note(p, "", id, 0); return 0; }
    void *def = fileResource(0, fid);
    if (!def) { note(p, " (copy not loaded)", id, 0); return 0; }
    s_slot = (uint32_t *)(uintptr_t)(regs[R4] + 0x1c + 4 * id);
    s_saved = *s_slot;
    *s_slot = (uint32_t)(uintptr_t)def;
    note(p, "", id, fid);
    return 0;
}

int shellswap_end_c(uint32_t *regs)         /* 0x48c54c, the request's exit (every path) */
{
    (void)regs;
    if (s_slot) { *s_slot = s_saved; s_slot = 0; }
    s_mark = 0;
    return 0;
}
