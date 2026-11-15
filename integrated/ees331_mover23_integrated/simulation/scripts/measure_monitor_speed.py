from pathlib import Path
import json,subprocess,os,signal,time
root=Path(__file__).resolve().parents[1]
runs=[Path(json.loads((root/'build'/name).read_text())['run_dir']) for name in ('five_soc_active.json','five_soc_fast_active.json')]
targets={str(r/'compile/obj/Vees331_soc_mover23_sim_top') for r in runs}
processes=[]
for line in subprocess.check_output(['ps','-eo','pid=,args='],text=True).splitlines():
 parts=line.strip().split(None,1)
 if len(parts)==2 and parts[1].split()[0] in targets:processes.append(int(parts[0]))
timings={}
try:
 for p in processes:os.kill(p,signal.SIGSTOP)
 for name,run in zip(('original','optimized'),runs):
  dest=run/'speed_gate';dest.mkdir(exist_ok=True);start=time.monotonic()
  with (dest/'simulation.log').open('w') as log:
   subprocess.run([str(run/'compile/obj/Vees331_soc_mover23_sim_top'),str(root/'build/fixtures/five_small'),str(dest)],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
  timings[name]=time.monotonic()-start
 assert (runs[0]/'speed_gate/metrics.json').read_bytes()==(runs[1]/'speed_gate/metrics.json').read_bytes()
finally:
 for p in processes:os.kill(p,signal.SIGCONT)
(root/'build/monitor_speed.json').write_text(json.dumps(timings,indent=2)+'\n')
print(json.dumps(timings),flush=True)
