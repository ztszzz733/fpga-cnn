"""Export all recorded 12-client FSM transitions without sampling."""
from pathlib import Path
import subprocess,json,sys,csv
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
g=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator/include/gtkwave');z=SIM/'.tools/zlib-linux/usr'
build=SIM/'build/reduced_state_export';build.mkdir(exist_ok=True)
source=(SIM/'scripts/export_soc_states.cpp').read_text()
a=source.index('std::string unit(');b=source.index('fstEnumHandle table(',a)
source=source[:a]+'''std::string unit(unsigned k){if(k<2)return "K3_"+std::to_string(k);if(k<8)return "K1_"+std::to_string(k-2);if(k<10)return "POST_"+std::to_string(k-8);return k==10?"ADD":"PAD";}
unsigned kind(unsigned k){return k<2?0:k<8?1:k<11?3:4;}
'''+source[b:]
source=source.replace('array<fstHandle,23>','array<fstHandle,12>').replace('array<unsigned,23>','array<unsigned,12>').replace('k<23','k<12').replace('raw+92-4*','raw+48-4*').replace('number(raw,23)','number(raw,12)')
source=source.replace('raw+253-11*(k+1),11','raw+120-10*(k+1),10').replace('c.job[k],11,n','c.job[k],10,n').replace('n%5','n%1').replace('n/5','n/1')
source=source.replace('"TASK",11','"TASK",10').replace('"COMPLETED_TASKS",12','"COMPLETED_TASKS",11').replace('Frame is slot 0..4','One image uses frame slot 0; no DW7 hardware')
cpp=SIM/'scripts/export_reduced_states.cpp';cpp.write_text(source)
objects=[SIM/'build/state_export_tool'/(n+'.o') for n in ('fstapi','fastlz','lz4')]
for n,p in zip(('fstapi','fastlz','lz4'),objects):
 if not p.exists():
  p.parent.mkdir(exist_ok=True)
  subprocess.run(['cc','-O2','-I'+str(z/'include'),'-c',str(g/(n+'.c')),'-o',str(p)],check=True)
exe=build/'export_reduced_states'
subprocess.run(['c++','-O2','-std=c++17','-I'+str(g),'-I'+str(z/'include'),str(cpp),*map(str,objects),str(z/'lib/x86_64-linux-gnu/libz.a'),'-o',str(exe)],check=True)
run=Path(json.loads((SIM/'build/reduced_soc_active.json').read_text())['run_dir'])
which=sys.argv[1] if len(sys.argv)>1 else 'full'
dest=run/which
if '--details-only' not in sys.argv:
 subprocess.run([str(exe),str(dest/'soc_reduced.fst'),str(dest/'soc_states.fst')],check=True)
if which=='full':
 events=list(csv.DictReader((dest/'events.csv').open()))
 cfg_end=next(int(e['cycle']) for e in events if e['event']=='INPUT_READY')
 first=next(int(e['cycle']) for e in events if e['event']=='START' and 2<=int(e['unit'])<8)
 for name,begin,end in [('cpu_config',0,(cfg_end+1000)*10000),('operator_detail',first*10000,(first+128)*10000)]:
  subprocess.run([str(exe),str(dest/'soc_reduced.fst'),str(dest/('soc_'+name+'.fst')),str(begin),str(end)],check=True)
print(dest/'soc_states.fst',flush=True)
