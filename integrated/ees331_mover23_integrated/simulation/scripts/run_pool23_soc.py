"""Bounded single-tile EES331 SoC simulation with real CPU and 23 CNN units.

This still uses the old 128 KiB CNN cache, not storage_v2 DATA MOVER.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
from bootstrap_verilator_native import build_native, native_environment

ROOT=Path(__file__).resolve().parents[1]
CASE=sys.argv[1] if len(sys.argv)>1 else 'short_row_2x2x2'
if CASE not in ('short_row_2x2x2','tile_8x8x32','tile_8x8x32_four_frames','four_frame_all_ops'):raise SystemExit('unknown fixture')
OUT=ROOT/'build/pool23_soc_formal'/CASE
OUT.mkdir(parents=True,exist_ok=True)
listed=[ROOT/line for line in (ROOT/'rtl/filelists/system_ees331.f').read_text().splitlines()
        if line.strip() and not line.startswith('#')]
sources=listed+[ROOT/'tb/ees331_soc_pool23_sim_top.sv']
main=ROOT/'tb/integration/ees331_soc_pool23_main.cpp'
record=dict(status='RUNNING',case=CASE,top='ees331_soc_pool23_sim_top',
            cpu='11.9 merged snapshot, normalized match to origin/moon e298f0c',
            cnn='11.9 EES331 POOL23=1, based on origin/zhang 264883e',
            memory='old datasram_ddr_subsystem cache, NOT new storage_v2 MOVER',
            sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sources+[main,ROOT/'firmware/ees331_cpu/program_ram_probe.mem']})
start=time.monotonic()
try:
    exe=build_native(sources,'ees331_soc_pool23_sim_top',OUT/'compile',main=main,
                     verilator_args=['--no-timing','-DEES331_EXTERNAL_PS',
                                     '--output-split-cfuncs','500'],jobs=2)
    record['compile_seconds']=time.monotonic()-start
    with (OUT/'simulation.log').open('w') as log:
        sim=subprocess.run([str(exe),str(ROOT/'build/fixtures'/CASE),str(OUT)],
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
