"""Prepare an evidence-based report only after full-network RTL PASS.

Reduced-graph rendering is explicitly confined to build/self_full_report_test
and watermarked SMALL. It cannot create the final docs/deliverables report.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {0: "3×3 / DW3", 1: "Post", 2: "Add", 3: "DW7", 4: "Pad", 5: "1×1"}
COLORS = {0: "#2563eb", 1: "#8b5cf6", 2: "#f59e0b", 3: "#dc2626", 4: "#06b6d4", 5: "#16a34a"}
ORDER = (0, 5, 3, 1, 2, 4)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows, columns=None):
    with path.open("w", newline="", encoding="utf-8-sig") as out:
        writer = csv.DictWriter(out, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def link(path: Path):
    return "</" + path.resolve().as_posix() + ">"


def prepare(run: Path, scenario="overlap", small_self_test=False):
    run = Path(run).resolve()
    result = read_json(run / "result.json")
    require(result.get("status") == "PASS", "A completed run/result.json PASS is required; running/partial runs cannot produce a report")
    for name, digest in result["source_signature"]["sources"].items():
        require(sha(ROOT / name) == digest, f"Compiled RTL/harness source changed: {name}")
    data = Path(result["data"]).resolve()
    manifest_path = data / "manifest.json"
    manifest = read_json(manifest_path)
    require(sha(manifest_path) == result["manifest_sha256"], "The generated manifest changed after the RTL run")
    require(bool(result.get("full_network")) == bool(manifest.get("full_network")), "Full/reduced graph labels disagree")
    require(result["frames"] == manifest["frames"] == 4, "This report requires four frames")
    if small_self_test:
        require(not result["full_network"], "SMALL self-test only accepts a reduced graph")
        out = ROOT / "build/self_full_report_test"
        title = "SMALL — 报告渲染自测，不能作为全网证据"
        docs = out / "SMALL_self_cnn_full_frames.md"
    else:
        require(result["full_network"] and manifest["full_network"], "Full-network PASS is mandatory; use --small-self-test only for isolated renderer QA")
        require(manifest["template_steps"] == 131 and manifest["total_tasks"] == 524 and
                manifest["input_shape"] == [112, 112, 3] and manifest["final_bytes_per_frame"] == 128,
                "Expected the complete four-image 131-step MobileFaceNet graph")
        out = ROOT / "deliverables/self_cnn_full_frames"
        title = "完整 MobileFaceNet：四图地址驱动并行 / 流水验证"
        docs = ROOT / "docs/self_cnn_full_frames.md"
    require(scenario in result["scenarios"], f"No passed scenario {scenario}")
    for name, digest in manifest["files_sha256"].items():
        require(sha(data / name) == digest, f"Generated input/checker file changed: {name}")
    scenarios = {}
    expected = (data / "expected.bin").read_bytes()
    finals = [j for j in manifest["jobs"] if j["result"]]
    require(len(finals) == manifest["frames"], "Final-output count mismatch")
    expected_final = b"".join(expected[j["expected_offset"]:j["expected_offset"] + j["bytes"]] for j in finals)
    for name, entry in result["scenarios"].items():
        metrics = read_json(run / name / "metrics.json")
        require(metrics == entry["metrics"] and metrics.get("status") == "PASS", f"Metrics provenance/status mismatch: {name}")
        for field, value in (("commands", manifest["total_tasks"]), ("expanded_commands", manifest["total_tasks"]),
                             ("checked_bytes", manifest["expected_bytes"]), ("macs", manifest["total_macs"]),
                             ("allocations", manifest["total_tasks"]), ("releases", manifest["total_tasks"]),
                             ("results", manifest["frames"])):
            require(metrics[field] == value, f"Coverage mismatch: {name}.{field}")
        output = run / name / "outputs.bin"
        require(sha(output) == entry["outputs_sha256"] == manifest["final_expected_sha256"], f"Final-output SHA mismatch: {name}")
        require(output.read_bytes() == expected_final, f"Final-output element mismatch: {name}")
        scenarios[name] = metrics
    metric = scenarios[scenario]
    jobs = {j["node"]: j for j in manifest["jobs"]}
    layers = {j["index"]: j for j in manifest["layers"]}
    with (run / scenario / "events.csv").open(newline="", encoding="utf-8-sig") as src:
        events = list(csv.DictReader(src))
    starts, ends = {}, {}
    previous_cycle = -1
    for event in events:
        cycle, node, unit, frame = (int(event[k]) for k in ("cycle", "node", "unit", "frame"))
        require(previous_cycle <= cycle <= metric["cycles"], "Event timestamps out of order/range")
        previous_cycle = cycle
        if event["event"] in ("launch", "done"):
            require(node in jobs and frame == jobs[node]["frame"], "Event frame/node mismatch")
            target = starts if event["event"] == "launch" else ends
            require(node not in target, f"Duplicate {event['event']} for node {node}")
            target[node] = (cycle, unit)
    require(set(starts) == set(ends) == set(jobs), "Incomplete launch/completion event coverage")
    tasks = []
    for node, j in sorted(jobs.items()):
        begin, unit = starts[node]
        end, end_unit = ends[node]
        require(unit == end_unit and begin < end, "Task event interval/engine mismatch")
        require(metric["units"][unit]["kind"] == j["opcode"], "Task assigned to incompatible unit")
        tasks.append(dict(node=node, frame=j["frame"], local_step=j["local_step"], layer=j["layer"],
            name=j["name"], opcode=j["opcode"], operator=NAMES[j["opcode"]], unit=unit,
            begin=begin, end=end, elapsed=end - begin, output_address=j["address"],
            output_bytes=j["bytes"], macs=j["macs"]))
    for frame in metric["frames"]:
        ft = sorted((t for t in tasks if t["frame"] == frame["frame"]), key=lambda t: t["local_step"])
        require(len(ft) == manifest["template_steps"], "Missing per-frame tasks")
        require(ft[0]["begin"] == frame["first_launch"] and frame["input_commit"] < ft[0]["begin"], "Input/launch lifecycle mismatch")
        require(ft[-1]["end"] < frame["read_complete"], "Output acknowledged before its producer completed")
        require(all(a["end"] < b["begin"] for a, b in zip(ft, ft[1:])), "Unexpected same-frame step overlap")

    grouped = defaultdict(list)
    for task in tasks:
        grouped[(task["frame"], task["layer"])].append(task)
    layer_rows = []
    for (frame, li), group in sorted(grouped.items()):
        layer = layers[li]
        begin, end = min(t["begin"] for t in group), max(t["end"] for t in group)
        active = sum(t["elapsed"] for t in group)
        layer_rows.append(dict(frame=frame, layer=li, name=layer["name"], operation=layer["operation"],
            kernel=layer.get("kernel", ""), depthwise=layer.get("depthwise", ""), stride=layer.get("stride", ""),
            output_shape="x".join(map(str, layer["shape"])), first_cycle=begin, last_cycle=end,
            layer_span=end - begin, operator_elapsed_sum=active, interstep_wait=end - begin - active,
            steps=len(group), units=";".join(map(str, sorted({t["unit"] for t in group}))), macs=sum(t["macs"] for t in group)))
    pools = []
    for opcode in ORDER:
        units = [u for u in metric["units"] if u["kind"] == opcode]
        require(units, f"Missing physical pool {opcode}")
        active = sum(u["active_cycles"] for u in units)
        work = sum(u["work_cycles"] for u in units)
        wait = sum(u["arbitration_wait_cycles"] for u in units)
        for u in units:
            require(0 <= u["work_cycles"] <= u["active_cycles"] <= metric["cycles"] and
                    0 <= u["arbitration_wait_cycles"] <= u["active_cycles"], "Invalid unit-cycle counters")
        pools.append(dict(opcode=opcode, operator=NAMES[opcode], instances=len(units),
            active_cycles=active, work_cycles=work, arbitration_wait_cycles=wait,
            average_busy_fraction=active / (len(units) * metric["cycles"]),
            work_per_active=work / active if active else 0,
            arbitration_wait_per_active=wait / active if active else 0,
            capacity_wait_frame_cycles=metric["capacity_wait_by_opcode"][opcode],
            free_pool_wait_frame_cycles=metric["scan_wait_by_opcode"][opcode],
            read_bytes=sum(u["read_bytes"] for u in units), write_bytes=sum(u["write_bytes"] for u in units),
            macs=sum(t["macs"] for t in tasks if t["opcode"] == opcode)))
    peak_pool = max(pools, key=lambda p: p["average_busy_fraction"])
    queue_pool = max(pools, key=lambda p: p["capacity_wait_frame_cycles"])
    active_sum = sum(p["active_cycles"] for p in pools)
    arb_sum = sum(p["arbitration_wait_cycles"] for p in pools)
    slow_layers = []
    for li, layer in layers.items():
        rows = [r for r in layer_rows if r["layer"] == li]
        slow_layers.append(dict(layer=li, name=layer["name"], operation=layer["operation"],
            shape="x".join(map(str, layer["shape"])), total_span=sum(r["layer_span"] for r in rows),
            maximum_span=max(r["layer_span"] for r in rows), macs=sum(r["macs"] for r in rows)))
    slow_layers.sort(key=lambda r: r["total_span"], reverse=True)

    # Quantization audit is optional, but its provenance must match this dataset.
    audit_path = ROOT / "build/self_full_generator_audit/quantization_review.json"
    audit = None
    if not small_self_test and audit_path.exists():
        candidate = read_json(audit_path)
        if candidate.get("status") == "AUDIT_PASS" and candidate.get("provenance", {}).get("generator_manifest_sha256") == sha(manifest_path):
            require(candidate["provenance"]["expected_sha256"] == sha(data / "expected.bin"), "Quantization audit checker mismatch")
            require([r["final_sha256"] for r in candidate["outputs"]] == manifest["final_frame_sha256"], "Quantization audit output mismatch")
            audit = candidate

    if out.exists() and (out / "provenance.json").exists():
        old = read_json(out / "provenance.json")
        require(old["run"] == str(run) and old["scenario"] == scenario, "Existing report belongs to a different run; preserve it before selecting this destination")
    out.mkdir(parents=True, exist_ok=True)
    evidence = out / "evidence"
    evidence.mkdir(exist_ok=True)
    for name in ("result.json",):
        shutil.copy2(run / name, evidence / name)
    shutil.copy2(manifest_path, evidence / "manifest.json")
    for name in ("metrics.json", "events.csv", "outputs.bin", "simulation.log", "mac_detail.vcd", "pipeline_detail.vcd"):
        src = run / scenario / name
        if src.exists():
            shutil.copy2(src, evidence / name)
    if audit is not None:
        shutil.copy2(audit_path, evidence / "quantization_review.json")
    write_csv(out / "task_events.csv", tasks)
    write_csv(out / "layer_events.csv", layer_rows)
    write_csv(out / "operator_summary.csv", pools)
    write_csv(out / "layer_summary.csv", slow_layers)
    comparison = [dict(scenario=name, cycles=m["cycles"], commands=m["commands"], macs=m["macs"],
                       checked_bytes=m["checked_bytes"], simulation_seconds=m["simulation_seconds"],
                       multi_frame_work_cycles=m["multi_frame_work_cycles"], cross_operator_work_cycles=m["cross_operator_work_cycles"])
                  for name, m in scenarios.items()]
    write_csv(out / "scenario_comparison.csv", comparison)
    last_layer = manifest["layers"][-1]
    scale, zero = float(last_layer["scale"]), int(last_layer["zero"])
    width = manifest["final_bytes_per_frame"]
    codes, dequantized = [], []
    output_bytes = (run / scenario / "outputs.bin").read_bytes()
    for f, final in enumerate(finals):
        values = output_bytes[f * width:(f + 1) * width]
        codes.append(dict(frame=final["frame"], **{f"v{i}": int(value) for i, value in enumerate(values)}))
        dequantized.append(dict(frame=final["frame"], **{f"v{i}": (int(value) - zero) * scale for i, value in enumerate(values)}))
    write_csv(out / "embeddings_u8.csv", codes)
    write_csv(out / "embeddings_dequantized.csv", dequantized)
    write_json(out / "embedding_format.json", dict(frames=4, components=width, dtype="UINT8", scale=scale, zero=zero,
        formula="approximate_real_value = (uint8_code - zero) * scale", l2_normalized=False,
        quantized_reference_element_equal=True, floating_point_element_equal=False,
        output_sha256=manifest["final_expected_sha256"]))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from PIL import Image
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "font.size": 10, "figure.facecolor": "white"})
    prefix = "SMALL 自测 | " if small_self_test else ""
    def save_figure(fig, name):
        if small_self_test:
            fig.text(.99, .01, "SMALL — NOT FULL-NETWORK EVIDENCE", ha="right", color="#b91c1c", fontsize=10, weight="bold")
        fig.savefig(out / name, dpi=160, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, 4, figsize=(12, 3.6))
    for f, ax in enumerate(axes):
        src = data / f"image{f}.ppm"
        ax.imshow(Image.open(src))
        ax.set_title(f"frame {finals[f]['frame']}\n112×112 合成 RGB", fontsize=11)
        ax.axis("off")
    fig.suptitle(prefix + "四张不同的数值测试输入；不用于人脸识别精度验收", fontsize=14, y=1.03)
    fig.tight_layout()
    save_figure(fig, "input_images.png")

    fig, ax = plt.subplots(figsize=(16, 6.4))
    for f, frame in enumerate(metric["frames"]):
        y = 3 - f
        ax.broken_barh([(frame["input_begin"], frame["input_commit"] - frame["input_begin"])], (y + .23, .10), facecolors="#0f766e")
        ax.plot([frame["input_commit"]] * 2, [y - .3, y + .36], color="#0f766e", linewidth=.8, linestyle=":")
        for task in tasks:
            if task["frame"] != frame["frame"]:
                continue
            ax.broken_barh([(task["begin"], task["elapsed"])], (y - .24, .38), facecolors=COLORS[task["opcode"]])
            if task["elapsed"] > metric["cycles"] * .035:
                ax.text((task["begin"] + task["end"]) / 2, y - .05, f"L{task['layer']}\nU{task['unit']}", ha="center", va="center", fontsize=8, color="white")
        ax.plot(frame["read_complete"], y - .05, "k|", markersize=15)
    ax.set(yticks=[3, 2, 1, 0], yticklabels=[f"frame {f['frame']}" for f in metric["frames"]],
           xlim=(0, metric["cycles"] * 1.015), ylim=(-.5, 3.6), xlabel="硬件周期（含地址模板展开、输入、计算和结果确认；不含仿真初始化）")
    ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
    ax.grid(axis="x", alpha=.2)
    ax.set_title(prefix + f"四图重叠执行：每图 {manifest['template_steps']} 个真实 RTL 步骤", loc="left", fontsize=16, pad=18)
    handles = [Patch(color="#0f766e", label="输入区间")] + [Patch(color=COLORS[k], label=NAMES[k]) for k in ORDER]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, -.18), ncol=7, frameon=False)
    fig.text(.13, .015, "每个色段对应一次 launch→done；跨度包含算子内部访存等待。黑竖线表示真实 SRAM 结果读完并确认。", color="#475569", fontsize=9)
    fig.subplots_adjust(bottom=.25, top=.86)
    save_figure(fig, "frame_pipeline.png")

    # A separate chart exposes every one of the 131 steps, including short
    # Post/Add/Pad segments that become tiny in the overview time axis.
    height = 23 if not small_self_test else 5.5
    fig, axes = plt.subplots(1, 4, figsize=(17, height), sharex=True, sharey=True)
    for f, ax in enumerate(axes):
        tag = metric["frames"][f]["frame"]
        for task in tasks:
            if task["frame"] == tag:
                ax.broken_barh([(task["begin"], task["elapsed"])], (task["local_step"] - .35, .7), facecolors=COLORS[task["opcode"]])
        ax.set_title(f"frame {tag}")
        ax.set_xlim(0, metric["cycles"])
        ax.set_ylim(manifest["template_steps"] - .2, -.8)
        ax.set_yticks(range(0, manifest["template_steps"], 5 if not small_self_test else 1))
        ax.grid(alpha=.15)
        ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        ax.set_xlabel("周期")
    axes[0].set_ylabel("固定流程步骤编号（从 0 开始）")
    fig.suptitle(prefix + "逐步骤甘特图：全部任务来自实际 launch / done 事件", fontsize=15, y=.995)
    fig.legend(handles=handles[1:], loc="lower center", ncol=6, frameon=False)
    fig.tight_layout(rect=(0, .025, 1, .98))
    save_figure(fig, "all_steps_gantt.png")

    fig, ax = plt.subplots(figsize=(15, 6.6))
    labels = [f"U{u['unit']}\n{NAMES[u['kind']]}" for u in metric["units"]]
    x = list(range(len(labels)))
    ax.bar([v - .25 for v in x], [u["active_cycles"] for u in metric["units"]], .25, color="#94a3b8", label="active：算子忙碌")
    ax.bar(x, [u["work_cycles"] for u in metric["units"]], .25, color="#2563eb", label="work：MAC / 接受写回")
    ax.bar([v + .25 for v in x], [u["arbitration_wait_cycles"] for u in metric["units"]], .25, color="#ef4444", label="wait：请求 valid 且未获 ready")
    ax.set(xticks=x, xticklabels=labels, ylabel="周期数（每个物理实例）")
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
    ax.grid(axis="y", alpha=.2)
    ax.set_axisbelow(True)
    ax.set_title(prefix + "算子忙碌、实际工作和 SRAM 仲裁等待", loc="left", fontsize=16, pad=18)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.14), ncol=3, frameon=False)
    fig.text(.13, .01, "work/wait 是 active 内的指标，不是可相加的时间分解。DW7 一次 work 含 8 路 MAC；Post/Add/Pad 记录接受写回。", fontsize=9, color="#475569")
    fig.subplots_adjust(bottom=.24, top=.88)
    save_figure(fig, "operator_cycles.png")

    # These are actual per-clock top-level samples, not a reconstructed waveform.
    # Their time axes start at the recorded window, not at network cycle zero.
    from plot_waveforms import read_vcd
    wave_views = []
    work_labels = ["K3 #0 MAC", "K3 #1 MAC", "K3 #2 MAC", "K3 #3 MAC", "K1 #0 MAC", "K1 #1 MAC",
                   "DW7 MAC (8 lanes)", "Post accepted write", "Add accepted write", "Pad accepted write"]
    for name in ("mac_detail", "pipeline_detail"):
        vcd_file = evidence / (name + ".vcd")
        if not vcd_file.exists():
            continue
        vcd = read_vcd(vcd_file)
        require(len(vcd.signals) == 10, "Unexpected full-network waveform signal count")
        gtk = [f'[dumpfile] "{vcd_file.as_posix()}"', '[size] 1800 1000', '[signals_width] 350']
        for path, signal in vcd.signals.items():
            gtk += ['@28' if signal.width == 1 else '@22', path + (f'[{signal.width-1}:0]' if signal.width > 1 else '')]
        (out / (name + '.gtkw')).write_text('\n'.join(gtk) + '\n')
        zoom = 'gtkwave::setZoomRangeTimes 0 2560000\ngtkwave::/View/Scale_To_Time_Dimension/ns\n'
        (out / (name + '.tcl')).write_text(zoom)
        (out / ('open_' + name + '.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0evidence\\' + name + '.vcd" -a "%~dp0' + name + '.gtkw" -S "%~dp0' + name + '.tcl"\n')
        verify = 'set log [open [file join [file dirname [info script]] validation_' + name + '.log] w]\nset failure [catch {\n' + zoom
        verify += 'set shown [gtkwave::getDisplayedSignals]\nputs $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\n'
        verify += 'if {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing or duplicate signals"}\n'
        verify += 'puts $log "PASS ' + name + '"\n} message]\nif {$failure} {puts $log "FAIL $message"}\nclose $log\ngtkwave::/File/Quit\n'
        (out / ('verify_' + name + '.tcl')).write_text(verify)
        signal = vcd.signals['cnn_full.operator_work']
        require(len(signal.events) > 1, "Empty real work waveform")
        fig, axes = plt.subplots(10, 1, figsize=(15, 8), sharex=True)
        for bit, ax in enumerate(axes):
            ax.step([t / 10 for t, value in signal.events], [(int(value, 2) >> bit) & 1 for t, value in signal.events],
                    where='post', color='#2563eb' if bit < 7 else '#16a34a', lw=1)
            ax.set(ylim=(-.1, 1.15), yticks=[0, 1], ylabel=work_labels[bit])
            ax.yaxis.label.set_rotation(0)
            ax.yaxis.set_label_coords(-.12, .25)
            ax.grid(axis='x', alpha=.2)
        axes[0].set_title(prefix + ('跨图卷积真实 MAC 同拍窗口' if name == 'mac_detail' else '跨图、跨类真实工作同拍窗口'), loc='left', fontsize=15)
        axes[-1].set_xlabel('窗口相对周期；采样自真实 RTL，未记录该窗口的全局起始周期')
        fig.subplots_adjust(left=.2, right=.98, top=.93, bottom=.08, hspace=.25)
        save_figure(fig, name + '.png')
        wave_views.append(name)
    write_json(out / 'wave_views.json', dict(views=wave_views, signals_per_view=10, clocks_per_window=257,
        global_origin_recorded=False, note='Only two 256-cycle windows were captured; full task timing is in events.csv.'))
    (out / 'validate_gtkwave.ps1').write_text(r'''$ErrorActionPreference='Stop'
$artifactRoot=$PSScriptRoot
$gtkExe=(Resolve-Path -LiteralPath (Join-Path $artifactRoot '..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe')).Path
$views=@('mac_detail','pipeline_detail')
$results=@()
foreach($view in $views){
  $logPath=Join-Path $artifactRoot ('validation_'+$view+'.log')
  if(Test-Path -LiteralPath $logPath){Remove-Item -LiteralPath $logPath}
  $arguments=@('-f',('evidence/'+$view+'.vcd'),'-a',($view+'.gtkw'),'-S',('verify_'+$view+'.tcl'))
  $process=Start-Process -FilePath $gtkExe -ArgumentList $arguments -WorkingDirectory $artifactRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifactRoot ('gtk_'+$view+'_stdout.log')) -RedirectStandardError (Join-Path $artifactRoot ('gtk_'+$view+'_stderr.log'))
  $exited=$process.WaitForExit(20000)
  if(-not $exited){Stop-Process -Id $process.Id}
  $contents=if(Test-Path -LiteralPath $logPath){Get-Content -LiteralPath $logPath -Raw}else{''}
  $status=if($exited -and $process.ExitCode -eq 0 -and $contents.Contains('PASS '+$view) -and $contents.Contains('SIGNALS=10 UNIQUE=10')){'PASS'}else{'FAIL'}
  $results += [pscustomobject]@{view=$view;status=$status;exited=$exited;signals=10;unique_signals=10;session_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot ($view+'.gtkw')) -Algorithm SHA256).Hash.ToLower();vcd_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot ('evidence/'+$view+'.vcd')) -Algorithm SHA256).Hash.ToLower();log=$contents.Trim()}
  Write-Output ($view+' '+$status)
}
$allPass=(@($results | Where-Object {$_.status -ne 'PASS'}).Count -eq 0)
[pscustomobject]@{status=$(if($allPass){'PASS'}else{'FAIL'});tool='GTKWave 3.3.100 actual Tcl validation';views=$results} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $artifactRoot 'gtkwave_validation.json') -Encoding UTF8
if(-not $allPass){exit 1}
''', encoding='utf-8')
    if not small_self_test:
        import xml.etree.ElementTree as ET
        diagram = ET.parse(ROOT / 'deliverables/self_cnn_four_frames/architecture.drawio')
        for cell in diagram.iter('mxCell'):
            value = cell.get('value', '')
            value = value.replace('11 个模板步骤 → 44 个四图任务', '131 个模板步骤 → 524 个四图任务（容量1024）')
            value = value.replace('256 KiB，4 个真双口 bank', '16 MiB 仿真容量，4 个真双口 bank')
            value = value.replace('completed_mask[63:0]', 'completed_mask[1023:0]')
            if value:
                cell.set('value', value)
        diagram.write(out / 'architecture.drawio', encoding='utf-8', xml_declaration=True)

    serial_text = "本次完整运行没有同数据、同配置的串行场景，未给出串行加速倍数。"
    if "serial" in scenarios and scenario != "serial":
        serial_text = (f"同一数据/算子配置的串行对照为 **{scenarios['serial']['cycles']:,} 拍**，"
                       f"批次端到端加速 **{scenarios['serial']['cycles'] / metric['cycles']:.3f}×**。该比值包含输入、任务展开和结果读取，不是单层 MAC 加速。")
    if peak_pool["opcode"] == queue_pool["opcode"] and peak_pool["average_busy_fraction"] >= .6:
        bottleneck = (f"当前瓶颈指向 **{peak_pool['operator']} 算子池**：{peak_pool['instances']} 个实例平均忙碌率 "
                      f"{peak_pool['average_busy_fraction']:.2%}，同时该类算子有最多的同类资源等待 "
                      f"{queue_pool['capacity_wait_frame_cycles']:,} 帧·拍。")
    else:
        bottleneck = (f"平均忙碌率最高的是 **{peak_pool['operator']}**（{peak_pool['average_busy_fraction']:.2%}）；"
                      f"同类算子资源等待最多的是 **{queue_pool['operator']}**（{queue_pool['capacity_wait_frame_cycles']:,} 帧·拍）。"
                      "这两项没有同时指向一个持续饱和的算子池，现有计数不足以将全部耗时归因到单一资源。")
    arb_fraction = arb_sum / active_sum if active_sum else 0
    if arb_fraction < .05:
        arbitration_text = "这项已观测到的仲裁反压占比较小，不能用它解释主要耗时。"
    else:
        arbitration_text = "仲裁反压已经可见；应结合具体层的请求分布与 bank 冲突进一步拆分。"
    arbitration_text += "等待 SRAM 正常响应、逐字节访问和单在途请求的固定成本不计入此项，因此不能据此声称没有访存瓶颈。"
    pw = next(p for p in pools if p['opcode'] == 5)
    compute_detail = (f"1×1 共执行 **{pw['macs']:,} MAC，占总 MAC 的 {pw['macs']/metric['macs']:.2%}**。"
                      f"其 MAC 脉冲仅占本类 active 的 {pw['work_per_active']:.2%}，"
                      f"本类仲裁等待仅占 active 的 {pw['arbitration_wait_per_active']:.3%}。"
                      "自研核在 `MAC_READ` 与 `MAC_ACC` 间交替，一个实例每两拍执行一次 MAC；"
                      f"两套实例合计在本批次达到 {pw['macs']/metric['cycles']:.4f} MAC/拍。"
                      f"从 active 中扣除每个 MAC 的两拍后，剩余 {pw['active_cycles']-2*pw['macs']:,} 实例·拍"
                      "包含输入/权重装载、写回、状态切换及仲裁等成本，不能全部归为 bank 冲突。"
                      "优先方向是将1×1 MAC读数与累加做流水、增加适量并行MAC并提升装载效率，再比较增加1×1实例的资源收益。"
                      "本次没有重综合或重新扫描全网实例数量，不宣称改为四套1×1就能得到某个确定加速倍数。")
    pw_parts = {'MAC_READ + MAC_ACC': 2*pw['macs'], '字节读请求/正常响应': 2*pw['read_bytes'],
                '32位写请求/正常响应': pw['write_bytes']//2, '请求仲裁反压': pw['arbitration_wait_cycles']}
    pw_parts['其余块切换/状态设置'] = pw['active_cycles'] - sum(pw_parts.values())
    require(pw_parts['其余块切换/状态设置'] >= 0, '1x1 cycle accounting inconsistent with current scalar RTL')
    pw_table = '\n'.join(f"| {label} | {count:,} | {count/pw['active_cycles']:.4%} |" for label, count in pw_parts.items())
    rowtext = "\n".join(f"| {p['operator']} | {p['instances']} | {p['average_busy_fraction']:.2%} | {p['work_cycles']:,} | {p['arbitration_wait_cycles']:,} | {p['capacity_wait_frame_cycles']:,} |" for p in pools)
    frame_table = "\n".join(f"| {f['frame']} | {f['input_commit']:,} | {f['first_launch']:,} | {f['read_complete']:,} |" for f in metric["frames"])
    scenario_table = "\n".join(f"| {name} | PASS | {m['cycles']:,} | {m['simulation_seconds']:.3f} s |" for name, m in scenarios.items())
    layer_table = "\n".join(f"| {r['layer']} | {r['operation']} | {r['shape']} | {r['total_span']:,} | {r['maximum_span']:,} |" for r in slow_layers[:8])
    quant_text = (f"最终每图输出 **{width} 个 UINT8 分量**，不是 IEEE 浮点。反量化为 `(code - {zero}) × {scale:.17g}`；"
                  "CSV 保留原始量化字节，并另给出反量化近似值。全图共用第一张图得到的诊断尺度，未做代表性数据集校准，也未测人脸识别精度。")
    if audit is not None:
        rmse = [r["dequant_vs_float_rmse"] for r in audit["outputs"]]
        cosine = [r["dequant_vs_float_cosine"] for r in audit["outputs"]]
        quant_text += (f" 独立浮点诊断中四图反量化输出与 FP32 的 RMSE 为 {min(rmse):.4f}～{max(rmse):.4f}，"
                       f"余弦相似度 {min(cosine):.4f}～{max(cosine):.4f}；量化输出与 FP32 **不是逐值相同**。"
                       "模型末尾 Reshape 仅改变形状，分量次序不变；模型及本入口均未加 L2 归一化。")
    warning = ("\n> **SMALL 渲染自测：以下数字来自前三层 ROI，仅用于验证报告脚本。不是完整 MobileFaceNet 性能或数值结论。**\n" if small_self_test else "")
    report = f"""# {title}
{warning}
本报告只使用已完成的真实 RTL 运行 `{run.name}`，场景 `{scenario}`。CNN 接收一份固定流程模板与四组图片/工作区地址，自主展开 **{manifest['template_steps']} 步/图、{manifest['total_tasks']} 个任务**，所有卷积、后处理、残差 Add、调度及 bai 四 bank SRAM 均执行实际 RTL。

