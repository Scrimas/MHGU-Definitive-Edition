/* The ported monsters' quests on GU's boards (monsters/gogmazios/notes/stage.md section 8; for Gogmazios quests
 * 11491 / 11492, monsters/gogmazios/tools/build_gog_quest.py). Two ways (allocations.toml): quest_slots = each
 * installed monster's quests take unused DUMMY entries of the quest list (a monster that is not installed keeps them
 * DUMMY); quest_append = its quests are new entries after GU's (quest_group_append, monsters/stygian_zinogre/notes/
 * quests.md 3). quest_group (loc/arc/village/common.arc) in memory: [[0x188ad90]+0xb4], count +0x64, entries +0x6c
 * (12 B: +4 quest ID, +8 group byte, +9, +10 name colour row). The loader step 0x3b7de8 walks it and loads loose
 * questData_%07d.ext for Hub G-rank IDs, then 0x3bb318 sorts them onto the star boards. Nothing real is replaced.
 * A map's Harvest Tours (port_tours: allocations.toml [[map]], maps/<map>/package.toml [[tour]]) are appended too, right
 * after the quests of their append_after monster. A tour's intruders are GU's own (questData +0xCC.., tools/tour4u.py):
 * GU rolls them, online as in its own quests. */
#include <stdint.h>
#include "util.h"
#include "game.h"
#include "port.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

/* entry byte +10 = the row of the quest name's colours on the boards (C: 0x3b22dc returns it, 1 for an ID not listed;
 * the board rows 0x6173c4 / 0x618644 index table 0x1635230 {unselected, selected} with it: 0 -> colours 0x13 / 0x0b,
 * 1 -> 0x11 / 0x12, 2 -> 0x09 / 0x14). GU's list (C, v1.0): Hub IDs 10101..10774 0 (300 of 313, the 13 others are
 * special quests), Hub G-rank IDs 11101..11457 1 (all), village IDs 0..641 0, 701..1055 1 (all) */
static uint8_t qg_colour(uint32_t id)
{
    return id < 700 || (id >= 10000 && id < 11000) ? 0 : 1;
}

static void quest_group_rename(void)
{
    uint32_t mgr = *(volatile uint32_t *)MAIN(0x188ad90u), grp, n, e, i, j, np = 0, lo = ~0u, hi = 0;
    uint16_t pair[PORT_N * PORT_QUESTS];       /* m * PORT_QUESTS + k */
    if (!mgr || !(grp = FIELD(uint32_t, mgr, 0xb4))) return;
    n = FIELD(uint32_t, grp, 0x64);
    e = FIELD(uint32_t, grp, 0x6c);
    if (!e) return;
    /* The slots, gathered before the list instead of checked for every entry: the loader step calls this ~1000 times
     * a town load, and every entry against every monster's slots cost ~2 M instructions a call, which MHGURecomp runs
     * in its interpreter (issue #30; its docs/STATUS.md). Same order as the per-entry loops it replaces. */
    for (int m = 0; m < PORT_N; m++)
        for (uint32_t k = 0; k < PORT_QUESTS; k++) {
            uint32_t s = port_monsters[m].quest_slots[k];
            /* slot 0 = none (a quest_append entry has no slots): GU's own quest 0 is entry 0 */
            if (!s || !port_monsters[m].quests[k]) continue;
            pair[np++] = (uint16_t)(m * PORT_QUESTS + k);
            if (s < lo) lo = s;
            if (s > hi) hi = s;
        }
    for (i = 0; i < n; i++) {
        volatile uint8_t *p = (volatile uint8_t *)(uintptr_t)(e + 12 * i);
        uint32_t id = *(volatile uint32_t *)(p + 4);
        if (id < lo || id > hi) continue;
        for (j = 0; j < np; j++) {
            int m = pair[j] / PORT_QUESTS;
            uint32_t k = pair[j] % PORT_QUESTS;
            const struct port_monster *pm = &port_monsters[m];
            if (id != pm->quest_slots[k] || !port_installed(m)) continue;
            *(volatile uint32_t *)(p + 4) = pm->quests[k];
            p[8] = 0;                              /* group: regular */
            p[10] = qg_colour(pm->quests[k]);      /* the DUMMY slot's 1 -> GU's row for the quest's rank */
            logf("mhgu-de: quest_group entry %u: %u -> %u (%s)", i, pm->quest_slots[k], pm->quests[k], pm->name);
        }
    }
}

