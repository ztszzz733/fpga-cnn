"""Bounded real-CPU/23-CNN SoC simulation through tile RAM and DATA MOVER."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
from bootstrap_verilator_native import build_native, native_environment

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent
CASE=sys.argv[1] if len(sys.argv)>1 else 'short_row_2x2x2'
CASES=('short_row_2x2x2','tile_8x8x32','tile_8x8x32_four_frames','four_frame_all_ops',
       'four_frame_all_ops_k1_bank1','four_frame_all_ops_k1_bank2')
if CASE not in CASES:raise SystemExit('unknown fixture')
K1_BANK={'four_frame_all_ops_k1_bank1':1,'four_frame_all_ops_k1_bank2':2}.get(CASE,0)
OUT=ROOT/'build/mover23_soc'/CASE
OUT.mkdir(parents=True,exist_ok=True)
listed=[BASE/line for line in (BASE/'rtl/filelists/system_ees331_mover23.f').read_text().splitlines()
        if line.strip() and not line.startswith('#')]
sources=listed+[ROOT/'tb/ees331_soc_mover23_sim_top.sv']
main=ROOT/'tb/integration/ees331_soc_mover23_main.cpp'
fixture=ROOT/'build/fixtures'/('four_frame_all_ops' if K1_BANK else CASE)
record=dict(status='RUNNING',case=CASE,top='ees331_soc_mover23_sim_top',
            k1_bank=K1_BANK,
            cpu='11.9 merged snapshot, normalized match to origin/moon e298f0c',
            cnn='11.9 EES331 POOL23=1, based on origin/zhang 264883e',
            memory='cnn_paged_mover: 23 clients -> 32 KiB tile RAM -> storage_v2 DATA MOVER -> AXI3 HP0',
            sources={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sources+[main,ROOT/'tb/integration/ees331_axi_mover_model.hpp',
                     BASE/'rtl/filelists/system_ees331_mover23.f',
                     ROOT/'firmware/ees331_cpu/program_ram_probe.mem']},
            fixture_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(fixture.iterdir()) if p.is_file()})
start=time.monotonic()
try:
    exe=build_native(sources,'ees331_soc_mover23_sim_top',OUT/'compile',main=main,
                     verilator_args=['--no-timing','-DEES331_EXTERNAL_PS',
                                     '--output-split-cfuncs','500'],jobs=2)
    record['compile_seconds']=time.monotonic()-start
    with (OUT/'simulation.log').open('w') as log:
        sim=subprocess.run([str(exe),str(fixture),str(OUT),str(K1_BANK)],
                           cwd=ROOT,env=native_environment(),stdout=log,
                           stderr=subprocess.STDOUT,timeout=180)
    record['simulation_seconds']=time.monotonic()-start-record['compile_seconds']
    record['returncode']=sim.returncode
    text=(OUT/'simulation.log').read_text(errors='replace')
    if sim.returncode or 'PASS EES331' not in text:raise RuntimeError(text[-2000:])
    record['status']='PASS'
    record['output_sha256']=hashlib.sha256((OUT/'outputs.bin').read_bytes()).hexdigest()
except Exception as exc:
    record.update(status='FAIL',error=str(exc))
    raise
finally:
    record['wall_seconds']=time.monotonic()-start
    (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-1200:])
