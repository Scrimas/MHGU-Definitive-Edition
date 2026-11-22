/* nextact.c: test aid (switch TEST_NEXT_ACTION, off in releases): a monster's next AI-picked action is the one a PC
 * tool asked for (tools/nextact.py). C = read in code, S = strong, G = guess.
 *
 * Where GU's AI picks (C): each frame the enemy update 0xa59fc runs the think check 0x82538 (this+0x7420 controlled
 * and this+0x72f0 a think requested), the think 0x82ddc calls the selector 0x82f80 once (0x82f54), and an EMC
 * `00 cat num` entry ends at 0x85a10: `mov r3, #0; bl 0x75574` = setAction(this, cat, num, mode 0) through its
 * wrapper, the selector's only call of it. So every monster class's AI pick passes there (r0 = this, r1 / r2 = the
 * pair) and no chained step does (setActionNext, the end slots 247..250 and class code call setAction themselves).
 * It runs only where the monster is controlled: online, the request applies on the machine that runs that monster,
 * and GU replicates the action to the others (S).
 * The request: romfs/nativeNX/mhgu_de/nextact.txt in the mod folder, 64 bytes, written by module/build.py install for
 * this switch and rewritten IN PLACE (same size) by tools/nextact.py: one line `seq=N em=0xID cat=C num=N`. Ryujinx
 * serves a mod's RomFS file from the host file when the game reads it (its size fixed at launch, S), so a fresh
 * request shows on the next read. Read at each AI pick; a seq applies once, to the first monster of that ID that
 * picks; the seq found at the first read counts as old (no replay of a previous session's request). Before it: the
 * SD card (nn::fs::MountSdCard / ...ForDebug imported from the sdk NSO): Ryujinx refused both, FS 6400 permission
 * denied (result 0x320002, test 2026-11-22: main.npdm has no SdCard permission).
 * Limits: a combo script passes here at each step (the request replaces the next one, the rest of the script goes
 * on); idle picks (0, 0xff) do not pass here; a pair outside the monster's state (flying, its rider, Dalamadur's
 * halves) can misbehave; online, setAction mode 0 runs the class's remap slot 127. Log: "nextact:" (every pick, every
 * swap: tools/nextact.py reads them). */
#ifdef TEST_NEXT_ACTION
#include <stdint.h>
#include "game.h"
#include "util.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

typedef struct { void *h; } fs_file;
typedef uint32_t (*fs_open_t)(fs_file *out, const char *path, int mode);
typedef uint32_t (*fs_size_t)(int64_t *out, fs_file f);
typedef uint32_t (*fs_read_t)(uint32_t *out, fs_file f, int64_t offset, void *buf, uint32_t size);
typedef void (*fs_close_t)(fs_file f);
#define fs_open FN(fs_open_t, 0x13f04b4)       /* GU's nn::fs imports (savefile.c) */
#define fs_size FN(fs_size_t, 0x13f043c)
#define fs_read FN(fs_read_t, 0x13f0448)
#define fs_close FN(fs_close_t, 0x13f046c)

#define ENEMY_MGR 0x1851fe0u            /* the enemy manager (module/main.c) */
typedef uint8_t *(*enemy_at_t)(void *mgr, uint32_t k);
#define enemyAt FN(enemy_at_t, 0x5ceb4) /* the k-th of the 10 monster slots, or 0 */
#define REQ_PATH "app:/nativeNX/mhgu_de/nextact.txt"

struct req { uint32_t seq, em, cat, num; };

static int s_first = 1;                 /* the first read: its seq is old */
static uint32_t s_done = 0xffffffffu;   /* the last seq applied (or found old) */

static int slot_of(void *self)
{
    void *mgr = *(void **)MAIN(ENEMY_MGR);
    for (uint32_t k = 0; mgr && k < 10; k++) if ((void *)enemyAt(mgr, k) == self) return (int)k;
    return -1;
}

static uint32_t num_at(const char **p)
{
    const char *s = *p;
    uint32_t v = 0, base = 10;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) { base = 16; s += 2; }
    for (;; s++) {
        uint32_t d = *s >= '0' && *s <= '9' ? (uint32_t)(*s - '0') : base == 16 && (*s | 0x20) >= 'a' &&
                     (*s | 0x20) <= 'f' ? (uint32_t)((*s | 0x20) - 'a' + 10) : 99;
        if (d >= base) break;
        v = v * base + d;
    }
    *p = s;
    return v;
}

/* `seq=N em=0xID cat=C num=N` (any order, other words ignored); 1 = all four found */
static int parse(const char *s, struct req *r)
{
    uint32_t got = 0;
    while (*s) {
        static const char *const keys[] = {"seq=", "em=", "cat=", "num="};
        int k = 0;
        for (; k < 4; k++) {
            const char *a = keys[k], *b = s;
            while (*a && *a == *b) a++, b++;
            if (!*a) { uint32_t v = num_at(&b); ((uint32_t *)r)[k] = v; got |= 1u << k; s = b; break; }
        }
        if (k == 4) s++;
    }
    return got == 15;
}

static int read_req(struct req *r)
{
    fs_file h;
    int64_t size;
    uint32_t n = 0;
    char buf[128];
    if (fs_open(&h, REQ_PATH, 1)) return 0;
    if (fs_size(&size, h) || size <= 0) { fs_close(h); return 0; }
    if (size > (int64_t)sizeof buf - 1) size = sizeof buf - 1;
    uint32_t e = fs_read(&n, h, 0, buf, (uint32_t)size);
    fs_close(h);
    if (e) return 0;
    buf[n < sizeof buf ? n : sizeof buf - 1] = 0;
    return parse(buf, r);
}

int nextact_pick_c(uint32_t *regs)          /* 0x85a10, before setAction(this, cat, num, 0) of an AI pick */
{
    void *self = (void *)regs[R0];
    uint32_t em = FIELD(uint16_t, self, EN_ID), cat = regs[R1], num = regs[R2];
    int slot = slot_of(self);
    struct req q;
    int ok = read_req(&q);
    if (s_first) {
        s_first = 0;
        if (ok) s_done = q.seq;
        logf("nextact: request file " REQ_PATH " %s (seq %u, old)", ok ? "read" : "NOT readable (build.py install with "
             "TEST_NEXT_ACTION writes it)", ok ? q.seq : 0);
    }
    static uint32_t s_seen;
    if (ok && q.seq != s_done && q.seq != s_seen) {     /* the file is read live: say so before the monster picks */
        s_seen = q.seq;
        logf("nextact: request %u seen (em %x %u/%u), waiting for that monster's next AI pick", q.seq, q.em, q.cat, q.num);
    }
    if (ok && q.seq != s_done && q.em == em) {
        s_done = q.seq;
        regs[R1] = q.cat, regs[R2] = q.num;
        logf("nextact: slot %d em %x: AI pick %u/%u -> %u/%u (request %u)", slot, em, cat, num, q.cat, q.num, q.seq);
        return 0;
    }
    logf("nextact: slot %d em %x: AI pick %u/%u", slot, em, cat, num);
    return 0;
}
#endif
