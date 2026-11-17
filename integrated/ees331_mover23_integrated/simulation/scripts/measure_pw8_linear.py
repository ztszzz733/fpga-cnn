from pathlib import Path
from datetime import datetime
import ctypes,hashlib,json,os,subprocess,time,sys
B=Path(__file__).resolve().parents[2]
H=B/'simulation/build/runs'
OUT=H/('resource_pw8_linear_'+datetime.now().strftime('%Y%m%d_%H%M%S'));OUT.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class MemoryStatus(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
def available():
 m=MemoryStatus();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
def util(p):
 rows={}
 for line in p.read_text().splitlines():
  c=[x.strip().rstrip('*').strip() for x in line.split('|')[1:-1]]
  if len(c)>=5 and c[0] in ['Slice LUTs','Slice Registers','LUT as Memory','Block RAM Tile','DSPs']:rows[c[0]]=float(c[1].replace(',',''))
 assert len(rows)==5,rows
 return rows
def timing(p):
 lines=p.read_text().splitlines()
 for i,l in enumerate(lines[:-2]):
  if 'WNS(ns)' in l:
   try:
    v=lines[i+2].split();return dict(wns_ns=float(v[0]),whs_ns=float(v[4]),setup_failing=int(v[2]),hold_failing=int(v[6]))
   except (ValueError,IndexError):pass
 raise RuntimeError('Missing timing summary')
files=['rtl/cnn_self/compact_word_ram.sv','rtl/cnn_self/self_pw8_engine.sv']
record={'status':'RUNNING','scope':'One PW8; same wrapper/part/clock as address baseline; no full CNN or network','part':'xc7z020clg484-1','period_ns':10,'threads':1,'sources':{n:sha(B/n) for n in files},'baseline':{}}
def save():(OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
old=B/'deliverables/pw8_address_20261113';baseline=json.loads((old/'resource_result.json').read_text())
assert baseline['status']=='PASS' and baseline['sources']['rtl/cnn_self/self_pw8_engine.sv']=='99e94b10cf431ad3a11094fab6983923fdd1218576ffef199cbb9b31de429685'
assert sha(old/'self_pw8_engine.sv')==baseline['sources']['rtl/cnn_self/self_pw8_engine.sv']
assert sha(B/files[0])==baseline['sources'][files[0]]
record['baseline']={'resource_record':str(old/'resource_result.json'),'record_sha256':sha(old/'resource_result.json'),'utilization':baseline['runs']['1']['utilization'],'synthesis_timing':baseline['synthesis_timing'],'route_timing':baseline['implementation_timing']}
for n in files:(OUT/Path(n).name).write_bytes((B/n).read_bytes())
(OUT/'resource_pw8.sv').write_bytes((old/'resource_pw8.sv').read_bytes())
(OUT/'clock.xdc').write_text('create_clock -name clk -period 10 [get_ports clk]\n')
record['staged_hashes']={n:sha(OUT/n) for n in ['compact_word_ram.sv','self_pw8_engine.sv','resource_pw8.sv','clock.xdc']}
save();print(OUT,flush=True)
def launch(stage,lines,limit=360):
 mem=available()/1024**3;record[stage+'_available_before_gib']=mem;save()
 if mem<2.5:raise RuntimeError('Not starting Vivado: under 2.5GiB available; no other process stopped')
 marker='PW8_LINEAR_'+stage.upper()+'_COMPLETE'
 tcl=OUT/(stage+'.tcl');tcl.write_text('\n'.join(['set_param general.maxThreads 1',*lines,'puts '+marker,'exit 0'])+'\n')
 cmd=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(OUT/(stage+'_vivado.log')),'-source',str(tcl)]
 t=time.monotonic();reason=None
 with (OUT/(stage+'_process.log')).open('w') as log:
  p=subprocess.Popen(cmd,cwd=OUT,env=dict(os.environ,XILINX_LOCAL_USER_DATA='no'),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
  record['active_pid']=p.pid;record['active_stage']=stage;save()
  while p.poll() is None:
   if time.monotonic()-t>limit:reason='TIMEOUT';break
   if available()<1536*1024**2:reason='MEMORY_GUARD';break
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:pass
  if reason:
   subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);p.wait(timeout=30)
 text=(OUT/(stage+'_process.log')).read_text(errors='replace')
 record[stage+'_seconds']=time.monotonic()-t
 if reason or p.returncode or marker not in text:raise RuntimeError(stage+': '+str(reason or p.returncode)+' '+ '\n'.join(l for l in text.splitlines() if l.startswith('ERROR:')))
 save()
try:
 lines=['create_project -in_memory -part xc7z020clg484-1']
 for n in ['compact_word_ram.sv','self_pw8_engine.sv','resource_pw8.sv']:lines+=['read_verilog -sv {'+(OUT/n).as_posix()+'}']
 lines+=['read_xdc {'+(OUT/'clock.xdc').as_posix()+'}','synth_design -top resource_pw8 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt']
 for command,name in [('report_utilization','utilization.rpt'),('report_utilization -hierarchical','hierarchical.rpt'),('report_timing_summary -max_paths 5','timing.rpt')]:lines+=[command+' -file {'+(OUT/name).as_posix()+'}']
 lines+=['write_checkpoint -force {'+(OUT/'synth.dcp').as_posix()+'}']
 launch('synth',lines)
 record['utilization']=util(OUT/'utilization.rpt');record['synthesis_timing']=timing(OUT/'timing.rpt')
 record['delta_per_pw8']={k:v-record['baseline']['utilization'][k] for k,v in record['utilization'].items()};save()
 assert record['utilization']['DSPs']==0
 # Same standalone implementation sequence as the baseline; not whole-SoC proof.
 lines=['open_checkpoint {'+(OUT/'synth.dcp').as_posix()+'}','opt_design','place_design','phys_opt_design','route_design',
  'report_timing_summary -max_paths 10 -file {'+(OUT/'implemented_timing.rpt').as_posix()+'}',
  'report_utilization -file {'+(OUT/'implemented_utilization.rpt').as_posix()+'}',
  'write_checkpoint -force {'+(OUT/'routed.dcp').as_posix()+'}']
 launch('route',lines)
 record['implemented_utilization']=util(OUT/'implemented_utilization.rpt');record['implementation_timing']=timing(OUT/'implemented_timing.rpt')
 record['ooc_10ns_met']=record['implementation_timing']['wns_ns']>=0 and record['implementation_timing']['whs_ns']>=0
 record['status']='PASS'
except BaseException as e:
 record.update(status='FAIL',error=str(e));raise
finally:
 record['sources_unchanged']=all(sha(B/n)==h for n,h in record['sources'].items());save()
print(json.dumps(record,indent=2),flush=True)
