"""Yosys RTL elaboration/process lowering and structural checks (not place/route)."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
tool = shutil.which(os.environ.get("YOSYS", "yosys"))
fallback = Path(r"D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite\bin\yosys.exe")
if not tool and fallback.is_file():
    tool = str(fallback)
if not tool:
    sys.exit("Yosys not found. Set YOSYS or add it to PATH.")
env = dict(os.environ)
env["PATH"] = os.pathsep.join([str(Path(tool).parent), str(Path(tool).parent.parent / "lib"), env.get("PATH", "")])
build = root / "build"
build.mkdir(exist_ok=True)
script = build / "check_structure.ys"
script.write_text("read_verilog " + " ".join(p.relative_to(root).as_posix() for p in sorted((root / "rtl").glob("*.v"))) +
                  "\nhierarchy -check -top cnn_accelerator_top\nproc\nopt\ncheck -assert\nstat\n", encoding="ascii")
result = subprocess.run([tool, "-Q", "-T", "-s", str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=180)
(build / "structure.log").write_text(result.stdout+result.stderr, encoding="utf-8")
print("\n".join((result.stdout+result.stderr).splitlines()[-45:]))
sys.exit(result.returncode)
