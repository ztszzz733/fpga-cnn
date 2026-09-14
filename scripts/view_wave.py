"""Run the small convolution, then open GTKWave with useful signals selected."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if "--image" in sys.argv[1:]:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_tests.py"), "top_smoke", "--waves"],
                   cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "render_wave.py")], cwd=ROOT, check=True)
    print("Waveform PNG images generated. Open build/wave_overview.png or build/wave_mac_detail.png.")
    sys.exit(0)
suite = Path(r"D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite")
viewer = shutil.which(os.environ.get("GTKWAVE", "gtkwave"))
if not viewer and (suite / "bin" / "gtkwave.exe").is_file():
    viewer = str(suite / "bin" / "gtkwave.exe")
if not viewer:
    sys.exit("GTKWave not found. Add it to PATH or set GTKWAVE to its executable path.")

subprocess.run([sys.executable, str(ROOT / "scripts" / "run_tests.py"), "top_smoke", "--waves"],
               cwd=ROOT, check=True)
wave = ROOT / "build" / "top_smoke.vcd"
save = ROOT / "build" / "top_smoke.gtkw"
signals = [
    ("28", "clk"), ("28", "rst_n"), ("28", "start"),
    ("28", "core_busy"), ("28", "done"), ("28", "error"),
    ("22", "mmio_rdata[31:0]"), ("22", "controller_state[4:0]"),
    ("28", "mem_read"), ("28", "mem_write"), ("28", "mem_ready"),
    ("22", "mem_addr[31:0]"), ("22", "mem_wdata[31:0]"),
    ("28", "mac_enable"), ("22", "tap[3:0]"),
    ("22", "input_value[7:0]"), ("22", "weight_value[7:0]"),
    ("22", "acc_value[31:0]"), ("22", "output_value[7:0]"),
]
save.write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1400 850\n'
                '[sst_width] 230\n[signals_width] 260\n[sst_expanded] 0\n'
                + "".join(f"@{fmt}\ntb_top_smoke.dut.{name}\n" for fmt,name in signals), encoding="utf-8")
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
        print("If the window does not appear, use: python scripts/view_wave.py --image")
    else:
        sys.exit(f"GTKWave exited ({code}); see {log}")
