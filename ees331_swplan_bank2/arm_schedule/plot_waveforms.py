"""Render the measured RTL run as a batch overview and cycle detail."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.patches import Patch


UNITS = ("K3 #0", "K3 #1", "K1 #0", "K1 #1", "K1 #2", "K1 #3",
         "Post #0", "Post #1", "Add", "Pad")
COLORS = ("#214F9F", "#B64B20")


def entries(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def overview(directory, fclk):
    events = entries(directory / "events.csv")
    memory = entries(directory / "memory_samples.csv")
    starts = {int(e["node"]): e for e in events if e["event"] == "START"}
    finishes = {int(e["node"]): e for e in events if e["event"] == "COMPLETE"}
    if starts.keys() != finishes.keys():
        raise ValueError("Incomplete RTL event trace")
    origin = int(next(e["cycle"] for e in events if e["event"] == "CONFIG_BEGIN"))
    def t(cycle):
        return (int(cycle) - origin) / (fclk * 1000)

    fig, (dispatch, traffic) = plt.subplots(
        2, 1, sharex=True, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]},
        layout="constrained",
    )
    for node, start in starts.items():
        start_ms, end_ms = t(start["cycle"]), t(finishes[node]["cycle"])
        unit, frame = int(start["unit"]), int(start["frame"])
        dispatch.broken_barh([(start_ms, end_ms - start_ms)], (unit - 0.34, 0.68),
                             facecolors=COLORS[frame], linewidth=0)
    for row in events:
        why = row["event"]
        if why in ("FRAME_SUBMIT", "RESULT_READ"):
            frame = int(row["frame"])
            position = t(row["cycle"])
            dispatch.axvline(position, color=COLORS[frame],
                             linestyle=":" if why == "FRAME_SUBMIT" else "--", alpha=.8)
            if why == "RESULT_READ":
                dispatch.annotate(f"帧 {100 + frame} 读回", (position, -.55), xytext=(-3, 3 + frame * 16),
                                  textcoords="offset points", ha="right", color=COLORS[frame], fontsize=9)
    dispatch.set_yticks(range(len(UNITS)), UNITS)
    dispatch.set_ylim(len(UNITS) - .5, -1.35)
    dispatch.grid(axis="x", alpha=.2)
    dispatch.set_axisbelow(True)
    dispatch.set_title("算子任务占用（实测 START / COMPLETE，点线为提交，虚线为读回）", loc="left")
    dispatch.legend(handles=[Patch(color=COLORS[i], label=f"帧 {100 + i} (112×112×3)")
                             for i in (0, 1)], loc="upper center", ncols=2)
    cycles = [t(row["cycle"]) for row in memory if int(row["cycle"]) >= origin]
    samples = [row for row in memory if int(row["cycle"]) >= origin]
    for key, label, color in [("ddr_read_bytes", "HP0 累计读取", "#214F9F"),
                              ("ddr_write_bytes", "HP0 累计写入", "#007568")]:
        traffic.plot(cycles, [int(row[key]) / (1024 * 1024) for row in samples], label=label, color=color)
    traffic.set_ylabel("数据量 (MiB)")
    traffic.set_xlabel(f"仿真时间 (ms)，按 {fclk} MHz FCLK 换算")
    traffic.grid(alpha=.2)
    traffic.legend(loc="upper left", ncols=2)
    traffic.set_xlim(0, t(events[-1]["cycle"]) * 1.015)
    fig.suptitle("EES331 双帧 CNN RTL 仿真 · 任务与 DDR 波形", fontsize=18)
    fig.savefig(directory / "waveform_overview.png", dpi=160)
    plt.close(fig)


def detail(directory, fclk):
    rows = [{k: int(v) for k, v in row.items()} for row in entries(directory / "detail.csv")]
    first = rows[0]["cycle"]
    selected = rows[0]["response"] & 0x3c or rows[0]["valid"] & rows[0]["ready"] & 0x3c
    unit = next(unit for unit in range(2, 6) if (selected or rows[0]["active"]) & (1 << unit))
    bit = 1 << unit
    signals = [
        (f"{UNITS[unit]} active", "active", bit),
        (f"{UNITS[unit]} mem_valid", "valid", bit),
        (f"{UNITS[unit]} mem_ready", "ready", bit),
        (f"{UNITS[unit]} mem_response", "response", bit),
        ("HP0 ARVALID", "hp_arvalid", 1),
        ("HP0 RVALID", "hp_rvalid", 1),
        ("HP0 AWVALID", "hp_awvalid", 1),
        ("HP0 BVALID", "hp_bvalid", 1),
    ]
    request_index = next(i for i, row in enumerate(rows) if row["valid"] & bit)
    start_index = max(0, request_index - 12)
    first_rows = rows[start_index:start_index + 160]
    fig, ax = plt.subplots(figsize=(14, 5.2), layout="constrained")
    cycles = [row["cycle"] - first for row in first_rows]
    for index, (_, key, mask) in enumerate(signals):
        values = [index - .65 * bool(row[key] & mask) for row in first_rows]
        ax.step(cycles, values, where="post", color="#214F9F" if index < 4 else "#007568", lw=1.15)
    ax.set_yticks([i - .31 for i in range(len(signals))], [label for label, _, _ in signals])
    ax.set_ylim(len(signals) - .5, -.95)
    ns_per_cycle = 1000 // fclk
    ax.set_xlabel(f"相对窗口起点的 FCLK 周期（绝对起点 {first:,}，{ns_per_cycle} ns/周期）")
    ax.set_title("K1 访存握手与响应的 RTL 信号", loc="left", fontsize=15)
    ax.grid(axis="x", alpha=.2)
    fig.savefig(directory / "waveform_detail.png", dpi=160)
    plt.close(fig)
    with (directory / "waveform_detail.vcd").open("w", encoding="ascii") as stream:
        stream.write("$timescale 1 ns $end\n$scope module EES331 $end\n")
        nets = [(f"k1_{unit - 2}_" + key, key, mask) if mask != 1 or key == "active"
                else (key, key, mask) for _, key, mask in signals]
        for i, (label, _, _) in enumerate(nets):
            stream.write(f"$var wire 1 {chr(33 + i)} {label} $end\n")
        stream.write("$upscope $end\n$enddefinitions $end\n")
        previous = [None] * len(nets)
        for row in rows:
            timestamp = (row["cycle"] - first) * ns_per_cycle
            values = [int(bool(row[key] & mask)) for _, key, mask in nets]
            if values != previous:
                stream.write(f"#{timestamp}\n")
                for i, value in enumerate(values):
                    if value != previous[i]:
                        stream.write(f"{value}{chr(33 + i)}\n")
                previous = values
        stream.write(f"#{(rows[-1]['cycle'] - first + 1) * ns_per_cycle}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--detail-only", action="store_true")
    args = parser.parse_args()
    directory = args.directory
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.is_file():
        font_manager.fontManager.addfont(font)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    metadata = directory / ('wave_capture.json' if args.detail_only else 'result.json')
    fclk = json.loads(metadata.read_text()).get("fclk_mhz", 100)
    if not args.detail_only:
        overview(directory, fclk)
    detail(directory, fclk)
