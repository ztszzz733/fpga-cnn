"""Compile and run independent Icarus testbenches; no third-party Python modules."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("tests", nargs="*", help="bench names without tb_ prefix; default all")
parser.add_argument("--iverilog", default=os.environ.get("IVERILOG", "iverilog"))
parser.add_argument("--vvp", default=os.environ.get("VVP", "vvp"))
parser.add_argument("--timeout", type=int, default=1800, help="seconds per compile/simulation")
parser.add_argument("--waves", action="store_true", help="write VCD for top_smoke or cnn_accelerator")
args = parser.parse_args()
if args.waves and (not args.tests or any(n.removeprefix("tb_") not in ("top_smoke", "cnn_accelerator") for n in args.tests)):
    parser.error("--waves requires explicit top_smoke and/or cnn_accelerator test names")
tool = shutil.which(args.iverilog)
if not tool:
    local = Path(r"D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite\bin\iverilog.exe")
    if local.is_file():
        tool = str(local)
if not tool:
    sys.exit("Icarus not found. Set IVERILOG or pass --iverilog path.")
vvp = shutil.which(args.vvp) or str(Path(tool).with_name("vvp.exe" if os.name == "nt" else "vvp"))
env = dict(os.environ)
env["PATH"] = os.pathsep.join([str(Path(tool).parent), str(Path(tool).parent.parent / "lib"), env.get("PATH", "")])
build = ROOT / "build"
build.mkdir(exist_ok=True)
stage_order = ["accelerator_regs", "relu_unit", "quantizer", "mac_unit", "maxpool_unit",
               "buffers", "address_generator", "accelerator_mem_if", "cnn_controller",
               "top_smoke", "cnn_accelerator"]
benches = [ROOT / "tb" / f"tb_{n.removeprefix('tb_')}.sv" for n in (args.tests or stage_order)]
if any(b.stem == "tb_cnn_accelerator" for b in benches):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_vectors.py")], check=True, cwd=ROOT)
for bench in benches:
    output = build / (bench.stem + ".vvp")
    command = [tool, "-g2012", "-Wall", "-s", bench.stem, "-o", str(output)]
    command += [str(p) for p in sorted((ROOT / "rtl").glob("*.v"))]
    command += [str(p) for p in sorted((ROOT / "tb").glob("model_*.sv"))] + [str(bench)]
    log = []
    with (build / (bench.stem + ".log")).open("w", encoding="utf-8") as log_file:
        for cmd in (command, [vvp, str(output)] + (["+vcd"] if args.waves else [])):
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            def stream_output():
                for line in proc.stdout:
                    log.append(line)
                    log_file.write(line)
                    log_file.flush()
                    print(line, end="", flush=True)
            reader = threading.Thread(target=stream_output, daemon=True)
            reader.start()
            try:
                proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                reader.join()
                message = f"TIMEOUT after {args.timeout}s: {bench.stem}; partial output preserved.\n"
                log_file.write(message)
                print(message, end="", flush=True)
                sys.exit(1)
            reader.join()
            if proc.returncode:
                print(f"FAILED ({proc.returncode}): {cmd[0]}", flush=True)
                sys.exit(proc.returncode)
    if f"PASS {bench.stem}" not in "".join(log):
        sys.exit(f"Missing PASS marker: {bench.stem}")
print(f"PASS: {len(benches)} testbench(es)")