/* 0x3b7de8: quest list loader step (runs repeatedly; the rename is idempotent) */
int quest_group_fix_c(uint32_t *regs)
{
    (void)regs;
    quest_group_rename();
    return 0;
}

/* 0x388d40(this): the results scene's clear write (results state machine 0x384848 -> 0x384af0 -> 0x384f8c): looks
 * the running quest [mgr+0xe0] up in the quest list and sets its bit in the cleared map [0x1897f78]+0x42c (0x523f30;
 * failed map +0x62c via 0x526b98 on state 4). The results scene loads its own fresh list (0x6a1f64 -> 0x3b190c) that
 * the loader-step rename never sees, so 11491 was not found and the clear went to bit 0 (quest-clear helper, C).
 * Renaming here puts it at its slot's index (11491 at 1412, 11492 at 1407), the bit the board and the Notes read.
 * Logged for a ported quest: the list index it is found at = the bit the write sets (an appended quest: 1509..). */
int quest_clear_fix_c(uint32_t *regs)
{
    uint32_t mgr = *(volatile uint32_t *)MAIN(0x188ad90u), grp, id = port_quest_id(), n, e, i;
    int t = port_tour_of(id);
    (void)regs;
    quest_group_rename();
    if (mgr && (grp = FIELD(uint32_t, mgr, 0xb4)) && (port_quest_owner(id, 0) >= 0 || t >= 0)) {
        n = FIELD(uint32_t, grp, 0x64);
        e = FIELD(uint32_t, grp, 0x6c);
        for (i = 0; e && i < n && *(volatile uint32_t *)(uintptr_t)(e + 12 * i + 4) != id; i++) ;
        logf("mhgu-de: clear write for quest %u: list index %u of %u", id, i, n);
    }
    return 0;
}

typedef void *(*qg_new_t)(uint32_t size, uint32_t align);
typedef void *(*qg_entry_t)(void *e);
typedef void (*qg_delete_t)(void *block);
#define qg_new FN(qg_new_t, 0x37a5ec)        /* new[](size, 16): the parser's allocator */
#define qg_ctor FN(qg_entry_t, 0x37a654)     /* entry ctor: vtable, +4 / +8..+10 = 0 */
#define qg_dtor FN(qg_entry_t, 0x37a684)     /* entry dtor */
#define qg_delete FN(qg_delete_t, 0x37a628)  /* delete[](entries - 8) */
#define QG_MAX (PORT_N * PORT_QUESTS + PORT_TOUR_N)
#define QG_PLACEHOLDER 1111010u              /* a vanilla DUMMY entry (index 1460, group 127, +10 = 1): in no
                                                quest_slots list (tools/alloc.py QUEST_PLACEHOLDER) */

/* 0x39bb6c: quest_group's parser 0x39bb30 (f32 4.0, u32 count, count x {u32 ID, u8 group, u8, u8}) at its common exit
 * `mov r0, r8` (r4 = this). Every load passes here (the boards' list and the results scene's fresh list, both via
 * 0x3b190c), so both get the appended block without a rename. The entries are rebuilt the parser's way (new[] with
 * the cookie {12, n + N} before them, ctor each), GU's copied and ours after; the old block is freed as the release
 * 0x39b9a8 frees it (dtor from the last, delete[]), and the game frees ours later the same way. The block = every
 * quest_append entry's quests in registry order, installed or not: a quest whose monster or questData file is missing
 * takes the placeholder, so no quest's index (its cleared / failed bit) ever moves. A map's tours follow the quests
 * of their append_after monster (a tour not present takes the placeholder too). */
