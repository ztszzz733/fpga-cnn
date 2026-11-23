#include "rv32_cnn.h"

// The host supplies [100,1] for each requested point. Each 30-degree
// coefficient in DDR is a pair of signed int8 values [hundreds, remainder].
// K1 forms the INT32 dot product; the result is scaled by 1000.
int ees331_user_task(const uint32_t args[EES331_TASK_ARGS],
                     uint32_t result[EES331_RESULT_WORDS])
{
    const uint32_t degrees = args[0], points = args[1], cosine = args[2];
    const uint32_t input = args[3], table = args[4], output = args[5], unit = args[6];
    if (degrees >= 360 || degrees % 30 || !points || points > 512 ||
        cosine > 1 || table > EES331_DDR_BYTES - 24)
        return EES331_TASK_INVALID;

    const uint32_t angle = degrees + (cosine ? 90u : 0u);
    const uint32_t step = (angle >= 360 ? angle - 360 : angle) / 30;
    const int status = ees331_k1_execute(unit, input, table + 2 * step, output,
                                         points, 2, 1);
    if (status == EES331_TASK_OK) {
        result[0] = output;
        result[1] = points * 4;
    }
    return status;
}
