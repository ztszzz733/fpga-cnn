#ifndef EES331_SCHEDULE_H
#define EES331_SCHEDULE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EES331_DDR_LIMIT 0x01000000u
/* K3[1:0], PW8[5:2], Post[7:6], Add[8], Pad[9]; DW7 disabled. */
#define EES331_UNIT_MASK 0x3ffu
#define EES331_FRAME_LIMIT 4u
#define EES331_STEP_LIMIT 256u

typedef struct {
    void *context;
    uint8_t *ddr;
    int (*read_plan)(void *, void *, uint32_t);
    int (*rpc)(void *, uint32_t, uint32_t, uint32_t, uint32_t[4]);
    void (*sync_ddr)(void *, uint32_t, uint32_t, int);
    uint64_t (*now_ms)(void *);
    void (*pause)(void *);
    int (*save)(void *, unsigned, uint32_t, const uint8_t *, uint32_t);
    void (*event)(void *, const char *, uint32_t);
    void (*error)(void *, const char *, int);
} ees331_schedule_io;

/* Run a single model group. Outputs are saved to their original slot order. */
int ees331_schedule(const ees331_schedule_io *io, uint32_t plan_bytes);

#ifdef __cplusplus
}
#endif
#endif
