/* shellswap.h: a port's own copies of GU shell families, swapped into GU's shell request for its posts only
 * (module/shellswap.c). */
#pragma once
#include <stdint.h>

struct shellswap {
    uint16_t em;                    /* EN_ID of the shell's owner */
    const char *tag;                /* log prefix */
    uint32_t (*fid)(uint32_t id);   /* file ID of the port's copy of GU shell id's family, 0 = GU's own */
    int (*any)(uint32_t id);        /* 1 = every request of this id takes the copy, whoever posts it (0 = none: only
                                       the requests shellswap_mark names) */
};

extern const struct shellswap em076_01_shellswap, em069_01_shellswap, em013_06_shellswap;

void shellswap_mark(void *owner);   /* the owner's next shell request takes its copy (its class's own post sites) */
