/* em013_06_state.c: G-rank Crimson Fatalis' state (struct gcf), its spawn setup and state frame, the rage glow of its
 * m51 / m52 layers and its theme (notes/plan.md 9). C = read in code, S = strong, G = guess; 4U addresses in [].
 * Spawn setup, GU slot 118 entry (0xd808f0) [4U slot 39 0x893cfc, em117 path, C]: GU's slot 118 parks the rage
 * materials for variants 1 / 2 only (1 "Normal" at frame 0, 2 = White: "Angry_End" at its last frame). em117 takes
 * White's setup 0x89ed3c (kinds 1 / 50 at the end of "Angry_End", W+0x17 = 0) and then the same for kinds 51 / 52
 * (its m51 / m52 additive layers): both here, before GU's slot 118 runs on (it has no case for variant 6). Then the
 * prominence fields and the zone record off [W+0x6d = 1, +0x6e = 0, +0x70 = 0, +0x74 = 0xff, +0x75 = 0, +0x38 =
 * 0xff]. The zone joins 4U's stage list 0x684b00 there; ours is read by our own hunter test instead.
 * State frame, GU slot 119 entry (0xd81a08) [4U slot 40 0x894050, C]: in the event quest (spawn byte 3 = 1, GU keeps
 * the Hyper flag in that byte, so the quest ID stands for it) 0x934508 every frame = GU 0xbd100: the rage, once on,
 * never runs out (GU's rage timer 0xbd1xx resets it while rec+0x520 is set, as 4U 0x936664); the zone timer (300
 * frames, then off).
 * Glow [4U slot 50 0x89de60, C]: em117 starts "Angry_Start" (enraged) / "Angry_End" (calm) on kinds 1 / 50
 * (0x89e670) AND 51 / 52 (0x89e8a0). GU's slot-132 variant-6 branch 0xd8dc64 does kinds 50 / 1 and stores its state
 * in work+0x36 (3 / 0); its exit is a `pop {.., pc}`, no hook point, so kinds 51 / 52 follow that state here, from
 * slot 119 (S: at most one frame after GU's switch, by the order of the two slots in GU's update).
 * Theme: the core's bgm.c, as a stand-in: em type 13 (every Fatalis, 0x60d & 0xff) answered only while one of our
 * quests runs, so GU's own Fatalis keep theirs everywhere else; a GU class runs this monster, so there is no class
 * registration: registered at the first spawn (the boss is found when its battle theme starts, so it has spawned). */
#include "em013_06.h"
#include "port.h"

enum { R0, R1, R2, R3, R4, R5, R12, LR };

int gcf_ours(const void *self)
{
    return self && FIELD(uint16_t, self, EN_ID) == G_CRIMSON_FATALIS_EM_ID;
}

int gcf_event_quest(void)
{
    int k = -1;
    return port_running_quest(&k) == G_CRIMSON_FATALIS_PORT && k == 1;     /* quests[1] = 11499 (allocations.toml) */
}

static void gcf_init(struct gcf *s, void *self, uint32_t quest)
{
    *s = (struct gcf){0};
    s->self = self;
    s->quest = quest;
    s->prom_on = 1;
    s->type = 0xff;
    s->zone.marker = 0xff;
}

/* one state per unit and quest (Monoblos' mb_state): a new quest starts it again */
static struct gcf s_gcf[4];

struct gcf *gcf_find(const void *self)
{
    for (uint32_t i = 0; i < 4; i++)
        if (self && s_gcf[i].self == self) return &s_gcf[i];
    return 0;
}

struct gcf *gcf_state(void *self)
{
    static uint32_t next;
    uint32_t q = port_quest_id();
    struct gcf *p = gcf_find(self);
    if (p && p->quest == q) return p;
    if (!p) p = &s_gcf[next++ & 3];
    gcf_init(p, self, q);
    return p;
}

/* the rage animation `name` on the materials of kinds k1 / k2, at its first frame or its last (at_end)
 * [0x89ed3c / 0x89e670 / 0x89e8a0; GU's own loops d80a38 / d8dcb0] */
