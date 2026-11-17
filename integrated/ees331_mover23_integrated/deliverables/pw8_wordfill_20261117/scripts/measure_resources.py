from pathlib import Path
import ctypes,datetime,hashlib,json,os,subprocess,time
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent
PROJECT=Path('D:/code/FPGA1/integrated/ees331_mover23_integrated')
unit_name=(ROOT/'active_unit.txt').read_text().strip().replace('/mnt/c/','C:/',1)
gate=json.loads((Path(unit_name)/'result.json').read_text());assert gate['status']=='PASS'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ROOT/'self_pw8_engine.sv')==gate['source_sha256']['self_pw8_engine.sv']
baseline=PROJECT/'deliverables/pw8_oc2_resources_20261115/new'
assert sha(baseline/'self_pw8_engine.sv')==sha(ROOT/'original_engine.sv')
assert sha(baseline/'compact_word_ram.sv')==sha(ROOT/'compact_word_ram.sv')
stamp=datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
OUT=ROOT/'resource_runs'/stamp;OUT.mkdir(parents=True,exist_ok=False)
(ROOT/'active_resource.txt').write_text(str(OUT)+'\n',encoding='utf-8')
class MemoryStatus(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
def available():
 m=MemoryStatus();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available/1024**3
def utilization(path):
 result={}
 for line in path.read_text().splitlines():
  cols=[x.strip().rstrip('*').strip() for x in line.split('|')[1:-1]]
  if len(cols)>=5 and cols[0] in ['Slice LUTs','Slice Registers','LUT as Memory','Block RAM Tile','DSPs','RAMB36/FIFO','RAMB18']:
   result[cols[0]]=float(cols[1].replace(',',''))
 assert len(result)>=5,result
 return result
def timing(path):
 lines=path.read_text().splitlines()
 for i,line in enumerate(lines[:-2]):
  if 'WNS(ns)' in line:
   try:
    v=lines[i+2].split();return dict(wns_ns=float(v[0]),whs_ns=float(v[4]),setup_failing=int(v[2]),hold_failing=int(v[6]))
   except (ValueError,IndexError):pass
 raise RuntimeError('missing timing summary')
record=dict(status='PREPARED',unit_gate=unit_name,scope='Single PW8 with INPUT_WORD_FILL=1; OOC synthesis, same 10ns constraints and ports as verified 20261115 baseline; no implementation or full SoC synthesis',baseline=dict(directory=str(baseline),source_sha256=sha(baseline/'self_pw8_engine.sv'),utilization=utilization(baseline/'utilization.rpt'),timing=timing(baseline/'timing.rpt'),reuse_previous_verified_synthesis=True),candidate_sha256=sha(ROOT/'self_pw8_engine.sv'))
def save():(OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
save();print('Resource run:',OUT,flush=True)
try:
 for name in ['self_pw8_engine.sv','compact_word_ram.sv']:(OUT/name).write_bytes((ROOT/name).read_bytes())
 wrapper=(baseline/'resource_pw8.sv').read_text();assert wrapper.count('.MAX_CHANNELS(512)')==1
 (OUT/'resource_pw8.sv').write_text(wrapper.replace('.MAX_CHANNELS(512)','.MAX_CHANNELS(512),.INPUT_WORD_FILL(1)',1),encoding='utf-8')
 (OUT/'clock.xdc').write_bytes((baseline/'clock.xdc').read_bytes())
 lines=['set_param general.maxThreads 1','create_project -in_memory -part xc7z020clg484-1']
 for name in ['compact_word_ram.sv','self_pw8_engine.sv','resource_pw8.sv']:lines.append('read_verilog -sv {'+(OUT/name).as_posix()+'}')
 lines+=['read_xdc {'+(OUT/'clock.xdc').as_posix()+'}','synth_design -top resource_pw8 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt']
 for cmd,name in [('report_utilization','utilization.rpt'),('report_utilization -hierarchical','hierarchical.rpt'),('report_timing_summary -max_paths 5','timing.rpt')]:lines.append(cmd+' -file {'+(OUT/name).as_posix()+'}')
 lines+=['write_checkpoint -force {'+(OUT/'synth.dcp').as_posix()+'}','puts WORD_FILL_RESOURCE_COMPLETE','exit 0']
 (OUT/'synth.tcl').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
 minimum=available();record['available_before_gib']=minimum;save()
 if minimum<4:raise RuntimeError('Resource run deferred: less than 4GiB available; other processes untouched')
 command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(OUT/'vivado.log'),'-source',str(OUT/'synth.tcl')]
 begin=time.monotonic();reason=None
 with (OUT/'process.log').open('w') as log:
  process=subprocess.Popen(command,cwd=OUT,env=dict(os.environ,XILINX_LOCAL_USER_DATA='no'),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
  record.update(status='RUNNING',active_pid=process.pid);save()
  while process.poll() is None:
   minimum=min(minimum,available())
   if minimum<1.5:reason='memory guard';break
   if time.monotonic()-begin>420:reason='time limit';break
   try:process.wait(timeout=10)
   except subprocess.TimeoutExpired:pass
  if reason:
   subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);process.wait(timeout=30)
 record.update(seconds=time.monotonic()-begin,minimum_available_gib=minimum)
 text=(OUT/'process.log').read_text(errors='replace')
 if reason or process.returncode or 'WORD_FILL_RESOURCE_COMPLETE' not in text:raise RuntimeError(str(reason or process.returncode)+'; see process.log')
 measured=utilization(OUT/'utilization.rpt')
 record.update(status='PASS',utilization=measured,timing=timing(OUT/'timing.rpt'),delta={n:v-record['baseline']['utilization'][n] for n,v in measured.items() if n in record['baseline']['utilization']})
 print(json.dumps({k:record[k] for k in ['utilization','delta','timing','seconds']},indent=2),flush=True)
except Exception as error:
 record.update(status='FAIL',error=str(error));raise
finally:
 save();print('Resource result:',OUT/'result.json',record['status'],flush=True)
