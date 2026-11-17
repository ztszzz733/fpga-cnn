"""Same-flow OOC synthesis of the exact linear 8-MAC and new 16-MAC PW8."""
from pathlib import Path
from datetime import datetime
import ctypes,hashlib,json,os,subprocess,time,sys
B=Path(__file__).resolve().parents[2]
H=B/'simulation/build/runs'
OUT=H/('resource_pw8_oc2_'+datetime.now().strftime('%Y%m%d_%H%M%S'));OUT.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class MemoryStatus(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
def available():
 m=MemoryStatus();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
def util(p):
 rows={}
 for line in p.read_text().splitlines():
  c=[x.strip().rstrip('*').strip() for x in line.split('|')[1:-1]]
  if len(c)>=5 and c[0] in ['Slice LUTs','Slice Registers','LUT as Memory','Block RAM Tile','DSPs','RAMB36/FIFO','RAMB18']:
   rows[c[0]]=float(c[1].replace(',',''))
 assert all(n in rows for n in ['Slice LUTs','Slice Registers','LUT as Memory','Block RAM Tile','DSPs']),rows
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
old=B/'deliverables/pw8_oc2_20261115/original_engine.sv'
assert sha(old)=='0a16ba33f74962235d487abd3d151635f2238e821b9ed4ae0709bfd2a16248c6'
assert sha(B/files[1])=='f34b3c290c6e7624460e8a7f03f6288d3238f1c9db9ad2ecc6400fcd0421567c'
gate=json.loads((B/'deliverables/pw8_oc2_20261115/result.json').read_text());assert gate['soc_jobs']==8 and gate['unit_parameter_cases']==213
record={'status':'PREPARED','scope':'One exact PW8, old 8 MAC versus new 16 MAC; no full CNN/SoC synthesis','part':'xc7z020clg484-1','period_ns':10,'max_channels':512,'kernel_fixed':1,'threads':1,'flatten_hierarchy':'rebuilt','flow':'Vivado 2025.2 out_of_context synthesis only; no place/route','sources':{n:sha(B/n) for n in files},'baseline_pw8_sha256':sha(old),'function_gate_sha256':sha(B/'deliverables/pw8_oc2_20261115/result.json'),'runs':{}}
def save():
 (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 (H/'pw8_oc2_resource_active.json').write_text(json.dumps({'status':record['status'],'run_dir':str(OUT)},indent=2)+'\n')
save();print(OUT,flush=True)
try:
 for mode in ['old','new']:
  d=OUT/mode;d.mkdir()
  (d/'self_pw8_engine.sv').write_bytes(old.read_bytes() if mode=='old' else (B/files[1]).read_bytes())
  (d/'compact_word_ram.sv').write_bytes((B/files[0]).read_bytes())
  (d/'resource_pw8.sv').write_bytes((B/'deliverables/pw8_address_20261113/resource_pw8.sv').read_bytes())
  (d/'clock.xdc').write_text('create_clock -name clk -period 10 [get_ports clk]\n')
  record['runs'][mode]={'status':'PREPARED','staged_hashes':{n:sha(d/n) for n in ['compact_word_ram.sv','self_pw8_engine.sv','resource_pw8.sv','clock.xdc']}}
  mem=available()/1024**3;record['runs'][mode]['available_before_gib']=mem;save()
  if mem<4:raise RuntimeError('Not starting '+mode+': under 4GiB available; other jobs untouched')
  lines=['set_param general.maxThreads 1','create_project -in_memory -part xc7z020clg484-1']
  for n in ['compact_word_ram.sv','self_pw8_engine.sv','resource_pw8.sv']:lines.append('read_verilog -sv {'+(d/n).as_posix()+'}')
  lines+=['read_xdc {'+(d/'clock.xdc').as_posix()+'}','synth_design -top resource_pw8 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt',
   'report_utilization -file {'+(d/'utilization.rpt').as_posix()+'}',
   'report_utilization -hierarchical -file {'+(d/'hierarchical.rpt').as_posix()+'}',
   'report_timing_summary -max_paths 5 -file {'+(d/'timing.rpt').as_posix()+'}',
   'write_checkpoint -force {'+(d/'synth.dcp').as_posix()+'}','puts PW8_OC2_RESOURCE_COMPLETE','exit 0']
  (d/'synth.tcl').write_text('\n'.join(lines)+'\n',newline='\n')
  cmd=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(d/'vivado.log'),'-source',str(d/'synth.tcl')]
  t=time.monotonic();reason=None;minimum=mem
  with (d/'process.log').open('w') as log:
   p=subprocess.Popen(cmd,cwd=d,env=dict(os.environ,XILINX_LOCAL_USER_DATA='no'),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
   record.update(status='SYNTHESIZING_'+mode.upper(),active_pid=p.pid);record['runs'][mode]['status']='RUNNING';save()
   while p.poll() is None:
    minimum=min(minimum,available()/1024**3)
    if time.monotonic()-t>420:reason='TIMEOUT';break
    if minimum<1.5:reason='MEMORY_GUARD';break
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:pass
   if reason:
    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);p.wait(timeout=30)
  record['runs'][mode].update(seconds=time.monotonic()-t,minimum_available_gib=minimum)
  text=(d/'process.log').read_text(errors='replace')
  if reason or p.returncode or 'PW8_OC2_RESOURCE_COMPLETE' not in text:
   record['runs'][mode]['status']='FAIL';raise RuntimeError(mode+': '+str(reason or p.returncode)+' '+ '\n'.join(l for l in text.splitlines() if l.startswith('ERROR:')))
  record['runs'][mode].update(status='PASS',utilization=util(d/'utilization.rpt'),synthesis_timing=timing(d/'timing.rpt'));save()
 a=record['runs']['old'];b=record['runs']['new']
 for n in ['compact_word_ram.sv','resource_pw8.sv','clock.xdc']:assert a['staged_hashes'][n]==b['staged_hashes'][n]
 record['delta_per_pw8']={k:v-a['utilization'][k] for k,v in b['utilization'].items() if k in a['utilization']}
 record['estimated_delta_six_pw8']={k:6*v for k,v in record['delta_per_pw8'].items()}
 record['status']='PASS'
except BaseException as e:
 record.update(status='FAIL',error=str(e));raise
finally:
 record['sources_unchanged']=all(sha(B/n)==h for n,h in record['sources'].items());save()
print(json.dumps(record,indent=2),flush=True)