static void glow(void *self, uint32_t k1, uint32_t k2, const char *name, int at_end)
{
    uint32_t n = FIELD(uint32_t, self, 0xfc), hit = 0;
    for (uint32_t i = 0; i < n; i++) {
        void *m = gcfMatGet(self, i);
        uint32_t kind = (FIELD(uint32_t, m, 0x18) >> 22) & 0xff;
        void *set = FIELD(void *, m, 0x74);
        if ((kind != k1 && kind != k2) || !set) continue;
        int idx = gcfAnimFind(set, name);
        if (idx < 0) continue;
        float f = at_end ? (float)*FIELD(uint32_t **, set, 0x10)[idx + 1] : 0.0f;
        gcfAnimPlay(m, 0, (uint32_t)idx);
        FIELD(float, m, 0x54) = f;
        gcfMatDirty(self);
        hit++;
    }
    static uint32_t s_n;
    if (++s_n <= 20) logf("gcfport: %s on kinds %u / %u%s: %u materials", name, k1, k2, at_end ? " (end)" : "", hit);
}

static int gcf_quest(void) { return port_running_quest(0) == G_CRIMSON_FATALIS_PORT; }
static int gcf_phase2(void *unit) { (void)unit; return 0; }   /* one stream, no phase 2 (allocations.toml bgm_ids) */

static const struct port_bgm k_bgm = {
    "gcfport", "em013_06", {0}, {G_CRIMSON_FATALIS_STANDIN_ID & 0xffu}, gcf_quest, GCF_BGM_STQR,
    {G_CRIMSON_FATALIS_BGM_ID0, G_CRIMSON_FATALIS_BGM_ID0}, gcf_phase2,
};

int em013_06_spawn_c(uint32_t *regs)           /* GU slot 118 entry 0xd808f0 (r0 = this) */
{
    void *self = (void *)regs[R0];
    if (!gcf_ours(self)) return 0;
    struct gcf *s = gcf_state(self);
    void *haze = s->haze;
    gcf_init(s, self, s->quest);
    s->haze = haze;
    FIELD(uint8_t *, self, GCF_EN_WORK)[0x36] = 0;       /* [W+0x17 = 0] */
    glow(self, 1, 50, "Angry_End", 1);
    glow(self, 51, 52, "Angry_End", 1);
    gcf_haze_open(self, s);
    s->zone.area = FIELD(uint8_t, self, GCF_EN_AREA);   /* [W+0x39 = W+0x14c] */
    port_bgm_register(&k_bgm);
    logf("gcfport: em013_06 spawn %x (quest %u, event %u)", (uint32_t)self, s->quest, gcf_event_quest());
    return 0;
}

int em013_06_state_c(uint32_t *regs)           /* GU slot 119 entry 0xd81a08 (r0 = this) */
{
    void *self = (void *)regs[R0];
    if (!gcf_ours(self)) return 0;
    struct gcf *s = gcf_state(self);
    if (gcf_event_quest()) gcfRageLock(self);
    uint8_t *rec = GCF_REC(self), rage = rec[0x518];
    if (rage != s->rage_seen) {                /* test 2: does the event quest's rage ever end? */
        static uint32_t s_n;
        if (++s_n <= 40)
            logf("gcfport: %x rage %u -> %u (lock %u, event %u, words 518..527 %x %x %x)", (uint32_t)self,
                 s->rage_seen, rage, rec[0x520], gcf_event_quest(), FIELD(uint32_t, rec, 0x518),
                 FIELD(uint32_t, rec, 0x51c), FIELD(uint32_t, rec, 0x520));
        s->rage_seen = rage;
    }
    if (s->zone.marker != 0xff && timerDown(self, &s->zone.timer, 1.0f)) s->zone.marker = 0xff;
    gcf_zone_hunter(self, s);
    uint8_t g = FIELD(uint8_t *, self, GCF_EN_WORK)[0x36];
    if (g != s->glow) {
        if (g == 3) glow(self, 51, 52, "Angry_Start", 0);
        else if (g == 0 && s->glow == 3) glow(self, 51, 52, "Angry_End", 0);
        s->glow = g;
    }
    return 0;
}
