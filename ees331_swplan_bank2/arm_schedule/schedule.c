#include "schedule.h"
#include "k3_plan.h"
#include <stddef.h>

enum {
    DDR_READY = 1, CONFIG_WRITE, CONFIG_COMMIT, START, FRAME, RESULT, ACK,
    RESET, CACHE_CONFIG, STATUS
};

typedef struct {
    uint32_t magic, frames, steps, units, model_bytes, model_crc, result_offset, result_bytes;
} schedule_header;

typedef struct {
    uint32_t id, input, bytes, workspace, workspace_bytes, crc;
} frame_plan;

static int failure(const ees331_schedule_io *io, const char *what, int status)
{
    io->error(io->context, what, status);
    return -1;
}

static int within(uint32_t base, uint32_t bytes, uint32_t limit)
{
    return base < limit && bytes != 0 && bytes <= limit - base;
}

static int overlaps(uint32_t a, uint32_t n, uint32_t b, uint32_t m)
{
    return a < b + m && b < a + n;
}

static uint32_t crc32(const uint8_t *data, uint32_t bytes)
{
    uint32_t crc = ~0u;
    while (bytes--) {
        crc ^= *data++;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((0u - (crc & 1u)) & 0xedb88320u);
    }
    return ~crc;
}

static int call(const ees331_schedule_io *io, uint32_t op, uint32_t a, uint32_t b,
                uint32_t *result)
{
    uint32_t unused[4];
    const int status = io->rpc(io->context, op, a, b, result ? result : unused);
    if (status)
        io->error(io->context, "mailbox RPC failed", (int)(op * 100) + status);
    return status;
}

static int upload(const ees331_schedule_io *io, uint32_t base, uint32_t bytes, uint32_t crc)
{
    for (uint32_t at = 0; at < bytes;) {
        uint32_t chunk = bytes - at;
        if (chunk > 16384u)
            chunk = 16384u;
        if (io->read_plan(io->context, io->ddr + base + at, chunk))
            return failure(io, "read model/input payload", -1);
        at += chunk;
    }
    if (crc32(io->ddr + base, bytes) != crc)
        return failure(io, "model/input CRC mismatch", -1);
    io->sync_ddr(io->context, base, bytes, 1);
    return 0;
}

