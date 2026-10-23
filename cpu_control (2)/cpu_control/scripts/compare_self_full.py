"""Compare two completed, numerically identical full MobileFaceNet RTL runs.

Final evidence requires K3/K1=4/2 versus 2/4, four identical images, the same
input pace, unchanged arithmetic/control/SRAM RTL, and independently passed
524-task runs. --self-test is confined to a watermarked build directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
NAMES = {0: "3×3 / DW3", 5: "1×1", 3: "DW7", 1: "Post", 2: "Add", 4: "Pad"}
COLORS = {0: "#2563eb", 5: "#16a34a", 3: "#dc2626", 1: "#8b5cf6", 2: "#f59e0b", 4: "#06b6d4"}
ORDER = (0, 5, 3, 1, 2, 4)
EXPECTED_BASELINE = {"K3": 4, "K1": 2, "Post": 1, "Add": 1, "DW7": 1, "Pad": 1}
EXPECTED_CANDIDATE = {"K3": 2, "K1": 4, "Post": 1, "Add": 1, "DW7": 1, "Pad": 1}
PROTECTED = (
    "rtl/cnn_self/self_conv_engine.sv",
    "rtl/cnn_quant/dw7_cached_engine.sv",
    "rtl/cnn_quant/quant_post_engine.sv",
    "rtl/cnn_quant/pad_hwc_engine.sv",
    "rtl/cnn_stream/bai/datasram_banked.sv",
    "rtl/cnn_stream/stream_dispatch.sv",
    "rtl/cnn_stream/stream_buffer_leases.sv",
    "rtl/cnn_stream/stream_result_handoff.sv",
    "rtl/cnn_stream/stream_fixed_programmer.sv",
    "rtl/cnn_stream/self_stream_top.sv",
    "rtl/cnn_stream/self_fixed_network_top.sv",
)
ALLOWED_SOURCE_CHANGES = {
    "tb/self_full_sim_top.sv": "verification top / operator-count parameters",
    "tb/integration/self_full_main.cpp": "checker / profiling harness and matching operator-count constants",
    "rtl/filelists/cnn_self_stream.f": "build source listing; protected RTL content must remain identical",
    "scripts/bootstrap_verilator_native.py": "native simulator build/tool flags",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path: Path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def link(path):
    return "</" + Path(path).resolve().as_posix() + ">"


def load_resource_review(source_hashes):
    """Authenticate existing OOC evidence; this never invokes synthesis."""
    source = ROOT / "build/self_full_pool_review/resource_delta.json"
    if not source.exists():
        return None, []
    review = read_json(source)
    require(review["new_synthesis_run"] is False and review["whole_top_status"]["validated"] is False,
            "Resource review must explicitly distinguish historical OOC evidence from a new whole-top result")
    files = [(source, "resource_delta.json")]
    markdown = source.with_suffix(".md")
    if markdown.exists():
        files.append((markdown, "resource_delta.md"))
    for kind in ("k3", "k1"):
        unit = review["units"][kind]
        require(unit["source_sha256"] == source_hashes["rtl/cnn_self/self_conv_engine.sv"],
                "Resource kernel differs from the arithmetic RTL used in simulation")
        require(unit["status"] == "PASS" and unit["stage"] == "out_of_context_synthesis" and
                unit["place_route_performed"] is False, "Unexpected resource evidence stage/status")
        for name, digest in unit["report_sha256"].items():
            path = Path(unit["evidence_run"]) / name
            require(sha(path) == digest, f"Historical resource evidence changed: {path}")
            files.append((path, kind + "/" + name))
    metrics = ("lut", "ff", "bram36_equivalent", "dsp48e1", "logical_input_plus_weight_cache_bytes")
    for key, pool in (("old_4k3_2k1", EXPECTED_BASELINE), ("candidate_2k3_4k1", EXPECTED_CANDIDATE)):
        total = review[key]
        require(total["estimated_convolution_only"] is True and total["pool"] == {k.lower(): v for k, v in pool.items()},
                "Resource estimate uses a different pool")
        for metric in metrics:
            expected = 0
            for kind in ("k3", "k1"):
                unit = review["units"][kind]
                value = (unit["logical_input_cache_bytes"] + unit["logical_weight_cache_bytes"]
                         if metric == "logical_input_plus_weight_cache_bytes" else unit[metric])
                expected += total["pool"][kind] * value
            require(total[metric] == expected, "Resource OOC sum mismatch: " + metric)
    for metric in metrics:
        require(review["candidate_minus_old"][metric] == review["candidate_2k3_4k1"][metric] - review["old_4k3_2k1"][metric],
                "Resource delta mismatch: " + metric)
    return review, files


def existing_gtkwave_validation(out, wave_views):
    """Authenticate prior GUI/Tcl evidence without starting GTKWave or changing logs."""
    evidence = out / 'gtkwave_validation.json'
    if not evidence.exists():
        return dict(status='NOT_VERIFIED', reason='No existing GTKWave validation JSON')
    try:
        recorded = json.loads(evidence.read_text(encoding='utf-8-sig'))
        require(recorded.get('status') == 'PASS', 'Existing GTKWave validation is not PASS')
        views = recorded['views']
        expected = {view['view']: view for view in wave_views}
        require(len(views) == len(expected) == 2 and {view['view'] for view in views} == set(expected),
                'Existing GTKWave evidence must contain exactly the two candidate views')
        verified = []
        for view in views:
            name = view['view']
            require(view.get('status') == 'PASS' and view.get('exited') is True and
                    view.get('signals') == view.get('unique_signals') == 10,
                    'Existing GTKWave view did not pass its ten-unique-signal check: ' + name)
            session_hash = sha(out / (name + '.gtkw'))
            vcd_hash = sha(out / expected[name]['vcd'])
            require(view.get('session_sha256', '').lower() == session_hash and
                    view.get('vcd_sha256', '').lower() == vcd_hash,
                    'GTKWave evidence hashes do not match the current session/VCD: ' + name)
            require('PASS ' + name in view.get('log', '') and 'SIGNALS=10 UNIQUE=10' in view.get('log', ''),
                    'GTKWave evidence is missing its Tcl success record: ' + name)
            verified.append(dict(view=name, session_sha256=session_hash, vcd_sha256=vcd_hash,
                                 signals=10, unique_signals=10))
        return dict(status='PASS', evidence='gtkwave_validation.json', evidence_sha256=sha(evidence),
                    tool=recorded.get('tool'), views=verified,
                    note='Previously executed GTKWave/Tcl validation; current session and VCD hashes rechecked.')
    except (RuntimeError, ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        return dict(status='NOT_VERIFIED', evidence='gtkwave_validation.json', reason=str(error))


def candidate_visuals(out, candidate, self_test, plt, save_figure):
    """Package actual candidate VCD samples with dynamically mapped work bits."""
    from plot_waveforms import read_vcd
    expected_signals = {
        "cnn_full.unit_active": 10, "cnn_full.operator_work": 10,
        "cnn_full.mem_valid": 10, "cnn_full.mem_ready": 10,
        "cnn_full.mem_write": 10, "cnn_full.mem_response": 10,
        "cnn_full.frames_ready": 4, "cnn_full.result_valid": 1,
        "cnn_full.result_ready": 1, "cnn_full.completed_count": 11,
    }
    units = sorted(candidate["metrics"]["units"], key=lambda u: u["unit"])
    require([u["unit"] for u in units] == list(range(10)), "Wave work bits require ten indexed physical units")
    kind_name = {0: "K3", 5: "K1", 3: "DW7", 1: "Post", 2: "Add", 4: "Pad"}
    work_labels = [f"{kind_name[u['kind']]} ({u['unit']}) " +
                   ("MAC (8 lanes)" if u["kind"] == 3 else "MAC" if u["kind"] in (0, 5) else "accepted write")
                   for u in units]
    wave_views = []
    for source_name in ("mac_detail", "pipeline_detail"):
        view = "candidate_" + source_name
        vcd_file = out / "evidence/candidate" / (source_name + ".vcd")
        require(vcd_file.exists(), "Missing actual candidate VCD: " + str(vcd_file))
        vcd = read_vcd(vcd_file)
        require({path: signal.width for path, signal in vcd.signals.items()} == expected_signals,
                "Unexpected candidate waveform signals or widths")
        require(len({signal.code for signal in vcd.signals.values()}) == 10,
                "Candidate VCD contains signal aliases")
        require(vcd.timescale == "1ns" and vcd.end_ns > 0, "Unexpected candidate VCD time scale/range")
        gtk = [f'[dumpfile] "{vcd_file.as_posix()}"', '[size] 1800 1000', '[signals_width] 350']
        for path, signal in vcd.signals.items():
            gtk += ['@28' if signal.width == 1 else '@22', path + (f'[{signal.width-1}:0]' if signal.width > 1 else '')]
        (out / (view + '.gtkw')).write_text('\n'.join(gtk) + '\n', encoding='utf-8')
        # GTKWave Tcl uses internal ps for this 1ns VCD; its visible axis is ns.
        zoom = (f'# Window-relative samples: 0..{vcd.end_ns:g} ns; global origin was not recorded.\n'
                f'gtkwave::setZoomRangeTimes 0 {round(vcd.end_ns * 1000)}\n'
                'gtkwave::/View/Scale_To_Time_Dimension/ns\n')
        (out / (view + '.tcl')).write_text(zoom, encoding='utf-8')
        (out / ('open_' + view + '.cmd')).write_text(
            '@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" '
            '-f "%~dp0evidence\\candidate\\' + source_name + '.vcd" -a "%~dp0' + view +
            '.gtkw" -S "%~dp0' + view + '.tcl"\n', encoding='utf-8')
        verify = ('set log [open [file join [file dirname [info script]] validation_' + view + '.log] w]\n'
                  'set failure [catch {\n' + zoom +
                  'set shown [gtkwave::getDisplayedSignals]\n'
                  'puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\n'
                  'if {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing or duplicate signals"}\n'
                  'puts $log "PASS ' + view + '"\n} message]\n'
                  'if {$failure} {puts $log "FAIL $message"}\nclose $log\ngtkwave::/File/Quit\n')
        (out / ('verify_' + view + '.tcl')).write_text(verify, encoding='utf-8')
        work = vcd.signals['cnn_full.operator_work']
        require(len(work.events) > 1 and work.events[0][0] == 0 and
                all(set(value) <= {'0', '1'} for _, value in work.events), "Empty or undefined candidate work waveform")
        times = [t / 10 for t, _ in work.events] + [vcd.end_ns / 10]
        values = [int(value, 2) for _, value in work.events] + [int(work.events[-1][1], 2)]
        fig, axes = plt.subplots(10, 1, figsize=(15, 8), sharex=True)
        for bit, ax in enumerate(axes):
            ax.step(times, [(value >> bit) & 1 for value in values], where='post', color=COLORS[units[bit]['kind']], lw=1)
            ax.set(ylim=(-.1, 1.15), yticks=[0, 1], ylabel=work_labels[bit], xlim=(0, vcd.end_ns / 10))
            ax.yaxis.label.set_rotation(0)
            ax.yaxis.label.set_horizontalalignment('right')
            ax.yaxis.set_label_coords(-.04, .25)
            ax.grid(axis='x', alpha=.2)
        prefix = 'SELFTEST | ' if self_test else ''
        axes[0].set_title(prefix + ('候选跨图真实 MAC 同拍窗口' if source_name == 'mac_detail' else '候选跨图、跨类真实工作同拍窗口'), loc='left', fontsize=15)
        axes[-1].set_xlabel('窗口相对周期（10 ns/拍采样）；实际 RTL VCD，未记录窗口的全局起始周期')
        fig.subplots_adjust(left=.25, right=.98, top=.93, bottom=.08, hspace=.25)
        save_figure(fig, view + '.png')
        wave_views.append(dict(view=view, vcd=str(vcd_file.relative_to(out).as_posix()),
            vcd_sha256=sha(vcd_file), signals=list(expected_signals), signals_count=10,
            start_ns=0, end_ns=vcd.end_ns, global_origin_recorded=False))
    gtk_validation = existing_gtkwave_validation(out, wave_views)
    write_json(out / 'wave_views.json', dict(views=wave_views, work_bit_labels=work_labels,
        gtk_validation_status=gtk_validation['status'], gtk_validation=gtk_validation,
        note='Actual candidate samples only. Window-relative time is not network-cycle zero; full timing is in events.csv.'))
    (out / 'validate_gtkwave.ps1').write_text(r'''$ErrorActionPreference='Stop'
$artifactRoot=$PSScriptRoot
$gtkExe=(Resolve-Path -LiteralPath (Join-Path $artifactRoot '..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe')).Path
$views=@('candidate_mac_detail','candidate_pipeline_detail')
$results=@()
foreach($view in $views){
  $sourceName=$view.Substring('candidate_'.Length)
  $vcdRelative='evidence/candidate/'+$sourceName+'.vcd'
  $logPath=Join-Path $artifactRoot ('validation_'+$view+'.log')
  if(Test-Path -LiteralPath $logPath){Remove-Item -LiteralPath $logPath}
  $arguments=@('-f',$vcdRelative,'-a',($view+'.gtkw'),'-S',('verify_'+$view+'.tcl'))
  $process=Start-Process -FilePath $gtkExe -ArgumentList $arguments -WorkingDirectory $artifactRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifactRoot ('gtk_'+$view+'_stdout.log')) -RedirectStandardError (Join-Path $artifactRoot ('gtk_'+$view+'_stderr.log'))
  $exited=$process.WaitForExit(20000)
  if(-not $exited){Stop-Process -Id $process.Id}
  $contents=if(Test-Path -LiteralPath $logPath){Get-Content -LiteralPath $logPath -Raw}else{''}
  $status=if($exited -and $process.ExitCode -eq 0 -and $contents.Contains('PASS '+$view) -and $contents.Contains('SIGNALS=10 UNIQUE=10')){'PASS'}else{'FAIL'}
  $results += [pscustomobject]@{view=$view;status=$status;exited=$exited;signals=10;unique_signals=10;session_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot ($view+'.gtkw')) -Algorithm SHA256).Hash.ToLower();vcd_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot $vcdRelative) -Algorithm SHA256).Hash.ToLower();log=$contents.Trim()}
  Write-Output ($view+' '+$status)
}
$allPass=(@($results | Where-Object {$_.status -ne 'PASS'}).Count -eq 0)
[pscustomobject]@{status=$(if($allPass){'PASS'}else{'FAIL'});tool='GTKWave 3.3.100 actual Tcl validation';views=$results} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $artifactRoot 'gtkwave_validation.json') -Encoding UTF8
if(-not $allPass){exit 1}
''', encoding='utf-8')
    if not self_test:
        import xml.etree.ElementTree as ET
        source = ROOT / 'deliverables/self_cnn_full_frames/architecture.drawio'
        diagram = ET.parse(source)
        cells = {cell.get('id'): cell for cell in diagram.iter('mxCell')}
        value = cells['ops'].get('value')
        require('K3 ×4' in value and 'K1 ×2' in value and
                '16 MiB 仿真容量' in cells['sram'].get('value'), 'Unexpected original full-network architecture')
        pool = candidate['result']['pool']
        cells['ops'].set('value', value.replace('K3 ×4', f"K3 ×{pool['K3']}").replace('K1 ×2', f"K1 ×{pool['K1']}"))
        diagram.write(out / 'architecture.drawio', encoding='utf-8', xml_declaration=True)
        write_json(out / 'architecture_source.json', dict(source=str(source), source_sha256=sha(source),
            changes=['K3 ×4 → K3 ×2', 'K1 ×2 → K1 ×4'], sram='16 MiB simulation capacity'))
    return gtk_validation


def load_run(path, self_test):
    path = Path(path).resolve()
    result = read_json(path / "result.json")
    require(result.get("status") == "PASS", f"Run is not fully PASS: {path}")
    data = Path(result["data"]).resolve()
    manifest = read_json(data / "manifest.json")
    require(sha(data / "manifest.json") == result["manifest_sha256"], "Manifest differs from run provenance")
    require(result["frames"] == manifest["frames"] == 4, "Four frames are required")
    require(bool(result["full_network"]) == bool(manifest["full_network"]), "Full-graph labels disagree")
    if not self_test:
        require(result["full_network"] and manifest["full_network"], "Only completed full-network runs can produce final comparison evidence")
        require(manifest["input_shape"] == [112, 112, 3] and manifest["template_steps"] == 131 and
                manifest["total_tasks"] == 524 and manifest["total_macs"] == 935241728 and
                manifest["expected_bytes"] == 77349168 and manifest["final_bytes_per_frame"] == 128,
                "Full MobileFaceNet shape/coverage contract mismatch")
        require(result["sram_capacity"] == manifest["memory_bytes"] == 16777216, "Expected unchanged 16MiB simulation SRAM")
    require("overlap" in result["scenarios"], "Both runs must contain the same streamed-input overlap scenario")
    metrics = read_json(path / "overlap/metrics.json")
    require(metrics == result["scenarios"]["overlap"]["metrics"] and metrics["status"] == "PASS", "Scenario metric provenance/status mismatch")
    for field, want in (("commands", manifest["total_tasks"]), ("expanded_commands", manifest["total_tasks"]),
                        ("checked_bytes", manifest["expected_bytes"]), ("macs", manifest["total_macs"]),
                        ("allocations", manifest["total_tasks"]), ("releases", manifest["total_tasks"]), ("results", 4)):
        require(metrics[field] == want, f"Incomplete actual RTL coverage: {path.name}.{field}")
    for name, digest in manifest["files_sha256"].items():
        require(sha(data / name) == digest, f"Changed fixture file: {name}")
    output = (path / "overlap/outputs.bin").read_bytes()
    digest = hashlib.sha256(output).hexdigest()
    require(digest == result["scenarios"]["overlap"]["outputs_sha256"] == manifest["final_expected_sha256"], "Final output hash mismatch")
    expected = (data / "expected.bin").read_bytes()
    finals = [j for j in manifest["jobs"] if j["result"]]
    require(len(finals) == 4 and len(output) == 4 * manifest["final_bytes_per_frame"], "Final-vector coverage mismatch")
    golden = b"".join(expected[j["expected_offset"]:j["expected_offset"] + j["bytes"]] for j in finals)
    require(output == golden, "Actual SRAM result bytes differ from the independent integer reference")
    pool = result["pool"]
    counts = Counter(u["kind"] for u in metrics["units"])
    require(counts == {0: pool["K3"], 5: pool["K1"], 3: pool["DW7"], 1: pool["Post"], 2: pool["Add"], 4: pool["Pad"]},
            "Declared pool counts disagree with physical unit telemetry")
    require(sum(u["tasks"] for u in metrics["units"]) == manifest["total_tasks"], "Per-unit task count mismatch")
    jobs = {j["node"]: j for j in manifest["jobs"]}
    starts, done = {}, {}
    with (path / "overlap/events.csv").open(newline="", encoding="utf-8-sig") as source:
        last = -1
        for event in csv.DictReader(source):
            cycle, node, unit, frame = (int(event[k]) for k in ("cycle", "node", "unit", "frame"))
            require(last <= cycle <= metrics["cycles"], "Event cycle order/range mismatch")
            last = cycle
            if event["event"] not in ("launch", "done"):
                continue
            require(node in jobs and jobs[node]["frame"] == frame, "Event node/frame mismatch")
            target = starts if event["event"] == "launch" else done
            require(node not in target, "Duplicate task event")
            target[node] = (cycle, unit)
    require(set(jobs) == set(starts) == set(done), "Missing launch/done events")
    tasks = []
    for node, job in sorted(jobs.items()):
        begin, unit = starts[node]
        end, end_unit = done[node]
        require(unit == end_unit and begin < end, "Task event interval mismatch")
        require(metrics["units"][unit]["kind"] == job["opcode"], "Task incompatible with physical unit class")
        tasks.append(dict(node=node, frame=job["frame"], layer=job["layer"], local_step=job["local_step"],
            opcode=job["opcode"], unit=unit, begin=begin, end=end, elapsed=end - begin, macs=job["macs"]))
    return dict(path=path, data=data, result=result, manifest=manifest, metrics=metrics, output=output, tasks=tasks)


def compare(baseline, candidate, self_test=False):
    baseline, candidate = Path(baseline).resolve(), Path(candidate).resolve()
    require(self_test or baseline != candidate, "Baseline and candidate must be different runs; the same run is allowed only with --self-test")
    base, cand = load_run(baseline, self_test), load_run(candidate, self_test)
    br, cr = base["result"], cand["result"]
    bm, cm = base["metrics"], cand["metrics"]
    manifest = base["manifest"]
    require(br["manifest_sha256"] == cr["manifest_sha256"], "Different input/data manifests: not a controlled comparison")
    require(br["input_pace"] == cr["input_pace"], "Input pacing changed")
    require(br["sram_capacity"] == cr["sram_capacity"], "SRAM capacity changed")
    require(base["output"] == cand["output"], "Baseline/candidate outputs are not elementwise identical")
    if not self_test:
        require(br["pool"] == EXPECTED_BASELINE, "Baseline must be K3=4,K1=2 and other pools one each")
        require(cr["pool"] == EXPECTED_CANDIDATE, "Candidate must be K3=2,K1=4 and other pools one each")
        require(br["exe_sha256"] != cr["exe_sha256"], "A changed physical pool must have a distinct compiled executable")
    bs, cs = br["source_signature"]["sources"], cr["source_signature"]["sources"]
    for source in PROTECTED:
        require(source in bs and source in cs and bs[source] == cs[source], f"Arithmetic/SRAM/control RTL changed: {source}")
    changes = []
    for source in sorted(set(bs) | set(cs)):
        if bs.get(source) != cs.get(source):
            require(source in ALLOWED_SOURCE_CHANGES, f"Unapproved source change outside configuration/build/harness: {source}")
            changes.append(dict(path=source, baseline_sha256=bs.get(source), candidate_sha256=cs.get(source),
                                allowed_role=ALLOWED_SOURCE_CHANGES[source]))
    resource, resource_files = (None, []) if self_test else load_resource_review(bs)
    # Host tool changes affect wall-time, not the hardware-cycle comparison.
    tools = dict(baseline_flags=br["source_signature"].get("flags"), candidate_flags=cr["source_signature"].get("flags"),
        baseline_verilator_sha256=br["source_signature"].get("verilator_sha256"),
        candidate_verilator_sha256=cr["source_signature"].get("verilator_sha256"),
        baseline_runner_sha256=br.get("runner_sha256"), candidate_runner_sha256=cr.get("runner_sha256"))
    cycles_saved = bm["cycles"] - cm["cycles"]
    reduction = cycles_saved / bm["cycles"]
    speedup = bm["cycles"] / cm["cycles"]
    conditional_hz = 100_000_000
    row_summary = []
    pool_rows = []
    for label, run in (("baseline", base), ("candidate", cand)):
        m = run["metrics"]
        row_summary.append(dict(configuration=label, k3=run["result"]["pool"]["K3"], k1=run["result"]["pool"]["K1"],
            cycles=m["cycles"], compute_done_cycle=m["compute_done_cycle"],
            conditional_ms_at_100MHz=m["cycles"] / 100_000,
            conditional_frames_per_second_at_100MHz=4 * conditional_hz / m["cycles"],
            multi_frame_work_cycles=m["multi_frame_work_cycles"], cross_operator_work_cycles=m["cross_operator_work_cycles"],
            input_mac_cycles=m["input_mac_cycles"], actual_macs=m["macs"], checked_bytes=m["checked_bytes"],
            simulation_seconds=m["simulation_seconds"]))
        for opcode in ORDER:
            units = [u for u in m["units"] if u["kind"] == opcode]
            active = sum(u["active_cycles"] for u in units)
            work = sum(u["work_cycles"] for u in units)
            wait = sum(u["arbitration_wait_cycles"] for u in units)
            require(all(0 <= u["work_cycles"] <= u["active_cycles"] <= m["cycles"] and
                        0 <= u["arbitration_wait_cycles"] <= u["active_cycles"] for u in units), "Invalid unit counters")
            pool_rows.append(dict(configuration=label, opcode=opcode, operator=NAMES[opcode], instances=len(units),
                active_cycles=active, work_cycles=work, arbitration_wait_cycles=wait,
                average_busy_fraction=active / (len(units) * m["cycles"]),
                arbitration_wait_per_active=wait / active if active else 0,
                capacity_wait_frame_cycles=m["capacity_wait_by_opcode"][opcode],
                free_pool_wait_frame_cycles=m["scan_wait_by_opcode"][opcode],
                read_bytes=sum(u["read_bytes"] for u in units), write_bytes=sum(u["write_bytes"] for u in units)))
    layer_rows = []
    for label, run in (("baseline", base), ("candidate", cand)):
        grouped = defaultdict(list)
        for task in run["tasks"]:
            grouped[(task["frame"], task["layer"])].append(task)
        for (frame, layer), group in sorted(grouped.items()):
            span = max(t["end"] for t in group) - min(t["begin"] for t in group)
            active = sum(t["elapsed"] for t in group)
            layer_rows.append(dict(configuration=label, frame=frame, layer=layer, span=span,
                                   operator_elapsed_sum=active, interstep_wait=span - active, steps=len(group)))
    out = ROOT / ("build/self_full_compare_test" if self_test else "deliverables/self_cnn_full_optimized")
    docs = out / "SELFTEST_comparison.md" if self_test else ROOT / "docs/self_cnn_full_optimized.md"
    if (out / "provenance.json").exists():
        old = read_json(out / "provenance.json")
        require(old["baseline"] == str(baseline) and old["candidate"] == str(candidate), "Existing comparison belongs to other runs; preserve it first")
    out.mkdir(parents=True, exist_ok=True)
    for label, run in (("baseline", base), ("candidate", cand)):
        dest = out / "evidence" / label
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run["path"] / "result.json", dest / "result.json")
        for name in ("metrics.json", "events.csv", "outputs.bin", "simulation.log", "mac_detail.vcd", "pipeline_detail.vcd"):
            src = run["path"] / "overlap" / name
            if src.exists():
                shutil.copy2(src, dest / name)
        write_csv(out / (label + "_task_events.csv"), run["tasks"])
    shutil.copy2(base["data"] / "manifest.json", out / "evidence/manifest.json")
    for source, name in resource_files:
        dest = out / "evidence/resources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    write_csv(out / "cycle_comparison.csv", row_summary)
    write_csv(out / "pool_comparison.csv", pool_rows)
    write_csv(out / "layer_comparison.csv", layer_rows)
    config = dict(status="SELFTEST_NOT_OPTIMIZATION_EVIDENCE" if self_test else "FULL_RTL_COMPARISON_PASS",
        baseline=dict(run=str(baseline), pool=br["pool"], exe_sha256=br["exe_sha256"], cycles=bm["cycles"]),
        candidate=dict(run=str(candidate), pool=cr["pool"], exe_sha256=cr["exe_sha256"], cycles=cm["cycles"]),
        manifest_sha256=br["manifest_sha256"], input_pace=br["input_pace"], sram_capacity=br["sram_capacity"],
        actual_macs=cm["macs"], checked_bytes=cm["checked_bytes"], commands=cm["commands"],
        output_sha256=manifest["final_expected_sha256"], output_elementwise_equal=True,
        protected_rtl_hashes={k: bs[k] for k in PROTECTED}, allowed_changed_recorded_sources=changes,
        tool_build_records=tools, cycles_saved=cycles_saved, cycle_reduction_fraction=reduction,
        speedup=speedup, conditional_clock_hz=conditional_hz, clock_implemented_verified=False,
        new_full_lut_measurement=False,
        existing_ooc_resource_estimate=resource,
        existing_ooc_resource_review_sha256=sha(ROOT / "build/self_full_pool_review/resource_delta.json") if resource else None)
    write_json(out / "comparison_config.json", config)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "font.size": 10, "figure.facecolor": "white"})
    prefix = "SELFTEST | " if self_test else ""
    def save(fig, name):
        if self_test:
            fig.text(.99, .01, "SELFTEST — NOT OPTIMIZATION EVIDENCE", ha="right", color="#b91c1c", weight="bold")
        fig.savefig(out / name, dpi=160, bbox_inches="tight")
        plt.close(fig)
    labels = [f"原配置 K3×{br['pool']['K3']} / K1×{br['pool']['K1']}",
              f"候选 K3×{cr['pool']['K3']} / K1×{cr['pool']['K1']}"]
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.barh([1, 0], [bm["cycles"], cm["cycles"]], color=["#64748b", "#16a34a"], height=.5)
    for y, row in zip([1, 0], row_summary):
        ax.text(row["cycles"] * 1.015, y, f"{row['cycles']:,} 拍\n{row['conditional_ms_at_100MHz']:.3f} ms @ 假设100MHz", va="center", fontsize=10)
    ax.set(yticks=[1, 0], yticklabels=labels, xlim=(0, max(bm["cycles"], cm["cycles"]) * 1.45), xlabel="四图批次实际 RTL 周期")
    ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
    ax.set_title(prefix + "相同四图、相同输入节奏：算子数量调整前后", loc="left", fontsize=15, pad=16)
    ax.grid(axis="x", alpha=.2)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, .06, 1, 1))
    save(fig, "cycle_comparison.png")

    fig, axes = plt.subplots(2, 1, figsize=(16, 11), sharex=True)
    limit = max(bm["cycles"], cm["cycles"])
    for ax, label, run in zip(axes, labels, (base, cand)):
        for f, frame in enumerate(run["metrics"]["frames"]):
            y = 3 - f
            ax.broken_barh([(frame["input_begin"], frame["input_commit"] - frame["input_begin"])], (y + .22, .1), facecolors="#0f766e")
            for task in run["tasks"]:
                if task["frame"] == frame["frame"]:
                    ax.broken_barh([(task["begin"], task["elapsed"])], (y - .23, .36), facecolors=COLORS[task["opcode"]])
            ax.plot(frame["read_complete"], y - .04, "k|", markersize=14)
        ax.axvline(run["metrics"]["cycles"], color="#64748b", linestyle="--", linewidth=.9)
        ax.set(yticks=[3, 2, 1, 0], yticklabels=[f"frame {r['frame']}" for r in run["metrics"]["frames"]],
               xlim=(0, limit * 1.015), ylim=(-.55, 3.55))
        ax.set_title(prefix + label + f"：每图 {manifest['template_steps']} 步", loc="left", fontsize=14)
        ax.grid(axis="x", alpha=.2)
    axes[-1].set_xlabel("同一硬件周期坐标；每个色段来自实际 launch→done，含内部访存等待")
    axes[-1].ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
    handles = [Patch(color="#0f766e", label="输入区间")] + [Patch(color=COLORS[op], label=NAMES[op]) for op in ORDER]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .015), ncol=7, frameon=False)
    fig.suptitle(prefix + "四图流水：原配置与候选配置共用横轴", fontsize=16, y=.99)
    fig.tight_layout(rect=(0, .07, 1, .97))
    save(fig, "timeline_comparison.png")

    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    for offset, label, color in ((-.18, "baseline", "#64748b"), (.18, "candidate", "#16a34a")):
        rows = [r for r in pool_rows if r["configuration"] == label]
        x = [i + offset for i in range(len(ORDER))]
        axes[0].bar(x, [r["average_busy_fraction"] * 100 for r in rows], .36, color=color,
                    label=labels[0 if label == "baseline" else 1])
        axes[1].bar(x, [r["arbitration_wait_per_active"] * 100 for r in rows], .36, color=color)
    axes[0].set_ylabel("同类实例平均忙碌率 (%)")
    axes[1].set_ylabel("仲裁等待 / active (%)")
    axes[1].set(xticks=list(range(len(ORDER))), xticklabels=[NAMES[op] for op in ORDER])
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False)
    axes[0].set_title(prefix + "算子池忙碌率与 SRAM 仲裁等待", loc="left", fontsize=15, pad=16)
    fig.text(.12, .02, "忙碌率分母包含该池实例数；仲裁计数仅 valid && !ready，不含正常 SRAM 响应等待。", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .06, 1, 1))
    save(fig, "pool_comparison.png")
    gtk_validation = candidate_visuals(out, cand, self_test, plt, save)

    improvement = (f"候选周期减少 **{cycles_saved:,} 拍（{reduction:.2%}）**，批次吞吐加速 **{speedup:.3f}×**。" if cycles_saved >= 0 else
                   f"候选周期增加 **{-cycles_saved:,} 拍（{-reduction:.2%}）**，原配置/候选吞吐比为 **{speedup:.3f}×**；该候选没有改善本轮性能。")
    k1b = next(r for r in pool_rows if r["configuration"] == "baseline" and r["opcode"] == 5)
    k1c = next(r for r in pool_rows if r["configuration"] == "candidate" and r["opcode"] == 5)
    k3b = next(r for r in pool_rows if r["configuration"] == "baseline" and r["opcode"] == 0)
    k3c = next(r for r in pool_rows if r["configuration"] == "candidate" and r["opcode"] == 0)
    table = "\n".join(f"| {label} | {r['k3']} | {r['k1']} | {r['cycles']:,} | {r['conditional_ms_at_100MHz']:.3f} | {r['conditional_frames_per_second_at_100MHz']:.3f} |"
                      for label, r in zip(("原配置", "候选"), row_summary))
    pool_table = "\n".join(f"| {NAMES[op]} | {b['instances']}→{c['instances']} | {b['average_busy_fraction']:.2%}→{c['average_busy_fraction']:.2%} | {b['arbitration_wait_cycles']:,}→{c['arbitration_wait_cycles']:,} | {b['capacity_wait_frame_cycles']:,}→{c['capacity_wait_frame_cycles']:,} |"
                           for op in ORDER for b in pool_rows if b["configuration"] == "baseline" and b["opcode"] == op
                           for c in pool_rows if c["configuration"] == "candidate" and c["opcode"] == op)
    change_text = "记录的源文件哈希没有变化；实例数量由编译参数选择。" if not changes else "\n".join(f"- `{c['path']}`：{c['allowed_role']}；`{c['baseline_sha256']}` → `{c['candidate_sha256']}`。" for c in changes)
    warning = "\n> **SELFTEST：报告脚本自测，允许同一次运行；以下不是算子优化结论。若输入是SMALL，也不是完整网络证据。**\n" if self_test else ""
    architecture_note = ("SELFTEST 不生成完整网络架构图。" if self_test else
                         f"[候选可编辑架构图]({link(out / 'architecture.drawio')}) 沿用完整网络图，只调整 K3 / K1 数量，保留 **16 MiB 仿真容量**表述。")
    gtk_note = (f"已有实际 GTKWave / Tcl 验证 **PASS**：两个候选会话均显示10根唯一信号，本次生成已重新核对当前 `.gtkw` 与 VCD 的 SHA256。详见 [GTKWave 验证证据]({link(out / 'gtkwave_validation.json')}) 和 [波形核验记录]({link(out / 'wave_views.json')})。"
                if gtk_validation['status'] == 'PASS' else
                "尚无与当前会话 / VCD 匹配的实际 GTKWave PASS 证据；`validate_gtkwave.ps1` 可执行验证并写入独立结果。" +
                f"核验状态记录在 [wave_views.json]({link(out / 'wave_views.json')})。")
    k1_mac_fraction = sum(job['macs'] for job in manifest['jobs'] if job['opcode'] == 5) / manifest['total_macs']
    configuration_text = "SELFTEST 只验证报告生成；以下正式候选配置与全网复现说明不在此自测中展开。"
    if not self_test:
        configuration_text = f"""候选真正的 RTL 例化参数是 `K3_UNITS=2`、`K1_UNITS=4`、`POST_UNITS=1`，DW7 / Add / Pad 各固定一套。`self_fixed_network_top` 与运行脚本默认仍保留 K3×4 / K1×2 以兼容历史入口；本候选由 `run_self_full.py --k3 2 --k1 4 --post 1` 显式选择，并将相同数量传给 RTL 和 C++ 校验器。仅查看默认参数不会得到本次候选配置。

