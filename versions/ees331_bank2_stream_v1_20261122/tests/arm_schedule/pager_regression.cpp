#include "Vcnn_paged_mover.h"
#include "Vcnn_paged_mover___024root.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <stdexcept>
using U32 = uint32_t;
static void need(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }

struct Bench {
    Vcnn_paged_mover d;
    AxiDdr<Vcnn_paged_mover> ram{d};
    unsigned cycles = 0;
    unsigned isolation_checks = 0;
    bool inject_error = false;

    Bench() {
        d.rst_n = 0;
        d.cnn_valid = d.cnn_write = d.cnn_byte = d.cnn_cancel = 0;
        d.cache_csr_we = d.cache_csr_re = 0;
        d.cache_csr_addr = d.cache_csr_wdata = 0;
        for (unsigned c = 0; c < 10; ++c) d.cnn_addr[c] = d.cnn_wdata[c] = 0;
        ram.stress = true;
        for (unsigned i = 0; i < 5; ++i) tick();
        d.rst_n = 1;
        tick();
    }
    void tick() {
        need(cycles++ < 15000000, "regression watchdog");
        d.clk = 0;
        ram.drive();
        if (inject_error) d.S_AXI_HP0_RRESP = 2;
        d.eval();
        const auto *r = d.rootp;
        if (d.rst_n && r->cnn_paged_mover__DOT__state >= 3 &&
            r->cnn_paged_mover__DOT__state <= 6 && !r->cnn_paged_mover__DOT__wb_for_scan) {
            for (unsigned b = 0; b < 2; ++b) if (r->cnn_paged_mover__DOT__comp_req & (1u << b)) {
                need(((r->cnn_paged_mover__DOT__comp_slot >> (9 * b)) & 511u) !=
                     r->cnn_paged_mover__DOT__request_slot, "compute touched the DMA-locked page");
                ++isolation_checks;
            }
        }
        if (d.rst_n) ram.capture();
        d.clk = 1; d.eval();
        d.clk = 0; d.eval();
    }
    U32 csr(U32 addr) {
        d.cache_csr_addr = addr; d.cache_csr_re = 1; d.eval();
        U32 result = d.cache_csr_rdata; d.cache_csr_re = 0;
        return result;
    }
    void cfg(U32 addr, U32 value) {
        d.cache_csr_addr = addr; d.cache_csr_wdata = value;
        d.cache_csr_we = 1; tick(); d.cache_csr_we = 0; tick();
    }
    void submit(unsigned owner, U32 addr, bool write = false, U32 value = 0, bool byte = false) {
        d.cnn_addr[owner] = addr; d.cnn_wdata[owner] = value;
        d.cnn_write = write ? 1u << owner : 0;
        d.cnn_byte = byte ? 1u << owner : 0;
        d.cnn_valid = 1u << owner;
        for (unsigned i = 0;; ++i) {
            if (i >= 30000) throw std::runtime_error("request acceptance timeout addr=" +
                std::to_string(addr) + " owner=" + std::to_string(owner) + " status=" +
                std::to_string(csr(0)) + " cycle=" + std::to_string(cycles) +
                " pending=" + std::to_string(d.rootp->cnn_paged_mover__DOT__client_pending) +
                " selected=" + std::to_string(d.rootp->cnn_paged_mover__DOT__selected) +
                " valid=" + std::to_string(d.rootp->cnn_paged_mover__DOT__selected_valid) +
                " lookup=" + std::to_string(d.rootp->cnn_paged_mover__DOT__lookup_pending));
            d.eval(); bool accepted = (d.cnn_ready >> owner) & 1;
            tick(); if (accepted) break;
        }
        d.cnn_valid = d.cnn_write = d.cnn_byte = 0;
    }
    U32 access(unsigned owner, U32 addr, bool write = false, U32 value = 0, bool byte = false) {
        submit(owner, addr, write, value, byte);
        for (unsigned i = 0;; ++i) {
            need(i < 30000 && !d.cnn_mem_fault, "request response timeout/fault");
            d.eval();
            if ((d.cnn_response >> owner) & 1) {
                U32 result = d.cnn_rdata[owner]; tick(); return result;
            }
            tick();
        }
    }
    void flush(U32 start, U32 bytes, bool invalidate) {
        cfg(8, start); cfg(12, bytes); cfg(4, invalidate ? 2 : 1);
        while (csr(0) & 2) { need(!d.cnn_mem_fault, "maintenance fault"); tick(); }
    }
    void parallel_banks(bool with_miss = false) {
        constexpr U32 stream_base=0x800000;
        auto expected=[](unsigned c,unsigned word){return 0x12340000u^(c<<8)^word;};
        if(!with_miss)for(unsigned c=0;c<4;++c)for(unsigned w=0;w<64;++w) {
            U32 value=expected(c,w),addr=stream_base+c*1024+w*4;
            for(unsigned b=0;b<4;++b)ram.data[addr+b]=uint8_t(value>>(b*8));
        }
        for (unsigned c = 0; c < 4; ++c)
            need(access(c, stream_base + c * 1024) == expected(c,0), "prime bank read");
        std::array<unsigned, 4> sent{}, received{};
        unsigned maximum_parallel = 0;
        bool miss_done = !with_miss;
        if (with_miss) submit(9, 0x700000);
        for (unsigned timeout = 0; *std::min_element(received.begin(), received.end()) < 64 || !miss_done; ++timeout) {
            need(timeout < 3000, "parallel stream timeout");
            d.cnn_valid = 0;
            for (unsigned c = 0; c < 4; ++c) if (sent[c] < 64) {
                d.cnn_valid |= 1u << c;
                d.cnn_addr[c] = stream_base + c * 1024 + sent[c] * 4;
            }
            d.eval();
            if (d.cnn_response & (1u << 9)) {
                need(!miss_done && d.cnn_rdata[9] == 0xa5a5a5a5, "concurrent miss response");
                miss_done = true;
            }
            unsigned parallel = 0;
            unsigned bank_mask = d.rootp->cnn_paged_mover__DOT__comp_req;
            unsigned bank_parallel = (bank_mask & 1u) + ((bank_mask >> 1) & 1u);
            for (unsigned c = 0; c < 4; ++c) {
                if (d.cnn_response & (1u << c)) {
                    need(received[c] < sent[c] && d.cnn_rdata[c] == expected(c,received[c]),
                         "stream response order/data");
                    ++received[c];
                }
                if (d.cnn_valid & d.cnn_ready & (1u << c)) { ++sent[c]; ++parallel; }
            }
            maximum_parallel = std::max(maximum_parallel, bank_parallel);
            tick();
        }
        d.cnn_valid = 0; tick();
        need(maximum_parallel == 2, "two-bank concurrent physical requests missing");
    }
    void run() {
        need(csr(0x3c) == 401408, "392 KiB cache capacity");
        std::cout << "Checking two-bank parallel streams" << std::endl;
        parallel_banks();
        parallel_banks(true);
        need(isolation_checks >= 128, "concurrent DMA/page-isolation scenario not exercised");
        // Exceed all 392 slots, repeatedly cross replacement-bank tails and
        // verify dirty eviction, last-word addressing and refill data.
        constexpr unsigned pages = 401;
        std::cout << "Checking dirty eviction and replacement wrap" << std::endl;
        for (unsigned pass = 0; pass < 2; ++pass) {
            for (unsigned i = 0; i < pages; ++i)
                access(i % 10, 0x10000 + i * 1024 + 1020, true, 0x12340000 + pass * 1024 + i);
            for (int i = pages - 1; i >= 0; --i)
                need(access(i % 10, 0x10000 + i * 1024 + 1020) == 0x12340000 + pass * 1024 + i,
                     "victim wrap/writeback corruption");
        }
        access(9, 0x10001, true, 0x7b, true);
        need(access(8, 0x10000) == 0xa5a57ba5, "byte enables and neighbor preservation");
        // A one-byte fence starting inside a page must flush that page.
        flush(0x10001, 1, false);
        need(ram.data[0x10001] == 0x7b, "partial-page fence skipped dirty data");
        flush(0x10000, pages * 1024, true);
        for (unsigned i = 0; i < pages; ++i) {
            U32 addr = 0x10000 + i * 1024 + 1020, value = 0;
            for (unsigned b = 0; b < 4; ++b) value |= U32(ram.data[addr + b]) << (8 * b);
            need(value == 0x12340400 + i, "flush did not publish all outputs");
            need(access(i % 10, addr) == value, "invalidate/refill corruption");
        }
        // Maintenance must wait for requests already acknowledged at the
        // upstream FIFO, including a queued cold-page write.
        submit(4, 0x680000, true, 0x55667788);
        need(csr(0) & 2, "queued request missing from cache busy status");
        cfg(8, 0x680000); cfg(12, 1024); cfg(4, 1);
        bool write_replied = false;
        while (csr(0) & 2) {
            if (d.cnn_response & (1u << 4)) write_replied = true;
            need(!d.cnn_mem_fault, "queued maintenance fault"); tick();
        }
        if (d.cnn_response & (1u << 4)) write_replied = true;
        need(write_replied && ram.data[0x680000] == 0x88 && ram.data[0x680003] == 0x55,
             "maintenance overtook an accepted write");
        auto before = ram.read_bytes;
        std::cout << "Checking cancel, AXI faults and recovery" << std::endl;
        submit(5, 0x300000);
        while (!ram.reading) { need(!d.cnn_mem_fault, "cancel setup fault"); tick(); }
        d.cnn_cancel = 1; tick(); d.cnn_cancel = 0;
        while (csr(0) & 2) { need(!d.cnn_response && !d.cnn_mem_fault, "cancel drain fault"); tick(); }
        need(ram.read_bytes - before == 1024 && !d.cnn_response, "cancelled page did not drain");
        inject_error = true; submit(3, 0x500000);
        while (!d.cnn_mem_fault) { need(!d.cnn_response, "AXI error replied as success"); tick(); }
        need(!ram.reading && !ram.rvalid, "AXI error burst not drained");
        inject_error = false; cfg(4, 3);
        need(!d.cnn_mem_fault, "AXI fault recovery");
        need(access(3, 0x500000) == 0xa5a5a5a5, "refill after AXI error");
        submit(7, 1);
        while (!d.cnn_mem_fault) { need(!d.cnn_response, "unaligned word replied"); tick(); }
        cfg(4, 3); cfg(0x10, 0x10000); cfg(0x14, 1);
        submit(7, 0x80, true);
        while (!d.cnn_mem_fault) { need(!d.cnn_response, "readonly write replied"); tick(); }
        std::cout << "PASS 392 KiB two-bank paging: two simultaneous physical bank requests, 512 ordered stream reads, "
                     "401-page dirty eviction, wrap, byte write, partial-page fence, invalidate/refill, "
                     "cancel drain, AXI error/recovery, alignment and readonly faults. cycles=" << cycles
                  << " page-isolation checks=" << isolation_checks << '\n';
    }
};
int main() {
    try { Bench bench; bench.run(); return 0; }
    catch (const std::exception &error) { std::cerr << "FAIL " << error.what() << '\n'; return 1; }
}
