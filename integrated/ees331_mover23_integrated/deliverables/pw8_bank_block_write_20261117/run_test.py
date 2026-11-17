from pathlib import Path
import datetime,hashlib,json,os,subprocess,time
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
RUN=ROOT/'runs'/datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S');RUN.mkdir(parents=True,exist_ok=False)
(ROOT/'active_run.txt').write_text(str(RUN)+'\n')
names=['compact_word_ram.sv','original_engine.sv','self_pw8_block_engine.sv','tile_local_ram.sv','tile_local_ram_bank4.sv','block_bank.sv','bank_benchmark_top.sv','bank_benchmark_main.cpp']
paths=[ROOT/n for n in names]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(status='COMPILING',scope='Real 32-bit bank only; no DDR; same PW8 arithmetic/input path, bank width/latency and RAM in both modes; strided blocks <=8 words and scalar one-word tails',sources={p.name:sha(p) for p in paths},ddr_included=False,resource_synthesis=False,production_changed=False)
def save():(RUN/'result.json').write_text(json.dumps(record,indent=2)+'\n')
command=[VR/'bin/verilator','--cc','--exe','--build','--assert','--no-timing','--top-module','bank_benchmark_top','-Wno-fatal','--threads','1','-j','2','-O1','--output-split-cfuncs','500','--Mdir',RUN/'obj','-CFLAGS','-std=c++20 -O2','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*paths]
(RUN/'command.json').write_text(json.dumps(list(map(str,command)),indent=2)+'\n')
env=dict(os.environ,VERILATOR_ROOT=str(VR),MAKEFLAGS='')
save();begin=time.monotonic()
try:
 t=time.monotonic()
 with (RUN/'compile.log').open('w') as log:subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
 record.update(status='RUNNING',compile_seconds=time.monotonic()-t);save();print('Compiled; running bank-only comparison',flush=True)
 t=time.monotonic()
 with (RUN/'simulation.log').open('w') as log:subprocess.run([str(RUN/'obj/Vbank_benchmark_top'),str(RUN/'metrics.json')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240,check=True)
 record['simulation_seconds']=time.monotonic()-t
 m=json.loads((RUN/'metrics.json').read_text());assert m['status']=='PASS' and not m['ddr_included']
 record.update(status='PASS',cases=len(m['cases']),comparisons=[dict(id=x['id'],width=x['width'],height=x['height'],ci=x['ci'],co=x['co'],total_saved_percent=100*(1-x['new']['cycles']/x['old']['cycles']),write_service_saved_percent=100*(1-x['new']['write_service_cycles']/x['old']['write_service_cycles'])) for x in m['cases']])
 assert all(sha(p)==record['sources'][p.name] for p in paths)
 print((RUN/'simulation.log').read_text(),flush=True)
except Exception as error:record.update(status='FAIL',error=str(error));raise
finally:record['wall_seconds']=time.monotonic()-begin;save();print('Result:',RUN/'result.json',record['status'],flush=True)
