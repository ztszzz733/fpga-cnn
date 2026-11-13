"""Generic numeric runner for planned pairs; full runs require a matching small PASS."""
import argparse,datetime,hashlib,json,os,shutil,struct,time
from pathlib import Path
from run_tests import ROOT,execute
from validate_buffer_plan import validate
STAGE=ROOT.parents[1]/'.network_pair_build'
BASE=ROOT.parents[1]/'.neureka_full_hier_build'
DATA=['memory.bin','jobs.bin','mutable.bin','leases.bin','results.bin','expected.bin','expected_offsets.bin','workload.json']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--reuse',action='store_true');p.add_argument('--full',action='store_true');p.add_argument('--gate',type=Path);a=p.parse_args()
 spec=json.loads((a.data/'workload.json').read_text());assert bool(spec['full_image'])==a.full,'full-image data requires --full'
 out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_network_pair');out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
 start=time.perf_counter();r=dict(status='RUNNING',full_image=a.full,cases={},timing_seconds={},scope='real RTL numeric pair, SRAM preloaded; no CPU/UART');save=lambda:(out/'result.json').write_text(json.dumps(r,indent=2));save()
 try:
  r['plan_validation']=validate(a.data)
  base=json.loads((BASE/'build_inputs.json').read_text())
  for n,h in {**base['sources'],**base['includes']}.items():assert digest(ROOT/n)==h,'stale library '+n
  wrapper=BASE/'obj/Vneureka_conv_engine/neureka_conv_engine.sv';lib=wrapper.parent/'libneureka_conv_engine.a';adapter=wrapper.parent/'neureka_conv_engine.cpp'
  assert digest(adapter)==json.loads((BASE/'eval_cache.json').read_text())['cached_wrapper_sha256']
  src=[ROOT/'rtl/cnn_quant'/n for n in ['network_dispatch_buffered.sv','network_buffer_leases.sv','network_result_handoff.sv','quant_network_output.sv','quant_post_engine.sv','dw7_cached_engine.sv','pad_hwc_engine.sv']]
  cpp=ROOT/'tb/integration/network_pair_main.cpp';inputs={str(f):digest(f) for f in src+[cpp,wrapper,lib,adapter]};r['build_inputs']=inputs
  r['data_hashes']={n:digest(a.data/n) for n in DATA};r['runner_sha256']=digest(Path(__file__))
  # Independently build the expected external byte stream in ascending frame ID.
  meta=list(struct.iter_unpack('<4I',(a.data/'results.bin').read_bytes()));offsets=struct.unpack('<'+'I'*len(meta),(a.data/'expected_offsets.bin').read_bytes());expected=(a.data/'expected.bin').read_bytes()
  final=sorted((tag,expected[offsets[j]:offsets[j]+n]) for j,(flag,tag,addr,n) in enumerate(meta) if flag)
  assert len(final)==spec['frames'] and len(set(tag for tag,b in final))==len(final)
  r['expected_output_sha256']=hashlib.sha256(b''.join(b for tag,b in final)).hexdigest()
  if a.full:
   assert a.gate is not None,'full run needs --gate small run directory'
   gate=json.loads((a.gate/'result.json').read_text())
   assert gate['status']=='PASS' and not gate['full_image'] and gate['build_inputs']==inputs and set(gate['cases'])=={'fast_reader','slow_reader'},'small gate mismatch'
   for name,m in gate['cases'].items():assert digest(a.gate/name/'outputs.bin')==m['output_sha256'] and 'PASS generic pair RTL' in (a.gate/name/'sim.log').read_text()
   r['small_gate']=str(a.gate)
  save();STAGE.mkdir(exist_ok=True);exe=STAGE/'obj/Vquant_network_output';manifest=STAGE/'inputs.json'
  vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr);stamp=time.perf_counter()
  if a.reuse:assert exe.exists() and json.loads(manifest.read_text())==inputs,'stale pair build'
  else:
   staged=[]
   for f in src+[cpp,wrapper]:d=STAGE/f.name;shutil.copyfile(f,d);staged.append(d)
   execute([vr/'bin/verilator','--cc','--exe','--build','--no-timing','--assert','-Wno-fatal','-O1','-j','2','-CFLAGS','-std=c++20',
    '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2','--top-module','quant_network_output','--Mdir',STAGE/'obj','-LDFLAGS',str(lib),*staged],STAGE,env,out/'compile.log',timeout=300)
   manifest.write_text(json.dumps(inputs,indent=2))
  r['timing_seconds']['compile']=0 if a.reuse else time.perf_counter()-stamp;r['executable_sha256']=digest(exe);save()
  for mode,name in enumerate(['fast_reader'] if a.full else ['fast_reader','slow_reader']):
   case=out/name;case.mkdir()
   for n in DATA:assert digest(a.data/n)==r['data_hashes'][n];shutil.copyfile(a.data/n,case/n)
   count=(case/'jobs.bin').stat().st_size//64;stamp=time.perf_counter()
   r['active_case']=name;r['case_started_at']=datetime.datetime.now().isoformat();save()
   try:execute([exe,str(count),str(mode)],case,env,case/'sim.log',timeout=86400 if a.full else 900)
   finally:r['timing_seconds'][name]=time.perf_counter()-stamp;save()
   assert 'PASS generic pair RTL' in (case/'sim.log').read_text()
   m=json.loads((case/'metrics.json').read_text());m['output_sha256']=digest(case/'outputs.bin');assert m['output_sha256']==r['expected_output_sha256']
   assert m['commands']==spec['commands'] and m['allocations']==m['releases']==spec['allocations']
   r['cases'][name]=m;save();print(name+': '+json.dumps(m),flush=True)
  r['status']='PASS';r.pop('active_case',None)
 except Exception as e:r['status']='FAIL';r['error']=str(e);print(str(e),flush=True)
 r['timing_seconds']['total']=time.perf_counter()-start;save();return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
