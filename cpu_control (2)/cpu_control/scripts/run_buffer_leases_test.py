"""Fast directed lifetime protocol test, no arithmetic approximation claims."""
import hashlib,json,os,shutil,time
from run_tests import ROOT,execute
def main():
 out=ROOT/'build/buffer_leases_test';out.mkdir(exist_ok=True)
 stage=ROOT.parents[1]/'.network_buffered_build/lease_test';stage.mkdir(parents=True,exist_ok=True)
 vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
 sources=[ROOT/'rtl/cnn_quant/network_buffer_leases.sv',ROOT/'tb/integration/tb_network_buffer_leases.sv']
 r=dict(status='RUNNING',hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources});stamp=time.perf_counter()
 try:
  for f in sources:shutil.copyfile(f,stage/f.name)
  execute([vr/'bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','2','--top-module','tb_network_buffer_leases','--Mdir',stage/'obj',
   '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3',*[stage/f.name for f in sources]],stage,env,out/'compile.log',timeout=120)
  r['compile_seconds']=time.perf_counter()-stamp;stamp=time.perf_counter()
  execute([stage/'obj/Vtb_network_buffer_leases'],out,env,out/'sim.log',timeout=30)
  r['simulation_seconds']=time.perf_counter()-stamp;r['status']='PASS'
 except Exception as e:r['status']='FAIL';r['error']=str(e)
 (out/'result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