选择四套 K1 的依据是该完整网络的 1×1 占 **{k1_mac_fraction:.2%} MAC**，原 K1 池平均忙碌率 **{k1b['average_busy_fraction']:.3%}**。本次固定流程四帧中，每帧至多推进一个当前任务，因此同时可用的 K1 任务最多四个；保留两套 K3 处理普通 3×3 / DW3 并维持跨图流水。此选择针对本次四图负载，收益由上面的完整 RTL 周期比较确认。

在项目根目录执行。若需重做匹配的四项小图 gate，可用：

```powershell
python scripts/run_self_full.py --k3 2 --k1 4 --post 1 --data build/self_full_small --modes overlap serial preloaded stress
```

已有匹配 gate `build/runs/20261023_194655_786340_self_full` 四项 PASS，可直接复用。使用当前候选编译缓存与同一四图完整数据的命令为：

```powershell
python scripts/run_self_full.py --k3 2 --k1 4 --post 1 --reuse --full --data build/self_full_data --gate build/runs/20261023_194655_786340_self_full --modes overlap
```

运行入口会核对编译缓存的源码/工具链签名，以及 gate 的相同可执行文件哈希、配置和四项 PASS；若重新编译改变签名或可执行文件，应改用新匹配 gate。上述是仿真复现与 RTL 参数应用说明，没有进行新的整机综合。"""
    resource_text = "没有附入单核资源估算。"
    if resource:
        old, new, delta = resource["old_4k3_2k1"], resource["candidate_2k3_4k1"], resource["candidate_minus_old"]
        resource_text = f"""已有独立单核 OOC 综合报告按本轮数量相加，**仅六个卷积核**的估算如下：

