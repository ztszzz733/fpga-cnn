"""Arithmetic/protocol checks of compact RAM operators, using production RTL."""
from pathlib import Path
from datetime import datetime
import os,subprocess,json,hashlib,time,sys
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
which=sys.argv[1]
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_compact_'+which);out.mkdir(parents=True)
if which=='k1':
 top='self_pw8_unit_top';cpp='self_pw8_unit_main.cpp';defs=[]
 files=['compact_word_ram.sv','self_conv_engine.sv','self_conv_pipe_engine.sv','self_pw4_overlap_engine.sv','self_pw4_engine.sv','self_pw8_engine.sv']
 sources=[BASE/'rtl/cnn_self'/n for n in files]+[SIM/'tb'/ (top+'.sv'),SIM/'tb/integration'/cpp]
elif which=='k3':
 top='self_k3par4_unit_top';cpp='self_k3par4_unit_main.cpp';defs=['-GK3_TEST=1']
 files=['compact_word_ram.sv','self_conv_wide_engine.sv','self_conv_spatial4_engine.sv','self_conv_pipe_engine.sv','self_pw4_engine.sv','self_pw4_overlap_engine.sv']
 sources=[BASE/'rtl/cnn_self'/n for n in files]+[SIM/'tb'/ (top+'.sv'),SIM/'tb/integration'/cpp]
elif which=='post':
 top='post_group_unit_top';defs=[]
 sources=[BASE/'rtl/cnn_quant/quant_post_engine.sv',BASE/'rtl/cnn_quant/quant_post_pipe_engine.sv',SIM/'tb/post_group_unit_top.sv',SIM/'tb/integration/post_group_unit_main.cpp']
else:raise ValueError(which)
start=time.monotonic();result={'status':'COMPILING','which':which,'sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
save();print(out,flush=True)
try:
 staged=out/'main.cpp'
 staged.write_bytes(sources[-1].read_bytes().replace(b'Vself_optimized_unit_top',b'Vself_k3par4_unit_top').replace(b'Vpost_pipe_unit_top',b'Vpost_group_unit_top'))
 compile_sources=sources[:-1]+[staged]
 flags=['--cc','--exe','--build','--no-timing','--assert','--top-module',top,'-Wno-fatal','-j','2','--output-split-cfuncs','500','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20'+(' -DCNN_K3_TEST' if which=='k3' else ''),'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']+defs
 with (out/'compile.log').open('w') as f:subprocess.run([str(VR/'bin/verilator'),*flags,*map(str,compile_sources)],cwd=SIM,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
 result['compile_seconds']=time.monotonic()-start;save();start=time.monotonic()
 with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj'/('V'+top)),str(out/'metrics.json')],stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
 result['simulation_seconds']=time.monotonic()-start;result['status']='PASS'
except Exception as e:result.update(status='FAIL',error=str(e));raise
finally:save()
print('PASS '+which,flush=True)
