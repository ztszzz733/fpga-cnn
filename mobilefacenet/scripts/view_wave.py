"""Open the MobileFaceNet VCD with relevant signals already selected."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image',action='store_true')
parser.add_argument('--vcd',type=Path,help='open an existing VCD without generating data')
parser.add_argument('--scope',default='tb_mobilefacenet.dut',help='DUT hierarchy for signal selection')
args=parser.parse_args()
if args.image and args.vcd:parser.error('For custom input images, run custom_wave.py instead.')
if args.image:parser.error('Use accelerator_wave.py --open; image rendering is archived with the old version.')
suite = Path(r"D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite")
viewer = shutil.which(os.environ.get("GTKWAVE", "gtkwave"))
if not viewer and (suite / "bin" / "gtkwave.exe").is_file():
    viewer = str(suite / "bin" / "gtkwave.exe")
if not viewer:
    sys.exit("GTKWave not found. Add it to PATH or set GTKWAVE to its executable path.")

wave=args.vcd.resolve() if args.vcd else ROOT/'build'/'mobilefacenet.vcd'
if args.vcd and not wave.is_file():parser.error(f'VCD not found: {wave}')
if not wave.is_file():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_tests.py"), "mobilefacenet", "--task-limit", "1", "--waves"],
                   cwd=ROOT, check=True)
save=wave.with_suffix('.gtkw')
signals = [
    ("28", "clk"), ("28", "rst_n"), ("28", "start"),
    ("28", "core_busy"), ("28", "done"), ("28", "error"),
    ("22", "mmio_rdata[31:0]"),
    ("28", "mem_read"), ("28", "mem_write"), ("28", "mem_ready"),
    ("22", "mem_addr[31:0]"), ("22", "mem_wdata[31:0]"),

]
if args.scope=='tb_task_queue.dut':
    signals += [("28","queue_active"),("22","queue_state[3:0]"),("22","queue_fetched[31:0]"),
                ("22","queue_buffered[31:0]"),("22","queue_completed[31:0]"),
                ("28","exec_start"),("28","exec_done"),("22","task_op[3:0]"),("28","regs.done_sticky")]
with wave.open(encoding='ascii') as header:
    has_array=False
    for line in header:
        if '$scope' in line and 'systolic_path' in line:has_array=True
        if '$enddefinitions' in line:break
if has_array:
    signals=[s for s in signals if s[1] not in ('sv','tap[5:0]','av[7:0]','wv[7:0]','normal_result[31:0]','out_value[7:0]')]
    signals += [('28','array_running'),('22','systolic_path.engine.state[3:0]'),
                ('22','systolic_path.engine.mb[31:0]'),('22','systolic_path.engine.nb[31:0]'),
                ('22','systolic_path.engine.kb[31:0]'),('22','systolic_path.engine.tile.tick[5:0]'),
                ('22','systolic_path.engine.raw[31:0]'),('22','systolic_path.engine.out_value[7:0]')]
save.write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1400 850\n'
                '[sst_width] 230\n[signals_width] 260\n[sst_expanded] 0\n'
                + "".join(f"@{fmt}\n{args.scope}.{name}\n" for fmt,name in signals), encoding="utf-8")
env = dict(os.environ)
tool_root = Path(viewer).resolve().parent.parent
env["PATH"] = os.pathsep.join([str(Path(viewer).parent), str(tool_root / "lib"), env.get("PATH", "")])
if os.name == "nt" and (tool_root / "share" / "gtkwave3").is_dir():
    env["GTK_EXE_PREFIX"] = str(tool_root)
    env["GTK_DATA_PREFIX"] = str(tool_root)
    cache = tool_root / "lib" / "gdk-pixbuf-2.0" / "2.10.0" / "loaders.cache"
    if cache.is_file():
        env["GDK_PIXBUF_MODULE_FILE"] = str(cache)
log = ROOT / "build" / "gtkwave.log"
with log.open("w", encoding="utf-8") as out:
    process = subprocess.Popen([viewer, "-f", str(wave), "-a", str(save),
                                "-4", "do_initial_zoom_fit 1"],
                               cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        print(f"GTKWave process started (PID {process.pid}): {wave}")
        if args.vcd:
            print(f"If no window appears, open this VCD in GTKWave manually: {wave}")

        else:
            print("For the current timing view: python mobilefacenet/scripts/accelerator_wave.py --open")
    else:
        sys.exit(f"GTKWave exited ({code}); see {log}")
