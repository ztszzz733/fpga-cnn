"""One real-CPU image through the actual reduced SoC and enlarged tile RAM."""
from pathlib import Path
from datetime import datetime
import hashlib,json,os,subprocess,time,signal,sys
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator');ZLIB=SIM/'.tools/zlib-linux'
OUT=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_k3_reuse_small_soc');OUT.mkdir(parents=True)
BUILD=OUT/'compile';BUILD.mkdir()
TOP='ees331_soc_reduced_sim_top';main=SIM/'tb/integration/ees331_soc_reduced_main.cpp'
sources=[BASE/s.strip() for s in (BASE/'rtl/filelists/system_ees331_reduced.f').read_text().splitlines() if s.strip() and not s.startswith('#')]+[SIM/'tb'/ (TOP+'.sv')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'status':'COMPILING','run_dir':str(OUT),'frames':1,'jobs':8,'pool':{'K3':2,'K1':6,'Post':2,'DW7':0,'Add':1,'Pad':1},'sources':{str(p.relative_to(BASE)):sha(p) for p in sources+[main,SIM/'tb/integration/ees331_axi_mover_model.hpp',SIM/'firmware/ees331_cpu/program_ram_probe.mem']},'external_models':'PS GP0 and AXI3 DDR; CPU/CNN/tile RAM/MOVER are production RTL','optimization':'K3 horizontal halo/full-layer weight reuse; small 8-task correctness gate only','baseline_run':'20261112_203157_reduced_single_soc','clock_reference':'100MHz for plotted timestamps only; no board frequency claim'}
def save():
 (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
save();start=time.monotonic();print(OUT,flush=True)
try:
 env=dict(os.environ,VERILATOR_ROOT=str(VR))
 flags=['--cc','--exe','--build','--top-module',TOP,'--no-timing','-DEES331_EXTERNAL_PS','--assert','--trace-fst','--trace-depth','1','--timescale','1ns/1ps','--output-split-cfuncs','500','-Wno-fatal','-O1','-j','1','-CFLAGS','-std=c++20 -O2 -I'+str(ZLIB/'usr/include'),'-LDFLAGS','-L'+str(ZLIB/'usr/lib/x86_64-linux-gnu'),'--Mdir',str(BUILD/'obj'),'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
 with (BUILD/'compile.log').open('w') as log:subprocess.run([str(VR/'bin/verilator'),*flags,*map(str,sources),str(main)],cwd=SIM,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
 record['compile_seconds']=time.monotonic()-start;record['exe_sha256']=sha(BUILD/'obj'/('V'+TOP));save()
 for size in ('small',):
  dest=OUT/size;dest.mkdir();record['status']='RUNNING_'+size.upper();save();begin=time.monotonic()
  fixture=SIM/('build/fixtures/reduced_single_'+size);m=json.loads((fixture/'manifest.json').read_text())
  for name,digest in m['files_sha256'].items():assert sha(fixture/name)==digest,name
  with (dest/'simulation.log').open('w') as log:
   p=subprocess.Popen([str(BUILD/'obj'/('V'+TOP)),str(fixture),str(dest)],cwd=SIM,env=env,stdout=log,stderr=subprocess.STDOUT)
   record['simulation_pid']=p.pid;save()
   while p.poll() is None:
    if time.monotonic()-begin>120:p.terminate();p.wait(timeout=10);raise RuntimeError('small SoC timeout')
    if (OUT/'STOP').exists():p.send_signal(signal.SIGTERM);p.wait(timeout=60);raise RuntimeError('stopped by user')
    time.sleep(2)
  record[size+'_seconds']=time.monotonic()-begin
  if p.returncode:raise RuntimeError(size+' failed: '+(dest/'simulation.log').read_text()[-2000:])
  metrics=json.loads((dest/'metrics.json').read_text())
  assert metrics['jobs']==m['total_tasks'] and metrics['checked_output_bytes']==m['expected_bytes'] and metrics['results']==1
  assert sha(dest/'outputs.bin')==m['final_sha256']
  record[size]={'metrics':metrics,'output_sha256':sha(dest/'outputs.bin')};save()
 record['status']='PASS'
except BaseException as e:record.update(status='FAIL',error=str(e));raise
finally:record['wall_seconds']=time.monotonic()-start;save()
print('PASS small 8-task SoC only',flush=True)
