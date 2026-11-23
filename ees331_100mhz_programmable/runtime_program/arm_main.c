#include "protocol.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xuartps.h"
#ifdef SDT
#include "sleep.h"
#include "xiltimer.h"
#else
#include "xtime_l.h"
#endif

#define UART_BASE 0xe0001000u
#define QUEUE_SIZE 16u
#define TIMEOUT_SECONDS 10u

static uint8_t image[EES331_IMEM_BYTES + EES331_IMAGE_MAX_DATA];
static struct task {
    uint32_t epoch, id, order, sequence, state, status;
    uint32_t args[EES331_TASK_ARGS], result[EES331_RESULT_WORDS];
} tasks[QUEUE_SIZE];
static struct task *active;
static uint32_t next_order;
static int updating;

static uint32_t rd(uint32_t offset) { return Xil_In32(EES331_GP0_BASE + offset); }
static void wr(uint32_t offset, uint32_t value) { Xil_Out32(EES331_GP0_BASE + offset, value); }

static void barrier(void)
{
    __asm__ volatile ("dsb sy" ::: "memory");
}

static void pump(void)
{
    if (active && rd(EES331_ACK) == active->sequence) {
        active->status = rd(EES331_REPLY_STATUS);
        for (unsigned i = 0; i < EES331_RESULT_WORDS; ++i)
            active->result[i] = rd(EES331_REPLY_DATA + 4 * i);
        active->state = active->status == EES331_TASK_OK ? EES331_DONE :
                        active->status == EES331_TASK_CANCELLED ? EES331_CANCELLED : EES331_FAILED;
        active = 0;
    }
    if (active || updating || (rd(EES331_PROGRAM_CONTROL) & 13u) != 1u ||
        rd(EES331_CPU_READY) != EES331_READY_VALUE)
        return;

    struct task *next = 0;
    for (unsigned i = 0; i < QUEUE_SIZE; ++i)
        if (tasks[i].state == EES331_QUEUED &&
            (!next || (int32_t)(tasks[i].order - next->order) < 0))
            next = &tasks[i];
    if (!next)
        return;

    uint32_t sequence = rd(EES331_REQUEST);
    if (sequence != rd(EES331_ACK))
        return;
    wr(EES331_COMMAND, EES331_EXEC_TASK);
    wr(EES331_ARGS, next->id);
    for (unsigned i = 0; i < EES331_TASK_ARGS; ++i)
        wr(EES331_ARGS + 4 * (i + 1), next->args[i]);
    barrier();
    wr(EES331_REQUEST, sequence + 1);
    barrier();
    next->sequence = sequence + 1;
    next->state = EES331_RUNNING;
    active = next;
}

static int expired(XTime begin)
{
    XTime now;
    XTime_GetTime(&now);
    return now - begin >= (XTime)COUNTS_PER_SECOND * TIMEOUT_SECONDS;
}

static int receive(void *destination, unsigned size)
{
    uint8_t *p = destination;
    XTime last_byte;
    XTime_GetTime(&last_byte);
    while (size) {
        if (XUartPs_IsReceiveData(UART_BASE)) {
            *p++ = (uint8_t)XUartPs_ReadReg(UART_BASE, XUARTPS_FIFO_OFFSET);
            --size;
            XTime_GetTime(&last_byte);
        } else {
            pump();
            if (expired(last_byte))
                return -1;
        }
    }
    return 0;
}

static void send_word(uint32_t word)
{
    for (unsigned i = 0; i < 4; ++i)
        XUartPs_SendByte(UART_BASE, (uint8_t)(word >> (8 * i)));
}

