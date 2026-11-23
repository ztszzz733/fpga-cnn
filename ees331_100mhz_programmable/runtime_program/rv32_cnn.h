#ifndef EES331_RV32_CNN_H
#define EES331_RV32_CNN_H
#include "rv32_user.h"
#include "cnn_simple.h"

static uint32_t cnn_read(void *context, uint32_t offset)
{
    (void)context;
    return ees331_register_read(0x1000u + offset);
}

static void cnn_write(void *context, uint32_t offset, uint32_t value)
{
    (void)context;
    ees331_register_write(0x1000u + offset, value);
}

static void cnn_fence(void *context)
{
    (void)context;
    __asm__ volatile("fence iorw,iorw" ::: "memory");
}

static int ees331_k1_execute(unsigned unit, uint32_t input, uint32_t weights,
                             uint32_t output, uint32_t rows, uint32_t inner, uint32_t cols)
{
    if (unit < 2 || unit > 3 || !rows || rows > 512 || !inner || inner > 512 || !cols || cols > 512)
        return EES331_TASK_INVALID;
    if (input >= EES331_DDR_BYTES || rows * inner > EES331_DDR_BYTES - input ||
        weights >= EES331_DDR_BYTES || inner * cols > EES331_DDR_BYTES - weights ||
        output >= EES331_DDR_BYTES || rows * cols * 4 > EES331_DDR_BYTES - output)
        return EES331_TASK_INVALID;

    const unsigned page = CNN_SIMPLE_PAGE(unit);
    const cnn_simple_io io = {0, cnn_read, cnn_write, cnn_fence};
    cnn_simple_descriptor descriptor;
    if (cnn_simple_make(&descriptor, unit, input, weights, output, rows, 1,
                        inner, cols, 1, 0, 0) || cnn_simple_submit(&io, unit, &descriptor))
        return EES331_TASK_INVALID;

    // An accepted CNN request can outlive a CPU task. Wait for the unit's
    // abort/drain state before acknowledging cancellation to the loader.
    unsigned cancelled = 0;
    uint32_t status;
    do {
        if (!cancelled && ees331_cancel_requested()) {
            cnn_write(0, page, 4);
            cancelled = 1;
        }
        status = cnn_read(0, page + 4);
    } while (status & 1u);
    if (cancelled)
        return EES331_TASK_CANCELLED;
    if ((status & 6u) != 2u)
        return EES331_TASK_INVALID;
    // Return only after the result is visible in PS DDR. If a stop is
    // requested during this writeback, the runtime acknowledges it afterward.
    return ees331_synchronize_cache(output, rows * cols * 4, 1);
}

#endif
