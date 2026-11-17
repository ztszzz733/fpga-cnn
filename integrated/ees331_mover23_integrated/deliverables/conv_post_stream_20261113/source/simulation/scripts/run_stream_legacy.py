from pathlib import Path
from datetime import datetime
import os,subprocess,json,hashlib,time,sys
B=Path(__file__).resolve().parents[2];S=B/'simulation';VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
out=S/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_stream_legacy');out.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=[B/'rtl/cnn_quant/quant_post_pipe_engine.sv',S/'tb/stream_legacy_post_frozen.sv',S/'tb/stream_legacy_post_top.sv',S/'tb/integration/stream_legacy_post_main.cpp']
j=dict(status='RUNNING',sources={str(p.relative_to(B)):sha(p) for p in files},groups={})
def save():(out/'result.json').write_text(json.dumps(j,indent=2)+'\n')
save();print(out,flush=True)
try:
 t=time.monotonic()
 cmd=[str(VR/'bin/verilator'),'--cc','--exe','--build','--no-timing','--assert','--top-module','stream_legacy_post_top','-Wno-fatal','-j','1','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*map(str,files)]
 with (out/'post_compile.log').open('w') as f:subprocess.run(cmd,cwd=S,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
 j['compile_seconds']=time.monotonic()-t;t=time.monotonic()
 with (out/'post_simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vstream_legacy_post_top'),str(out/'post_metrics.json')],stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
 j['post_sim_seconds']=time.monotonic()-t;j['groups']['post']='PASS';save()
 for name,script in [('pw8','run_pw8_addr_unit.py'),('k3','run_k3_reuse_units.py')]:
  before=set((S/'build/runs').iterdir());t=time.monotonic()
  with (out/(name+'_launcher.log')).open('w') as f:subprocess.run([sys.executable,'-B',str(S/'scripts'/script)],stdout=f,stderr=subprocess.STDOUT,timeout=240,check=True)
  suffix='_remaining_pw8_addr' if name=='pw8' else '_reuse_unit'
  runs=[p for p in (set((S/'build/runs').iterdir())-before) if p.is_dir() and p.name.endswith(suffix) and (p/'result.json').exists()];assert len(runs)==1
  r=runs[0];jr=json.loads((r/'result.json').read_text());assert jr['status']=='PASS' and jr['sources_unchanged'];j['groups'][name]={'status':'PASS','run':str(r),'wall_seconds':time.monotonic()-t};save()
 j['status']='PASS'
except BaseException as e:j.update(status='FAIL',error=str(e));raise
finally:j['sources_unchanged']=all(sha(B/n)==h for n,h in j['sources'].items());save()
print('PASS all legacy paths',flush=True)
