from pathlib import Path
import hashlib,json,os,subprocess,time,sys
R=Path(__file__).resolve().parent;lat=int(sys.argv[1]) if len(sys.argv)>1 else 2
D=R/f'latency{lat}';D.mkdir(exist_ok=True);O=D/'obj'
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
names=['compact_word_ram.sv','original_engine.sv','self_pw8_read_source.sv','self_pw8_continuous_engine.sv','tile_local_ram.sv','tile_local_ram_bank4.sv','continuous_read_adapter.sv','pipeline_bank.sv','bank_benchmark_top.sv','bank_benchmark_main.cpp']
files=[R/n for n in names];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
res={'status':'COMPILING','bank_response_latency_cycles':lat,'production_changed':False,'ddr_included':False,'sources':{p.name:sha(p) for p in files}}
def save():(D/'result.json').write_text(json.dumps(res,indent=2)+'\n')
env=os.environ.copy();env['VERILATOR_ROOT']=str(VR);env['MAKEFLAGS']=''
cmd=[VR/'bin/verilator','--cc','--exe','--build','--assert','--no-timing','--top-module','bank_benchmark_top',f'-GLATENCY={lat}','-Wno-fatal','--threads','1','-j','2','-O1','--output-split-cfuncs','500','--Mdir',O,'-CFLAGS','-std=c++20 -O2','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*files]
(D/'command.json').write_text(json.dumps([str(v) for v in cmd],indent=2)+'\n')
def run(c,log,timeout):
 t=time.perf_counter()
 with (D/log).open('w') as f:p=subprocess.run([str(x) for x in c],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
 if p.returncode:raise RuntimeError(f'{log}: exit {p.returncode}')
 return time.perf_counter()-t
t=time.perf_counter();save()
try:
 res['compile_seconds']=run(cmd,'compile.log',600);res['status']='RUNNING';save()
 res['simulation_seconds']=run([O/'Vbank_benchmark_top',D/'metrics.json'],'simulation.log',180)
 m=json.loads((D/'metrics.json').read_text());assert m['status']=='PASS' and len(m['cases'])==16
 for p in files:assert sha(p)==res['sources'][p.name]
 res['measurements']=m;res['status']='PASS'
except Exception as e:res['status']='FAIL';res['error']=str(e);raise
finally:
 res['wall_seconds']=time.perf_counter()-t;save();print(json.dumps(res,indent=2),flush=True)
