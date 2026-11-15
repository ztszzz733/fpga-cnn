from pathlib import Path
from datetime import datetime
import subprocess,os,json,time
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_reduced_pager');out.mkdir(parents=True)
sources=[BASE/'rtl/cnn_ddr/cnn_paged_mover.sv',BASE/'storage_v2/rtl/tile_local_ram.sv',BASE/'storage_v2/rtl/data_mover.sv',SIM/'tb/integration/reduced_pager_main.cpp']
cmd=[str(VR/'bin/verilator'),'--cc','--exe','--build','--assert','--no-timing','--top-module','cnn_paged_mover','-GCLIENTS=12','-GLOCAL_BYTES=3072','-Wno-fatal','-j','2','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*map(str,sources)]
record={'status':'RUNNING','capacity':3072,'pages':3}
try:
 with (out/'compile.log').open('w') as f:subprocess.run(cmd,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
 with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vcnn_paged_mover')],stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
 record['status']='PASS';print((out/'simulation.log').read_text(),flush=True)
except Exception as e:record.update(status='FAIL',error=str(e));raise
finally:(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