四图最终结果均经实际 SRAM IO 口读取并与独立整数参考逐字节一致，总用时 **{metric['cycles']:,} 拍**，计算完成于 {metric['compute_done_cycle']:,} 拍。{serial_text}

仅按 **100 MHz** 换算，该批四图为 **{metric['cycles']/1e8:.5f} 秒**，批次吞吐 **{4e8/metric['cycles']:.4f} 图/秒**；这是频率假设下的周期换算，100 MHz 尚未通过此完整配置的布局布线时序验证。均摊时间 {metric['cycles']/4e8:.5f} 秒/图不等于首图延迟。主机仿真计算耗时 {metric['simulation_seconds']/60:.2f} 分钟，包含初始化与收尾的运行器耗时为 {result['wall_seconds']/60:.2f} 分钟。

## 输入、重叠与流水

- [四张输入图]({link(out / 'input_images.png')})：合成测试 RGB，完整输入形状 `{manifest['input_shape']}`。
- [四图流水总览]({link(out / 'frame_pipeline.png')})、[每个步骤的甘特图]({link(out / 'all_steps_gantt.png')})。
- [算子 active/work/wait]({link(out / 'operator_cycles.png')})、[全部任务事件表]({link(out / 'task_events.csv')})、[逐层事件汇总]({link(out / 'layer_events.csv')})。
- [MAC 同拍采样图]({link(out / 'mac_detail.png')})、[跨类同拍采样图]({link(out / 'pipeline_detail.png')})；对应 `open_mac_detail.cmd` / `open_pipeline_detail.cmd` 可打开真实 VCD 的 GTKWave 会话，每个会话10根物理信号各出现一次。窗口相对时间不代表网络从零开始，窗口外没有记录，不推断为RTL未知。
- [可编辑架构图]({link(out / 'architecture.drawio')})：完整入口配置 `MAX_TASKS=1024`、模板容量256、SRAM 16 MiB；此前短流程默认64任务的配置不能直接装下本次524任务。

