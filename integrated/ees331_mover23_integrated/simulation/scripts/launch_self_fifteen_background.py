"""Launch one detached Linux runner. It still cannot survive WSL shutdown/reboot."""
from pathlib import Path
from datetime import datetime
import json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
gate=ROOT/'build/runs/20261025_150333_123534_self_fifteen'
assert json.loads((gate/'result.json').read_text())['status']=='PASS'
name=datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_self_fifteen'
run=ROOT/'build/runs'/name
log=ROOT/'build/runs'/(name+'.launcher.log')
command=[sys.executable,str(ROOT/'scripts/run_self_six_wsl.py'),'--frames','15','--pw8','--frame-priority','--dw-cache','--post-group','16','--reuse','--full','--data',str(ROOT/'build/self_fifteen_full'),'--gate',str(gate),'--run-dir',str(run)]
with log.open('x') as f:
 p=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
info=dict(run=str(run),pid=p.pid,launcher_log=str(log),command=command,started_at=datetime.now().isoformat(),scope='Detached from calling shell; no runtime checkpoint and cannot survive WSL shutdown')
(ROOT/'build/self_fifteen_active.json').write_text(json.dumps(info,indent=2))
print(json.dumps(info),flush=True)
