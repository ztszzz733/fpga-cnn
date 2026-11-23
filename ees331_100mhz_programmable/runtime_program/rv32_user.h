#ifndef EES331_RV32_USER_H
#define EES331_RV32_USER_H
#include "protocol.h"

int ees331_user_task(const uint32_t args[EES331_TASK_ARGS],
                     uint32_t result[EES331_RESULT_WORDS]);
int ees331_cancel_requested(void);
int ees331_synchronize_cache(uint32_t address, uint32_t bytes, uint32_t operation);
uint32_t ees331_register_read(uint32_t index);
void ees331_register_write(uint32_t index, uint32_t value);

#endif