最多 {metric['peak_active_frames']} 图同时有在途任务。跨图真实 MAC / 接受写回重叠 {metric['multi_frame_work_cycles']:,} 拍，跨算子类型真实工作重叠 {metric['cross_operator_work_cycles']:,} 拍；后续图输入期间已有图 MAC 推进 {metric['input_mac_cycles']:,} 拍。单纯多图 busy 为 {metric['multi_frame_cycles']:,} 拍，未将其等同于实际运算重叠。

| frame | 图像提交 | 首步启动 | 结果读取确认 |
|---:|---:|---:|---:|
{frame_table}

任务条跨度来自实际 launch→done，包含算子内部装载、计算和写回等待。每张图内部按固定顺序执行；流水发生在不同图片、不同算子之间，不声称同一层按行输出直接流入下一层。

## 本次完整运行的性能限制

{bottleneck}

{compute_detail}

| 算子池 | 数量 | 平均忙碌率 | work 实例·拍 | 仲裁等待 实例·拍 | 等同类资源 帧·拍 |
|---|---:|---:|---:|---:|---:|
{rowtext}

平均忙碌率 = 同类实例 active 总和 /（实例数 × 批次周期）；不同实例的周期不能直接相加为批次耗时。卷积 work 为 MAC 脉冲，DW7 每次 work 含 8 路 MAC；Post/Add/Pad 的 work 为成功接受写回。work、wait 都不是与 active 互斥的分项。

