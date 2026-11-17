from pathlib import Path
import os,subprocess,time,json,datetime,hashlib,sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent;SRC=ROOT/'perf_source'
unit=Path((ROOT/'active_unit.txt').read_text().strip());gate=json.loads((unit/'result.json').read_text());assert gate['status']=='PASS'
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
RUN=ROOT/'perf_runs'/datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S');RUN.mkdir(parents=True)
(ROOT/'active_perf.txt').write_text(str(RUN)+'\n')
names=['rtl/cnn_self/compact_word_ram.sv','rtl/cnn_self/self_pw8_engine.sv','rtl/cnn_self/self_conv_spatial4_engine.sv','storage_v2/rtl/data_mover.sv','storage_v2/rtl/tile_local_ram.sv','storage_v2/rtl/tile_local_ram_bank4.sv','rtl/cnn_ddr/cnn_paged_mover.sv','rtl/cnn_ddr/cnn_plan_storage.sv','rtl/cnn_ddr/storage_plan_queue.sv','conv_memory_perf_top.sv']
sources=[SRC/n for n in names]+[ROOT/'perf_main.cpp']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SRC/'rtl/cnn_self/self_pw8_engine.sv')==gate['source_sha256']['self_pw8_engine.sv']
record=dict(status='COMPILING',unit_gate=str(unit),sources={str(p):sha(p) for p in sources},variants={},scope='Same explicit new storage; two real PW8s; enable word fill only on instance 0, instance 1 unchanged; includes load and DDR output visibility; not full network')
variants=[('off',0),('one_enabled',1)]
if '--reuse-baseline' in sys.argv:
 previous=ROOT/'perf_runs/20261117_154036'
 old=json.loads((previous/'result.json').read_text());assert old['status']=='PASS'
 for path,value in record['sources'].items():
  if not path.endswith('/rtl/cnn_self/self_pw8_engine.sv'):
   assert old['sources'][path]==value,('baseline common source mismatch',path)
 record['variants']['off']=old['variants']['off']
 record['baseline_reused']=dict(directory=str(previous/'off'),reason='Same wrapper, driver and storage; disabled candidate is exact-cycle equivalent to independent original in all 213 final-source parameter cases')
 variants=[('one_enabled',1)]
def save():(RUN/'result.json').write_text(json.dumps(record,indent=2)+'\n')
env=dict(os.environ,VERILATOR_ROOT=str(VR),MAKEFLAGS='')
def execute(command,log,limit):
 t=time.monotonic()
 with log.open('w') as f:subprocess.run(list(map(str,command)),cwd=SRC,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=limit,check=True)
 return time.monotonic()-t
save();begin=time.monotonic()
try:
 for name,enabled in variants:
  d=RUN/name;d.mkdir();obj=d/'obj'
  cmd=[VR/'bin/verilator','--cc','--exe','--build','--assert','--no-timing','--top-module','conv_memory_perf_top','-GPLAN=1',f'-GWORD_FILL={enabled}','-Wno-fatal','--threads','1','-j','2','-O1','--output-split-cfuncs','500','--Mdir',obj,'-CFLAGS',f'-std=c++20 -O2 -I{SRC/"simulation/tb/integration"}','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*sources]
  print('Compiling matched real-storage case:',name,flush=True)
  compile_seconds=execute(cmd,d/'compile.log',600)
  sim_seconds=execute([obj/'Vconv_memory_perf_top','explicit'],d/'simulation.log',60)
  lines=(d/'simulation.log').read_text().splitlines();m=[json.loads(line[5:]) for line in lines if line.startswith('PERF ')];assert len(m)==1 and m[0]['status']=='PASS'
  record['variants'][name]=dict(compile_seconds=compile_seconds,simulation_seconds=sim_seconds,metrics=m[0]);save();print('\n'.join(lines),flush=True)
 a=record['variants']['off']['metrics'];b=record['variants']['one_enabled']['metrics'];assert a['cycles']==144209,'baseline must reproduce prior exact workload'
 assert a['ddr_read_bytes']==b['ddr_read_bytes'] and a['ddr_write_bytes']==b['ddr_write_bytes']
 record.update(status='PASS',saved_percent=100*(1-b['cycles']/a['cycles']))
 for path,h in record['sources'].items():assert sha(Path(path))==h
except Exception as error:record.update(status='FAIL',error=str(error));raise
finally:record['wall_seconds']=time.monotonic()-begin;save();print('Performance:',RUN/'result.json',record['status'],flush=True)
