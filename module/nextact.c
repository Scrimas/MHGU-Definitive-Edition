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
 * The request: a UDP datagram to 127.0.0.1:47123 from tools/nextact.py, one line `seq=N em=0xID cat=C num=N`. The
 * module keeps one reference of GU's socket service through GU's own counted wrapper (0x813b44(obj, &result): the
 * first reference runs nn::socket::Initialize, 0x813bb4 releases; obj = [0x1840900]+0x2c via 0x8110e0, as GU's online
 * code calls it, C), so GU's own online start / stop keeps working; the socket is non-blocking and drained at each AI
 * pick (the last request wins). A seq applies once, to the first monster of that ID that picks. Tried before (test
 * 2026-11-22): the SD card (Ryujinx refused it: FS 6400, main.npdm has no SdCard permission) and a mod RomFS file
 * rewritten in place (Ryujinx keeps the launch copy: the game never saw the change).
 * Limits: a combo script passes here at each step (the request replaces the next one, the rest of the script goes
 * on); idle picks (0, 0xff) do not pass here; a pair outside the monster's state (flying, its rider, Dalamadur's
 * halves) can misbehave; online, setAction mode 0 runs the class's remap slot 127. Log: "nextact:" (every pick, every
 * swap: tools/nextact.py reads them). */
#ifdef TEST_NEXT_ACTION
#include <stdint.h>
#include "game.h"
#include "util.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

/* GU's nn::socket imports (dump/gu_plt.json) and its counted service start (C) */
typedef int (*sock_socket_t)(int domain, int type, int proto);
typedef int (*sock_bind_t)(int fd, const void *addr, uint32_t len);
typedef int (*sock_recv_t)(int fd, void *buf, uint32_t len, int flags);
typedef int (*sock_fcntl_t)(int fd, int cmd, ...);
typedef int (*sock_errno_t)(void);
typedef void (*sock_ref_t)(void *obj, int32_t *result);
typedef void *(*sock_obj_t)(void *mgr);
#define sock_socket FN(sock_socket_t, 0x13f0508)   /* nn::socket::Socket */
#define sock_bind   FN(sock_bind_t, 0x13f0574)     /* nn::socket::Bind */
#define sock_recv   FN(sock_recv_t, 0x13f05a4)     /* nn::socket::Recv */
#define sock_fcntl  FN(sock_fcntl_t, 0x13f0520)    /* nn::socket::Fcntl */
#define sock_errno  FN(sock_errno_t, 0x13f0514)    /* nn::socket::GetLastErrno */
#define sock_ref    FN(sock_ref_t, 0x813b44)       /* GU: socket service reference (Initialize at the first) */
#define sock_obj    FN(sock_obj_t, 0x8110e0)       /* GU: its owner from [0x1840900] (ldr r0, [r0, #0x2c]) */
#define AF_INET_ 2
#define SOCK_DGRAM_ 2
#define F_SETFL_ 4
#define O_NONBLOCK_ 4                              /* the BSD values nn::socket takes */
#define MSG_DONTWAIT_ 0x80
#define REQ_PORT 47123

#define ENEMY_MGR 0x1851fe0u            /* the enemy manager (module/main.c) */
typedef uint8_t *(*enemy_at_t)(void *mgr, uint32_t k);
#define enemyAt FN(enemy_at_t, 0x5ceb4) /* the k-th of the 10 monster slots, or 0 */

struct req { uint32_t seq, em, cat, num; };

static int s_fd = -2;                   /* -2 not opened yet, -1 failed */
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

static void open_socket(void)
{
    void *mgr = *(void **)MAIN(0x1840900u);
    int32_t res = -1;
    s_fd = -1;
    if (!mgr) { logf("nextact: no network manager yet (0x1840900): requests off"); return; }
    sock_ref(sock_obj(mgr), &res);                  /* kept for the session: GU's own stop leaves the service up */
    int fd = sock_socket(AF_INET_, SOCK_DGRAM_, 0);
    struct { uint8_t len, family; uint16_t port; uint32_t addr; uint8_t zero[8]; } sa = {
        16, AF_INET_, (uint16_t)(REQ_PORT >> 8 | (REQ_PORT & 0xff) << 8), 0x0100007fu, {0}};   /* network order */
    int b = fd < 0 ? -1 : sock_bind(fd, &sa, sizeof sa);
    int f = fd < 0 ? -1 : sock_fcntl(fd, F_SETFL_, O_NONBLOCK_);
    logf("nextact: socket service reference %x, UDP socket %d, bind 127.0.0.1:%d %d, non-blocking %d (errno %d)%s",
         (uint32_t)res, fd, REQ_PORT, b, f, sock_errno(), fd >= 0 && b == 0 ? ": requests on" : ": requests OFF");
    if (fd >= 0 && b == 0) s_fd = fd;
}

/* 1 = a request: the last datagram waiting (each logged) */
static int read_req(struct req *r)
{
    char buf[96];
    int ok = 0, n;
    while ((n = sock_recv(s_fd, buf, sizeof buf - 1, MSG_DONTWAIT_)) > 0) {
        buf[n] = 0;
        for (char *c = buf; *c; c++) if (*c == '\n' || *c == '\r') *c = 0;
        struct req q;
        int good = parse(buf, &q);
        logf("nextact: datagram \"%s\" -> %s", buf, good ? "request" : "not a request");
        if (good) *r = q, ok = 1;
    }
    return ok;
}

int nextact_pick_c(uint32_t *regs)          /* 0x85a10, before setAction(this, cat, num, 0) of an AI pick */
{
    void *self = (void *)regs[R0];
    uint32_t em = FIELD(uint16_t, self, EN_ID), cat = regs[R1], num = regs[R2];
    int slot = slot_of(self);
    if (s_fd == -2) open_socket();
    static struct req q;                       /* the latest request read, kept until its monster picks */
    static int have;
    struct req got;
    if (s_fd >= 0 && read_req(&got)) q = got, have = 1;
    int ok = have;
    static uint32_t s_seen;
    if (ok && q.seq != s_done && q.seq != s_seen) {     /* in: say so before the monster picks */
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
