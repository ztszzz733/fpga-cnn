from pathlib import Path
from datetime import datetime
import subprocess,os,json,hashlib
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent;VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_reduced_tile_ram');out.mkdir(parents=True)
sources=[BASE/'storage_v2/rtl/tile_local_ram.sv',SIM/'tb/integration/reduced_tile_ram_main.cpp']
r={'status':'RUNNING','capacity':401408,'words':100352,'sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
try:
 flags=['--cc','--exe','--build','--assert','--no-timing','--top-module','tile_local_ram','-GBYTES=401408','-Wno-fatal','-j','2','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
 with (out/'compile.log').open('w') as f:subprocess.run([str(VR/'bin/verilator'),*flags,*map(str,sources)],env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
 with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vtile_local_ram')],stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
 r['status']='PASS';print((out/'simulation.log').read_text(),flush=True)
except Exception as e:r.update(status='FAIL',error=str(e));raise
finally:(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