进一步依据已核对的状态机与真实 MAC/读写计数，可将两套1×1累计 active 分解如下。每次字节读、每次32位写分别经历请求与正常响应两拍；反压额外计数。这里的分母是 **{pw['active_cycles']:,} 实例·拍**，不是全局批次时间：

| 1×1内部阶段 | 累计实例·拍 | 占1×1 active |
|---|---:|---:|
{pw_table}

SRAM `valid && !ready` 仲裁等待合计 {arb_sum:,} 实例·拍，占全部算子 active 合计的 **{arb_fraction:.2%}**。{arbitration_text}

`capacity_wait_by_opcode` 与 `scan_wait_by_opcode` 都是各图累计的等待帧·拍，不是批次周期百分比；后者表示有同类空闲单元时仍未启动，还包括槽释放和调度扫描等，不能称纯调度耗时。

下表按四图合计层跨度排序。跨度包含该层各算子及其中等待，反映本轮执行路径，不能当作纯 MAC 时间：

| 网络层 | 类型 | 输出 H×W×C | 四图合计层跨度 | 最大单图层跨度 |
|---:|---|---|---:|---:|
{layer_table}

本报告据已测资源忙碌与等待定位下一步优化对象；没有用短流程数据代替全网测量，也没有假设增加一个算子就必然获得同等比例收益。

