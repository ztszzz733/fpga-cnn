from pathlib import Path
from datetime import datetime
import json,subprocess,hashlib,os,time
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_cache_read_pressure');out.mkdir(parents=True)
sources=[BASE/'rtl/cnn_ddr/cnn_paged_mover.sv',BASE/'storage_v2/rtl/data_mover.sv',BASE/'storage_v2/rtl/tile_local_ram.sv',SIM/'tb/integration/cache_read_pressure.cpp']
r={'status':'COMPILING','kind':'Synthetic requests, not image inference; current production RTL and 392 KiB RAM','sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[SIM/'tb/integration/ees331_axi_mover_model.hpp']}}
def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
save();print(out,flush=True);start=time.monotonic()
try:
 flags=['--cc','--exe','--build','--assert','--no-timing','--top-module','cnn_paged_mover','-GCLIENTS=12','-GLOCAL_BYTES=401408','-Wno-fatal','-j','2','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
 with (out/'compile.log').open('w') as f:subprocess.run([str(VR/'bin/verilator'),*flags,*map(str,sources)],env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
 with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vcnn_paged_mover'),str(out/'metrics.json')],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
 r['status']='PASS';r['metrics']=json.loads((out/'metrics.json').read_text());print((out/'simulation.log').read_text(),flush=True)
except Exception as e:r.update(status='FAIL',error=str(e));raise
finally:r['seconds']=time.monotonic()-start;save()