int ees331_schedule(const ees331_schedule_io *io, uint32_t plan_bytes)
{
    schedule_header plan;
    frame_plan frame[EES331_FRAME_LIMIT];
    if (io->read_plan(io->context, &plan, sizeof(plan)) ||
        plan.magic != 0x31435345u || !plan.frames || plan.frames > EES331_FRAME_LIMIT ||
        !plan.steps || plan.steps > EES331_STEP_LIMIT || !plan.units ||
        (plan.units & ~EES331_UNIT_MASK) || !within(0, plan.model_bytes, EES331_DDR_LIMIT) ||
        (plan.model_bytes & 1023u))
        return failure(io, "invalid plan header", -1);
    uint32_t expected = sizeof(plan) + plan.frames * sizeof(frame_plan) +
                        plan.steps * 20u * sizeof(uint32_t) + plan.model_bytes;
    for (unsigned f = 0; f < plan.frames; ++f) {
        frame_plan *p = &frame[f];
        if (io->read_plan(io->context, p, sizeof(*p)) ||
            !within(p->input, p->bytes, EES331_DDR_LIMIT) ||
            !within(p->workspace, p->workspace_bytes, EES331_DDR_LIMIT) ||
            !within(plan.result_offset, plan.result_bytes, p->workspace_bytes) ||
            ((p->input | p->workspace | p->workspace_bytes) & 1023u) || (p->bytes & 63u) ||
            p->input < plan.model_bytes || p->workspace < plan.model_bytes ||
            overlaps(p->input, p->bytes, p->workspace, p->workspace_bytes))
            return failure(io, "invalid DDR frame partition", (int)f);
        for (unsigned g = 0; g < f; ++g) {
            const frame_plan *q = &frame[g];
            if (p->id == q->id || overlaps(p->input, p->bytes, q->input, q->bytes) ||
                overlaps(p->workspace, p->workspace_bytes, q->input, q->bytes) ||
                overlaps(p->input, p->bytes, q->workspace, q->workspace_bytes) ||
                overlaps(p->workspace, p->workspace_bytes, q->workspace, q->workspace_bytes))
                return failure(io, "overlapping DDR frame partitions", (int)f);
        }
        expected += p->bytes;
    }
    if (expected != plan_bytes)
        return failure(io, "plan file size mismatch", -1);

    uint32_t state[4];
    const uint64_t ready_deadline = io->now_ms(io->context) + 10000;
    for (;;) {
        if (call(io, STATUS, 0, 0, state) || (state[0] & 42u) || (state[2] & 28u))
            return failure(io, "CNN busy, output held, or faulted", -1);
        if ((state[2] & 3u) == 1u)
            break;
        if (io->now_ms(io->context) >= ready_deadline)
            return failure(io, "pager initialization timeout", -1);
        io->pause(io->context);
    }
    if (call(io, DDR_READY, 0x44524459u, 0, NULL) || call(io, RESET, 0, 0, state) ||
        call(io, CACHE_CONFIG, 0x14, 0, NULL) ||
        call(io, CONFIG_WRITE, 0x10, plan.units, NULL))
        return -1;
    const uint32_t epoch = state[0];
    io->event(io->context, "CONFIG_BEGIN", 0);
    for (unsigned step = 0; step < plan.steps; ++step) {
        uint32_t row[20];
        if (io->read_plan(io->context, row, sizeof(row)))
            return failure(io, "read task row", (int)step);
        const unsigned final = step == plan.steps - 1u;
        if (row[0] > 5u || row[0] == 3u || ((row[16] >> 15) & 1u) != final ||
            (final && (row[3] != plan.result_offset || row[19] != plan.result_bytes)))
            return failure(io, "unsupported task or result schema", (int)step);
        if (!ees331_validate_k3(row))
            return failure(io, "invalid software K3 read plan", (int)step);
        if (row[0]==0u) {
            const uint64_t out_bytes=(uint64_t)((row[7]-3u)/row[10]+1u)*
                                     ((row[8]-3u)/row[10]+1u)*row[9]*4u;
            for (unsigned f=0; f<plan.frames; ++f) {
                const frame_plan *p=&frame[f];
                const unsigned am=row[16]&3u, bm=(row[16]>>2)&3u;
                const uint32_t alimit=am==1?p->bytes:am==2?p->workspace_bytes:plan.model_bytes;
                const uint32_t blimit=bm==1?p->bytes:bm==2?p->workspace_bytes:plan.model_bytes;
                if (am>2 || bm>2 || !within(row[1],row[12],alimit) ||
                    !within(row[2],row[15],blimit) ||
                    !within(row[3],(uint32_t)out_bytes,p->workspace_bytes))
                    return failure(io,"K3 tensor outside software partition",(int)step);
            }
        }
        if (call(io, CONFIG_WRITE, 0x14, step, NULL) ||
            call(io, CONFIG_WRITE, 0x18, 0, NULL))
            return -1;
        for (unsigned w = 0; w < 20; ++w)
            if (call(io, CONFIG_WRITE, 0x1c, row[w], NULL))
                return -1;
        if (call(io, CONFIG_COMMIT, 4, 0, NULL))
            return failure(io, "template step rejected", (int)step);
    }
    for (unsigned f = 0; f < plan.frames; ++f) {
        const frame_plan *p = &frame[f];
        if (call(io, CONFIG_WRITE, 0x20, f, NULL) ||
            call(io, CONFIG_WRITE, 0x24, p->input, NULL) ||
            call(io, CONFIG_WRITE, 0x28, p->workspace, NULL) ||
            call(io, CONFIG_WRITE, 0x2c, p->id, NULL) ||
            call(io, CONFIG_COMMIT, 8, 0, NULL))
            return -1;
    }
    if (upload(io, 0, plan.model_bytes, plan.model_crc) ||
        call(io, CACHE_CONFIG, 0x10, plan.model_bytes, NULL) ||
        call(io, CACHE_CONFIG, 0x14, 1, NULL) ||
        call(io, CONFIG_WRITE, 0x0c, plan.frames, NULL) ||
        call(io, START, 0, 0, NULL))
        return -1;
    io->event(io->context, "BATCH_START", 0);
    for (unsigned f = 0; f < plan.frames; ++f) {
        const frame_plan *p = &frame[f];
        if (upload(io, p->input, p->bytes, p->crc) || call(io, FRAME, f, p->id, NULL))
            return -1;
        io->event(io->context, "FRAME_SUBMIT", f);
    }

    unsigned seen = 0;
    const uint64_t deadline = io->now_ms(io->context) + 600000;
    for (unsigned received = 0; received < plan.frames;) {
        uint32_t reply[4];
        const int rc = io->rpc(io->context, RESULT, 0, 0, reply);
        if (rc == 2) {
            if (io->now_ms(io->context) >= deadline)
                return failure(io, "CNN results timeout", -1);
            io->pause(io->context);
            continue;
        }
        if (rc)
            return failure(io, "result RPC failed", rc);
        unsigned f = 0;
        while (f < plan.frames && frame[f].id != reply[0])
            ++f;
        if (f == plan.frames || (seen & (1u << f)) || reply[2] != plan.result_bytes ||
            reply[1] != frame[f].workspace + plan.result_offset || reply[3] != epoch)
            return failure(io, "result descriptor mismatch", (int)reply[0]);
        io->sync_ddr(io->context, reply[1], reply[2], 0);
        if (io->save(io->context, f, reply[0], io->ddr + reply[1], reply[2]))
            return failure(io, "save CNN result", (int)f);
        io->event(io->context, "RESULT_READ", f);
        if (call(io, ACK, reply[0], reply[3], NULL))
            return -1;
        seen |= 1u << f;
        ++received;
    }
    if (call(io, STATUS, 0, 0, state) || (state[0] & 14u) != 4u ||
        state[1] != plan.frames * plan.steps)
        return failure(io, "final task count/state mismatch", -1);
    io->event(io->context, "BATCH_DONE", state[1]);
    return 0;
}