## 数值与输出含义

每个场景完成 {metric['commands']:,} 个任务、{metric['macs']:,} 次标量 MAC；检查 **{metric['checked_bytes']:,} 个输出字节**、{metric['allocations']} 次分配和 {metric['releases']} 次释放。检查方法为每次真实 RTL 写请求逐字节比较整数 golden，同时核对后续真实 SRAM 读响应；最终向量、只读区和槽尾保护区经 SRAM 端口实际读取。不是所有中间张量都另做一次完整读回。

{quant_text}

- [原始 UINT8 向量]({link(out / 'embeddings_u8.csv')})、[反量化近似向量]({link(out / 'embeddings_dequantized.csv')})、[格式与尺度]({link(out / 'embedding_format.json')})。
- 四图最终输出 SHA256：`{manifest['final_expected_sha256']}`。
- 原始 `outputs.bin`、metrics、events 与运行签名保存在 [evidence]({link(evidence)})。

初始执行内存只含共享权重/量化参数和 A5；运行中的图像通过实际端口写入，所有中间 golden 都只存在于 checker 文件。preloaded 场景若出现在下表，是实际 CPU A 口预装图片后运行；不等同于处理器执行固件。

| 完整运行场景 | 状态 | 批次周期 | 仿真计算耗时（主机） |
|---|---|---:|---:|
{scenario_table}

