#include "rv32_user.h"

static volatile uint32_t *register_at(uint32_t offset)
{
    return (volatile uint32_t *)(uintptr_t)(EES331_GP0_BASE + offset);
}

uint32_t ees331_register_read(uint32_t index)
{
    *register_at(8) = index;
    return *register_at(12);
}

void ees331_register_write(uint32_t index, uint32_t value)
{
    *register_at(8) = index;
    *register_at(12) = value;
}

int ees331_cancel_requested(void)
{
    return ees331_register_read(EES331_PROGRAM_CONTROL) == EES331_CANCEL;
}

int ees331_synchronize_cache(uint32_t address, uint32_t bytes, uint32_t operation)
{
    if (!bytes || address >= EES331_DDR_BYTES || bytes > EES331_DDR_BYTES - address ||
        (operation != 1 && operation != 2))
        return EES331_TASK_INVALID;
    ees331_register_write(0x2008, address);
    ees331_register_write(0x200c, bytes);
    ees331_register_write(0x2004, operation);
    uint32_t state;
    do {
        state = ees331_register_read(0x2000);
    } while (state & 2u);
    return (state & 12u) ? EES331_TASK_INVALID : EES331_TASK_OK;
}

void ees331_run(void)
{
    ees331_register_write(EES331_CPU_READY, EES331_READY_VALUE);
    for (;;) {
        uint32_t sequence = *register_at(16);
        if (sequence != *register_at(20)) {
            uint32_t args[EES331_TASK_ARGS];
            uint32_t result[EES331_RESULT_WORDS] = {0};
            for (unsigned i = 0; i < EES331_TASK_ARGS; ++i)
                args[i] = ees331_register_read(EES331_ARGS + 4 * (i + 1));
            uint32_t command = ees331_register_read(EES331_COMMAND);
            int status = EES331_TASK_INVALID;
            if (ees331_cancel_requested())
                status = EES331_TASK_CANCELLED;
            else if (command == EES331_EXEC_TASK)
                status = ees331_user_task(args, result);
            else if (command == EES331_CACHE_SYNC)
                status = ees331_synchronize_cache(args[0], args[1], args[2]);
            if (status == EES331_TASK_OK && ees331_cancel_requested())
                status = EES331_TASK_CANCELLED;
            for (unsigned i = 0; i < EES331_RESULT_WORDS; ++i)
                ees331_register_write(EES331_REPLY_DATA + 4 * i,
                                      status == EES331_TASK_OK ? result[i] : 0);
            ees331_register_write(EES331_REPLY_STATUS, (uint32_t)status);
            __asm__ volatile("fence iorw,iorw" ::: "memory");
            *register_at(20) = sequence;
        }

        if (ees331_register_read(EES331_PROGRAM_CONTROL) != 0) {
            // Also covers a task published just before the stop request.
            if (*register_at(16) != *register_at(20))
                continue;
            ees331_register_write(EES331_PROGRAM_CONTROL, 1);
            // Hardware holds this CPU in reset after accepting the stop.
            for (;;)
                __asm__ volatile("nop");
        }
    }
}
