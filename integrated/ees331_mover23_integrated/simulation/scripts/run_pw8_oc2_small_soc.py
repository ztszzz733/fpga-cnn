"""Eight-task production-SoC gate after the PW8 paired-channel unit test."""
from pathlib import Path
from datetime import datetime
import json,hashlib,os,subprocess,time,signal,sys
SIM=Path(__file__).resolve().parents[1];B=SIM.parent;VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def local(s):return Path(s.replace('D:\\','/mnt/d/').replace('D:/','/mnt/d/').replace('\\','/'))
unit=local(sys.argv[1]);u=json.loads((unit/'result.json').read_text());assert u['status']=='PASS'
for n,h in u['sources'].items():assert sha(B/n)==h,n
names=[s.strip() for s in (B/'rtl/filelists/system_ees331_reduced.f').read_text().splitlines() if s.strip() and not s.startswith('#')]
TOP='ees331_soc_reduced_sim_top';names+=['simulation/tb/'+TOP+'.sv','simulation/tb/integration/ees331_pw8_linear_full_main.cpp','simulation/tb/integration/ees331_axi_mover_model.hpp','simulation/firmware/ees331_cpu/program_ram_probe.mem','rtl/filelists/system_ees331_reduced.f']
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pw8_oc2_small_soc');out.mkdir(parents=True)
record={'status':'COMPILING','scope':'8-task small SoC only; not full image/network or resource measurement','sources':{n:sha(B/n) for n in names},'unit_gate':str(unit),'unit_result_sha256':sha(unit/'result.json'),'frames':1,'jobs':8,'full_network':False,'synthesis_run':False}
def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
def run(cmd,log,env,limit):
 t=time.monotonic()
 with log.open('w') as f:subprocess.run(cmd,cwd=SIM,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=limit,check=True)
 return time.monotonic()-t
save();print(out,flush=True);t=time.monotonic()
try:
 env=dict(os.environ,VERILATOR_ROOT=str(VR),CNN_NO_CONTROL_TRACE='1')
 flags=['--cc','--exe','--build','--top-module',TOP,'--no-timing','-DEES331_EXTERNAL_PS','--assert','--output-split-cfuncs','500','-Wno-fatal','-O1','-j','1','-CFLAGS','-std=c++20 -O2','--Mdir',str(out/'obj'),'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
 record['compile_seconds']=run([str(VR/'bin/verilator'),*flags,*[str(B/n) for n in names[:-3]]],out/'compile.log',env,480);record['status']='RUNNING';save()
 fixture=SIM/'build/fixtures/reduced_single_small';m=json.loads((fixture/'manifest.json').read_text())
 for n,h in m['files_sha256'].items():assert sha(fixture/n)==h,n
 dest=out/'small';dest.mkdir();record['simulation_seconds']=run([str(out/'obj'/('V'+TOP)),str(fixture),str(dest)],dest/'simulation.log',env,120)
 metrics=json.loads((dest/'metrics.json').read_text());assert metrics['status']=='PASS' and metrics['jobs']==8 and metrics['checked_output_bytes']==m['expected_bytes'] and metrics['results']==1
 assert sha(dest/'outputs.bin')==m['final_sha256'];record.update(status='PASS',metrics=metrics,output_sha256=sha(dest/'outputs.bin'),fixture_manifest_sha256=sha(fixture/'manifest.json'))
except BaseException as e:record.update(status='FAIL',error=str(e));raise
finally:
 record['wall_seconds']=time.monotonic()-t;record['sources_unchanged']=all(sha(B/n)==h for n,h in record['sources'].items());save()
assert record['sources_unchanged'];print('PASS 8-task SoC with paired-channel PW8',flush=True)
