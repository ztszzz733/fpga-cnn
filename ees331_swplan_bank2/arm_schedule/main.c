#include "schedule.h"
#include "FreeRTOS.h"
#include "task.h"
#include "ff.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xuartps.h"

#define UART1_BASE 0xe0001000u
#define MAILBOX_BASE 0x40000000u
#define DDR_BASE 0x10000000u

static FATFS volume;
static FIL plan_file;
static XUartPs uart;

static void barrier(void)
{
    __asm__ volatile ("dsb sy" ::: "memory");
}

static uint64_t now_ms(void *context)
{
    (void)context;
    static TickType_t previous;
    static uint64_t ticks;
    const TickType_t now = xTaskGetTickCount();
    ticks += (TickType_t)(now - previous);
    previous = now;
    return ticks * 1000u / configTICK_RATE_HZ;
}

static void pause_task(void *context)
{
    (void)context;
    vTaskDelay(pdMS_TO_TICKS(2u) + 1u);
}

static int mailbox(void *context, uint32_t op, uint32_t a, uint32_t b, uint32_t reply[4])
{
    uint64_t deadline = now_ms(context) + 10000u;
    while (Xil_In32(MAILBOX_BASE + 8u) != Xil_In32(MAILBOX_BASE + 12u)) {
        if (now_ms(context) >= deadline)
            return -1;
        pause_task(context);
    }
    const uint32_t sequence = Xil_In32(MAILBOX_BASE + 8u) + 1u;
    Xil_Out32(MAILBOX_BASE + 16u, op);
    Xil_Out32(MAILBOX_BASE + 20u, a);
    Xil_Out32(MAILBOX_BASE + 24u, b);
    Xil_Out32(MAILBOX_BASE + 28u, 0);
    Xil_Out32(MAILBOX_BASE + 32u, 0);
    barrier();
    Xil_Out32(MAILBOX_BASE + 8u, sequence);
    barrier();
    deadline = now_ms(context) + 10000u;
    const uint64_t fast_poll_end = now_ms(context) + 1u;
    while (Xil_In32(MAILBOX_BASE + 12u) != sequence) {
        const uint64_t now = now_ms(context);
        if (now >= deadline)
            return -1;
        if (now >= fast_poll_end)
            pause_task(context);
    }
    barrier();
    for (unsigned i = 0; i < 4u; ++i)
        reply[i] = Xil_In32(MAILBOX_BASE + 84u + 4u * i);
    return (int)Xil_In32(MAILBOX_BASE + 80u);
}

static void synchronize(void *context, uint32_t address, uint32_t bytes, int for_device)
{
    (void)context;
    barrier();
    if (for_device)
        Xil_DCacheFlushRange(DDR_BASE + address, bytes);
    else
        Xil_DCacheInvalidateRange(DDR_BASE + address, bytes);
    barrier();
}

static int read_plan(void *context, void *destination, uint32_t bytes)
{
    UINT read_bytes = 0;
    return f_read(context, destination, bytes, &read_bytes) != FR_OK || read_bytes != bytes;
}

static int save_result(void *context, unsigned slot, uint32_t id, const uint8_t *data, uint32_t bytes)
{
    (void)context;
    char path[] = "0:/OUT0.BIN";
    path[6] = (char)('0' + slot);
    FIL output;
    UINT written = 0;
    FRESULT status = f_open(&output, path, FA_WRITE | FA_CREATE_ALWAYS);
    if (status != FR_OK)
        return -1;
    status = f_write(&output, data, bytes, &written);
    const FRESULT closed = f_close(&output);
    if (status != FR_OK || closed != FR_OK || written != bytes)
        return -1;
    xil_printf("EES331 FRAME %u wrote %u bytes to %s\r\n", id, bytes, path);
    return 0;
}

static void event(void *context, const char *name, uint32_t argument)
{
    xil_printf("EES331 %s %u t_ms=%u\r\n", name, argument, (uint32_t)now_ms(context));
}

static void report_error(void *context, const char *error, int code)
{
    (void)context;
    xil_printf("EES331 ERROR %s (%d)\r\n", error, code);
}

static void run_task(void *unused)
{
    (void)unused;
    int status = -1;
    FRESULT fs = f_mount(&volume, "0:/", 1);
    if (fs == FR_OK) {
        fs = f_open(&plan_file, "0:/PLAN.BIN", FA_READ);
        if (fs == FR_OK) {
            if (Xil_In32(MAILBOX_BASE) == 0x45455332u) {
                const ees331_schedule_io io = {
                    &plan_file, (uint8_t *)DDR_BASE, read_plan, mailbox, synchronize,
                    now_ms, pause_task, save_result, event, report_error
                };
                status = ees331_schedule(&io, (uint32_t)f_size(&plan_file));
            } else {
                report_error(NULL, "unexpected PL mailbox ID", -1);
            }
            if (f_close(&plan_file) != FR_OK)
                status = -1;
        }
    }
    if (fs != FR_OK)
        report_error(NULL, "open SD PLAN.BIN", fs);
    if (f_mount(NULL, "0:/", 0) != FR_OK)
        status = -1;
    xil_printf("EES331 SCHEDULER %s\r\n", status ? "FAIL" : "PASS");
    vTaskDelete(NULL);
}

int main(void)
{
    XUartPs_Config *config = XUartPs_LookupConfig(UART1_BASE);
    if (!config || config->BaseAddress != UART1_BASE ||
        XUartPs_CfgInitialize(&uart, config, UART1_BASE) != XST_SUCCESS ||
        XUartPs_SetBaudRate(&uart, 115200u) != XST_SUCCESS)
        return 1;
    XUartPs_SetOperMode(&uart, XUARTPS_OPER_MODE_NORMAL);
    if (xTaskCreate(run_task, "cnn", 4096u, NULL, tskIDLE_PRIORITY + 1u, NULL) != pdPASS)
        return 2;
    vTaskStartScheduler();
    return 3;
}
