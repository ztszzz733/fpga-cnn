#include "Vees331_soc_reduced_sim_top.h"
#include "schedule.c"
#include "ees331_axi_mover_model.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace fs = std::filesystem;
using U32 = uint32_t;
using U64 = uint64_t;
constexpr unsigned units = 10;
constexpr unsigned frames = 2;
struct WaveCaptured {};
const bool wave_only = std::getenv("EES331_WAVE_ONLY") != nullptr;
#ifndef SIM_FCLK_MHZ
#define SIM_FCLK_MHZ 20
#endif
constexpr U64 cycles_per_ms = SIM_FCLK_MHZ * 1000;

static void check(bool pass, const char *message)
{
    if (!pass)
        throw std::runtime_error(message);
}

static std::vector<uint8_t> binary(const fs::path &path)
{
    std::ifstream file(path, std::ios::binary);
    check(bool(file), "missing binary fixture");
    return {std::istreambuf_iterator<char>(file), {}};
}

static std::vector<U32> words(const fs::path &path)
{
    std::ifstream file(path);
    check(bool(file), "missing fixture table");
    std::vector<U32> result;
    for (U32 value; file >> std::hex >> value;)
        result.push_back(value);
    return result;
}

class Bench {
    Vees331_soc_reduced_sim_top dut;
    AxiDdr<Vees331_soc_reduced_sim_top> ddr{dut};
    const std::vector<uint8_t> plan, expected;
    const std::vector<U32> nodes, guards;
    std::vector<uint8_t> seen;
    std::vector<bool> started, completed;
    std::array<std::vector<uint8_t>, frames> outputs;
    std::array<U64, units> starts{};
    std::ofstream events, samples, detail;
    size_t plan_pos = 0;
    U32 sequence = 0;
    U64 cycle = 0, verified = 0, jobs = 0, overlap = 0, result_count = 0;
    unsigned detail_left = 0;
    bool enabled = false, first_k1 = false;

    unsigned node(unsigned unit) const
    {
        const unsigned bit = unit * 10, index = bit / 32;
        U64 value = dut.debug_node[index];
        if (index + 1 < 4)
            value |= U64(dut.debug_node[index + 1]) << 32;
        return unsigned(value >> (bit % 32)) & 1023u;
    }

    void event(const char *kind, unsigned first = 0, unsigned unit = 0, unsigned frame = 0)
    {
        events << cycle << ',' << kind << ',' << first << ',' << unit << ',' << frame << '\n';
    }

    void monitor()
    {
        if (dut.debug_error || dut.debug_fault)
            throw std::runtime_error("CNN/DDR fault at cycle " + std::to_string(cycle));
        const U32 launch = dut.debug_unit_start, done = dut.debug_completion;
        const U32 writes = dut.debug_valid & dut.debug_ready & dut.debug_write;
        const U32 active = dut.debug_unit_active;
        if (!first_k1 && (dut.debug_response & 0x3cu)) {
            first_k1 = true;
            detail_left = 512;
        }
        if (active & (active - 1u))
            ++overlap; // At most one active operation per frame.
        if (!(launch | done | writes))
            return;
        for (unsigned unit = 0; unit < units; ++unit) {
            const U32 mask = 1u << unit;
            if (!((launch | done | writes) & mask))
                continue;
            const unsigned n = node(unit);
            check(n < started.size(), "operator reported an invalid node");
            if (launch & mask) {
                check(!started[n], "task started twice");
                started[n] = true;
                ++starts[unit];
                event("START", n, unit, n % frames);
            }
            if (done & mask) {
                check(started[n] && !completed[n], "unexpected task completion");
                completed[n] = true;
                ++jobs;
                event("COMPLETE", n, unit, n % frames);
            }
            if (writes & mask) {
                const U32 address = dut.debug_addr[unit];
                const U32 bytes = (dut.debug_byte & mask) ? 1u : 4u;
                const U32 base = nodes[n * 3], size = nodes[n * 3 + 1];
                check(address >= base && U64(address) + bytes <= U64(base) + size,
                      "operator wrote outside its assigned output");
                const size_t position = nodes[n * 3 + 2] + address - base;
                const U32 data = dut.debug_wdata[unit];
                for (unsigned byte = 0; byte < bytes; ++byte) {
                    const size_t offset = position + byte;
                    if (offset >= seen.size() || seen[offset] || uint8_t(data >> (8 * byte)) != expected[offset])
                        throw std::runtime_error("output mismatch at node " + std::to_string(n) +
                                                 ", byte " + std::to_string(address - base + byte));
                    seen[offset] = 1;
                }
                verified += bytes;
            }
        }
    }