| 项目 | 原配置 | 候选 | 候选减原配置 |
|---|---:|---:|---:|
| LUT | {old['lut']:,} | {new['lut']:,} | {delta['lut']:+,} |
| FF | {old['ff']:,} | {new['ff']:,} | {delta['ff']:+,} |
| BRAM36 等效 | {old['bram36_equivalent']:g} | {new['bram36_equivalent']:g} | {delta['bram36_equivalent']:+g} |
| DSP48E1 | {old['dsp48e1']} | {new['dsp48e1']} | {delta['dsp48e1']:+} |
| 声明的输入与权重局部缓存 KiB | {old['logical_input_plus_weight_cache_bytes'] / 1024:g} | {new['logical_input_plus_weight_cache_bytes'] / 1024:g} | {delta['logical_input_plus_weight_cache_bytes'] / 1024:+g} |

这不是新的整机综合，不包括 Post / Add / DW7 / Pad、控制、共享 SRAM 与仲裁；集成优化也可能改变相加结果。局部缓存减少不改变共享 SRAM 的 {br['sram_capacity'] / 1048576:g} MiB 地址空间。单核源码和历史报告哈希已核验，详见 [资源证据]({link(out / 'evidence/resources/resource_delta.json')})。

现有历史整体综合曾因 Post 参数 RAM 推断失败而未完成，DW7 权重 RAM 另有可能展开为寄存器的警告；本次没有重新完成整机综合或布局布线。"""
    report = f"""# {'SELFTEST — ' if self_test else ''}完整 MobileFaceNet 四图：算子数量调整对比
{warning}
原配置 **K3×{br['pool']['K3']}、K1×{br['pool']['K1']}**；候选 **K3×{cr['pool']['K3']}、K1×{cr['pool']['K1']}**。Post / Add / DW7 / Pad 均各一套。两轮使用同一份四图数据、固定网络模板、输入节奏和 SRAM 参数，并分别取得真实 RTL PASS。

