"""Fast scheduling-only capacity/protocol validation with latency models."""
import hashlib,json,os,time
from pathlib import Path
from run_tests import ROOT,execute
def main():
 out=ROOT/'build/network_parallel_data/full_plan';stage=ROOT.parents[1]/'.network_parallel_build/dispatch_test'
 vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
 src=[ROOT/'rtl/cnn_quant/network_dispatch.sv',ROOT/'tb/integration/tb_network_dispatch.sv'];start=time.perf_counter()
 # No whitespace paths in generated make dependencies.
 stage.mkdir(parents=True,exist_ok=True)
 import shutil
 for f in src:shutil.copyfile(f,stage/f.name)
 r={'status':'RUNNING','scope':'746 commands, latency models only, no arithmetic','hashes':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in src+[out/'commands.hex']}}
 try:
  execute([vr/'bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','2','--top-module','tb_network_dispatch','--Mdir',stage/'obj',
   '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3',*[stage/f.name for f in src]],stage,env,out/'compile.log',timeout=120)
  r['compile_seconds']=time.perf_counter()-start;stamp=time.perf_counter()
  execute([stage/'obj/Vtb_network_dispatch'],out,env,out/'dispatch.log',timeout=30)
  r['simulation_seconds']=time.perf_counter()-stamp;r['status']='PASS'
 except Exception as e:r['status']='FAIL';r['error']=str(e)
 r['total_seconds']=time.perf_counter()-start;(out/'dispatch_result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
