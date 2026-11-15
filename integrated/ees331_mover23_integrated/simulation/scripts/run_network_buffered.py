"""Reuse hash-verified compiled NEureka RTL as a DPI library, two independent instances.
Only the new dispatch/wrapper/post/DW7/pad/test host are compiled here.
"""
import argparse,datetime,hashlib,json,os,shutil,time
from pathlib import Path
from run_tests import ROOT,execute
STAGE=ROOT.parents[1]/'.network_buffered_build'
BASE=ROOT.parents[1]/'.neureka_full_hier_build'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--reuse',action='store_true');p.add_argument('--reuse-passed',type=Path);a=p.parse_args()
 out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_network_buffered');out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
 start=time.perf_counter();r=dict(status='RUNNING',cases={},timing_seconds={},scope='six ROI frames with synthetic residual, constrained intermediate pool');save=lambda:(out/'result.json').write_text(json.dumps(r,indent=2));save()
 try:
  from validate_buffer_plan import validate
  r['buffer_plan_validation']=validate(a.data);save()
  base=json.loads((BASE/'build_inputs.json').read_text())
  for n,h in {**base['sources'],**base['includes']}.items():assert digest(ROOT/n)==h,'stale library '+n
  wrapper=BASE/'obj/Vneureka_conv_engine/neureka_conv_engine.sv';lib=wrapper.parent/'libneureka_conv_engine.a'
  adapter=wrapper.parent/'neureka_conv_engine.cpp';cache=json.loads((BASE/'eval_cache.json').read_text())
  assert digest(adapter)==cache['cached_wrapper_sha256']
  src=[ROOT/'rtl/cnn_quant'/n for n in ['network_dispatch_buffered.sv','network_buffer_leases.sv','quant_network_buffered.sv','quant_post_engine.sv','dw7_cached_engine.sv','pad_hwc_engine.sv']]
  cpp=ROOT/'tb/integration/network_buffered_main.cpp';inputs={str(f):digest(f) for f in src+[cpp,wrapper,lib,adapter]};r['build_inputs']=inputs
  r['data_hashes']={f.name:digest(f) for f in a.data.iterdir() if f.is_file()};save()
  STAGE.mkdir(exist_ok=True);exe=STAGE/'obj/Vquant_network_buffered';manifest=STAGE/'inputs.json'
  vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr);stamp=time.perf_counter()
  if a.reuse:assert exe.exists() and json.loads(manifest.read_text())==inputs,'stale parallel build'
  else:
   staged=[]
   for f in src+[cpp,wrapper]:d=STAGE/f.name;shutil.copyfile(f,d);staged.append(d)
   execute([vr/'bin/verilator','--cc','--exe','--build','--no-timing','--assert','-Wno-fatal','-O1','-j','2','-CFLAGS','-std=c++20',
    '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2','--top-module','quant_network_buffered','--Mdir',STAGE/'obj',
    '-LDFLAGS',str(lib),*staged],STAGE,env,out/'compile.log',timeout=300)
   manifest.write_text(json.dumps(inputs,indent=2))
  r['timing_seconds']['compile']=0 if a.reuse else time.perf_counter()-stamp;r['executable_sha256']=digest(exe);save()
  for mode,name in enumerate(['dual','only_engine1','skew_stall','restart']):
   case=out/name;case.mkdir()
   if a.reuse_passed:
    prior=json.loads((a.reuse_passed/'result.json').read_text())
    assert prior['build_inputs']==inputs and prior['data_hashes']==r['data_hashes'],'prior run mismatch'
    if name in prior['cases']:
     assert 'PASS buffered RTL' in (a.reuse_passed/name/'sim.log').read_text()
     assert digest(a.reuse_passed/name/'outputs.bin')==prior['cases'][name]['output_sha256']
     shutil.copytree(a.reuse_passed/name,case,dirs_exist_ok=True)
     r['cases'][name]=prior['cases'][name];r['timing_seconds'][name]=0
     r.setdefault('reused_cases',{})[name]={'run':str(a.reuse_passed),'original_seconds':prior['timing_seconds'][name]};save();continue
   for f in a.data.iterdir():
    if f.is_file():assert digest(f)==r['data_hashes'][f.name];shutil.copyfile(f,case/f.name)
   count=(case/'jobs.bin').stat().st_size//64;stamp=time.perf_counter()
   execute([exe,str(count),str(mode)],case,env,case/'sim.log',timeout=900)
   assert 'PASS buffered RTL' in (case/'sim.log').read_text()
   metrics=json.loads((case/'metrics.json').read_text());metrics['output_sha256']=digest(case/'outputs.bin');r['cases'][name]=metrics
   r['timing_seconds'][name]=time.perf_counter()-stamp;save();print(name+': '+json.dumps(metrics),flush=True)
  assert len({c['output_sha256'] for c in r['cases'].values()})==1
  r['status']='PASS'
 except Exception as e:r['status']='FAIL';r['error']=str(e);print(str(e),flush=True)
 r['timing_seconds']['total']=time.perf_counter()-start;save();return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