原配置 **{bm['cycles']:,} 拍**，候选 **{cm['cycles']:,} 拍**。{improvement} 这比较的是同一四图批次端到端周期；不是串行到并行的加速，也不是将短图比例套到全网。

| 配置 | K3 | K1 | 四图实际周期 | 条件时间 ms @100MHz | 条件吞吐 图/s @100MHz |
|---|---:|---:|---:|---:|---:|
{table}

**100MHz 仅用于算术换算，尚无新的全设计布局布线或时序达标证据。** 主机仿真耗时与硬件周期分别记录，编译优化造成的主机加速不当作硬件性能提升。

## 实测图与计数

- [周期比较]({link(out / 'cycle_comparison.png')})、[同轴四图流水前后对比]({link(out / 'timeline_comparison.png')})、[算子池忙碌与仲裁]({link(out / 'pool_comparison.png')})。
- [周期 CSV]({link(out / 'cycle_comparison.csv')})、[各池 CSV]({link(out / 'pool_comparison.csv')})、[逐层 CSV]({link(out / 'layer_comparison.csv')})。
- [候选 MAC 同拍采样]({link(out / 'candidate_mac_detail.png')})、[候选跨类工作采样]({link(out / 'candidate_pipeline_detail.png')})；`open_candidate_mac_detail.cmd` / `open_candidate_pipeline_detail.cmd` 打开候选实际 VCD，会话各含10根物理信号且不重复。横轴是采样窗口相对时间，未记录全局起点，不能当作网络从零开始。
- {architecture_note} {gtk_note} 报告生成本身不启动 GTKWave。