int quest_group_append_c(uint32_t *regs)
{
    static uint32_t s_logged;
    uint8_t *grp = (uint8_t *)(uintptr_t)regs[R4], g[QG_MAX], c[QG_MAX], *e, *blk, *ne;
    uint32_t id[QG_MAX], n, N = 0, i;
    for (int m = 0; m < PORT_N; m++) {
        for (int k = 0; port_monsters[m].quest_append && k < PORT_QUESTS; k++) {
            uint32_t q = port_monsters[m].quests[k];
            if (!q) continue;
            int on = port_installed(m) && port_quest_present(m, k);
            id[N] = on ? q : QG_PLACEHOLDER;
            g[N] = on ? 0 : 127;                       /* group: regular / DUMMY */
            c[N++] = on ? qg_colour(q) : 1;
        }
        for (int t = 0; t < PORT_TOUR_N; t++) {        /* the tours listed after this monster's quests */
            if (port_tours[t].after != m) continue;
            int on = port_tour_present(t);
            id[N] = on ? port_tours[t].quest : QG_PLACEHOLDER;
            g[N] = on ? 0 : 127;
            c[N++] = on ? qg_colour(port_tours[t].quest) : 1;
        }
    }
    n = FIELD(uint32_t, grp, 0x64);
    e = (uint8_t *)(uintptr_t)FIELD(uint32_t, grp, 0x6c);
    if (!N || !n || !e) return 0;
    for (i = 0; n >= N && i < N; i++)                  /* already there (a failed parse keeps the list it had) */
        if (FIELD(uint32_t, e, 12 * (n - N + i) + 4) != id[i] || e[12 * (n - N + i) + 8] != g[i]) break;
    if (n >= N && i == N) return 0;
    blk = qg_new(12 * (n + N) + 8, 16);
    if (!blk) {
        logf("mhgu-de: quest_group: new[] failed, %u quests not appended", N);
        return 0;
    }
    FIELD(uint32_t, blk, 0) = 12;
    FIELD(uint32_t, blk, 4) = n + N;
    ne = blk + 8;
    for (i = 0; i < n + N; i++) {
        uint8_t *p = ne + 12 * i;
        qg_ctor(p);
        if (i < n) {
            FIELD(uint32_t, p, 4) = FIELD(uint32_t, e, 12 * i + 4);
            p[8] = e[12 * i + 8], p[9] = e[12 * i + 9], p[10] = e[12 * i + 10];
        } else {
            FIELD(uint32_t, p, 4) = id[i - n];
            p[8] = g[i - n], p[9] = 0, p[10] = c[i - n];
        }
    }
    for (i = n; i-- > 0;) qg_dtor(e + 12 * i);
    qg_delete(e - 8);
    FIELD(uint32_t, grp, 0x6c) = (uint32_t)(uintptr_t)ne;
    FIELD(uint32_t, grp, 0x64) = n + N;
    if (s_logged++ < 4) logf("mhgu-de: quest_group: %u entries + %u appended (indexes %u..%u)", n, N, n, n + N - 1);
    return 0;
}

/* The counter's quest lists (C): 0x3bc96c(mgr, i) -> u32 quest IDs, 0x3bc9f8(mgr, i) -> their count, mgr =
 * [0x188ae38]. List i = a regular quest's star (village 1..10, Hub 1..7, G 11..14; slot map 0x1753ff4 by counter
 * mode) holds that star board's quests, locked ones too (its builder 0x3bab28 has no unlock check); list 23 is the
 * Hunt of the Day, the day's monster at every rank. */
typedef const uint32_t *(*qlist_t)(void *mgr, uint32_t i);
typedef uint16_t (*qlist_count_t)(void *mgr, uint32_t i);
typedef uint8_t (*quest_check_t)(void *unused, uint32_t id);
#define qlist FN(qlist_t, 0x3bc96c)
#define qlist_count FN(qlist_count_t, 0x3bc9f8)
#define quest_check FN(quest_check_t, 0x3b2174)
#define QLIST_STAR_LAST 14u
#define QLIST_DAILY 23u

