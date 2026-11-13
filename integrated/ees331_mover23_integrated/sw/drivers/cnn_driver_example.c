/* FPGA1 queue driver: uncached, in-order, same-clock CPU memory contract.
 * Reserve all task regions until completion. A signal fence is only a compiler
 * barrier; cached platforms need their own cache and I/O synchronization API.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>

typedef struct {
    volatile uint32_t CONTROL;
    volatile const uint32_t STATUS;
    volatile uint32_t QUEUE_BASE;
    volatile const uint32_t reserved0[3];
    volatile uint32_t TASK_COUNT;
    volatile const uint32_t reserved1[2];
} cnn_registers;
typedef struct {
    uint32_t version_opcode, input_addr, output_addr, weight_addr;
    uint32_t bias_or_params_addr, height_width, channels, layer_param;
} cnn_task;
_Static_assert(offsetof(cnn_registers, QUEUE_BASE) == 8, "queue offset");
_Static_assert(offsetof(cnn_registers, TASK_COUNT) == 0x18, "count offset");
_Static_assert(sizeof(cnn_registers) == 0x24, "MMIO size");
_Static_assert(sizeof(cnn_task) == 32, "descriptor size");
enum { CNN_OK=0, CNN_BAD_ARGUMENT=-1, CNN_BUSY=-2, CNN_ERROR=-3, CNN_TIMEOUT=-4 };

int cnn_run_queue(uintptr_t mmio_base, uint32_t queue_addr,
                  uint32_t task_count, uint32_t poll_limit)
{
    if (!poll_limit || !task_count || (mmio_base & 3u) || (queue_addr & 31u))
        return CNN_BAD_ARGUMENT;
    cnn_registers *r = (cnn_registers *)mmio_base;
    if (r->STATUS & 1u) return CNN_BUSY;
    atomic_signal_fence(memory_order_seq_cst);
    r->QUEUE_BASE = queue_addr;
    r->TASK_COUNT = task_count;
    r->CONTROL = 0x3du;
    for (uint32_t n=0; n<poll_limit; ++n) {
        uint32_t s = r->STATUS;
        if (s & 4u) return CNN_ERROR;
        if ((s & 3u) == 2u) {
            atomic_signal_fence(memory_order_seq_cst);
            return CNN_OK;
        }
    }
    // Timeout does not release RAM ownership.
    return CNN_TIMEOUT;
}

int cnn_soft_reset(uintptr_t mmio_base, uint32_t poll_limit)
{
    if (!poll_limit || (mmio_base & 3u)) return CNN_BAD_ARGUMENT;
    cnn_registers *r = (cnn_registers *)mmio_base;
    r->CONTROL = 2u;
    for (uint32_t n=0; n<poll_limit; ++n)
        if (!(r->STATUS & 1u)) return CNN_OK;
    // The CPU memory subsystem fault needs system reset, not just CONTROL=2.
    return CNN_TIMEOUT;
}
