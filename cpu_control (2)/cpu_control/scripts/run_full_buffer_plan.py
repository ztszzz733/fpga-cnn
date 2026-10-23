"""Verify full graph control against real RTL; operators are latency models."""
import argparse,hashlib,json,os,shutil,time
from pathlib import Path
from run_tests import ROOT,execute
from validate_buffer_plan import validate
def main():
 p=argparse.ArgumentParser();p.add_argument('data',type=Path);a=p.parse_args();out=a.data.resolve()
 stage=ROOT.parents[1]/'.network_output_build/full_plan_test';stage.mkdir(parents=True,exist_ok=True)
 vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
 src=[ROOT/'rtl/cnn_quant'/n for n in ['network_dispatch_buffered.sv','network_buffer_leases.sv','network_result_handoff.sv']]+[ROOT/'tb/integration/tb_full_buffer_plan.sv']
 r=dict(status='RUNNING',scope='control only; no operator arithmetic',hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in src+[out/n for n in ['commands.hex','leases.hex','results.hex','jobs.bin','memory.bin']]});start=time.perf_counter()
 try:
  r['static_validation']=validate(out)
  for f in src:shutil.copyfile(f,stage/f.name)
  execute([vr/'bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','2','--top-module','tb_full_buffer_plan','--Mdir',stage/'obj',
   '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3',*[stage/f.name for f in src]],stage,env,out/'control_compile.log',timeout=120)
  r['compile_seconds']=time.perf_counter()-start;stamp=time.perf_counter()
  execute([stage/'obj/Vtb_full_buffer_plan'],out,env,out/'control_sim.log',timeout=60)
  r['simulation_seconds']=time.perf_counter()-stamp;r['status']='PASS'
 except Exception as e:r['status']='FAIL';r['error']=str(e)
 r['total_seconds']=time.perf_counter()-start;(out/'control_result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