static int qlist_find(void *mgr, uint32_t i, uint32_t id, const uint32_t **l, uint32_t *n)
{
    uint32_t k;
    *l = qlist(mgr, i);
    *n = *l ? qlist_count(mgr, i) : 0;
    for (k = 0; k < *n && (*l)[k] != id; k++) ;
    return k < *n;
}

/* a ported quest is unlocked when its star board is open: when that board holds an unlocked GU quest (the counter's
 * own test for a star tab, 0x783074, next to its progress flag). On the Hunt of the Day alone, its rank has no board
 * here yet; on no list (none built, or the other hall's quest): unlocked, as before. */
static int star_board_open(uint32_t id)
{
    void *mgr = *(void *volatile *)MAIN(0x188ae38u);
    const uint32_t *l;
    uint32_t n;
    if (!mgr) return 1;
    for (uint32_t i = 1; i <= QLIST_STAR_LAST; i++) {
        if (!qlist_find(mgr, i, id, &l, &n)) continue;
        for (uint32_t k = 0; k < n; k++)
            if (port_quest_owner(l[k], 0) < 0 && port_tour_of(l[k]) < 0 && quest_check(0, l[k])) return 1;
        return 0;
    }
    return !qlist_find(mgr, QLIST_DAILY, id, &l, &n);
}

/* 0x3b2174(_, id) -> bool: "quest unlocked?" (script check_quest_unlocked has no rule for our IDs). Mid hook 0x3b2194,
 * before its check call 0x3d7e90: r1 = &result byte, r2 = id; nonzero -> 0x3b219c returns the byte (build.py
 * MID_EXIT). Not at the entry: the Forge plugin Key Quest Markers checks its first 0x20 bytes (issue #10). A ported
 * quest follows its star board (star_board_open): answering 1 let the Hunt of the Day list ported quests of ranks
 * not reached yet, and the village take them (issue #46). Tours stay unlocked. */
int quest_unlocked_c(uint32_t *regs)
{
    int m = port_quest_owner(regs[R2], 0), t = port_tour_of(regs[R2]);
    if (m >= 0 ? !port_installed(m) : !port_tour_present(t)) return 0;
    *(uint8_t *)(uintptr_t)regs[R1] = (uint8_t)(m < 0 || star_board_open(regs[R2]));
    return 1;
}

/* 0x3bb318(boards, quest ID, star, record) -> void: puts a quest on its star board, appended, unless the board already
 * holds that ID (C). Callers: the regular boards' builder 0x3bab28.. (per loaded quest, in quest-list order: record
 * = 0x39b848(0x3ba50c(boards, ID), 0), star = s8 record +14 = questData +0x12, C) and the event boards' 0x3bc234 /
 * 0x3bc458. A board shows its quests in the order they are put, so a quest put early keeps that place: the builder's
 * own call later finds it there.
 * - GU's tours lead their boards (the maintainer, 2026-11-10): before a board's first quest that is no tour (record
 *   +0x0c = questData +0x10 type, 3 = Harvest Tour), our tours of that board go in first.
 * - Each ported quest follows its anchor, a GU quest of its board (port_boards, tools/board_order.py: GU's own block
 *   order, NEWSAVE_MAPREWORK.md C10): before the builder puts the first regular quest listed after the anchor, the
 *   ported quests anchored before it go in, in anchor order. A locked anchor or a locked next quest doesn't matter:
 *   list indexes decide. A ported quest whose anchor is not in the list keeps its place at the end. */
typedef void *(*qres_find_t)(void *boards, uint32_t id);
typedef uint8_t *(*qres_record_t)(void *res, uint32_t k);
typedef void (*board_put_t)(void *boards, uint32_t id, uint32_t star, void *record);
#define qres_find FN(qres_find_t, 0x3ba50c)
#define qres_record FN(qres_record_t, 0x39b848)
#define board_put FN(board_put_t, 0x3bb318)
#define QD_TYPE_TOUR 3
#define REGULAR_MAX 20000u                    /* board quest IDs: village < 10000, hub 10000..19999 */
#define BOARD_MAX 64

