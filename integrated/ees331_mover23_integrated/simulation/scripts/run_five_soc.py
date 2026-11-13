"""Compile and run the actual five-context CPU/CNN/MOVER SoC, with FST states."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import shutil
import time
from datetime import datetime

SIM=Path(__file__).resolve().parents[1]
BASE=SIM.parent
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
ZLIB=SIM/'.tools/zlib-linux'
for relative in ('usr/include/zlib.h','usr/include/zconf.h','usr/lib/x86_64-linux-gnu/libz.a'):
 target=ZLIB/relative;target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():
  shutil.copyfile(Path('/mnt/d/code/FPGA1/cpu_control (2)/cpu_control/.tools/zlib-linux')/relative,target)
OUT=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_five_full_soc')
OUT.mkdir(parents=True)
BUILD=OUT/'compile'
BUILD.mkdir()
main=SIM/'tb/integration/ees331_soc_five_main.cpp'
text=(SIM/'tb/integration/ees331_soc_mover23_main.cpp').read_text()
text=text.replace('#include "verilated.h"','#include "verilated.h"\n#include "verilated_fst_c.h"')
text=text.replace('Vees331_soc_mover23_sim_top d;', 'std::unique_ptr<VerilatedFstC> trace;\n Vees331_soc_mover23_sim_top d;')
text=text.replace('bool check=false;', 'bool check=false;\n std::ofstream events;\n std::array<U64,5> input_cycles{},result_cycles{};')
text=text.replace('need(info[0]>=1 && info[0]<=4', 'need(info[0]>=1 && info[0]<=5')
text=text.replace('unsigned bit=k*10,','unsigned bit=k*11,').replace(')&1023;',')&2047;')
text=text.replace('ram.stress=true;', '''ram.stress=true;
  events.open(out/"events.csv");events<<"cycle,event,node,unit,frame\\n";
  Verilated::traceEverOn(true);trace=std::make_unique<VerilatedFstC>();d.trace(trace.get(),1);
  trace->open((out/"soc_five.fst").string().c_str());''')
text=text.replace('started++;unit_starts[k]++;', 'started++;unit_starts[k]++;events<<cycle<<",START,"<<n<<","<<k<<","<<f<<"\\n";')
text=text.replace('completed[n]=true;finished++;', 'completed[n]=true;finished++;events<<cycle<<",COMPLETE,"<<n<<","<<k<<","<<f<<"\\n";')
text=text.replace('need(cycle<20000000,"cycle watchdog")', 'need(cycle<50000000000ULL,"cycle watchdog")')
text=text.replace('d.FCLK_CLK0=1;d.eval();d.FCLK_CLK0=0;d.eval();cycle++;', '''trace->dump(U64(cycle*10000ULL));
  d.FCLK_CLK0=1;d.eval();trace->dump(U64(cycle*10000ULL+5000ULL));d.FCLK_CLK0=0;d.eval();cycle++;
  if(cycle%1000000ULL==0){
   std::ofstream p(out/"progress.json");p<<"{\\"cycles\\":"<<cycle<<",\\"started\\":"<<started<<",\\"finished\\":"<<finished<<",\\"checked_bytes\\":"<<checked<<",\\"page_misses\\":"<<d.debug_page_misses<<",\\"ddr_read_bytes\\":"<<ram.read_bytes<<",\\"ddr_write_bytes\\":"<<ram.write_bytes<<"}\\n";
   std::cout<<"PROGRESS cycle="<<cycle<<" jobs="<<finished<<"/"<<info[2]<<" read="<<ram.read_bytes<<" write="<<ram.write_bytes<<std::endl;
  }''')
text=text.replace('void cfg(U32 a,U32 v){rpc(2,a,v);}', 'void cfg(U32 a,U32 v){rpc(2,a,v);}')
text=text.replace('wr(16,op);wr(20,a);', 'events<<cycle<<",CPU_OP_"<<op<<",0,0,0\\n";wr(16,op);wr(20,a);')
text=text.replace('rpc(5,f,im[f*5+4]);', 'input_cycles[f]=cycle;events<<cycle<<",INPUT_READY,0,0,"<<f<<"\\n";rpc(5,f,im[f*5+4]);')
text=text.replace('rpc(7,r[1],r[4]);got++;', 'result_cycles[f]=cycle;events<<cycle<<",DDR_RESULT,0,0,"<<f<<"\\n";rpc(7,r[1],r[4]);got++;')
text=text.replace('s<16;s++', 's<info[0]*4;s++')
text=text.replace('check=false;rpc(8);', '''std::ofstream timing(out/"output_timing.csv");timing<<"frame,input_cycle,ddr_result_cycle,latency_cycles\\n";
  for(unsigned f=0;f<info[0];f++)timing<<f<<","<<input_cycles[f]<<","<<result_cycles[f]<<","<<result_cycles[f]-input_cycles[f]<<"\\n";
  check=false;rpc(8);''')
text=text.replace('std::cout<<"UNIT_STARTS";', 'trace->close();events.close();\n  std::cout<<"UNIT_STARTS";')
main.write_text(text)
sources=[BASE/s.strip() for s in (BASE/'rtl/filelists/system_ees331_mover23.f').read_text().splitlines() if s.strip() and not s.startswith('#')]
sources += [SIM/'tb/ees331_soc_mover23_sim_top.sv']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'status':'COMPILING','run_dir':str(OUT),'frames':5,'full_network':True,'jobs':655,
        'pool':{'K3':4,'K1':12,'Post':4,'DW7':1,'Add':1,'Pad':1},
        'external_models':'PS GP0 transactions and AXI3 DDR; real CPU/CNN/storage RTL',
        'sources':{str(p.relative_to(BASE)):sha(p) for p in sources+[main,SIM/'tb/integration/ees331_axi_mover_model.hpp',SIM/'firmware/ees331_cpu/program_ram_probe.mem']},
        'started_at':datetime.now().isoformat(),'wave_timescale':'1ps, 10000ps per modeled cycle (100MHz simulation reference)'}
save=lambda:(OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
(SIM/'build/five_soc_active.json').write_text(json.dumps({'run_dir':str(OUT),'status':'RUNNING'},indent=2)+'\n')
save();start=time.monotonic()
try:
 env=dict(os.environ,VERILATOR_ROOT=str(VR))
 flags=['--cc','--exe','--build','--top-module','ees331_soc_mover23_sim_top','--no-timing','-DEES331_EXTERNAL_PS','--assert','--trace-fst','--trace-depth','1','--timescale','1ns/1ps','--output-split-cfuncs','500','-Wno-fatal','-O1','-j','2','-CFLAGS','-std=c++20 -O2 -I'+str(ZLIB/'usr/include'),'-LDFLAGS','-L'+str(ZLIB/'usr/lib/x86_64-linux-gnu'),'--Mdir',str(BUILD/'obj')]
 flags += ['-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
 with (BUILD/'compile.log').open('w') as log:
  subprocess.run([str(VR/'bin/verilator'),*flags,*map(str,sources),str(main)],cwd=SIM,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 record['compile_seconds']=time.monotonic()-start;record['exe_sha256']=sha(BUILD/'obj/Vees331_soc_mover23_sim_top');save()
 for size in ('small','full'):
  dest=OUT/size;dest.mkdir();record['status']='RUNNING_'+size.upper();save();begin=time.monotonic()
  with (dest/'simulation.log').open('w') as log:
   process=subprocess.run([str(BUILD/'obj/Vees331_soc_mover23_sim_top'),str(SIM/('build/fixtures/five_'+size)),str(dest)],cwd=SIM,env=env,stdout=log,stderr=subprocess.STDOUT)
  record[size+'_seconds']=time.monotonic()-begin
  if process.returncode:raise RuntimeError(size+' failed; '+(dest/'simulation.log').read_text()[-2500:])
  assert 'PASS EES331' in (dest/'simulation.log').read_text()
  metrics=json.loads((dest/'metrics.json').read_text());assert metrics['results']==5
  record[size]={'metrics':metrics,'output_sha256':sha(dest/'outputs.bin')};save()
  if size=='full':
   assert metrics['jobs']==655 and metrics['checked_output_bytes']==96686460
   assert record[size]['output_sha256']=='08863d5da4d2febb5a6f60ee8abd41712a48c53ff0c997161e283a87a11fa709'
 record['status']='PASS'
except BaseException as exc:
 record.update(status='FAIL',error=str(exc));raise
finally:
 record['wall_seconds']=time.monotonic()-start;save()
 (SIM/'build/five_soc_active.json').write_text(json.dumps({'run_dir':str(OUT),'status':record['status']},indent=2)+'\n')
print(json.dumps(record,indent=2),flush=True)

