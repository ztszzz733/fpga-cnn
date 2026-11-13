from pathlib import Path
from datetime import datetime
import os,subprocess,json,hashlib,time,sys
SIM=Path(__file__).resolve().parents[1];B=SIM.parent;VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
kind='pw8_addr';top='pw8_addr_top'
sources=[B/'rtl/cnn_self/compact_word_ram.sv',B/'rtl/cnn_self/self_pw8_engine.sv',SIM/'tb/baseline_pw8_addr.sv',SIM/'tb/pw8_addr_top.sv',SIM/'tb/integration/pw8_addr_main.cpp']
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_remaining_'+kind);out.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
j={'status':'COMPILING','kind':kind,'sources':{str(p.relative_to(B)):sha(p) for p in sources},'full_network':False}
def save():(out/'result.json').write_text(json.dumps(j,indent=2)+'\n')
save();print(out,flush=True);t=time.monotonic()
try:
 cmd=[str(VR/'bin/verilator'),'--cc','--exe','--build','--no-timing','--assert','--top-module',top,'-Wno-fatal','-j','1','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*map(str,sources)]
 with (out/'compile.log').open('w') as log:subprocess.run(cmd,cwd=SIM,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=log,stderr=subprocess.STDOUT,timeout=240,check=True)
 j['compile_seconds']=time.monotonic()-t;j['status']='RUNNING';save();t=time.monotonic()
 with (out/'simulation.log').open('w') as log:subprocess.run([str(out/'obj'/('V'+top)),str(out/'metrics.json')],stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
 j['simulation_seconds']=time.monotonic()-t;j['status']='PASS'
except BaseException as e:j.update(status='FAIL',error=str(e));raise
finally:j['sources_unchanged']=all(sha(B/n)==h for n,h in j['sources'].items());save()
print('PASS '+kind,flush=True)
