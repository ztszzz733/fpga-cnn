"""Render every signal used by the documented ADD flow from a real Datapath VCD."""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.patches import Polygon

from plot_waveforms import read_vcd, segments


BASE = "tb_cpu_datapath."

# suffix, display name, radix, optional enum names
GROUPS = [
    ("00 时钟与流水级有效位", [
        ("clk", "clk", "bin", None),
        ("rst_n", "rst_n", "bin", None),
        ("valid_d", "valid_d", "bin", None),
        ("valid_e", "valid_e", "bin", None),
        ("valid_m", "valid_m", "bin", None),
        ("valid_w", "valid_w", "bin", None),
        ("rf_writes", "rf_writes", "dec", None),
    ]),
    ("01 IF 取指与 IF/ID", [
        ("dut.pc_q", "pc_q", "hex", None),
        ("dut.next_pc", "next_pc", "hex", None),
        ("dut.pc4_seq", "pc4_seq", "hex", None),
        ("pc_sel", "pc_sel", "enum", {0: "NEXT", 1: "TARGET", 2: "JALR"}),
        ("pc_en", "pc_en", "bin", None),
        ("imem_addr", "imem_addr", "hex", None),
        ("imem_re", "imem_re", "bin", None),
        ("imem_rdata", "imem_rdata", "hex", None),
        ("dut.fetch_valid", "fetch_valid", "bin", None),
        ("dut.fetch_instr", "fetch_instr", "hex", None),
        ("dut.fetch_pc", "fetch_pc", "hex", None),
        ("dut.fetch_pc4", "fetch_pc4", "hex", None),
        ("if_id_en", "if_id_en", "bin", None),
        ("if_id_flush", "if_id_flush", "bin", None),
    ]),
    ("02 ID 译码、寄存器读取与 ID/EX 输入", [
        ("instr_d", "instr_d", "hex", None),
        ("dut.pc_d", "pc_d", "hex", None),
        ("dut.pc4_d", "pc4_d", "hex", None),
        ("rs1_d", "rs1_d", "dec", None),
        ("rs2_d", "rs2_d", "dec", None),
        ("dut.rd_d", "rd_d", "dec", None),
        ("dut.rd1_d", "rd1_d / x1 data", "dec", None),
        ("dut.rd2_d", "rd2_d / x2 data", "dec", None),
        ("dut.imm_d", "imm_d", "hex", None),
        ("uses_rs1_d", "uses_rs1_d", "bin", None),
        ("uses_rs2_d", "uses_rs2_d", "bin", None),
        ("u_control.legal_main", "legal_main", "bin", None),
        ("u_control.legal_alu", "legal_alu", "bin", None),
        ("alu_ctrl", "alu_ctrl", "enum", {0: "ADD", 1: "SUB", 2: "AND", 3: "OR"}),
        ("alu_src_a_sel", "alu_src_a_sel", "enum", {0: "REG", 1: "PC", 2: "ZERO"}),
        ("alu_src_b_sel", "alu_src_b_sel", "enum", {0: "REG", 1: "IMM"}),
        ("regwrite_d", "regwrite_d", "bin", None),
        ("memread_d", "memread_d", "bin", None),
        ("memwrite_d", "memwrite_d", "bin", None),
        ("wb_sel_d", "wb_sel_d", "enum", {0: "ALU", 1: "LOAD", 2: "PC4"}),
        ("branch_type_d", "branch_type_d", "enum", {0: "NONE"}),
        ("jump_d", "jump_d", "enum", {0: "NONE", 1: "JAL", 2: "JALR"}),
        ("imm_type_d", "imm_type_d", "dec", None),
        ("id_ex_flush", "id_ex_flush", "bin", None),
    ]),
    ("03 流水控制、冒险与前递", [
        ("u_control.load_use", "load_use", "bin", None),
        ("u_control.operand_unready", "operand_unready", "bin", None),
        ("fwd_a", "fwd_a", "enum", {0: "REG", 1: "WB", 2: "MEM"}),
        ("fwd_b", "fwd_b", "enum", {0: "REG", 1: "WB", 2: "MEM"}),
        ("fwd_store", "fwd_store", "enum", {0: "REG", 1: "WB", 2: "MEM"}),
        ("u_control.redirect", "redirect", "bin", None),
        ("pc_sel", "pc_sel", "enum", {0: "NEXT", 1: "TARGET", 2: "JALR"}),
        ("pc_en", "pc_en", "bin", None),
        ("if_id_en", "if_id_en", "bin", None),
        ("if_id_flush", "if_id_flush", "bin", None),
        ("id_ex_flush", "id_ex_flush", "bin", None),
    ]),
    ("04 EX 执行、比较与 EX/MEM 输入", [
        ("valid_e", "valid_e", "bin", None),
        ("dut.pc_e", "pc_e", "hex", None),
        ("dut.pc4_e", "pc4_e", "hex", None),
        ("rs1_e", "rs1_e", "dec", None),
        ("rs2_e", "rs2_e", "dec", None),
        ("rd_e", "rd_e", "dec", None),
        ("dut.rd1_e", "rd1_e", "dec", None),
        ("dut.rd2_e", "rd2_e", "dec", None),
        ("dut.uses_rs1_e", "uses_rs1_e", "bin", None),
        ("dut.uses_rs2_e", "uses_rs2_e", "bin", None),
        ("dut.alu_ctrl_e", "alu_ctrl_e", "enum", {0: "ADD", 1: "SUB", 2: "AND", 3: "OR"}),
        ("dut.alu_src_a_sel_e", "alu_src_a_sel_e", "enum", {0: "REG", 1: "PC", 2: "ZERO"}),
        ("dut.alu_src_b_sel_e", "alu_src_b_sel_e", "enum", {0: "REG", 1: "IMM"}),
        ("dut.regwrite_e", "regwrite_e", "bin", None),
        ("memread_e", "memread_e", "bin", None),
        ("dut.memwrite_e", "memwrite_e", "bin", None),
        ("dut.wb_sel_e", "wb_sel_e", "enum", {0: "ALU", 1: "LOAD", 2: "PC4"}),
        ("dut.branch_type_e", "branch_type_e", "enum", {0: "NONE"}),
        ("dut.jump_e", "jump_e", "enum", {0: "NONE", 1: "JAL", 2: "JALR"}),
        ("fwd_a", "fwd_a", "enum", {0: "REG", 1: "WB", 2: "MEM"}),
        ("fwd_b", "fwd_b", "enum", {0: "REG", 1: "WB", 2: "MEM"}),
        ("fwd_store", "fwd_store", "enum", {0: "REG", 1: "WB", 2: "MEM"}),
        ("dut.src1_fwd_e", "src1_fwd_e", "dec", None),
        ("dut.src2_fwd_e", "src2_fwd_e", "dec", None),
        ("dut.store_data_fwd_e", "store_data_fwd_e", "dec", None),
        ("dut.alu_a_e", "alu_a_e", "dec", None),
        ("dut.alu_b_e", "alu_b_e", "dec", None),
        ("dut.alu_result_e", "alu_result_e", "dec", None),
        ("dut.cmp_eq_e", "cmp_eq_e", "bin", None),
        ("dut.cmp_lt_e", "cmp_lt_e", "bin", None),
        ("dut.cmp_ltu_e", "cmp_ltu_e", "bin", None),
        ("u_control.redirect", "redirect", "bin", None),
        ("dut.branch_target", "branch_target", "hex", None),
        ("dut.jalr_target", "jalr_target", "hex", None),
    ]),
    ("05 MEM 访存旁路与 MEM/WB 输入", [
        ("valid_m", "valid_m", "bin", None),
        ("dut.alu_result_m", "alu_result_m", "dec", None),
        ("dut.write_data_m", "write_data_m", "dec", None),
        ("rd_m", "rd_m", "dec", None),
        ("regwrite_m", "regwrite_m", "bin", None),
        ("memread_m", "memread_m", "bin", None),
        ("dut.memwrite_m", "memwrite_m", "bin", None),
        ("dut.wb_sel_m", "wb_sel_m", "enum", {0: "ALU", 1: "LOAD", 2: "PC4"}),
        ("dut.mem_forward_m", "mem_forward_m", "dec", None),
        ("dmem_addr", "dmem_addr", "hex", None),
        ("dmem_wdata", "dmem_wdata", "hex", None),
        ("dmem_wstrb", "dmem_wstrb", "hex", None),
        ("dmem_re", "dmem_re", "bin", None),
        ("dmem_we", "dmem_we", "bin", None),
        ("dut.dmem_rdata", "dmem_rdata", "hex", None),
        ("mmio_addr", "mmio_addr", "hex", None),
        ("mmio_wdata", "mmio_wdata", "hex", None),
        ("mmio_re", "mmio_re", "bin", None),
        ("mmio_we", "mmio_we", "bin", None),
        ("dut.mmio_rdata", "mmio_rdata", "hex", None),
        ("dut.mmio_ready", "mmio_ready", "bin", None),
        ("dut.read_data_m", "read_data_m", "dec", None),
    ]),
    ("06 WB 写回与寄存器提交", [
        ("valid_w", "valid_w", "bin", None),
        ("dut.read_data_w", "read_data_w", "dec", None),
        ("dut.alu_result_w", "alu_result_w", "dec", None),
        ("dut.pc4_w", "pc4_w", "hex", None),
        ("dut.wb_sel_w", "wb_sel_w", "enum", {0: "ALU", 1: "LOAD", 2: "PC4"}),
        ("dut.wb_data_w", "wb_data_w", "dec", None),
        ("rd_w", "rd_w", "dec", None),
        ("regwrite_w", "regwrite_w", "bin", None),
        ("dut.rf_we", "rf_we", "bin", None),
        ("x6_value", "x6_value / committed x6", "dec", None),
        ("rf_writes", "rf_writes", "dec", None),
    ]),
]


