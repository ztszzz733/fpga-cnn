"""Compile independent Icarus benches; full regression generates NumPy golden data."""
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
parser.add_argument("--waves", action="store_true", help="write build/mobilefacenet.vcd or build/task_queue.vcd for the selected integration bench")
parser.add_argument("--task-limit", type=int, default=0, help="run first N integration tasks; 0=all")
parser.add_argument("--tasks", help="use an exported tasks.txt instead of built-in vectors")
parser.add_argument("--queue-dir", help="use a directory produced by pack_queue.py")
parser.add_argument("--prefetch-depth", type=int, default=4, help="queue descriptor FIFO depth (>=1)")
parser.add_argument("--ram-bytes", type=int, default=262144, help="simulation RAM size")
args = parser.parse_args()
if args.prefetch_depth<1:parser.error("--prefetch-depth must be >=1")
if args.waves and (not args.tests or any(n.removeprefix("tb_") not in ("mobilefacenet","task_queue") for n in args.tests)):
    parser.error("--waves requires explicit mobilefacenet or task_queue test names")
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
stage_order = ['accelerator_regs', 'mac_unit', 'conv_engine', 'depthwise_conv_engine', 'conv1x1',
               'relu6_unit', 'add_unit', 'quantizer', 'address_generator', 'buffers',
               'accelerator_mem_if', 'mobilefacenet_controller', 'task_descriptor_fifo', 'task_descriptor_reader',
               'top_smoke', 'mobilefacenet', 'task_queue']
benches = [ROOT / "tb" / f"tb_{n.removeprefix('tb_')}.sv" for n in (args.tests or stage_order)]
if any(b.stem=='tb_mobilefacenet' for b in benches) and not args.tasks:
    subprocess.run([sys.executable,str(ROOT/'scripts'/'generate_vectors.py')],cwd=ROOT,check=True)
if any(b.stem=='tb_task_queue' for b in benches) and not args.queue_dir:
    subprocess.run([sys.executable,str(ROOT/'scripts'/'generate_queue_vectors.py')],cwd=ROOT,check=True)
for bench in benches:
    output = build / (bench.stem + ".vvp")
    command = [tool, "-g2012", "-Wall", "-s", bench.stem, "-o", str(output)]
    if bench.stem=='tb_mobilefacenet':
        command += [f'-Ptb_mobilefacenet.RAM_BYTES={args.ram_bytes}']
    if bench.stem=='tb_task_queue':
        command += [f'-Ptb_task_queue.RAM_BYTES={args.ram_bytes}',f'-Ptb_task_queue.PREFETCH_DEPTH={args.prefetch_depth}']
    command += [str(p) for p in sorted((ROOT / "rtl").glob("*.sv"))]
    command += [str(p) for p in sorted((ROOT / "tb").glob("model_*.sv"))] + [str(bench)]
    log = []
    with (build / (bench.stem + ".log")).open("w", encoding="utf-8") as log_file:
        runtime_args=(["+vcd"] if args.waves else [])
        if bench.stem=='tb_mobilefacenet':
            runtime_args += [f'+limit={args.task_limit}']
            if args.tasks:runtime_args += [f'+tasks={Path(args.tasks).resolve().as_posix()}']
        if bench.stem=='tb_task_queue' and args.queue_dir:
            runtime_args += [f'+queue_dir={Path(args.queue_dir).resolve().as_posix()}']
        for cmd in (command, [vvp, str(output)] + runtime_args):
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
