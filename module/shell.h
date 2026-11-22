/* shell.h: the ports' own attack shells (core; moved from Dalamadur's dala_shell.c on 2026-11-22, its second user being
 * the G-rank Crimson Fatalis). A 4U shell class becomes a GU uShellEnemy subclass with our DTI and a vtable copy,
 * posted through our own copy of GU's request 0x48c4f0, on a shell family of the port's (its def file ID in the
 * port's file range, a row whose param class is EmBase01). Evidence: Gogmazios' em089_shell.c (which keeps its own
 * copy) and Dalamadur's dala_meteor.c / dala_shell*.c. C = read in code, S = strong, G = guess. */
#pragma once
#include <stdint.h>
#include "game.h"

/* ---- GU uShellEnemy (main offsets / fields) ---- */
#define VT_uShellEnemy_SLOTS 83
#define SIZE_uShellEnemy     0x15d0u
#define SH_STATE             0xc      /* u32 unit state (& 7: 1 / 2 = alive) */
#define SH_DT                28       /* float time scale [4U +20] */
#define SH_POS               0x40     /* float x, y, z [4U +0x100] */
#define SH_ANGLES            0xfe8    /* u32 x, y, z [4U +0x110 / +0x114 / +0x118] */
#define SH_POS2              0x1000   /* bone-1001 capsule second point [4U +0x120] (GU 0x16e46c) */
#define SH_AREA              0x1054   /* u8 area [4U +0x130] */
#define SH_PARAM             0x136c   /* param object, owner at +0xc */
#define SH_ATK0              0x13a8   /* attack slot 0 [4U +360] */
#define ATK_ACTIVE           0x5      /* u8 slot active [4U +0x16d - 360] */
#define ATK_F14              0x14     /* float passed to slot 80 */
#define ATK_GROUP            0x34     /* u16 hit group: global serial at arming, GU 0x168ed0 / 4U 0xb70134 (C) */
#define ATK_TIME             0x60     /* float window length from the record's s16 +2 [4U slot +88] (C) */
#define SHELL_FIELDS         SIZE_uShellEnemy   /* first byte of a class's own fields */

/* a port's shell family: the def's file ID (served by the file_id hook), the shell table row whose param class our
 * request builds (EmBase01, DTI 0x188cb88), and the log prefix of the port */
struct shell_family {
    uint32_t file, row;
    const char *tag;
};

typedef struct {
    MtDTI dti;
    uint32_t dti_vt[2 + 3];
    uint32_t vt[2 + VT_uShellEnemy_SLOTS];
    uint32_t size;
    uint8_t registered;
} shcls_t;

/* class set-up: copies uShellEnemy's vtable, puts the given slots (0 = keep the base), registers the DTI */
void shell_register(shcls_t *c, const struct shell_family *f, const char *name, uint32_t size,
                    void *(*new_fn)(MtDTI *), void (*del)(void *), MtDTI *(*get_dti)(void *), void (*move)(void *),
                    int (*setup)(void *, void *), void (*kill)(void *));
void *shell_new(shcls_t *c);                        /* alloc + uShellEnemy ctor + our vtable, own fields zeroed */
void shell_free(shcls_t *c, void *self);            /* uShellEnemy dtor + release (slot 1) */
/* our copy of the GU request 0x48c4f0 (em089_shell.c): live-shell bound, the 64-B param (row f->row, entry 0, owner
 * and its record fields); 0 when the post is dropped (logged under `what`) */
void *shell_param(const struct shell_family *f, void *owner, const char *what);
void shell_param_free(void *param);
/* resource f->file, slot 79 set-up, unit line 18, shell manager; on failure the shell is deleted (slot 1) and 0
 * returned */
void *shell_start(const struct shell_family *f, void *shell, void *param, const char *what);
/* 4U 0x9ab120(shell, records, volumes, record, a, b) = GU slot 80(shell, 0, HDS entry, -1, a, b, group, f14); 4U
 * then writes a request group unless 0xffff, GU takes it as the group argument. 1 = armed */
int shell_arm(const struct shell_family *f, void *self, uint32_t hds, uint32_t a, uint32_t b, uint32_t group);
void shell_slots_off(void *self);                   /* 4U +0x16e = 255, +0x16d = 0 (0x4a247c's attack slots 0..2) */
void *shell_owner(void *self);
int shell_live(void *self);                         /* unit state 1 / 2 */
int shell_timer(void *self, float *t);              /* 4U 0x9aad4c: t -= dt, 1 once <= 0 (clamped) */
float shell_dt(void *self);                         /* 4U frames this tick = the shell's +28 */
uint32_t shell_group(void *self);                   /* 4U this+0x19c = slot 0 +0x34 */
float shell_owner_step(void *owner);                /* 4U 0x94460c: owner +668 (motion speed) * dt */
int shell_listener_pos(float *out);                 /* the local hunter (4U 0xaf79a4 +0xe30 + 16 stand-in) */

/* sounds (ids = the 4U request ids of the owner's request) */
void shell_snd_pos(void *owner, uint32_t id, const float *pos, uint32_t area);   /* 4U 0x312484 = GU 0x4efb98 */
void shell_snd_obj(void *owner, uint32_t id, void *obj, uint32_t area);          /* 4U 0x304d3c = GU 0x4efe58 */
void shell_snd_move(void *owner, uint32_t id, const float *pos);                 /* 4U 0x301074 = GU 0x4eff24 */
/* 4U 0x304c34(mgr, id, owner, joint, area, -2): the joint's position now (0xb054ac, else W+0x198), then a type-8
 * request there (0x312100), i.e. a point sound at the joint (C) -> GU jointPos + 0x4efb98 */
void shell_snd_joint_pos(void *owner, uint32_t id, uint32_t joint, uint32_t area);
/* 4U 0xbfd568(mgr *0x105729c, id, &pos) when the shell's area is the local player's (0xc4f188, C) = GU
 * 0x49eac(owner, id, pos, 0) with that test (Gogmazios' em089_shell016.c pairing of 0xbfe98c, S) */
void shell_cam_shake_pos(void *owner, uint32_t id, const float *pos, uint32_t area);
