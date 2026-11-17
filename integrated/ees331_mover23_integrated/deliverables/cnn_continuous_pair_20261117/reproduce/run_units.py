from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parent;U=R/'units';S=R/'new/rtl/cnn_self';VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'status':'RUNNING','variants':{}}
def save():(U/'result.json').write_text(json.dumps(record,indent=2)+'\n')
env=dict(os.environ,VERILATOR_ROOT=str(VR));env['MAKEFLAGS']='';save();start=time.monotonic()
try:
 for kind,k3 in [('pw',0),('k3',1)]:
  d=U/kind;d.mkdir();files=[S/'compact_word_ram.sv',S/'continuous_read_adapter.sv',S/'self_pw8_engine.sv',S/'self_conv_spatial4_engine.sv',U/'self_word_buffer_unit_top.sv',U/f'{kind}_main.cpp']
  hashes={str(p.relative_to(R)):sha(p) for p in files};obj=d/'obj'
  cmd=[VR/'bin/verilator','--cc','--exe','--build','--no-timing','--assert','--top-module','self_word_buffer_unit_top',f'-GK3={k3}','-Wno-fatal','-j','1','--Mdir',obj,'-CFLAGS','-std=c++20 -O2'+(' -DCNN_K3_TEST' if k3 else ''),'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*files]
  t=time.monotonic()
  with (d/'compile.log').open('w') as f:subprocess.run([str(x) for x in cmd],cwd=U,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
  compile_s=time.monotonic()-t;t=time.monotonic()
  with (d/'simulation.log').open('w') as f:subprocess.run([str(obj/'Vself_word_buffer_unit_top'),str(d/'metrics.json')],cwd=U,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
  m=json.loads((d/'metrics.json').read_text());assert m['status']=='PASS'
  assert all(sha(R/n)==h for n,h in hashes.items())
  record['variants'][kind]={'status':'PASS','compile_seconds':compile_s,'simulation_seconds':time.monotonic()-t,'cases':len(m['cases']),'sources':hashes};save()
 record['status']='PASS'
except BaseException as e:record['status']='FAIL';record['error']=str(e);raise
finally:
 record['wall_seconds']=time.monotonic()-start;save();print(json.dumps(record,indent=2))