/* the quest list's entries (quest_group in memory): count, entry k's ID */
static uint32_t qg_list(uint32_t *e)
{
    uint32_t mgr = *(volatile uint32_t *)MAIN(0x188ad90u), grp;
    if (!mgr || !(grp = FIELD(uint32_t, mgr, 0xb4)) || !(*e = FIELD(uint32_t, grp, 0x6c))) return 0;
    return FIELD(uint32_t, grp, 0x64);
}
#define QG_ID(e, k) (*(volatile uint32_t *)(uintptr_t)((e) + 12 * (k) + 4))

/* the ported quest b's board record in this pass (looked up once per pass: 0 = not on any board here, i.e. not
 * installed, not present or not loaded) */
static uint8_t *s_brec[BOARD_MAX];
static uint64_t s_bseen;
static uint8_t *board_rec(void *boards, int b)
{
    const struct port_board *pb = &port_boards[b];
    if (!(s_bseen >> b & 1)) {
        s_bseen |= 1ull << b;
        s_brec[b] = 0;
        if (port_installed(pb->monster) && port_quest_present(pb->monster, pb->k)) {
            void *res = qres_find(boards, pb->quest);
            uint8_t *r = res ? qres_record(res, 0) : 0;
            if (r && FIELD(uint32_t, r, 8) == pb->quest) s_brec[b] = r;
        }
    }
    return s_brec[b];
}

static void board_place_ported(void *boards, uint32_t id, uint32_t star)
{
    static uint32_t s_e, s_n, s_cur, s_last;  /* the list the anchors were found in; cursor; last call's index */
    static uint32_t s_aidx[BOARD_MAX];        /* each anchor's list index (0xffffffff = not listed) */
    static uint8_t s_order[BOARD_MAX];        /* port_boards rows by anchor index */
    static uint64_t s_done, s_logged;
    static void *s_boards;
    uint32_t e, n = qg_list(&e), idx, k;
    int nb = port_board_n < BOARD_MAX ? port_board_n : BOARD_MAX;
    if (!n || !nb) return;
    if (e != s_e || n != s_n) {               /* a new list: find the anchors (60k reads, once per load) */
        s_e = e, s_n = n, s_cur = 0, s_last = 0xffffffffu;
        for (int b = 0; b < nb; b++) {
            s_aidx[b] = 0xffffffffu;
            for (k = 0; k < n; k++)
                if (QG_ID(e, k) == port_boards[b].after) { s_aidx[b] = k; break; }
            if (s_aidx[b] == 0xffffffffu)
                logf("mhgu-de: board: quest %u's anchor %u is not listed (stays last)", port_boards[b].quest,
                     port_boards[b].after);
            int j = b;                        /* insertion by anchor index, ties in table order */
            while (j > 0 && s_aidx[s_order[j - 1]] > s_aidx[b]) { s_order[j] = s_order[j - 1]; j--; }
            s_order[j] = (uint8_t)b;
        }
    }
    for (k = 0; k < n; k++) {                 /* this quest's index: the builder walks the list in order */
        uint32_t c = (s_cur + k) % n;
        if (QG_ID(e, c) == id) break;
    }
    if (k == n) return;                       /* not listed (an event board's quest) */
    idx = (s_cur + k) % n;
    s_cur = idx;
    if (boards != s_boards || idx < s_last || s_last == 0xffffffffu) {      /* a new pass */
        static uint32_t s_n;
        if (++s_n <= 8) {                     /* the raised caps (build.py QUEST_LIMIT_SITES): loaded quests, and the */
            uint32_t full = 0, top = 0;       /* fullest of the 18 boards (u16 counts at L+0x38, C; list 14 through */
            for (uint32_t k = 0; k < 18; k++) /* 0x3bc9f8 read 0 in test 2: its slot map is not the board index) */
                if (FIELD(uint16_t, boards, 0x38 + 2 * k) > top) top = FIELD(uint16_t, boards, 0x38 + 2 * k), full = k;
            logf("mhgu-de: board pass: %u quests loaded (list %u), fullest board %u: %u quests (previous pass)",
                 FIELD(uint32_t, boards, 0x28), n, full, top);
        }
        s_done = s_bseen = 0;
    }
    s_boards = boards, s_last = idx;
    for (int o = 0; o < nb; o++) {
        int b = s_order[o];
        if (s_aidx[b] >= idx) break;          /* anchors in order: the rest come later */
        if (s_done >> b & 1 || (port_boards[b].quest < 10000u) != (id < 10000u)) continue;
        uint8_t *r = board_rec(boards, b);
        if (r && (uint8_t)r[14] != (uint8_t)star) continue;             /* another board's turn: its next quest */
        s_done |= 1ull << b;
        if (!r) continue;
        board_put(boards, port_boards[b].quest, (uint16_t)(int16_t)(int8_t)r[14], r);
        if (!(s_logged >> b & 1)) {
            s_logged |= 1ull << b;
            logf("mhgu-de: board: quest %u put after %u (list %u), before quest %u (list %u, star %u)",
                 port_boards[b].quest, port_boards[b].after, s_aidx[b], id, idx, star);
        }
    }
}

