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
parser.add_argument("--queue-experiment", action="store_true", help="capture editable queue outputs and omit deliberate error injections")
parser.add_argument("--overview", action="store_true", help="capture one complete task_queue run with selected whole-accelerator signals")
parser.add_argument("--serial",action="store_true",help="use pre-array serial convolution for an identical-task baseline")
parser.add_argument("--prefetch-depth", type=int, default=4, help="queue issue-window depth (>=1)")
parser.add_argument("--ram-bytes", type=int, default=262144, help="simulation RAM size")
parser.add_argument("--case", choices=('mixed','raw','war','waw','word'),default='mixed',help='concurrent queue fixture')
parser.add_argument("--ram-wait", type=int,default=3,help='RAM wait pattern for concurrent queue tests')
args = parser.parse_args()
if args.serial or args.queue_experiment:
    parser.error('Legacy serial/experiment switches are unsupported; use operator_queue for current scalar engines.')
if args.overview and (args.tests != ['task_queue'] or args.queue_experiment or args.serial or args.waves):
    parser.error('--overview requires task_queue with the default array path, without --waves/--serial/--queue-experiment')
if args.prefetch_depth<1:parser.error("--prefetch-depth must be >=1")
if args.queue_experiment and (args.tests != ['task_queue'] or not args.queue_dir):
    parser.error("--queue-experiment requires task_queue and --queue-dir")
if args.waves and (not args.tests or any(n.removeprefix("tb_") not in ("mobilefacenet","task_queue","concurrent_queue","operator_queue") for n in args.tests)):
    parser.error("--waves requires explicit mobilefacenet, task_queue or concurrent_queue test names")
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
stage_order = ['accelerator_regs', 'systolic_pe', 'systolic_matmul', 'systolic_read_cache',
               'quantizer', 'address_generator',
               'accelerator_mem_if', 'task_descriptor_fifo', 'task_descriptor_reader',
               'shared_array', 'accelerator_mem_arbiter', 'top_smoke', 'queue_only',
               'mobilefacenet', 'task_queue', 'streaming_control', 'concurrent_queue',
               'vector_math','operator_descriptor','operator_control','operator_queue']
benches = [ROOT / "tb" / f"tb_{n.removeprefix('tb_')}.sv" for n in (args.tests or stage_order)]
if any(b.stem=='tb_mobilefacenet' for b in benches) and not args.tasks:
    subprocess.run([sys.executable,str(ROOT/'scripts'/'generate_vectors.py')],cwd=ROOT,check=True)
if any(b.stem=='tb_task_queue' for b in benches) and not args.queue_dir:
    subprocess.run([sys.executable,str(ROOT/'scripts'/'generate_queue_vectors.py')],cwd=ROOT,check=True)
if any(b.stem=='tb_concurrent_queue' for b in benches):
    subprocess.run([sys.executable,str(ROOT/'scripts'/'generate_concurrent_vectors.py')],cwd=ROOT,check=True)
if any(b.stem=='tb_operator_queue' for b in benches) and not args.queue_dir:
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_operator_vectors.py')],cwd=ROOT,check=True)
for bench in benches:
    output = build / (bench.stem + ".vvp")
    command = [tool, "-g2012", "-Wall", "-s", bench.stem, "-o", str(output)]
    if bench.stem=='tb_mobilefacenet':
        command += [f'-Ptb_mobilefacenet.RAM_BYTES={args.ram_bytes}',f'-Ptb_mobilefacenet.USE_SYSTOLIC={int(not args.serial)}']
    if bench.stem=='tb_task_queue':
        command += [f'-Ptb_task_queue.RAM_BYTES={args.ram_bytes}',f'-Ptb_task_queue.PREFETCH_DEPTH={args.prefetch_depth}',
                    f'-Ptb_task_queue.USE_SYSTOLIC={int(not (args.serial or args.queue_experiment))}']
    if bench.stem in ('tb_concurrent_queue','tb_operator_queue'):
        command += [f'-P{bench.stem}.WAIT_CYCLES={args.ram_wait}',f'-P{bench.stem}.PREFETCH_DEPTH={args.prefetch_depth}']
    command += [str(p) for p in sorted((ROOT / "rtl").glob("*.sv"))]
    command += [str(p) for p in sorted((ROOT / "tb" / "support").glob("*.sv"))]
    command += [str(p) for p in sorted((ROOT / "tb").glob("model_*.sv"))] + [str(bench)]
    log = []
    with (build / (bench.stem + ".log")).open("w", encoding="utf-8") as log_file:
        runtime_args=(["+vcd"] if args.waves else [])
        if bench.stem=='tb_mobilefacenet':
            runtime_args += [f'+limit={args.task_limit}']
            if args.tasks:runtime_args += [f'+tasks={Path(args.tasks).resolve().as_posix()}']
        if bench.stem=='tb_task_queue' and args.queue_dir:
            runtime_args += [f'+queue_dir={Path(args.queue_dir).resolve().as_posix()}']
        if bench.stem=='tb_concurrent_queue':runtime_args += [f'+case={args.case}']
        if bench.stem=='tb_operator_queue' and args.queue_dir:
            runtime_args += [f'+folder={Path(args.queue_dir).resolve().as_posix()}','+generic']
        if args.queue_experiment:runtime_args += ['+experiment']
        if args.overview:runtime_args += ['+overview']
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
