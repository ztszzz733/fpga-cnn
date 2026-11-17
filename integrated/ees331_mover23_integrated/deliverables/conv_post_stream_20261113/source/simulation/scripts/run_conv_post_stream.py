"""Isolated real K3/PW8 -> shared affine post streaming and fallback checks."""
from pathlib import Path
from datetime import datetime
import os,subprocess,json,hashlib,time
B=Path(__file__).resolve().parents[2];SIM=B/'simulation';VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
files=[B/p for p in ['rtl/cnn_self/compact_word_ram.sv','rtl/cnn_self/self_pw8_engine.sv','rtl/cnn_self/self_conv_spatial4_engine.sv','rtl/cnn_quant/quant_post_pipe_engine.sv','rtl/cnn_stream/conv_post_pair_engine.sv','simulation/tb/conv_post_stream_top.sv','simulation/tb/integration/conv_post_stream_main.cpp']]
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_conv_post_stream');out.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
j=dict(status='COMPILING',sources={str(p.relative_to(B)):sha(p) for p in files},full_network=False,integrated_scheduler=False)
def save():(out/'result.json').write_text(json.dumps(j,indent=2)+'\n')
save();print(out,flush=True);t=time.monotonic()
try:
 cmd=[str(VR/'bin/verilator'),'--cc','--exe','--build','--trace','--trace-depth','1','--no-timing','--assert','--top-module','conv_post_stream_top','-Wno-fatal','-j','1','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*map(str,files)]
 with (out/'compile.log').open('w') as f:subprocess.run(cmd,cwd=SIM,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,timeout=240,check=True)
 j['compile_seconds']=time.monotonic()-t;j['status']='RUNNING';save();t=time.monotonic()
 with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vconv_post_stream_top'),str(out)],stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
 j['simulation_seconds']=time.monotonic()-t;j['status']='PASS';j['exe_sha256']=sha(out/'obj/Vconv_post_stream_top')
except BaseException as e:j.update(status='FAIL',error=str(e));raise
finally:j['sources_unchanged']=all(sha(B/n)==h for n,h in j['sources'].items());save()
print('PASS conv_post_stream',flush=True)