int tour_board_c(uint32_t *regs)
{
    static int s_putting;
    static uint32_t s_logged;                 /* bit k: tour k's first placement logged (the later calls are no-ops) */
    int t = port_tour_of(regs[R1]);
    const uint8_t *rec = (const uint8_t *)(uintptr_t)regs[R3];
    if (t >= 0) return 0;
    if (s_putting || !rec || regs[R1] >= REGULAR_MAX) return 0;          /* events */
    s_putting = 1;
    if (rec[0x0c] != QD_TYPE_TOUR)                                       /* GU's tours lead, then ours */
        for (int k = 0; k < PORT_TOUR_N; k++) {
            const struct port_tour *pt = &port_tours[k];
            if ((pt->quest < 10000u) != (regs[R1] < 10000u) || !port_tour_present(k)) continue;
            void *res = qres_find((void *)(uintptr_t)regs[R0], pt->quest);
            uint8_t *r = res ? qres_record(res, 0) : 0;
            if (!r || FIELD(uint32_t, r, 8) != pt->quest || (uint8_t)r[14] != (uint8_t)regs[R2]) continue;
            board_put((void *)(uintptr_t)regs[R0], pt->quest, (uint16_t)(int16_t)(int8_t)r[14], r);
            if (k < 32 && !(s_logged >> k & 1)) {
                s_logged |= 1u << k;
                logf("mhgu-de: tour %u put on star board %u before quest %u", pt->quest, regs[R2], regs[R1]);
            }
        }
    if (port_quest_owner(regs[R1], 0) < 0) board_place_ported((void *)(uintptr_t)regs[R0], regs[R1], regs[R2]);
    s_putting = 0;
    return 0;
}

/* 0x7ca340(out, const char *s, n): UTF-8 helper (8 callers), strlen(s) first. Abandoning the Gogmazios quest crashed
 * here with s = NULL while the quest setup had been skipped (null questLink, fixed in the arc layout). Safety net: a
 * null string becomes "" (the helper's own length-0 path), logged with the caller so a remaining source can be
 * found. */
int utf8_null_guard_c(uint32_t *regs)
{
    static const char empty[1];
    static uint32_t s_n;
    if (regs[R1]) return 0;
    regs[R1] = (uint32_t)(uintptr_t)empty;
    if (++s_n <= 20) logf("mhgu-de: null string to 0x7ca340 from lr=%x (quest %u)", regs[LR] - MAIN_BASE,
                          port_quest_id());
    return 0;
}

