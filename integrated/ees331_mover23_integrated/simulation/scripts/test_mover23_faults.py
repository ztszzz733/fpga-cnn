"""Directed fault and recovery check for the real 23-client paged MOVER."""
from pathlib import Path
import hashlib
import json
import subprocess
import time
from bootstrap_verilator_native import build_native, native_environment

SIM=Path(__file__).resolve().parents[1]
BASE=SIM.parent
OUT=SIM/'build/mover23_faults'
OUT.mkdir(parents=True,exist_ok=True)
sources=[BASE/'storage_v2/rtl/tile_local_ram.sv',BASE/'storage_v2/rtl/data_mover.sv',
         BASE/'rtl/cnn_ddr/cnn_paged_mover.sv']
main=SIM/'tb/cnn_paged_mover_fault_main.cpp'
record={'status':'RUNNING','sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sources+[main]}}
start=time.monotonic()
try:
    exe=build_native(sources,'cnn_paged_mover',OUT/'compile',main=main,
                     verilator_args=['--no-timing'],jobs=2)
    with (OUT/'simulation.log').open('w') as log:
        result=subprocess.run([str(exe)],cwd=SIM,env=native_environment(),
                              stdout=log,stderr=subprocess.STDOUT,timeout=30)
    record['returncode']=result.returncode
    record['status']='PASS' if result.returncode==0 and 'PASS mover23 faults' in (OUT/'simulation.log').read_text() else 'FAIL'
    if record['status']!='PASS':raise RuntimeError((OUT/'simulation.log').read_text())
finally:
    record['wall_seconds']=time.monotonic()-start
    (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print((OUT/'simulation.log').read_text())