| 算子池 | 实例数 原→候选 | 平均忙碌率 原→候选 | 仲裁等待 实例·拍 原→候选 | 等同类资源 帧·拍 原→候选 |
|---|---:|---:|---:|---:|
{pool_table}

1×1 的累计同类资源等待从 {k1b['capacity_wait_frame_cycles']:,} 变为 {k1c['capacity_wait_frame_cycles']:,} 帧·拍；3×3/DW3 从 {k3b['capacity_wait_frame_cycles']:,} 变为 {k3c['capacity_wait_frame_cycles']:,} 帧·拍。这些真实计数用于判断增加 K1、减少 K3 后等待是否转移，最终收益以总周期实测为准。

平均忙碌率 = 同类 active 总和 /（实例数 × 本轮总周期）。仲裁等待只计 `valid && !ready`，不包含正常 SRAM 响应延迟、逐字节请求的固定开销。排队是各图累计的帧·拍，不能除总周期当作批次占比；有空闲池仍未启动的计数还包含槽释放和调度扫描。任务条 busy 跨度不等同于每拍都在 MAC。

## 相同算术与结果证明

两轮分别完成 **{cm['commands']} 个任务、{cm['macs']:,} 次标量 MAC、{cm['checked_bytes']:,} 个输出字节校验**，各 {cm['allocations']} 次分配/释放及四份外部读取确认。四图输出逐值完全相同，并与独立整数 golden 相同；合计 {len(cand['output'])} 字节 SHA256：`{manifest['final_expected_sha256']}`。

