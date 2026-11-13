from pathlib import Path
from datetime import datetime
import json,subprocess,os,time,sys,hashlib,ctypes
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
capacity=int(sys.argv[1]) if len(sys.argv)>1 else 32768
out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_reduced_synth_'+str(capacity));out.mkdir(parents=True)
record={'status':'RUNNING','capacity':capacity,'part':'xc7z020clg484-1','out':str(out)}
sources=[BASE/line.strip() for line in (BASE/'rtl/filelists/system_ees331_reduced.f').read_text().splitlines() if line.strip() and not line.startswith('#')]
record['sources']={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
save();(SIM/'build/reduced_synth_active.json').write_text(json.dumps({'run_dir':str(out),'capacity':capacity},indent=2)+'\n');start=time.monotonic()
cmd=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(out/'vivado.log'),'-source',str(BASE/'scripts/synth_reduced_bram.tcl'),'-tclargs',str(BASE),str(out),str(capacity)]
with (out/'process.log').open('w') as log:
 p=subprocess.Popen(cmd,cwd=out,env=dict(os.environ,XILINX_LOCAL_USER_DATA='no'),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
 record['pid']=p.pid;save()
 try:code=p.wait(timeout=1800)
 except subprocess.TimeoutExpired:
  subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW);p.wait();code=-1
text=(out/'process.log').read_text(errors='replace');record.update(status='PASS' if code==0 and 'REDUCED_BRAM_SYNTH_COMPLETE' in text else 'FAIL',seconds=time.monotonic()-start)
if record['status']=='PASS':
 resources={}
 for line in (out/'utilization.rpt').read_text().splitlines():
  fields=[v.strip().rstrip('*').strip() for v in line.split('|')[1:-1]]
  if len(fields)>=5 and fields[0] in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):resources[fields[0]]=float(fields[1].replace(',',''))
 record['resources']=resources
else:record['errors']=[s for s in text.splitlines() if 'ERROR:' in s][-12:]
save();print(json.dumps(record),flush=True)
if record['status']!='PASS':raise SystemExit(1)
