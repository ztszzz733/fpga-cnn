"""Avoid empty monitor work; require exact gate equivalence before full run."""
from pathlib import Path
import json,shutil,subprocess,time,hashlib,os
from datetime import datetime
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
previous=Path(json.loads((SIM/'build/five_soc_active.json').read_text())['run_dir'])
old=json.loads((previous/'result.json').read_text())
assert 'small' in old and old['small']['metrics']['jobs']==40
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_five_full_soc_fast');out.mkdir()
build=out/'compile';shutil.copytree(previous/'compile',build)
original=SIM/'tb/integration/ees331_soc_five_main.cpp';main=original.with_name('ees331_soc_five_fast_main.cpp')
text=original.read_text()
anchor='need(!d.debug_error&&!d.debug_fault,"CNN/MOVER error at cycle "+std::to_string(cycle));'
assert anchor in text
text=text.replace(anchor,'''if(d.debug_error||d.debug_fault)need(false,"CNN/MOVER error at cycle "+std::to_string(cycle));
  // Every checked write, launch, completion and work pulse still takes the
  // original complete monitor path. Empty cycles cannot alter its counters.
  if(!(d.debug_unit_start|d.debug_completion|d.debug_work|(d.debug_valid&d.debug_ready&d.debug_write)))return;''')
main.write_text(text)
mk=build/'obj/Vees331_soc_mover23_sim_top.mk'
mk.write_text(mk.read_text().replace('ees331_soc_five_main','ees331_soc_five_fast_main'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={k:v for k,v in old.items() if k not in ('status','full','small','error','full_seconds','small_seconds','wall_seconds','exe_sha256')}
record.update(status='COMPILING',run_dir=str(out),started_at=datetime.now().isoformat(),previous_run=str(previous),monitor_optimization='Only skip event-free monitor cycles; error flags checked every cycle; RTL/timing/trace unchanged')
record['sources']=dict(old['sources']);record['sources'].pop(str(original.relative_to(BASE)));record['sources'][str(main.relative_to(BASE))]=sha(main)
save=lambda:(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
save();begin=time.monotonic()
try:
 with (build/'fast_compile.log').open('w') as log:
  subprocess.run(['make','-C',str(build/'obj'),'-f',mk.name,'-j','2','CFG_CXXFLAGS_PCH_I=-include','OPT_FAST=-O2'],stdout=log,stderr=subprocess.STDOUT,check=True)
 record['fast_compile_seconds']=time.monotonic()-begin;record['exe_sha256']=sha(build/'obj/Vees331_soc_mover23_sim_top');save()
 for size in ('small','full'):
  dest=out/size;dest.mkdir();record['status']='RUNNING_'+size.upper();save();start=time.monotonic()
  with (dest/'simulation.log').open('w') as log:
   p=subprocess.run([str(build/'obj/Vees331_soc_mover23_sim_top'),str(SIM/('build/fixtures/five_'+size)),str(dest)],cwd=SIM,stdout=log,stderr=subprocess.STDOUT)
  record[size+'_seconds']=time.monotonic()-start
  if p.returncode:raise RuntimeError((dest/'simulation.log').read_text()[-2500:])
  metrics=json.loads((dest/'metrics.json').read_text())
  record[size]={'metrics':metrics,'output_sha256':sha(dest/'outputs.bin')};save()
  if size=='small':
   assert record['small']==old['small'],'small gate metrics or bytes differ'
   assert (dest/'events.csv').read_bytes()==(previous/'small/events.csv').read_bytes(),'gate event times differ'
   record['gate_exact_equivalence']=True;save()
   (SIM/'build/five_soc_fast_active.json').write_text(json.dumps({'run_dir':str(out),'status':'RUNNING_FULL'},indent=2)+'\n')
  else:
   assert metrics['jobs']==655 and metrics['checked_output_bytes']==96686460 and metrics['results']==5
   assert record['full']['output_sha256']=='08863d5da4d2febb5a6f60ee8abd41712a48c53ff0c997161e283a87a11fa709'
 record['status']='PASS'
except BaseException as exc:
 record.update(status='FAIL',error=str(exc));raise
finally:
 record['wall_seconds']=time.monotonic()-begin;save()
 (SIM/'build/five_soc_fast_active.json').write_text(json.dumps({'run_dir':str(out),'status':record['status']},indent=2)+'\n')
print(json.dumps(record,indent=2),flush=True)