def fix_xsim_parameter_widths(source: Path, destination: Path) -> int:
    text = source.read_text(encoding="utf-8")

    def replace(match: re.Match) -> str:
        prefix, msb, lsb, suffix = match.groups()
        return prefix + str(abs(int(msb) - int(lsb)) + 1) + suffix

    text, count = re.subn(
        r"(\$var\s+\w+\s+)0(?=\s+\S+\s+MEM_BYTES\s+\[(\d+):(\d+)\])"
        r"(\s+\S+\s+MEM_BYTES\s+\[\d+:\d+\]\s+\$end)",
        replace,
        text,
    )
    destination.write_text(text, encoding="utf-8")
    return count


def format_value(bits: str, radix: str, enum: dict[int, str] | None) -> str:
    if any(char in bits for char in "xz"):
        return "X/Z" if len(bits) > 8 else bits.upper()
    value = int(bits, 2)
    if enum and value in enum:
        return enum[value]
    if radix == "hex":
        return f"0x{value:0{(len(bits) + 3) // 4}X}"
    if radix == "bin":
        return str(value)
    return str(value)


def render(vcd, rows, destination: Path, title: str, start=28.0, end=95.0):
    available = {font.name for font in font_manager.fontManager.ttflist}
    fonts = [name for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans") if name in available]
    plt.rcParams["font.family"] = fonts or ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    figure_height = max(6.0, len(rows) * 0.42 + 2.8)
    fig, axes = plt.subplots(len(rows), 1, figsize=(17, figure_height), sharex=True, squeeze=False)
    fig.patch.set_facecolor("#f7fafc")
    stage_spans = [(28, 45, "#eaf3fb"), (45, 55, "#edf8f1"), (55, 65, "#fff4dc"),
                   (65, 75, "#f6effb"), (75, 85, "#fdeff1"), (85, 95, "#eef1f4")]
    boundaries = [30, 35, 45, 55, 65, 75, 85]

    previous_group = None
    for index, (ax_row, row) in enumerate(zip(axes, rows)):
        ax = ax_row[0]
        group, suffix, label, radix, enum = row
        path = BASE + suffix
        signal = vcd.signals[path]
        ax.set_facecolor("#f7fafc")
        ax.set_ylim(-0.25, 1.25)
        ax.set_yticks([])
        for left, right, color in stage_spans:
            ax.axvspan(left, right, color=color, alpha=0.32, linewidth=0)
        for boundary in boundaries:
            ax.axvline(boundary, color="#9aa9b6", linewidth=0.65, alpha=0.75)
        if group != previous_group:
            ax.text(-0.265, 1.18, group, transform=ax.transAxes, ha="left", va="bottom",
                    fontsize=10, color="#174a67", weight="bold")
            previous_group = group
        ax.text(-0.012, 0.5, label, transform=ax.transAxes, ha="right", va="center", fontsize=8.5)

        for left, right, bits in segments(signal, start, end):
            unknown = any(char in bits for char in "xz")
            if signal.width == 1 and not unknown:
                value = int(bits, 2)
                ax.plot([left, right], [value, value], color="#007e87", linewidth=1.45)
                if left > start:
                    ax.plot([left, left], [0, 1], color="#007e87", linewidth=0.9)
            else:
                color = "#efb63f" if unknown else "#cbe9ef"
                bevel = min(0.12, (right - left) / 5)
                polygon = Polygon(
                    [(left, .5), (left + bevel, .12), (right - bevel, .12), (right, .5),
                     (right - bevel, .88), (left + bevel, .88)],
                    closed=True, facecolor=color, edgecolor="#496779", linewidth=.6,
                    hatch="//" if unknown else None,
                )
                ax.add_patch(polygon)
                shown = format_value(bits, radix, enum)
                if (right - left) * 17 >= len(shown) * 0.62:
                    ax.text((left + right) / 2, .5, shown, ha="center", va="center", fontsize=7.5, clip_on=True)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis="x", length=0, labelsize=8)

    last = axes[-1][0]
    last.set_xlim(start, end)
    last.set_xticks(list(range(30, 96, 5)))
    last.set_xlabel("仿真时间（ns）")
    fig.suptitle(title, fontsize=15, weight="bold", x=.59)
    fig.text(.275, .012,
             "阶段：28–45 IF 取指｜45–55 ID 译码｜55–65 EX 执行｜65–75 MEM｜75–85 WB 有效｜85 ns x6 完成写入",
             fontsize=9, color="#405060")
    fig.subplots_adjust(left=.275, right=.992, top=.972, bottom=.04, hspace=.16)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination.with_suffix(".png"), dpi=180, facecolor=fig.get_facecolor())
    fig.savefig(destination.with_suffix(".svg"), facecolor=fig.get_facecolor())
    plt.close(fig)


