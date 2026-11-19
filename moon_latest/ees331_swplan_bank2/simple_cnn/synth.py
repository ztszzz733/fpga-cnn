from pathlib import Path
import ctypes,hashlib,json,subprocess,time
BASE=Path(__file__).resolve().parent
OUT=BASE/'synthesis';OUT.mkdir(exist_ok=True)
class Memory(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),*[(n,ctypes.c_ulonglong) for n in ['total_phys','free_phys','total_page','free_page','total_virtual','free_virtual','free_ext']]]
def mem():
 m=Memory();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.free_page/2**30
files=sorted(p for p in (BASE/'rtl').glob('*.sv') if p.name!='face_soc_ees331_simple_top.sv')
(OUT/'clock.xdc').write_text('create_clock -name cnn_clk -period 10.000 [get_ports clk]\n')
lines=['set_param general.maxThreads 1','create_project -in_memory -part xc7z020clg484-1']
lines+=['read_verilog -sv {'+p.as_posix()+'}' for p in files]
lines+=['read_xdc {'+(OUT/'clock.xdc').as_posix()+'}',
 'synth_design -top cnn_simple_top -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt',
 'write_checkpoint -force {'+(OUT/'synth.dcp').as_posix()+'}',
 'report_utilization -file {'+(OUT/'utilization.rpt').as_posix()+'}',
 'report_utilization -hierarchical -file {'+(OUT/'hierarchy.rpt').as_posix()+'}',
 'check_timing -verbose -file {'+(OUT/'check_timing.rpt').as_posix()+'}',
 'report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 -file {'+(OUT/'timing.rpt').as_posix()+'}',
 'report_timing -delay_type max -max_paths 20 -nworst 1 -input_pins -file {'+(OUT/'paths.rpt').as_posix()+'}',
 'puts SIMPLE_CNN_SYNTH_COMPLETE','exit 0']
(OUT/'synth.tcl').write_text('\n'.join(lines)+'\n')
result={'status':'PREPARING','clock_ns':10,'part':'xc7z020clg484-1','top':'cnn_simple_top','max_channels':512,
        'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'free_commit_gib':mem()}
def save(): (OUT/'result.json').write_text(json.dumps(result,indent=2))
save()
assert result['free_commit_gib']>=4,'Insufficient free commit before synthesis'
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
t=time.perf_counter()
with (OUT/'launcher.log').open('w') as log:
 p=subprocess.Popen(['D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace','-source',str(OUT/'synth.tcl'),'-log',str(OUT/'vivado.log'),'-journal',str(OUT/'vivado.jou')],cwd=OUT,stdout=log,stderr=subprocess.STDOUT,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
 result.update(status='RUNNING',pid=p.pid);save()
 while p.poll() is None:
  time.sleep(3)
  if mem()<2:
   subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW);p.wait();result['status']='MEMORY_GUARD';break
 result.update(exit_code=p.returncode,wall_seconds=time.perf_counter()-t)
if result['status']=='RUNNING':result['status']='COMPLETE' if p.returncode==0 and 'SIMPLE_CNN_SYNTH_COMPLETE' in (OUT/'vivado.log').read_text(errors='replace') else 'ERROR'
save();print(json.dumps(result,indent=2))
