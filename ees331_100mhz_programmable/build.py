"""Recreate the complete EES331 Vivado project and run synthesis."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
VARIANT = "simple_cnn_bank256_page_write"
BUILD_FILES = (
    "build.tcl", "create_board.tcl", "ps_preset.tcl", "logic_opt_post.tcl",
    "timing_closure", "local_kib.txt", "k1_units.txt",
    "source/firmware/ees331_cpu/program.mem",
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Path to a new Vivado build directory")
    parser.add_argument("--vivado", default="vivado", help="Vivado on PATH or absolute path to its executable")
    parser.add_argument("--implement", action="store_true", help="Also run placement, routing and timing checks")
    args = parser.parse_args()
    vivado = shutil.which(args.vivado)
    if vivado is None:
        parser.error("Vivado was not found. Pass --vivado with the full executable path.")
    vivado = str(Path(vivado).resolve())

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = ROOT / VARIANT / "soc.f"
    sources = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    files = [*BUILD_FILES, manifest.relative_to(ROOT)]
    files.extend((manifest.parent / name).resolve().relative_to(ROOT) for name in sources)
    for relative in dict.fromkeys(files):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    temp = out / "temp"
    temp.mkdir()
    env = dict(os.environ, EES331_CNN_VARIANT="bank256_page_write",
               XILINX_LOCAL_USER_DATA="no", TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    if os.name == "nt":
        windows = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
        env.setdefault("SystemRoot", windows)
        env.setdefault("windir", windows)
        env.setdefault("ComSpec", str(Path(windows) / "System32" / "cmd.exe"))
        env.setdefault("PROCESSOR_ARCHITECTURE", "AMD64")

    stages = [
        ("ps", "create_board.tcl", [out / "source", out / "project", out / "ps_preset.tcl"],
         "EES331_PS_BD_COMPLETE"),
        ("synth", "build.tcl", ["synth", out], "EES331_STAGE_COMPLETE synth"),
    ]
    def run_stage(stage, script, arguments, marker):
        command = [vivado, "-mode", "batch", "-nojournal", "-log", str(out / f"{stage}.log"),
                   "-source", str(out / script), "-tclargs", *map(str, arguments)]
        log = out / f"{stage}_console.log"
        print(f"{stage}: {log}", flush=True)
        with log.open("wb") as stream:
            result = subprocess.run(command, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT)
        output = log.read_bytes()
        if not result.returncode and any(line.startswith(marker.encode("ascii")) for line in output.splitlines()):
            return True
        if stage == "impl" and b"Routed timing failed; see timing_summary.rpt" in output:
            return False
        raise SystemExit(f"Vivado stage {stage} did not complete. See {log}")

    for stage in stages:
        run_stage(*stage)

    if args.implement:
        implementation = "impl"
        if not run_stage(implementation, "build.tcl", [implementation, out], "EES331_STAGE_COMPLETE impl"):
            implementation = "impl_timing"
            run_stage(implementation, "build.tcl", [implementation, out], "EES331_STAGE_COMPLETE impl_timing")

    print(f"Vivado project: {out / 'project/ees331_ddr.xpr'}")
    print(f"Synthesis timing: {out / 'synth/timing_summary.rpt'}")
    if args.implement:
        print(f"Implementation timing: {out / implementation / 'timing_summary.rpt'}")

if __name__ == "__main__":
    main()