算术 RTL、bai SRAM 及核心调度/租约/固定模板展开 RTL 的记录哈希必须逐一相同，否则脚本拒绝生成本报告。实际中间写请求逐字节比较 golden，后续真实 SRAM 读响应核对；最终结果、只读区和尾部保护经 SRAM 端口读取。没有用软件数值替代算子运行，也不声称所有中间数据都额外完整回读。

结果为每图 {manifest['final_bytes_per_frame']} 个 UINT8 量化分量，采用跨图固定的首图诊断尺度。整数 golden 一致不代表与 FP32 逐值相同，也不代表人脸识别精度验证。

## 应用候选配置与复现

{configuration_text}

## 允许变化的构建 / 测试记录

{change_text}

构建 flags、Verilator 与运行脚本哈希、允许改变文件的前后哈希均写入 [comparison_config.json]({link(out / 'comparison_config.json')})。上述允许项仅是构建/包装/校验范围，不能据此推导算法改变；受保护算术与存储哈希检查始终执行。

## 资源与存储边界

**没有新的完整 LUT 综合结果。** 六个卷积实例的类型分配变了，不能仅按实例总数宣称总 LUT 不变或符合 FPGA 容量。

{resource_text}

两轮均采用 **{br['sram_capacity'] / 1048576:g} MiB 仿真 SRAM**；执行初值 **{manifest['init_bytes']:,} 字节（{manifest['init_bytes'] / 1048576:.3f} MiB）**，四个复用工作区各 {manifest['workspace_bytes']:,} 字节。这不代表 Zynq-7020 片内可容纳，仍需分块/外存和板级资源、时序验证。CPU/UART 固件集成与识别精度不在本次 PASS 范围。