def value_at(signal, time_ns: float) -> str:
    index = bisect.bisect_right([time for time, _ in signal.events], time_ns) - 1
    return signal.events[index][1] if index >= 0 else "x" * signal.width


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    job = args.run_root.resolve() / "add"
    raw_vcd = job / "waves/real_control_datapath.vcd"
    plot_vcd = job / "waves/real_control_datapath_all_signals_plot.vcd"
    width_fixes = fix_xsim_parameter_widths(raw_vcd, plot_vcd)
    vcd = read_vcd(plot_vcd)

    all_rows = []
    seen = set()
    missing = []
    for group, entries in GROUPS:
        group_rows = []
        for suffix, label, radix, enum in entries:
            path = BASE + suffix
            if path not in vcd.signals:
                missing.append(path)
                continue
            row = (group, suffix, label, radix, enum)
            group_rows.append(row)
            if path not in seen:
                all_rows.append(row)
                seen.add(path)
        safe_name = group.split()[0]
        render(vcd, group_rows, job / "figures" / f"add_signals_{safe_name}",
               f"ADD 全信号波形：{group}")
    if missing:
        raise RuntimeError("VCD missing required signals: " + ", ".join(missing))

    render(vcd, all_rows, job / "figures/add_all_flow_signals",
           "ADD：真实 Control + 生产 Datapath 全流程信号（x1=1，x2=2，x6=3）")

    sample_times = [40, 50, 60, 70, 80, 90]
    manifest = []
    trace = []
    for group, suffix, label, radix, enum in all_rows:
        signal = vcd.signals[BASE + suffix]
        manifest.append({"group": group, "signal": label, "path": signal.path, "width": signal.width})
    for time_ns in sample_times:
        sample = {"time_ns": time_ns}
        for _, suffix, label, radix, enum in all_rows:
            bits = value_at(vcd.signals[BASE + suffix], time_ns)
            sample[label] = format_value(bits, radix, enum)
        trace.append(sample)

    with (job / "add_all_signal_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", "signal", "path", "width"])
        writer.writeheader()
        writer.writerows(manifest)
    with (job / "add_all_signal_trace.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trace[0]))
        writer.writeheader()
        writer.writerows(trace)

    def numeric(suffix: str, time_ns: float) -> int:
        bits = value_at(vcd.signals[BASE + suffix], time_ns)
        if any(char in bits for char in "xz"):
            raise AssertionError((suffix, time_ns, bits))
        return int(bits, 2)

    checks = {
        "id_instruction": numeric("instr_d", 50) == 0x00208333,
        "id_sources": numeric("rs1_d", 50) == 1 and numeric("rs2_d", 50) == 2,
        "id_control": numeric("alu_ctrl", 50) == 0 and numeric("regwrite_d", 50) == 1,
        "ex_operands_and_result": numeric("dut.alu_a_e", 60) == 1 and numeric("dut.alu_b_e", 60) == 2 and numeric("dut.alu_result_e", 60) == 3,
        "mem_result": numeric("dut.alu_result_m", 70) == 3 and numeric("rd_m", 70) == 6,
        "wb_result": numeric("dut.wb_data_w", 80) == 3 and numeric("rd_w", 80) == 6 and numeric("dut.rf_we", 80) == 1,
        "no_data_sram_access": all(numeric(name, time) == 0 for name in ("dmem_re", "dmem_we") for time in sample_times),
        "no_mmio_access": all(numeric(name, time) == 0 for name in ("mmio_re", "mmio_we") for time in sample_times),
        "single_register_write": numeric("rf_writes", 90) == 1,
        "x6_committed_value": numeric("x6_value", 90) == 3,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    result = {
        "status": "PASS",
        "raw_vcd": str(raw_vcd),
        "plot_vcd": str(plot_vcd),
        "xsim_header_width_fixes": width_fixes,
        "unique_plotted_signals": len(all_rows),
        "groups": [name for name, _ in GROUPS],
        "sample_times_ns": sample_times,
        "checks": checks,
    }
    (job / "add_all_signal_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: plotted {len(all_rows)} unique ADD-flow signals")
    print(job / "figures/add_all_flow_signals.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
