"""Run Vivado from a plain temporary path (the parent repo contains '(2)')."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
VIVADO = Path(os.environ.get('VIVADO_BAT', r'D:\Xilinx\2025.2\Vivado\bin\vivado.bat'))
OUT = ROOT / 'build' / 'synth_v2'
OUT.mkdir(parents=True, exist_ok=True)

if not VIVADO.is_file():
    raise FileNotFoundError(VIVADO)
with tempfile.TemporaryDirectory(prefix='storage_v2_') as raw:
    tmp = Path(raw)
    (tmp / 'rtl').mkdir()
    (tmp / 'scripts').mkdir()
    (tmp / 'tb').mkdir()
    for source in (ROOT / 'rtl').glob('*.sv'):
        shutil.copy2(source, tmp / 'rtl' / source.name)
    shutil.copy2(ROOT / 'scripts' / 'synth.tcl', tmp / 'scripts' / 'synth.tcl')
    shutil.copy2(ROOT / 'tb' / 'program_loader_top.sv', tmp / 'tb' / 'program_loader_top.sv')
    selected = sys.argv[1] if len(sys.argv)>1 else ''
    cmd = [str(VIVADO), '-mode', 'batch', '-source', 'scripts/synth.tcl',
           '-tclargs', tmp.as_posix(), (tmp / 'results').as_posix(), selected]
    with (OUT / 'vivado.log').open('w') as log:
        result = subprocess.run(cmd, cwd=tmp, stdout=log, stderr=subprocess.STDOUT)
    if (tmp / 'results').exists():
        shutil.copytree(tmp / 'results', OUT / 'reports', dirs_exist_ok=True)
    if result.returncode:
        tail = (OUT / 'vivado.log').read_text(errors='replace').splitlines()[-20:]
        raise RuntimeError(f'Vivado exit {result.returncode}:\n' + '\n'.join(tail))
    print('PASS Vivado OOC synthesis:', OUT)
