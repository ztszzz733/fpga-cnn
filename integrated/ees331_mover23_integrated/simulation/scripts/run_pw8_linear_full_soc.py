"""Isolated A/B of the current reduced one-image SoC; only PW8 source differs."""
from pathlib import Path
from datetime import datetime
import hashlib,json,os,subprocess,time,signal,sys
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator');ZLIB=SIM/'.tools/zlib-linux'
OUT=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pw8_linear_full_soc');OUT.mkdir(parents=True)
TOP='ees331_soc_reduced_sim_top'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=[s.strip() for s in (BASE/'rtl/filelists/system_ees331_reduced.f').read_text().splitlines() if s.strip() and not s.startswith('#')]
names+=['simulation/tb/'+TOP+'.sv','simulation/tb/integration/ees331_pw8_linear_full_main.cpp','simulation/tb/integration/ees331_axi_mover_model.hpp','simulation/firmware/ees331_cpu/program_ram_probe.mem','rtl/filelists/system_ees331_reduced.f']
record={'status':'PREPARING','run_dir':str(OUT),'frames':1,'jobs':129,'pool':{'K3':2,'K1':6,'Post':2,'DW7':0,'Add':1,'Pad':1},'final_shape':[7,7,128],'final_bytes':6272,'sources':{n:sha(BASE/n) for n in names},'variants':{},'fixtures':{},'clock_reference':'100MHz conditional conversion only; no board timing guarantee','network_variant':'Current reduced MobileFaceNet; DW7 and associated Post omitted, not original 128D embedding','external_models':'PS upload/control GP0 and AXI3 DDR; production CPU/CNN/shared RAM/MOVER RTL','synthesis_requested':False}
def save():
 (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 (SIM/'build/pw8_linear_full_active.json').write_text(json.dumps({'status':record['status'],'run_dir':str(OUT)},indent=2)+'\n')
def check_sources():assert all(sha(BASE/n)==h for n,h in record['sources'].items()),'Production/test sources changed during A/B run'
def command(cmd,cwd,env,log,limit):
 t=time.monotonic()
 with log.open('w') as f:
  p=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  record['child_pid']=p.pid;record['active_command']=str(log.relative_to(OUT));save()
  try:
   while p.poll() is None:
    if (OUT/'STOP').exists():raise RuntimeError('stopped by user')
    if time.monotonic()-t>limit:raise RuntimeError('timeout: '+str(log))
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:pass
  except BaseException:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=15)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   raise
 if p.returncode:raise RuntimeError('command failed: '+str(log)+'\n'+log.read_text(errors='replace')[-1800:])
 return time.monotonic()-t
save();start=time.monotonic();print(OUT,flush=True)
try:
 check_sources()
 original=BASE/'deliverables/pw8_linear_20261115/original_engine.sv'
 assert sha(original)=='99e94b10cf431ad3a11094fab6983923fdd1218576ffef199cbb9b31de429685'
 assert record['sources']['rtl/cnn_self/self_pw8_engine.sv']=='0a16ba33f74962235d487abd3d151635f2238e821b9ed4ae0709bfd2a16248c6'
 for size in ('small','full'):
  fixture=SIM/('build/fixtures/reduced_single_'+size);m=json.loads((fixture/'manifest.json').read_text())
  for name,digest in m['files_sha256'].items():assert sha(fixture/name)==digest,name
  record['fixtures'][size]={'directory':str(fixture),'manifest_sha256':sha(fixture/'manifest.json'),'files_sha256':m['files_sha256'],'expected_sha256':m['final_sha256']}
 # Copy once, then change exactly one source in the old snapshot. Production is
 # never changed while compiling or running either variant.
 for variant in ('old','new'):
  check_sources();d=OUT/variant;d.mkdir();snap=d/'source';snap.mkdir()
  for n in names:
   q=snap/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes((BASE/n).read_bytes())
  if variant=='old':(snap/'rtl/cnn_self/self_pw8_engine.sv').write_bytes(original.read_bytes())
  r={'status':'COMPILING','snapshot_hashes':{n:sha(snap/n) for n in names}};record['variants'][variant]=r;record['status']='COMPILING_'+variant.upper();save()
  env=dict(os.environ,VERILATOR_ROOT=str(VR));env.pop('CNN_NO_CONTROL_TRACE',None)
  source_names=names[:-3] # source list + observation top + C++ main (header not separate)
  sources=[snap/n for n in source_names]
  obj=d/'obj'
  flags=['--cc','--exe','--build','--top-module',TOP,'--no-timing','-DEES331_EXTERNAL_PS','--assert','--output-split-cfuncs','500','-Wno-fatal','-O1','-j','1','-CFLAGS','-std=c++20 -O2','--Mdir',str(obj),'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
  # Header location is the same as the copied C++ main; no generated FST code.
  r['compile_seconds']=command([str(VR/'bin/verilator'),*flags,*map(str,sources)],snap/'simulation',env,d/'compile.log',480)
  exe=obj/('V'+TOP);r['exe_sha256']=sha(exe);save()
  for mode in ('small','small_notrace','full'):
   if variant=='old' and mode=='small_notrace':continue
   size='small' if mode.startswith('small') else 'full';dest=d/mode;dest.mkdir()
   r['status']='RUNNING_'+mode.upper();record['status']='RUNNING_'+variant.upper()+'_'+mode.upper();save()
   runenv=dict(env)
   if variant=='old' or mode=='small_notrace':runenv['CNN_NO_CONTROL_TRACE']='1'
   r[mode+'_seconds']=command([str(exe),str(SIM/('build/fixtures/reduced_single_'+size)),str(dest)],snap/'simulation',runenv,dest/'simulation.log',120 if size=='small' else 1800)
   metrics=json.loads((dest/'metrics.json').read_text());manifest=json.loads((SIM/('build/fixtures/reduced_single_'+size)/'manifest.json').read_text())
   assert metrics['status']=='PASS' and metrics['jobs']==manifest['total_tasks'] and metrics['checked_output_bytes']==manifest['expected_bytes'] and metrics['results']==1
   assert sha(dest/'outputs.bin')==manifest['final_sha256']
   r[mode]={'metrics':metrics,'output_sha256':sha(dest/'outputs.bin')};save()
   if mode=='small_notrace':
    assert r[mode]['metrics']==r['small']['metrics'],'trace changed small simulation'
    for n in ['outputs.bin','output_timing.csv','events.csv','operator_profile.csv']:assert sha(dest/n)==sha(d/'small'/n),n
  r['status']='PASS';save()
 old=record['variants']['old'];new=record['variants']['new']
 changed=[n for n in names if old['snapshot_hashes'][n]!=new['snapshot_hashes'][n]]
 assert changed==['rtl/cnn_self/self_pw8_engine.sv'],changed
 assert old['full']['output_sha256']==new['full']['output_sha256']
 check_sources();record.update(status='PASS',changed_sources=changed,source_hashes_unchanged=True)
except BaseException as e:record.update(status='FAIL',error=str(e));raise
finally:record['wall_seconds']=time.monotonic()-start;save()
print('PASS one-image SoC A/B, intermediate checks, same output, new control waveform',flush=True)
