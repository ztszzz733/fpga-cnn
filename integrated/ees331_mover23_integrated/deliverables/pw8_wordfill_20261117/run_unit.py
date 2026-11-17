from pathlib import Path
import datetime,hashlib,json,os,subprocess,time
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
RUN=ROOT/'unit_runs'/datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
RUN.mkdir(parents=True,exist_ok=False)
(ROOT/'active_unit.txt').write_text(str(RUN)+'\n')
paths=[ROOT/n for n in ['compact_word_ram.sv','self_pw8_engine.sv','baseline_pw8_wordfill.sv','pw8_wordfill_top.sv','pw8_wordfill_main.cpp']]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(status='COMPILING',source_sha256={p.name:sha(p) for p in paths},scope='Experimental single-outstanding 64B FF transpose staging; parameter defaults off; no production changes')
def save():(RUN/'result.json').write_text(json.dumps(record,indent=2)+'\n')
env=dict(os.environ,VERILATOR_ROOT=str(VR),MAKEFLAGS='')
command=[VR/'bin/verilator','--cc','--exe','--build','--no-timing','--assert','--top-module','pw8_wordfill_top','-Wno-fatal','--threads','1','-j','2','-O1','--output-split-cfuncs','500','--Mdir',RUN/'obj','-CFLAGS','-std=c++20 -O2','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*paths]
(RUN/'command.json').write_text(json.dumps([str(x) for x in command],indent=2)+'\n')
save();begin=time.monotonic()
try:
 t=time.monotonic()
 with (RUN/'compile.log').open('w') as log:subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
 record.update(status='RUNNING',compile_seconds=time.monotonic()-t);save();print('Compiled; running numerical/protocol comparison',flush=True)
 t=time.monotonic()
 with (RUN/'simulation.log').open('w') as log:subprocess.run([str(RUN/'obj/Vpw8_wordfill_top'),str(RUN/'metrics.json')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240,check=True)
 record['simulation_seconds']=time.monotonic()-t
 metrics=json.loads((RUN/'metrics.json').read_text());assert metrics['status']=='PASS'
 record.update(status='PASS',parameter_cases=len(metrics['cases']))
 for p in paths:assert sha(p)==record['source_sha256'][p.name],p
 print((RUN/'simulation.log').read_text().splitlines()[-1],flush=True)
except Exception as error:
 record.update(status='FAIL',error=str(error));raise
finally:
 record['wall_seconds']=time.monotonic()-begin;save();print('Unit result:',RUN/'result.json',record['status'],flush=True)
