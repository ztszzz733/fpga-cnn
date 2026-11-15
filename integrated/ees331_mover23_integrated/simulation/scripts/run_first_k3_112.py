from pathlib import Path
from datetime import datetime
import json,hashlib,subprocess,time,os,csv
SIM=Path(__file__).resolve().parents[1];B=SIM.parent
C=SIM/'build/runs/20261113_153421_k3_reuse_small_soc';OBJ=C/'compile/obj'
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator');Z=SIM/'.tools/zlib-linux'
F=SIM/'build/fixtures/reduced_single_full';D=B/'deliverables/mover_speed_single_20261112'
O=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_first_k3_112');O.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'status':'PREPARING','run_dir':str(O),'rtl_cache':str(C),'full_network_executed':False,'rtl_compile_seconds':0,'cpu_configuration':'same full template and fixture as previous full run, stop at first convolution completion','reference_clock_hz':100000000}
def save():(O/'result.json').write_text(json.dumps(record,indent=2)+'\n')
def duration(p):
 events=list(csv.DictReader(p.open()));start=[int(e['cycle']) for e in events if e['event']=='START' and int(e['node'])==1];end=[int(e['cycle']) for e in events if e['event']=='COMPLETE' and int(e['node'])==1]
 assert len(start)==len(end)==1
 return {'start':start[0],'end':end[0],'cycles':end[0]-start[0]}
save();print(O,flush=True);t=time.monotonic()
try:
 cache=json.loads((C/'result.json').read_text());assert cache['status']=='PASS'
 for n,h in cache['sources'].items():assert sha(B/n)==h,n
 assert sha(OBJ/'Vees331_soc_reduced_sim_top')==cache['exe_sha256']
 record['sources']=cache['sources'];record['cache_result_sha256']=sha(C/'result.json')
 model=json.loads((F/'manifest.json').read_text());assert model['jobs'][1]['macs']==5419008
 for n,h in model['files_sha256'].items():assert sha(F/n)==h,n
 row=[int(x,16) for x in (F/'commands.hex').read_text().split()][16:32]
 assert row[6:12]==[3,114,114,64,2,0],row
 record['configuration']={'original_image':[112,112,3],'padded_input':[114,114,3],'kernel':[3,3],'stride':2,'output':[56,56,64],'macs':5419008}
 record['fixture_sha256']=model['files_sha256'];record['baseline']=duration(D/'full_events.csv');record['baseline_event_sha256']=sha(D/'full_events.csv')
 assert json.loads((D/'result.json').read_text())['status']=='PASS'
 record['production_differences_vs_old']={}
 for n,h in cache['sources'].items():
  archived=D/'source'/n
  if archived.is_file() and sha(archived)!=h:record['production_differences_vs_old'][n]={'before':sha(archived),'now':h}
 main=SIM/'tb/integration/ees331_first_k3_112_main.cpp';record['harness_sha256']=sha(main)
 flags=['-std=c++20','-O2','-DVM_TRACE=1','-DVM_TRACE_FST=1','-DVM_TRACE_VCD=0','-DVM_SC=0','-DVM_TIMING=0','-DVM_COVERAGE=0','-I'+str(OBJ),'-I'+str(VR/'include'),'-I'+str(VR/'include/vltstd'),'-I'+str(SIM/'tb/integration'),'-I'+str(Z/'usr/include')]
 record['status']='BUILDING_HARNESS_ONLY';save();begin=time.monotonic()
 with (O/'build.log').open('w') as log:
  subprocess.run(['g++',*flags,'-c',str(main),'-o',str(O/'main.o')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
  subprocess.run(['g++',str(O/'main.o'),*[str(OBJ/n) for n in ['verilated.o','verilated_fst_c.o','verilated_threads.o','Vees331_soc_reduced_sim_top__ALL.a']],'-L'+str(Z/'usr/lib/x86_64-linux-gnu'),'-lz','-pthread','-o',str(O/'first_k3')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
 record['harness_build_seconds']=time.monotonic()-begin;record['status']='RUNNING_FIRST_CONV';save();begin=time.monotonic()
 with (O/'simulation.log').open('w') as log:subprocess.run([str(O/'first_k3'),str(F),str(O)],cwd=SIM,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
 record['simulation_seconds']=time.monotonic()-begin
 metrics=json.loads((O/'metrics.json').read_text());assert metrics['status']=='PASS' and metrics['jobs']==2 and metrics['checked_output_bytes']==841804
 gold=(F/'expected.bin').read_bytes()[38988:841804];assert (O/'conv_output.bin').read_bytes()==gold
 record['metrics']=metrics;record['output_sha256']=sha(O/'conv_output.bin');record['new']=duration(O/'events.csv')
 record['reduction_percent']=100*(1-record['new']['cycles']/record['baseline']['cycles']);record['speedup']=record['baseline']['cycles']/record['new']['cycles']
 record['sources_unchanged']=all(sha(B/n)==h for n,h in record['sources'].items());assert record['sources_unchanged'];assert sha(main)==record['harness_sha256']
 record['status']='PASS'
except BaseException as e:record.update(status='FAIL',error=str(e));raise
finally:record['wall_seconds']=time.monotonic()-t;save()
print(json.dumps({k:record[k] for k in ['status','baseline','new','reduction_percent','speedup','harness_build_seconds','simulation_seconds','production_differences_vs_old']},indent=2),flush=True)