## 存储与实现边界

**本入口使用 {result['sram_capacity'] / 1048576:g} MiB 的仿真 SRAM 参数，执行初值为 {manifest['init_bytes']:,} 字节（{manifest['init_bytes'] / 1048576:.3f} MiB）。这不代表 Zynq-7020 能在片内容纳此存储。** 四个复用工作区每个 {manifest['workspace_bytes']:,} 字节，共享只读/输入区域 {manifest['readonly_end']:,} 字节。真实板级实现仍需分块/外存方案及资源、布局布线、时序验证。

本轮证明完整图的量化整数算术、四图自主调度及跨图重叠，不证明识别精度、CPU/UART 集成或板级性能。上方100 MHz仅为条件换算。原 Post / DW7 存储综合问题不因 RTL 仿真 PASS 自动消失；本轮没有新的完整顶层LUT/FF/BRAM/DSP报告，不能用单卷积资源乘实例数代替完整资源占用。

## 复现与来源

- 运行目录：`{run}`。
- 数据目录：`{data}`；模型 SHA256：`{manifest['model_sha256']}`。
- 生成器：`scripts/gen_self_full.py`，运行器：`scripts/run_self_full.py`，本报告：`scripts/prepare_self_full.py`。
- 报告命令：`python scripts/prepare_self_full.py "{run}" --scenario {scenario}`{' --small-self-test' if small_self_test else ''}。
- 全网运行必须先通过同一可执行文件的小图 gate；报告只接受全网 PASS，SMALL 自测输出被限制在 build 目录。
"""
    (out / "README.md").write_text(report, encoding="utf-8")
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(report, encoding="utf-8")
    summary = dict(status="SMALL_RENDER_SELF_TEST" if small_self_test else "FULL_RTL_PASS_REPORT", run=str(run),
        scenario=scenario, full_network=bool(manifest["full_network"]), metrics=metric, pools=pools,
        busiest_pool=peak_pool["operator"], longest_capacity_wait_pool=queue_pool["operator"],
        arbitration_wait_per_all_active=arb_fraction, slowest_layers=slow_layers[:8],
        pointwise_cycle_accounting=pw_parts,
        final_output_sha256=manifest["final_expected_sha256"], docs=str(docs), report=str(out / "README.md"))
    write_json(out / "report_summary.json", summary)
    provenance = dict(run=str(run), scenario=scenario, small_self_test=small_self_test,
        result_sha256=sha(run / "result.json"), manifest_sha256=sha(manifest_path),
        report_script_sha256=sha(Path(__file__)), exe_sha256=result["exe_sha256"],
        files_sha256={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "provenance.json"})
    write_json(out / "provenance.json", provenance)
    print(json.dumps({"status": summary["status"], "report": str(out / "README.md"), "docs": str(docs),
                      "cycles": metric["cycles"], "busiest_pool": summary["busiest_pool"]}, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--scenario", default="overlap")
    parser.add_argument("--small-self-test", action="store_true", help="watermarked renderer QA confined to build/self_full_report_test")
    args = parser.parse_args()
    prepare(args.run, args.scenario, args.small_self_test)
