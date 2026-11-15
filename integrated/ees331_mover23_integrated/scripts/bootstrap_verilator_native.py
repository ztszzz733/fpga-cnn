"""Project-local Windows Verilator/MSVC bootstrap; never changes system PATH.

The small PyPI Windows wheel is a third-party packaging of Verilator.  Its
package version is 5.48.0 but its bundled runtime reports 5.49; record both.
Use the bundled executable and headers together, not a system installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / ".tools/verilator-native"
WHEEL = "verilator-5.48.0-py3-none-win_amd64.whl"
URL = "https://files.pythonhosted.org/packages/e1/83/af403e28686d4bdaffe517809fdd77b5c746f3b7953a5880acb60f12e716/" + WHEEL
SHA256 = "e03aad7e023bbe585f909276f3c03af66f7ede72155f8f75fdaf4f1ec8250e09"
VERILATOR_ROOT = DEST / "verilator"
VERILATOR = VERILATOR_ROOT / "bin/verilator_bin.exe"
VS = Path("D:/visual studio2")
VCVARS = VS / "VC/Auxiliary/Build/vcvars64.bat"
CMAKE = VS / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
NINJA = VS / "Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(proxy: str = "http://127.0.0.1:7897") -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / WHEEL
    if not archive.exists() or sha(archive) != SHA256:
        subprocess.run(["curl.exe", "--fail", "--location", "--proxy", proxy,
                        "--retry", "3", "--retry-all-errors", "--connect-timeout", "15",
                        "--max-time", "120", URL, "--output", str(archive)], check=True)
    if sha(archive) != SHA256:
        raise RuntimeError("Wheel differs from pinned PyPI SHA256")
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (DEST / name).resolve().is_relative_to(DEST.resolve()):
                raise RuntimeError("Unsafe archive path")
        z.extractall(DEST)
    provenance = {
        "package": "verilator 5.48.0 (Windows wheel)", "package_url": "https://pypi.org/project/verilator/5.48.0/",
        "package_repository": "https://github.com/dau-dev/verilator-python",
        "upstream_repository": "https://github.com/verilator/verilator",
        "upstream_install_documentation": "https://verilator.org/guide/latest/install-cmake.html",
        "download_url": URL, "sha256": SHA256, "bytes": archive.stat().st_size,
        "binary_version": subprocess.check_output([str(VERILATOR), "--version"], text=True).strip(),
        "runtime_version_header": (VERILATOR_ROOT / "include/verilated_config.h").read_text(),
        "binary_sha256": sha(VERILATOR), "cmake": str(CMAKE), "ninja": str(NINJA), "vcvars": str(VCVARS),
        "notes": "Package says 5.48.0; bundled upstream header says 5.49 development. Matched binary/runtime used together. No global installation.",
    }
    compiler = VS / "VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe"
    provenance["local_toolchain"] = {
        "compiler": {"path": str(compiler), "version": "MSVC 19.44.35215.0 (14.44.35207 directory)", "sha256": sha(compiler)},
        "cmake": {"path": str(CMAKE), "version": subprocess.check_output([str(CMAKE), "--version"], text=True).splitlines()[0], "sha256": sha(CMAKE)},
        "ninja": {"path": str(NINJA), "version": subprocess.check_output([str(NINJA), "--version"], text=True).strip(), "sha256": sha(NINJA)},
        "origin": "Already installed Visual Studio; no compiler download or global modification",
    }
    provenance["runtime_sha256"] = {p.relative_to(VERILATOR_ROOT).as_posix(): sha(p)
                                    for p in sorted((VERILATOR_ROOT / "include").rglob("*")) if p.is_file()}
    (DEST / "SOURCE.json").write_text(json.dumps(provenance, indent=2) + "\n")


def native_environment() -> dict[str, str]:
    """Return process-local x64 MSVC/SDK environment, preserving normal host env."""
    if not VCVARS.exists():
        raise FileNotFoundError(VCVARS)
    # This fixed batch file is read-only; 'set' only reports to this subprocess.
    result = subprocess.run(f'cmd.exe /u /d /s /c ""{VCVARS}" >nul && set"',
                            capture_output=True, encoding="utf-16-le", check=True)
    env = dict(os.environ)
    for line in result.stdout.splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            env[key] = value
    # Windows environment names are case insensitive; avoid duplicate Path/PATH.
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    env[path_key] = str(Path(sys.executable).parent) + os.pathsep + env[path_key]
    env["VERILATOR_ROOT"] = VERILATOR_ROOT.as_posix()
    env["VSLANG"] = "1033"
    return env


def run_logged(args: list[str], cwd: Path, env: dict[str, str], log: Path) -> None:
    with log.open("w") as out:
        out.write(subprocess.list2cmdline(args) + "\n")
        out.flush()
        result = subprocess.run(args, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}), see {log}")


def build_native(sources: list[Path], top: str, build: Path,
                 main: Path | None = None, verilator_args: list[str] | None = None,
                 jobs: int = 4, cpp_defines: list[str] | None = None) -> Path:
    """Verilate RTL, then compile generated C++ with existing MSVC/CMake/Ninja.

    If main is omitted, generate the standard event-driven main (--timing).
    Custom C++ main callers may pass --no-timing for externally clocked RTL.
    This helper does not execute the resulting simulation.
    """
    build = build.resolve()
    build.mkdir(parents=True, exist_ok=True)
    obj = build / "generated"
    env = native_environment()
    args = [str(VERILATOR), "--cc", "--compiler", "msvc", "--top-module", top,
            "--prefix", "V" + top, "--Mdir", str(obj), "-Wno-fatal", "--assert"]
    if main is None:
        args += ["--main", "--timing"]
    args += verilator_args or []
    args += [str(p.resolve()) for p in sources]
    run_logged(args, build, env, build / "verilate.log")
    cpp = sorted(obj.glob("*.cpp"))
    cpp += [VERILATOR_ROOT / "include/verilated.cpp", VERILATOR_ROOT / "include/verilated_threads.cpp"]
    if main is None or "--timing" in (verilator_args or []):
        cpp.append(VERILATOR_ROOT / "include/verilated_timing.cpp")
    if any(a.startswith("--trace") for a in (verilator_args or [])):
        cpp.append(VERILATOR_ROOT / "include/verilated_vcd_c.cpp")
    if main:
        cpp.append(main.resolve())
    lines = ["cmake_minimum_required(VERSION 3.20)", "project(native_verilator_sim LANGUAGES CXX)",
             "set(CMAKE_CXX_STANDARD 20)", "set(CMAKE_CXX_STANDARD_REQUIRED ON)",
             "add_executable(sim", *[f'  "{p.as_posix()}"' for p in cpp], ")",
             f'target_include_directories(sim PRIVATE "{obj.as_posix()}" "{(VERILATOR_ROOT / "include").as_posix()}" "{(VERILATOR_ROOT / "include/vltstd").as_posix()}")',
             "target_compile_definitions(sim PRIVATE VL_TIME_CONTEXT " + " ".join(cpp_defines or []) + ")",
             "target_compile_options(sim PRIVATE /O2 /bigobj /EHsc /wd4100 /wd4127 /wd4244 /wd4267 /wd4324 /wd4389 /wd4456 /wd4459 /wd4702 /wd4804 /wd5054)"]
    (build / "CMakeLists.txt").write_text("\n".join(lines) + "\n")
    run_logged([str(CMAKE), "-S", str(build), "-B", str(build / "cppbuild"), "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_MAKE_PROGRAM={NINJA.as_posix()}"], build, env, build / "configure.log")
    run_logged([str(CMAKE), "--build", str(build / "cppbuild"), "--parallel", str(jobs)], build, env, build / "compile.log")
    return build / "cppbuild/sim.exe"


def smoke() -> None:
    work = DEST / "smoke"
    work.mkdir(parents=True, exist_ok=True)
    source = work / "native_smoke.sv"
    source.write_text('''module native_smoke;
  bit clk = 0;
  logic reset = 1;
  logic [31:0] count;
  logic signed [31:0] sum;
  logic signed [7:0] weight [0:3];
  always #5 clk = !clk;
  initial begin
    weight[0] = -3; weight[1] = 5; weight[2] = -7; weight[3] = 11;
    #12 reset = 0;
    repeat (1000) @(negedge clk);
    if (count !== 1000 || sum !== 753000) $fatal(1, "count=%0d sum=%0d", count, sum);
    $display("NATIVE_VERILATOR_SMOKE PASS cycles=%0d signed_mac=%0d", count, sum);
    $finish;
  end
  always_ff @(posedge clk) begin
    if (reset) begin count <= 0; sum <= 0; end
    else begin count <= count + 1; sum <= sum + $signed({1'b0, count[15:0]}) * weight[count[1:0]]; end
  end
endmodule
''')
    exe = build_native([source], "native_smoke", work, jobs=4)
    run_logged([str(exe)], work, native_environment(), work / "simulation.log")
    result = {"status": "PASS", "exe": str(exe), "exe_sha256": sha(exe), "source_sha256": sha(source),
              "simulation_log": (work / "simulation.log").read_text(), "compiler": str(VS / "VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe")}
    if "NATIVE_VERILATOR_SMOKE PASS" not in result["simulation_log"]:
        raise RuntimeError("Smoke simulation did not report PASS")
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def project_smoke() -> None:
    """Run the existing scalar-reference convolution regression, not a network."""
    from test_self_conv import generate
    work = DEST / "self_conv_unit"
    work.mkdir(exist_ok=True)
    cases = generate(work, 733)
    sources = [ROOT / "rtl/cnn_self/self_conv_engine.sv", ROOT / "tb/self_conv_unit.sv"]
    source_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    started = time.perf_counter()
    exe = build_native(sources, "tb_self_conv_unit", work,
                       verilator_args=["-I" + work.as_posix()], jobs=4)
    compile_seconds = time.perf_counter() - started
    env = native_environment()
    started = time.perf_counter()
    run_logged([str(exe)], work, env, work / "simulation.log")
    simulation_seconds = time.perf_counter() - started
    metrics = json.loads((work / "metrics.json").read_text())
    if "PASS tb_self_conv_unit" not in (work / "simulation.log").read_text():
        raise RuntimeError("Project convolution regression did not pass")
    expected = b"".join(bytes(int(x, 16) for x in (work / f"case_{i:02d}_expected.hex").read_text().split())
                        for i in range(len(cases)))
    if expected != (work / "outputs.bin").read_bytes():
        raise RuntimeError("Project convolution outputs differ from Python reference")
    result = {"status": "PASS", "simulator": "native Windows Verilator/MSVC",
              "compile_seconds": compile_seconds, "simulation_seconds": simulation_seconds,
              "cases": len(cases), "metrics": metrics, "outputs_sha256": sha(work / "outputs.bin"),
              "source_sha256": source_hashes, "exe": str(exe)}
    historical = ROOT / "build/runs/20261023_145746_335613_self_conv_unit/metrics.json"
    if historical.exists():
        result["historical_xsim_metrics_equal"] = metrics == json.loads(historical.read_text())
        result["historical_xsim_metrics_path"] = str(historical)
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--project-smoke", action="store_true")
    options = parser.parse_args()
    if not options.skip_download:
        install(options.proxy)
    if options.smoke:
        smoke()
    elif options.project_smoke:
        project_smoke()
    else:
        print(VERILATOR)