static uint32_t word_at(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint32_t crc32(const uint8_t *p, unsigned length)
{
    uint32_t crc = 0xffffffffu;
    for (unsigned i = 0; i < length; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static void cancel_queued(void)
{
    for (unsigned i = 0; i < QUEUE_SIZE; ++i)
        if (tasks[i].state == EES331_QUEUED) {
            tasks[i].state = EES331_CANCELLED;
            tasks[i].status = EES331_TASK_CANCELLED;
        }
}

static uint32_t load_program(void)
{
    uint32_t header[5];
    if (receive(header, sizeof header))
        return 1;
    const uint32_t mode = header[0], text = header[2], data = header[3];
    if (header[1] != EES331_IMAGE_MAGIC || !text || text > EES331_IMEM_BYTES ||
        data > EES331_IMAGE_MAX_DATA || ((text | data) & 3u))
        return 2;
    if (receive(image, text + data))
        return 1;
    if ((mode != EES331_DRAIN && mode != EES331_CANCEL) ||
        crc32(image, text + data) != header[4])
        return 2;

    uint32_t control = rd(EES331_PROGRAM_CONTROL);
    if ((control & 1u) && !(control & 12u))
        wr(EES331_PROGRAM_CONTROL, mode);
    cancel_queued();

    XTime start;
    XTime_GetTime(&start);
    while ((rd(EES331_PROGRAM_CONTROL) & 1u) || active) {
        pump();
        if (expired(start))
            return 3;
    }

    wr(EES331_PROGRAM_CONTROL, EES331_BEGIN);
    for (unsigned offset = 0; offset < EES331_IMEM_BYTES; offset += 4)
        wr(EES331_IMEM_WINDOW + offset, offset < text ? word_at(image + offset) : EES331_RV_NOP);
    for (unsigned offset = 0; offset < EES331_DMEM_BYTES; offset += 4) {
        unsigned relative = offset - EES331_DATA_START;
        wr(EES331_DMEM_WINDOW + offset, relative < data ? word_at(image + text + relative) : 0);
    }
    barrier();
    if (!(rd(EES331_PROGRAM_CONTROL) & 16u))
        return 4;
    wr(EES331_PROGRAM_CONTROL, EES331_START);
    barrier();

    XTime_GetTime(&start);
    while (rd(EES331_CPU_READY) != EES331_READY_VALUE)
        if (expired(start))
            return 5;
    return 0;
}

static uint32_t queue_task(uint32_t *id, uint32_t *epoch)
{
    uint32_t input[1 + EES331_TASK_ARGS];
    if (receive(input, sizeof input))
        return 1;
    *id = input[0];
    *epoch = rd(EES331_PROGRAM_EPOCH);
    if ((rd(EES331_PROGRAM_CONTROL) & 13u) != 1u ||
        rd(EES331_CPU_READY) != EES331_READY_VALUE)
        return 2;
    struct task *slot = 0;
    for (unsigned i = 0; i < QUEUE_SIZE; ++i) {
        if (tasks[i].state != EES331_EMPTY && tasks[i].id == *id && tasks[i].epoch == *epoch)
            return 3;
        if (tasks[i].state == EES331_EMPTY && !slot)
            slot = &tasks[i];
    }
    if (!slot)
        return 4;
    slot->id = *id;
    slot->epoch = *epoch;
    slot->order = next_order++;
    slot->state = EES331_QUEUED;
    slot->status = 0;
    for (unsigned i = 0; i < EES331_TASK_ARGS; ++i)
        slot->args[i] = input[i + 1];
    for (unsigned i = 0; i < EES331_RESULT_WORDS; ++i)
        slot->result[i] = 0;
    return 0;
}

static void reply_task(void)
{
    uint32_t key[2];
    if (receive(key, sizeof key)) {
        send_word(1);
        return;
    }
    for (unsigned i = 0; i < QUEUE_SIZE; ++i) {
        struct task *t = &tasks[i];
        if (t->state == EES331_EMPTY || t->epoch != key[0] || t->id != key[1])
            continue;
        send_word(0);
        send_word(t->state);
        send_word(t->status);
        for (unsigned j = 0; j < EES331_RESULT_WORDS; ++j)
            send_word(t->result[j]);
        if (t->state >= EES331_DONE)
            t->state = EES331_EMPTY;
        return;
    }
    send_word(2);
}

static int synchronize_cache(uint32_t address, uint32_t bytes, uint32_t operation)
{
    pump();
    if (active || (rd(EES331_PROGRAM_CONTROL) & 13u) != 1u ||
        rd(EES331_CPU_READY) != EES331_READY_VALUE)
        return -1;
    const uint32_t sequence = rd(EES331_REQUEST);
    if (sequence != rd(EES331_ACK))
        return -1;
    // This is an internal SDK operation, serialized with the task mailbox.
    wr(EES331_COMMAND, EES331_CACHE_SYNC);
    wr(EES331_ARGS + 4, address);
    wr(EES331_ARGS + 8, bytes);
    wr(EES331_ARGS + 12, operation);
    barrier();
    wr(EES331_REQUEST, sequence + 1);
    barrier();
    XTime start;
    XTime_GetTime(&start);
    while (rd(EES331_ACK) != sequence + 1)
        if (expired(start))
            return -1;
    return rd(EES331_REPLY_STATUS) == EES331_TASK_OK ? 0 : -1;
}

static void transfer_ddr(int write)
{
    uint32_t range[2];
    if (receive(range, sizeof range)) {
        send_word(1);
        return;
    }
    const uint32_t address = range[0], bytes = range[1];
    if (!bytes || bytes > sizeof image || address >= EES331_DDR_BYTES ||
        bytes > EES331_DDR_BYTES - address) {
        send_word(2);
        return;
    }
    if (write && receive(image, bytes)) {
        send_word(1);
        return;
    }
    // No queued task may begin between the fence and the host transfer.
    if (active) {
        send_word(3);
        return;
    }
    for (unsigned i = 0; i < QUEUE_SIZE; ++i)
        if (tasks[i].state == EES331_QUEUED) {
            send_word(3);
            return;
        }
    if (synchronize_cache(address, bytes, write ? 2u : 1u)) {
        send_word(4);
        return;
    }

    const uintptr_t physical = EES331_DDR_BASE + address;
    uint8_t *ddr = (uint8_t *)physical;
    if (write) {
        for (unsigned i = 0; i < bytes; ++i)
            ddr[i] = image[i];
        Xil_DCacheFlushRange(physical, bytes);
        barrier();
        send_word(0);
    } else {
        Xil_DCacheInvalidateRange(physical, bytes);
        barrier();
        send_word(0);
        for (unsigned i = 0; i < bytes; ++i)
            XUartPs_SendByte(UART_BASE, ddr[i]);
    }
}

int main(void)
{
#ifdef SDT
    /* The BSP starts the global timer on its first sleep call. */
    usleep(1);
#endif
    XUartPs uart;
    XUartPs_Config *cfg = XUartPs_LookupConfig(UART_BASE);
    if (!cfg || XUartPs_CfgInitialize(&uart, cfg, UART_BASE) != XST_SUCCESS ||
        XUartPs_SetBaudRate(&uart, 115200) != XST_SUCCESS)
        return 1;
    XUartPs_SetOperMode(&uart, XUARTPS_OPER_MODE_NORMAL);
    for (;;) {
        pump();
        if (!XUartPs_IsReceiveData(UART_BASE))
            continue;
        uint8_t command = (uint8_t)XUartPs_ReadReg(UART_BASE, XUARTPS_FIFO_OFFSET);
        switch (command) {
        case 'L': {
            updating = 1;
            uint32_t status = load_program();
            updating = 0;
            send_word(status);
            send_word(rd(EES331_PROGRAM_EPOCH));
            break;
        }
        case 'T': {
            uint32_t id = 0, epoch = 0;
            uint32_t status = queue_task(&id, &epoch);
            send_word(status);
            send_word(epoch);
            send_word(id);
            break;
        }
        case 'R':
            reply_task();
            break;
        case 'W':
        case 'M':
            transfer_ddr(command == 'W');
            break;
        case 'S':
            send_word(0);
            send_word(rd(EES331_PROGRAM_CONTROL));
            send_word(rd(EES331_PROGRAM_EPOCH));
            send_word(rd(EES331_CPU_READY));
            break;
        default:
            send_word(0xffffffffu);
        }
    }
}
