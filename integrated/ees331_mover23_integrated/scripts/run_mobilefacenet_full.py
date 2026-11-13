"""WSL, cycle-driven C++ SRAM harness; real RTL operators, sparse control waves."""
import argparse,datetime,hashlib,json,os,shutil,time
from pathlib import Path
from run_tests import ROOT,execute
from run_neureka_benchmark import sources
from cache_neureka_eval import install as install_eval_cache
STAGE=ROOT.parents[1]/'.neureka_full_hier_build'
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--reuse',action='store_true');p.add_argument('--stall',action='store_true');p.add_argument('--timeout',type=int,default=3600)
 a=p.parse_args();out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_mobilefacenet_full');out.mkdir(parents=True)
 print('RUN_DIR='+str(out),flush=True);started=time.perf_counter()
 spec=json.loads((a.data/'workload.json').read_text());result=dict(status='RUNNING',timing_seconds={},data_source=str(a.data),full_network=True,uart=False,cpu=False)
 src=[s for s in sources() if s.name!='tb_neureka_benchmark.sv']+[ROOT/'rtl/cnn_quant'/n for n in ['quant_post_engine.sv','dw7_cached_engine.sv','pad_hwc_engine.sv','quant_network_sequential.sv']]
 cpp=ROOT/'tb/integration/mobilefacenet_full_main.cpp'
 control='`verilator_config\nhier_block -module "neureka_conv_engine"\n'
 key=dict(sources={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src+[cpp]},flags=3,control=control)
 key['includes']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for repo in ['hci','hwpe-stream','hwpe-ctrl'] for f in (ROOT/'third_party'/repo).rglob('*.svh')}
 result['build_inputs']=key;result['data_hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.data.iterdir() if f.is_file()}
 def save():(out/'result.json').write_text(json.dumps(result,indent=2))
 save();STAGE.mkdir(parents=True,exist_ok=True);exe=STAGE/'obj/Vquant_network_sequential';manifest=STAGE/'build_inputs.json'
 vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
 try:
  stamp=time.perf_counter()
  if a.reuse:
   assert exe.exists() and json.loads(manifest.read_text())==key,'stale simulator; rebuild required'
   result['timing_seconds']['compile']=0
  else:
   staged=[]
   for i,s in enumerate(src):
    d=STAGE/f'{i:03}_{s.name}';shutil.copyfile(s,d);staged.append(d)
   for repo in ['hci','hwpe-stream','hwpe-ctrl']:
    for f in (ROOT/'third_party'/repo).rglob('*.svh'):shutil.copyfile(f,STAGE/f.name)
   shutil.copyfile(cpp,STAGE/cpp.name)
   (STAGE/'hierarchy.vlt').write_text(control)
   execute([vr/'bin/verilator','--cc','--exe','--build','--hierarchical','--no-timing','--assert','-Wno-fatal','-O1','-j','2','-CFLAGS','-std=c++20',
    '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2','--top-module','quant_network_sequential','--Mdir',STAGE/'obj','-I'+str(STAGE),STAGE/'hierarchy.vlt',*staged,STAGE/cpp.name],STAGE,env,out/'compile.log',timeout=1800)
   manifest.write_text(json.dumps(key,indent=2));result['timing_seconds']['compile']=time.perf_counter()-stamp
  # Generation/compilation and evaluation-cache identity are separately checked.
  # Existing generated model is reused; no RTL re-Verilation for this adapter.
  cache_start=time.perf_counter()
  result['eval_cache']=install_eval_cache(out)
  result['timing_seconds']['eval_adapter']=time.perf_counter()-cache_start
  result['simulator_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
  save()
  for f in a.data.iterdir():
   if f.is_file():
    assert hashlib.sha256(f.read_bytes()).hexdigest()==result['data_hashes'][f.name],'data changed'
    shutil.copyfile(f,out/f.name)
  stamp=time.perf_counter()
  try:execute([exe,str(spec['descriptor_base']),str(spec['job_count']),str(spec['final_address']),str(spec['final_bytes']),str(int(a.stall))],out,env,out/'sim.log',timeout=a.timeout)
  finally:result['timing_seconds']['simulation']=time.perf_counter()-stamp
  assert 'PASS full network RTL' in (out/'sim.log').read_text()
  result['metrics']=json.loads((out/'metrics.json').read_text());result['output_sha256']=hashlib.sha256((out/'embedding.bin').read_bytes()).hexdigest()
  result['status']='PASS'
 except Exception as e:result['status']='FAIL';result['error']=str(e);print(str(e),flush=True)
 result['timing_seconds']['total']=time.perf_counter()-started;save();print(json.dumps(result.get('metrics',result.get('error'))),flush=True)
 return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
