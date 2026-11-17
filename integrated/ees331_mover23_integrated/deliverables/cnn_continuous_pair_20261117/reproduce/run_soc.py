from pathlib import Path
import hashlib,json,os,subprocess,time,signal,sys
R=Path(__file__).resolve().parent;variant=sys.argv[1];assert variant in ['old','new']
S=R/variant;OUT=R/'runs'/variant;OUT.mkdir(parents=True,exist_ok=True)
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
TOP='ees331_soc_reduced_sim_top';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=[x.strip() for x in (S/'rtl/filelists/system_ees331_reduced.f').read_text().splitlines() if x.strip() and not x.startswith('#')]
names+=['simulation/tb/ees331_soc_reduced_sim_top.sv','simulation/tb/integration/ees331_pw8_linear_full_main.cpp']
src=[S/n for n in names]
record={'status':'COMPILING','variant':variant,'network':'Current 129-step reduced MobileFaceNet per image, DW7 disabled, 7x7x128 output','frames':2,'sources':{n:sha(S/n) for n in names},'scenarios':{},'ddr_model':'deterministic stress AXI3; actual CPU/CNN/MOVER/bank RTL','input':'two complete tensors interleaved PS upload, then frame commits; no UART/intra-image stripes','resource_synthesis':False}
def save():(OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
def run(c,log,timeout,env):
 t=time.monotonic()
 with log.open('w') as f:
  p=subprocess.Popen([str(x) for x in c],cwd=S/'simulation',env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  record['pid']=p.pid;save()
  try:
   while p.poll() is None:
    if (R/'STOP').exists():raise RuntimeError('stopped by user')
    if time.monotonic()-t>timeout:raise RuntimeError('timeout '+str(log))
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:pass
  except BaseException:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   raise
 if p.returncode:raise RuntimeError(str(log)+' exit '+str(p.returncode)+'\n'+log.read_text(errors='replace')[-2400:])
 return time.monotonic()-t
t=time.monotonic();save()
try:
 env=dict(os.environ,VERILATOR_ROOT=str(VR));env['CNN_NO_CONTROL_TRACE']='1'
 obj=OUT/'obj'
 cmd=[VR/'bin/verilator','--cc','--exe','--build','--top-module',TOP,'--no-timing','-DEES331_EXTERNAL_PS','--assert','--output-split-cfuncs','500','-Wno-fatal','-O1','-j','1','-CFLAGS','-std=c++20 -O2','--Mdir',obj,'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*src]
 (OUT/'command.json').write_text(json.dumps([str(x) for x in cmd],indent=2))
 record['compile_seconds']=run(cmd,OUT/'compile.log',600,env);record['exe_sha256']=sha(obj/('V'+TOP));save()
 for size in ['small','full']:
  if variant=='new' and size=='full':
   gate=json.loads((R/'units/result.json').read_text());assert gate['status']=='PASS','operator gates missing'
  fixture=R/'fixtures'/f'pair_{size}';m=json.loads((fixture/'manifest.json').read_text())
  for n,h in m['files_sha256'].items():assert sha(fixture/n)==h,n
  dest=OUT/size;dest.mkdir();record['status']='RUNNING_'+size.upper();save()
  runenv=dict(env)
  # Keep full-network task events and profiles; sampled control waveform is
  # enabled only for the short correctness gate to avoid a huge VCD.
  if variant=='new' and size=='small':runenv.pop('CNN_NO_CONTROL_TRACE',None)
  seconds=run([obj/('V'+TOP),fixture,dest],dest/'simulation.log',240 if size=='small' else 2400,runenv)
  metrics=json.loads((dest/'metrics.json').read_text());assert metrics['status']=='PASS'
  assert metrics['jobs']==m['total_tasks'] and metrics['checked_output_bytes']==m['expected_bytes'] and metrics['results']==2
  assert sha(dest/'outputs.bin')==m['final_sha256']
  record['scenarios'][size]={'status':'PASS','simulation_seconds':seconds,'metrics':metrics,'output_sha256':sha(dest/'outputs.bin'),'fixture_manifest_sha256':sha(fixture/'manifest.json')};save()
 for n,h in record['sources'].items():assert sha(S/n)==h,n
 record['status']='PASS'
except BaseException as e:record['status']='FAIL';record['error']=str(e);raise
finally:
 record['wall_seconds']=time.monotonic()-t;save();print(json.dumps({k:v for k,v in record.items() if k!='sources'},indent=2),flush=True)
