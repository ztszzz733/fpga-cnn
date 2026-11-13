"""Focused MOVER tests on production RTL, compiled under WSL."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib,os,sys,time
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
which=sys.argv[1] if len(sys.argv)>1 else 'burst'
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_mover_speed_'+which);out.mkdir(parents=True)
main=BASE/'storage_v2/tb/data_mover.cpp' if which=='legacy' else SIM/'tb/integration/mover_speed_unit.cpp'
sources=[BASE/'storage_v2/rtl/data_mover.sv',main]
record={'status':'COMPILING','sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'mode':which}
def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
save();start=time.monotonic();print(out,flush=True)
try:
 flags=['--cc','--exe','--build','--no-timing','--assert','--top-module','data_mover','-Wno-fatal','-j','2','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
 if which=='legacy':flags+=['-GMAX_BURST_BEATS=1']
 with (out/'compile.log').open('w') as f:subprocess.run([str(VR/'bin/verilator'),*flags,*map(str,sources)],env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
 record['status']='RUNNING';save()
 with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vdata_mover'),str(BASE/'storage_v2/build/vectors')],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
 record['status']='PASS';print((out/'simulation.log').read_text(),flush=True)
except Exception as e:record.update(status='FAIL',error=str(e));raise
finally:record['seconds']=time.monotonic()-start;save()
