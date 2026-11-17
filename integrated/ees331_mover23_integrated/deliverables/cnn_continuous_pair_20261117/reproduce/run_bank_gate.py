from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parent;S=R/'new';D=R/'bank_gate';D.mkdir(exist_ok=True)
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator');src=S/'rtl/cnn_ddr/cnn_paged_mover.sv'
s=src.read_text();a=s.index(')(\n')+3;b=s.index('\n);',a);ports=s[a:b]
(D/'bank_multi_top.sv').write_text('module bank_multi_top(\n'+ports+'\n);\n cnn_paged_mover #(.CLIENTS(4),.LOCAL_BYTES(401408)) dut(.*);\nendmodule\n')
files=[S/'storage_v2/rtl/tile_local_ram.sv',S/'storage_v2/rtl/tile_local_ram_bank4.sv',S/'storage_v2/rtl/data_mover.sv',src,D/'bank_multi_top.sv',R/'bank_multi_main.cpp']
# Export widths depend on the parameter name in the copied port declaration.
p=D/'bank_multi_top.sv';p.write_text(p.read_text().replace('module bank_multi_top(', 'module bank_multi_top #(parameter CLIENTS=4)('))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();record={'status':'COMPILING','sources':{str(p.relative_to(R)):sha(p) for p in files}}
def save():(D/'result.json').write_text(json.dumps(record,indent=2))
env=dict(os.environ,VERILATOR_ROOT=str(VR));save();t=time.monotonic()
try:
 cmd=[VR/'bin/verilator','--cc','--exe','--build','--no-timing','--assert','--top-module','bank_multi_top','-Wno-fatal','-j','1','-O1','--output-split-cfuncs','500','--Mdir',D/'obj','-CFLAGS',f'-std=c++20 -O2 -I{S/"simulation/tb/integration"}','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*files]
 with (D/'compile.log').open('w') as f:subprocess.run([str(x) for x in cmd],env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
 record['compile_seconds']=time.monotonic()-t;t2=time.monotonic()
 with (D/'simulation.log').open('w') as f:subprocess.run([str(D/'obj/Vbank_multi_top'),str(D/'metrics.json')],env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
 record['simulation_seconds']=time.monotonic()-t2;record['metrics']=json.loads((D/'metrics.json').read_text());assert record['metrics']['status']=='PASS'
 assert all(sha(R/n)==h for n,h in record['sources'].items());record['status']='PASS'
except BaseException as e:record['status']='FAIL';record['error']=str(e);raise
finally:record['wall_seconds']=time.monotonic()-t;save();print(json.dumps(record,indent=2))
