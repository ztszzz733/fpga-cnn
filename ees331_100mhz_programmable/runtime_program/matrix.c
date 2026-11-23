#include "rv32_cnn.h"

static uint32_t invocations;

int ees331_user_task(const uint32_t args[EES331_TASK_ARGS],
                     uint32_t result[EES331_RESULT_WORDS])
{
    if (args[8]) {
        const int status = ees331_k1_execute(2, args[0], args[1], args[2],
                                             args[3], args[4], args[5]);
        if (status == EES331_TASK_OK) {
            result[0] = args[2];
            result[1] = args[3] * args[5] * 4;
        }
        return status;
    }

    // Limit inputs so signed products and sums are representable.
    for (unsigned i = 0; i < 8; ++i)
        if ((int32_t)args[i] < -16384 || (int32_t)args[i] > 16384)
            return EES331_TASK_INVALID;

    for (unsigned row = 0; row < 2; ++row) {
        if (ees331_cancel_requested())
            return EES331_TASK_CANCELLED;
        for (unsigned col = 0; col < 2; ++col) {
            int32_t x = (int32_t)args[row * 2] * (int32_t)args[4 + col];
            int32_t y = (int32_t)args[row * 2 + 1] * (int32_t)args[6 + col];
            result[row * 2 + col] = (uint32_t)(x + y);
        }
    }
    ++invocations;
    return EES331_TASK_OK;
}