    void tick()
    {
        check(cycle < 3000000000ULL, "simulation cycle watchdog");
        ddr.drive();
        dut.FCLK_CLK0 = 0;
        dut.eval();
        if (enabled)
            monitor();
        if (dut.FCLK_RESET0_N)
            ddr.capture();
        if (detail_left) {
            detail << cycle << ',' << dut.debug_unit_active << ',' << dut.debug_valid << ','
                   << dut.debug_ready << ',' << dut.debug_response << ',' << dut.debug_write << ','
                   << unsigned(dut.debug_memory_state) << ',' << unsigned(dut.debug_mover_state) << ','
                   << unsigned(dut.S_AXI_HP0_ARVALID) << ',' << unsigned(dut.S_AXI_HP0_RVALID) << ','
                   << unsigned(dut.S_AXI_HP0_AWVALID) << ',' << unsigned(dut.S_AXI_HP0_BVALID) << '\n';
            --detail_left;
            if (!detail_left && wave_only)
                throw WaveCaptured{};
        }
        dut.FCLK_CLK0 = 1;
        dut.eval();
        ++cycle;
        if (cycle % 20000u == 0)
            samples << cycle << ',' << ddr.read_bytes << ',' << ddr.write_bytes << ','
                    << dut.debug_completed << ',' << dut.debug_page_misses << '\n';
        if (cycle % 2000000u == 0) {
            events.flush();
            samples.flush();
            std::cout << "cycle " << cycle << " jobs " << jobs << "/" << started.size()
                      << " verified " << verified << std::endl;
        }
    }

    void write(U32 offset, U32 value)
    {
        dut.M_AXI_GP0_AWADDR = 0x40000000u + offset;
        dut.M_AXI_GP0_WDATA = value;
        dut.M_AXI_GP0_AWVALID = 1;
        dut.M_AXI_GP0_WVALID = 1;
        for (unsigned wait = 0; dut.M_AXI_GP0_AWVALID || dut.M_AXI_GP0_WVALID; ++wait) {
            check(wait < 1000u, "GP0 write timeout");
            dut.eval();
            const bool aw = dut.M_AXI_GP0_AWREADY;
            const bool w = dut.M_AXI_GP0_WREADY;
            tick();
            if (aw)
                dut.M_AXI_GP0_AWVALID = 0;
            if (w)
                dut.M_AXI_GP0_WVALID = 0;
        }
        for (unsigned wait = 0; !dut.M_AXI_GP0_BVALID; ++wait) {
            check(wait < 1000u, "GP0 write response timeout");
            tick();
        }
        check(dut.M_AXI_GP0_BRESP == 0 && dut.M_AXI_GP0_BID == 0x123, "GP0 write response rejected");
        dut.M_AXI_GP0_BREADY = 1;
        tick();
        dut.M_AXI_GP0_BREADY = 0;
    }

    U32 read(U32 offset)
    {
        dut.M_AXI_GP0_ARADDR = 0x40000000u + offset;
        dut.M_AXI_GP0_ARVALID = 1;
        for (unsigned wait = 0;; ++wait) {
            check(wait < 1000u, "GP0 read timeout");
            dut.eval();
            const bool accepted = dut.M_AXI_GP0_ARREADY;
            tick();
            if (accepted)
                break;
        }
        dut.M_AXI_GP0_ARVALID = 0;
        for (unsigned wait = 0; !dut.M_AXI_GP0_RVALID; ++wait) {
            check(wait < 1000u, "GP0 read response timeout");
            tick();
        }
        check(dut.M_AXI_GP0_RRESP == 0 && dut.M_AXI_GP0_RID == 0x456 && dut.M_AXI_GP0_RLAST,
              "GP0 read response rejected");
        const U32 value = dut.M_AXI_GP0_RDATA;
        dut.M_AXI_GP0_RREADY = 1;
        tick();
        dut.M_AXI_GP0_RREADY = 0;
        return value;
    }

    int rpc(U32 op, U32 a, U32 b, U32 reply[4])
    {
        if (op != 6 && op != 2)
            event("MAILBOX", op);
        write(16, op);
        write(20, a);
        write(24, b);
        write(28, 0);
        write(32, 0);
        write(8, ++sequence);
        if (op == 4)
            enabled = true;
        const auto deadline = cycle + 20000000u;
        while (read(12) != sequence)
            check(cycle < deadline, "RISC-V mailbox ACK timeout");
        const auto status = int(read(80));
        for (unsigned i = 0; i < 4; ++i)
            reply[i] = read(84 + 4 * i);
        return status;
    }

public:
    Bench(const fs::path &fixture, const fs::path &out)
        : plan(binary(fixture / "PLAN.BIN")), expected(binary(fixture / "expected_intermediate.bin")),
          nodes(words(fixture / "nodes.hex")), guards(words(fixture / "guards.hex")),
          seen(expected.size()), started(nodes.size() / 3), completed(nodes.size() / 3),
          events(out / "events.csv"), samples(out / "memory_samples.csv"), detail(out / "detail.csv")
    {
        check(nodes.size() % 3 == 0, "bad software oracle node table");
        check(bool(events) && bool(samples) && bool(detail), "could not open waveform output");
        events << "cycle,event,node,unit,frame\n";
        samples << "cycle,ddr_read_bytes,ddr_write_bytes,completed,page_misses\n";
        detail << "cycle,active,valid,ready,response,write,pager,mover,hp_arvalid,hp_rvalid,hp_awvalid,hp_bvalid\n";
        std::fill(ddr.data.begin(), ddr.data.end(), 0xa5);
        ddr.stress = true;
        dut.M_AXI_GP0_AWID = 0x123;
        dut.M_AXI_GP0_WID = 0x123;
        dut.M_AXI_GP0_ARID = 0x456;
        dut.M_AXI_GP0_AWSIZE = dut.M_AXI_GP0_ARSIZE = 2;
        dut.M_AXI_GP0_AWBURST = dut.M_AXI_GP0_ARBURST = 1;
        dut.M_AXI_GP0_WSTRB = 15;
        dut.M_AXI_GP0_WLAST = 1;
        dut.FCLK_RESET0_N = 0;
        for (unsigned i = 0; i < 5; ++i)
            tick();
        dut.FCLK_RESET0_N = 1;
        for (unsigned i = 0; i < 1200; ++i)
            tick();
    }

