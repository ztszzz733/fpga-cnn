"""Build the routed-board RTL with modeled PS AXI/DDR and run the ARM schedule."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
BOARD = HERE.parent
REPO = BOARD / "source"
REFERENCE = Path("D:/zhang/fpga-cnn/cpu_control (2)/cpu_control")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_tools(toolchain, msvc):
    helper = REPO / "simulation/scripts/bootstrap_verilator_native.py"
    spec = importlib.util.spec_from_file_location("verilator_build", helper)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    native.VERILATOR_ROOT = toolchain
    native.VERILATOR = toolchain / "bin/verilator_bin.exe"
    native.VCVARS = msvc / "VC/Auxiliary/Build/vcvars64.bat"
    native.CMAKE = msvc / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
    native.NINJA = msvc / "Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe"

    def native_environment():
        # cmd /u encodes its own "set" output as UTF-16, but vcvars may
        # emit diagnostics in another encoding on stderr.
        proc = subprocess.run(f'cmd.exe /u /d /s /c ""{native.VCVARS}" >nul && set"',
                              stdout=subprocess.PIPE, check=True)
        environment = dict(os.environ)
        for line in proc.stdout.decode("utf-16-le").splitlines():
            if "=" in line and not line.startswith("="):
                key, value = line.split("=", 1)
                environment[key] = value
        path_name = next(key for key in environment if key.upper() == "PATH")
        environment[path_name] = str(Path(sys.executable).parent) + os.pathsep + environment[path_name]
        environment["VERILATOR_ROOT"] = toolchain.as_posix()
        environment["VSLANG"] = "1033"
        return environment

    native.native_environment = native_environment
    return native


def compile_sim(source, output, toolchain, msvc, fclk):
    native = native_tools(toolchain, msvc)
    make = REPO / "simulation/tb/ees331_soc_reduced_sim_top.sv"
    wrapper = make.read_text(encoding="utf-8")
    # The upstream observation wrapper has the same 10 units and memory
    # geometry as the board build. Select the board's mailbox ROM.
    if (source.parent / "k1_units.txt").read_text().strip() != "4" or (source.parent / "local_kib.txt").exists():
        raise ValueError("Expected the four-PW8 board and default 392 KiB memory")
    wrapper = wrapper.replace("program_ram_probe.mem", "program.mem")
    debug_top = output / "ees331_soc_reduced_sim_top.sv"
    debug_top.write_text(wrapper, encoding="utf-8")
    manifest = json.loads((source.parent / "source_sha256.json").read_text(encoding="utf-8-sig"))
    for relative, expected in manifest.items():
        if sha(source / relative) != expected:
            raise ValueError(f"Board build snapshot changed: {relative}")
    sources = [
        source / line.strip()
        for line in (source / "rtl/filelists/system_ees331_reduced.f").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    (output / "rtl_sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return native.build_native(
        sources + [debug_top], "ees331_soc_reduced_sim_top", output / "compile",
        main=HERE / "simulate.cpp",
        verilator_args=["--no-timing", "-DEES331_EXTERNAL_PS", "--output-split", "12000",
                        "--output-split-cfuncs", "500"],
        jobs=4, cpp_defines=[f"SIM_FCLK_MHZ={fclk}"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO)
    parser.add_argument("--fixture", type=Path, default=HERE / "fixture")
    parser.add_argument("--output", type=Path, default=HERE / "simulation_bank2")
    parser.add_argument("--toolchain", type=Path, default=REFERENCE / ".tools/verilator-native/verilator")
    parser.add_argument("--msvc", type=Path, default=Path("D:/visual studio2"))
    parser.add_argument("--fclk", type=int, default=100, choices=(100,))
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--wave-only", action="store_true", help="Capture the first PW8 memory response and following handshakes")
    args = parser.parse_args()
    source, fixture, output = (path.resolve() for path in (args.source, args.fixture, args.output))
    output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    executable = (output / "compile/cppbuild/sim.exe" if args.reuse else
                  compile_sim(source, output, args.toolchain, args.msvc, args.fclk))
    compiled = time.monotonic()
    print(f"Running {executable}", flush=True)
    environment = dict(os.environ)
    if args.wave_only:
        environment['EES331_WAVE_ONLY'] = '1'
    with (output / "sim.log").open("w") as log:
        subprocess.run([str(executable), str(fixture), str(output)], cwd=source,
                       env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    if args.wave_only:
        if 'WAVE_CAPTURE COMPLETE' not in (output / 'sim.log').read_text():
            raise RuntimeError('Handshake waveform capture did not complete')
        (output / 'wave_capture.json').write_text(json.dumps({
            'status': 'CAPTURED', 'fclk_mhz': args.fclk, 'cycles_captured': 512,
            'rtl_manifest_sha256': sha(source.parent / 'source_sha256.json'),
            'plan_sha256': sha(fixture / 'PLAN.BIN'), 'harness_sha256': sha(HERE / 'simulate.cpp'),
            'note': 'Partial observation run; full functional result is in simulation_100/result.json'
        }, indent=2) + '\n')
        print('WAVE_CAPTURE COMPLETE', flush=True)
        return
    received = output / "outputs.bin"
    if (fixture / "expected_results.bin").read_bytes() != received.read_bytes():
        raise RuntimeError("Final output mismatch")
    result = json.loads((output / "metrics.json").read_text())
    result.update(compile_seconds=compiled - start,
                  fclk_mhz=args.fclk,
                  simulation_seconds=time.monotonic() - compiled, outputs_sha256=sha(received),
                  plan_sha256=sha(fixture / "PLAN.BIN"),
                  scheduler_sha256=sha(HERE / "schedule.c"),
                  harness_sha256=sha(HERE / "simulate.cpp"),
                  cpu_model="Native execution of common ARM scheduling code; AXI GP0/DDR modeled",
                  rtl="Board RISC-V ROM/core, CNN, page RAM and HP0 mover")
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