## 原始证据与复现

- 原配置运行：`{baseline}`。
- 候选运行：`{candidate}`。
- 两轮数据 manifest SHA256：`{br['manifest_sha256']}`。
- 原配置 / 候选 metrics、events、outputs、运行签名与日志保存在 [evidence]({link(out / 'evidence')})；输入节奏均为 {br['input_pace']} 拍参数。
- 生成命令：`python scripts/compare_self_full.py --baseline "{baseline}" --candidate "{candidate}"{' --self-test' if self_test else ''}`。
- 正式入口只接受不同运行、4/2→2/4 两种配置、完整网络 PASS；SELFTEST 输出固定隔离在 build 目录。
"""
    (out / "README.md").write_text(report, encoding="utf-8")
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(report, encoding="utf-8")
    provenance = dict(baseline=str(baseline), candidate=str(candidate), self_test=self_test,
        baseline_result_sha256=sha(baseline / "result.json"), candidate_result_sha256=sha(candidate / "result.json"),
        script_sha256=sha(Path(__file__)), docs_sha256=sha(docs),
        files_sha256={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "provenance.json"})
    write_json(out / "provenance.json", provenance)
    print(json.dumps({"status": config["status"], "baseline_cycles": bm["cycles"], "candidate_cycles": cm["cycles"],
        "cycle_reduction_fraction": reduction, "speedup": speedup, "report": str(out / "README.md")}, indent=2))
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true", help="isolate a watermarked rendering check in build; allows same-run/small inputs")
    args = parser.parse_args()
    compare(args.baseline, args.candidate, args.self_test)