    void run(const fs::path &out)
    {
        check(read(0) == 0x45455332u && read(100) == 0x43505532u, "board RISC-V ROM failed to start");
        const ees331_schedule_io io{
            this, ddr.data.data(),
            [](void *p, void *dest, U32 n) {
                auto &b = *static_cast<Bench *>(p);
                if (n > b.plan.size() - b.plan_pos)
                    return -1;
                std::copy_n(b.plan.data() + b.plan_pos, n, static_cast<uint8_t *>(dest));
                b.plan_pos += n;
                return 0;
            },
            [](void *p, U32 op, U32 a, U32 b, U32 reply[4]) {
                return static_cast<Bench *>(p)->rpc(op, a, b, reply);
            },
            [](void *p, U32 address, U32 length, int for_device) {
                auto &b = *static_cast<Bench *>(p);
                b.event(for_device ? "DDR_PUBLISH" : "DDR_FENCED", address);
                if (for_device && address)
                    for (U32 i = 0; i < length / 4; ++i)
                        b.tick(); // Model bounded PS upload delay, not SD timing.
            },
            [](void *p) { return static_cast<Bench *>(p)->cycle / cycles_per_ms; },
            [](void *p) {
                for (unsigned i = 0; i < cycles_per_ms * 2; ++i)
                    static_cast<Bench *>(p)->tick();
            },
            [](void *p, unsigned slot, U32, const uint8_t *data, U32 bytes) {
                auto &b = *static_cast<Bench *>(p);
                if (slot >= frames || !b.outputs[slot].empty())
                    return -1;
                b.outputs[slot].assign(data, data + bytes);
                ++b.result_count;
                return 0;
            },
            [](void *p, const char *name, U32 arg) {
                static_cast<Bench *>(p)->event(name, arg, 0, arg < frames ? arg : 0);
            },
            [](void *p, const char *what, int status) {
                const auto &b = *static_cast<Bench *>(p);
                std::cerr << "schedule at " << b.cycle << ": " << what << " (" << status << ")\n";
            },
        };
        check(ees331_schedule(&io, U32(plan.size())) == 0, "ARM scheduling code failed");
        check(jobs == started.size() && verified == expected.size(), "incomplete reference coverage");
        check(result_count == frames && overlap && ddr.read_bytes && ddr.write_bytes,
              "missing concurrent work or DDR traffic");
        for (U32 address : guards)
            for (unsigned i = 0; i < 64; ++i)
                check(ddr.data.at(address + i) == 0xa5, "workspace guard overwritten");

        std::ofstream result(out / "outputs.bin", std::ios::binary);
        for (const auto &frame : outputs)
            result.write(reinterpret_cast<const char *>(frame.data()), frame.size());
        check(bool(result), "failed to save simulation outputs");
        std::ofstream metrics(out / "metrics.json");
        metrics << "{\"status\":\"PASS\",\"cycles\":" << cycle << ",\"jobs\":" << jobs
                << ",\"checked_output_bytes\":" << verified << ",\"frames\":" << result_count
                << ",\"overlap_cycles\":" << overlap << ",\"ddr_read_bytes\":" << ddr.read_bytes
                << ",\"ddr_write_bytes\":" << ddr.write_bytes << ",\"page_misses\":"
                << dut.debug_page_misses << ",\"unit_starts\":[";
        for (unsigned i = 0; i < units; ++i)
            metrics << (i ? "," : "") << starts[i];
        metrics << "]}\n";
        std::cout << "PASS EES331 jobs=" << jobs << ", verified bytes=" << verified << '\n';
    }
};

int main(int argc, char **argv)
{
    try {
        check(argc == 3, "usage: sim FIXTURE OUTPUT");
        Bench bench(argv[1], argv[2]);
        bench.run(argv[2]);
        return 0;
    } catch (const WaveCaptured &) {
        std::cout << "WAVE_CAPTURE COMPLETE: 512 cycles from the first PW8 memory response\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL EES331: " << error.what() << '\n';
        return 1;
    }
}
