/* b0gate.h: a port's 4U motion-effect conditions (MEF byte 0) for the core PSL gate, module/b0gate.c. */
#pragma once
#include <stdint.h>

struct b0rec { uint16_t id; uint8_t b0; };     /* a MEF record and its condition bit */
struct b0act { uint8_t cat, num, bit; };       /* a 4U action (GU runs it under the same numbers) and a bit its
                                                  handler sets on every frame */
struct b0port {
    uint16_t em;                                /* EN_ID */
    const char *tag;                            /* log prefix */
    const struct b0rec *rec;
    uint32_t nrec;
    const struct b0act *act;
    uint32_t nact;
    uint32_t (*extra)(const void *self);        /* bits 4U sets outside the actions (its ground bits), or 0 */
};

extern const struct b0port em005_01_b0port, em068_01_b0port, em069_01_b0port, em070_01_b0port, em089_b0port,
    em090_00_b0port, em090_01_b0port;

/* a port whose 4U code is tied to its own ungated records: told of each PEL u post of its unit (it gates nothing) */
struct b0post {
    uint16_t em;                                /* EN_ID */
    void (*posted)(void *self, uint32_t id);
};

extern const struct b0post em013_06_b0post;
