"""Run the address-driven self-CNN with actual arithmetic and bai SRAM RTL.

Full runs require the same executable to have passed the small four-frame gate.
No reference tensor is used as a memory responder or injected into an operator.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time

from bootstrap_verilator_native import build_native, VERILATOR

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".self_full_native"
FILELIST = ROOT / "rtl/filelists/cnn_self_stream.f"
MAIN = ROOT / "tb/integration/self_full_main.cpp"
FLAGS = ["--no-timing", "-DSYNTHESIS", "--output-split-cfuncs", "500"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p: Path, value: dict) -> None:
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sources() -> list[Path]:
    return [ROOT / line.strip() for line in FILELIST.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")] + [ROOT / "tb/self_full_sim_top.sv"]


def build(reuse: bool, k3: int, k1: int, post: int) -> tuple[Path, dict]:
    src = sources()
    tracked = src + [MAIN, FILELIST, ROOT / "scripts/bootstrap_verilator_native.py"]
    flags = FLAGS + [f"-GK3_UNITS={k3}", f"-GK1_UNITS={k1}", f"-GPOST_UNITS={post}"]
    defines = [f"CNN_K3={k3}", f"CNN_K1={k1}", f"CNN_POST={post}"]
    target = BUILD / f"k3_{k3}_k1_{k1}_post_{post}"
    signature = {"sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in tracked},
                 "verilator_sha256": sha(VERILATOR), "flags": flags, "cpp_defines": defines,
                 "toolchain": json.loads((ROOT / ".tools/verilator-native/SOURCE.json").read_text())}
    stamp = target / "signature.json"
    exe = target / "cppbuild/sim.exe"
    if reuse:
        old = json.loads(stamp.read_text())
        if old["signature"] != signature or old["exe_sha256"] != sha(exe):
            raise RuntimeError("Compiled simulation differs from source/toolchain signature; rebuild required")
        return exe, old
    start = time.perf_counter()
    exe = build_native(src, "self_full_sim_top", target, main=MAIN, verilator_args=flags, jobs=4, cpp_defines=defines)
    value = {"signature": signature, "exe_sha256": sha(exe), "compile_seconds": time.perf_counter()-start}
    save(stamp, value)
    return exe, value


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "build/self_full_small")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--gate", type=Path)
    ap.add_argument("--k3", type=int, choices=range(1, 5), default=4)
    ap.add_argument("--k1", type=int, choices=range(1, 5), default=2)
    ap.add_argument("--post", type=int, choices=range(1, 5), default=1)
    ap.add_argument("--modes", nargs="+", choices=["overlap", "serial", "preloaded", "stress"],
                    default=["overlap", "serial", "preloaded", "stress"])
    ap.add_argument("--pace", type=int, default=80, help="minimum clocks between 4-byte input transfers")
    ap.add_argument("--timeout", type=int, default=86400)
    args = ap.parse_args()
    if args.pace < 0:
        ap.error("pace must be nonnegative")
    pool = {"K3": args.k3, "K1": args.k1, "Post": args.post, "Add": 1, "DW7": 1, "Pad": 1}
    exe, compiled = build(args.reuse, args.k3, args.k1, args.post)
    if args.build_only:
        print(json.dumps({"exe": str(exe), "compile_seconds": compiled["compile_seconds"]}))
        return
    data = args.data.resolve()
    manifest = json.loads((data / "manifest.json").read_text())
    if bool(manifest["full_network"]) != args.full:
        raise RuntimeError("Full data requires --full; --full cannot label a reduced graph")
    for name, digest in manifest["files_sha256"].items():
        if sha(data / name) != digest:
            raise RuntimeError("Fixture hash mismatch: " + name)
    if args.full:
        if not args.gate:
            raise RuntimeError("Full arithmetic requires --gate with passed small four-frame results")
        gate = json.loads((args.gate / "result.json").read_text())
        required = {"overlap", "serial", "preloaded", "stress"}
        if (gate["status"] != "PASS" or gate["full_network"] or gate["frames"] != 4 or
                gate["exe_sha256"] != compiled["exe_sha256"] or gate["pool"] != pool or
                not required.issubset(gate["scenarios"])):
            raise RuntimeError("Gate is not the matching complete small four-frame regression")
    out = ROOT / "build/runs" / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_self_full")
    out.mkdir(parents=True)
    result = {"status": "RUNNING", "full_network": args.full, "frames": manifest["frames"],
              "run": str(out), "data": str(data), "manifest_sha256": sha(data / "manifest.json"),
              "exe_sha256": compiled["exe_sha256"], "source_signature": compiled["signature"],
              "compile_seconds": 0 if args.reuse else compiled["compile_seconds"],
              "pool": pool,
              "exe_path": str(exe),
              "sram_capacity": 16777216, "input_pace": args.pace, "scenarios": {},
              "started_at": datetime.now().isoformat(), "runner_sha256": sha(Path(__file__))}
    save(out / "result.json", result)
    print("RUN " + str(out), flush=True)
    started = time.perf_counter()
    try:
        for mode in args.modes:
            dest = out / mode
            dest.mkdir()
            result["active_mode"] = mode
            save(out / "result.json", result)
            command = [str(exe), str(data), str(dest), mode, str(args.pace)]
            begin = time.perf_counter()
            with (dest / "simulation.log").open("w") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                result["simulation_pid"] = process.pid
                save(out / "result.json", result)
                try:
                    code = process.wait(timeout=args.timeout)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
            if code:
                raise RuntimeError(f"{mode} failed ({code}); see {dest / 'simulation.log'}")
            metrics = json.loads((dest / "metrics.json").read_text())
            digest = sha(dest / "outputs.bin")
            if (metrics["status"] != "PASS" or metrics.get("pool") != pool or metrics["commands"] != manifest["total_tasks"] or
                    metrics["macs"] != manifest["total_macs"] or digest != manifest["final_expected_sha256"]):
                raise RuntimeError("Final numerical/coverage/MAC/hash mismatch in " + mode)
            result["scenarios"][mode] = {"metrics": metrics, "outputs_sha256": digest,
                                          "wall_seconds": time.perf_counter()-begin}
            save(out / "result.json", result)
            print(f"PASS {mode}: {metrics['cycles']} cycles, {metrics['commands']} tasks", flush=True)
        result["status"] = "PASS"
    except BaseException as exc:
        result["status"] = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAIL"
        result["error"] = str(exc)
        raise
    finally:
        result["wall_seconds"] = time.perf_counter()-started
        result["finished_at"] = datetime.now().isoformat()
        result.pop("simulation_pid", None)
        result.pop("active_mode", None)
        save(out / "result.json", result)
    print("PASS RUN " + str(out), flush=True)


if __name__ == "__main__":
    main()
