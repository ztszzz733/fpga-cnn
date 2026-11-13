"""Offline schedule screening using measured task durations; not an RTL result.

The model ignores changing SRAM contention, scan overhead and handoff latency.
It cannot prove a speedup, correctness, or an indefinitely sustained output rate.
"""
from pathlib import Path
import heapq
import json
import hashlib

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'deliverables/self_cnn_ten_20261024_014153_249128_self_ten'
POOLS={'3×3':'K3','DW3':'K3','1×1':'K1','DW7':'DW7','后处理':'Post','Add':'Add','补边':'Pad'}
CAP={'K3':2,'K1':4,'DW7':1,'Post':1,'Add':1,'Pad':1}

def main():
    rows=json.loads((BASE/'task_timeline/tasks.json').read_text(encoding='utf-8'))
    frames=sorted({r['frame'] for r in rows})
    tasks={f:[r for r in rows if r['frame']==f and r['node'] is not None] for f in frames}
    commits={r['frame']:r['end'] for r in rows if r['kind']=='输入'}
    report={'scope':__doc__,'source_sha256':hashlib.sha256((BASE/'task_timeline/tasks.json').read_bytes()).hexdigest(),'policies':{}}
    policies=['node_order','ready_fifo','oldest_frame','furthest_step','depthwise_first']
    policies += [f'oldest_frame_gap_{ms}' for ms in (125,150,160,175,200)]
    policies += [f'oldest_frame_window_{n}' for n in (3,4,5,6)]
    for policy in policies:
        next_job={f:0 for f in frames};ready=dict(commits);active=set();ends={};heap=[];free=dict(CAP);t=0;trace=[]
        started=set();window=int(policy.rsplit('_',1)[1]) if '_window_' in policy else len(frames)
        if '_gap_' in policy:
            gap=int(policy.rsplit('_',1)[1])*100000
            ready={f:max(commits[f],min(commits.values())+i*gap) for i,f in enumerate(frames)}
        while len(ends)<len(frames):
            while heap and heap[0][0]<=t:
                end,f,pool=heapq.heappop(heap);active.remove(f);free[pool]+=1;next_job[f]+=1;ready[f]=end
                if next_job[f]==len(tasks[f]):ends[f]=end
            for pool in CAP:
                candidates=[f for f in frames if f not in active and f not in ends and ready[f]<=t and POOLS[tasks[f][next_job[f]]['kind']]==pool and (f in started or len(started)-len(ends)<window)]
                def key(f):
                    j=tasks[f][next_job[f]]
                    if policy=='node_order':return (j['node'],)
                    if policy=='ready_fifo':return (ready[f],f)
                    if policy.startswith('oldest_frame'):return (commits[f],ready[f],j['node'])
                    if policy=='furthest_step':return (-next_job[f],commits[f])
                    return (j['kind']!='DW3',commits[f],j['node'])
                for f in sorted(candidates,key=key)[:free[pool]]:
                    j=tasks[f][next_job[f]];end=t+j['end']-j['start']
                    free[pool]-=1;active.add(f);started.add(f);heapq.heappush(heap,(end,f,pool));trace.append(dict(frame=f,node=j['node'],start=t,end=end,pool=pool))
            future=[h[0] for h in heap]+[ready[f] for f in frames if f not in ends and f not in active and ready[f]>t]
            if not future:
                assert len(ends)==len(frames);break
            t=min(future)
        ordered=sorted(ends.items(),key=lambda kv:kv[1]);times=[end/1e5 for _,end in ordered]
        report['policies'][policy]=dict(first_ms=times[0],batch_ms=times[-1],output_order=[f-99 for f,_ in ordered],output_ms=times,
            gaps_ms=[b-a for a,b in zip(times,times[1:])],trace=trace)
    dest=ROOT/'build/self_ten_schedule_screen';dest.mkdir(exist_ok=True)
    (dest/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,p in report['policies'].items():
        print(name,json.dumps({k:v for k,v in p.items() if k!='trace'}))

if __name__=='__main__':main()