/* MH4U's second intruder on our tours (D19; NEWSAVE_MAPREWORK.md C6c). GU keeps one intruder per quest (C): the
 * quest start rolls one index into the quest manager's +0x165d (0x3ab588: a weighted pick, or 0xff = none) and its
 * minute into +0x165f (minute +0xCD at the chance +0xCE, then +3 min and +10 % per miss, as MH4U), and the scheduler
 * 0x3a08e8 brings it while +0x165e (intruders that came) is 0 and fewer than 2 large monsters are out. MH4U also rolls
 * a second one from the remaining entries, whose checks start 5 minutes after the first came at 0 %, then every 3
 * minutes at +10 % (C, 4U 0x69e0cc / 0x6a6d2c). Online, the host's roll reaches the guests with two u16 the host draws
 * at quest start, +0x1550 / +0x1552 (0x3acb58, packet 0x3ad394 / 0x3ad71c): the second roll is a hash of them, so
 * every machine computes the same one. Hook 0x3a1808 (r1 = the manager), in the scheduler's state 6 after an
 * intruder slot's spawn, before GU counts it: our tours get the second intruder armed in GU's own fields (+0x165d
 * the pick, +0x165f its minute, +0x165e left at 0); nonzero skips GU's count (build.py MID_EXIT -> 0x3a1814). */
#define QM_SEED 0x1550u         /* 2 x u16, host random, synced */
#define QM_INTR 0x165du         /* u8 intruder index 0..2 (boss slot 2..4), 0xff none */
#define QM_INTR_N 0x165eu       /* u8 intruders that came */
#define QM_INTR_MIN 0x165fu     /* u8 the quest minute it comes at */
#define QM_LIMIT 0xccu          /* int the quest's minutes */
#define QM_REC 0xa4u            /* the running quest's record: weights at +0xdc + index (questData +0xD2 + index) */

static uint32_t intr_rand(uint32_t *s)
{
    *s ^= *s << 13; *s ^= *s >> 17; *s ^= *s << 5;
    return *s;
}

int intruder_came_c(uint32_t *regs)
{
    static uint32_t s_done;     /* the seed of the quest whose second intruder was handled */
    uint8_t *m = (uint8_t *)(uintptr_t)regs[R1];
    uint32_t id = port_quest_id(), rec, seed, h = 2166136261u, i, pick = 3, r, minute, chance, limit;
    if (!m || port_tour_of(id) < 0 || m[QM_INTR_N] != 0 || m[QM_INTR] > 2) return 0;
    rec = FIELD(uint32_t, m, QM_REC);
    seed = FIELD(uint32_t, m, QM_SEED);
    if (!rec || seed == s_done) return 0;           /* the second intruder came (or there is none): GU counts it */
    s_done = seed;
    for (i = 0; i < 4; i++) h = (h ^ (id >> 8 * i & 0xffu)) * 16777619u;
    for (i = 0; i < 4; i++) h = (h ^ (seed >> 8 * i & 0xffu)) * 16777619u;
    h = (h ^ m[QM_INTR]) * 16777619u;
    h = (h ^ m[QM_INTR_MIN]) * 16777619u;
    if (!h) h = 1;
    r = intr_rand(&h) % 100;                        /* MH4U's walk: weight <= r goes on, so weight 0 never comes */
    for (i = 0; i < 3; i++) {
        uint32_t w = FIELD(uint8_t, rec, 0xdc + i);
        if (i == m[QM_INTR] || !w) continue;
        if (w <= r) { r -= w; continue; }
        pick = i;
        break;
    }
    if (pick > 2) {
        logf("mhgu-de: tour %u: intruder %u came at minute %u; no second intruder", id, m[QM_INTR] + 2u, m[QM_INTR_MIN]);
        return 0;
    }
    limit = FIELD(uint32_t, m, QM_LIMIT);
    for (minute = m[QM_INTR_MIN] + 5u, chance = 0; minute < limit; minute += 3, chance += 10)
        if (intr_rand(&h) % 100 < chance) break;
    if (minute >= limit || minute > 255) {
        logf("mhgu-de: tour %u: second intruder (slot %u) would come after the time limit: none", id, pick + 2);
        return 0;
    }
    logf("mhgu-de: tour %u: intruder %u came at minute %u; second intruder armed: slot %u at minute %u", id,
         m[QM_INTR] + 2u, m[QM_INTR_MIN], pick + 2, minute);
    m[QM_INTR] = (uint8_t)pick;
    m[QM_INTR_MIN] = (uint8_t)minute;
    return 1;                                       /* GU's count stays 0: its own check brings the second */
}
