"""Recount remaining real modules with hierarchy preserved and no timing/DCP overhead."""
import argparse,ctypes,hashlib,json,os,re,subprocess,time
from datetime import datetime
from pathlib import Path
ROOT=Path('D:/code/FPGA1/cpu_control (2)/cpu_control')
class Mem(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(x,ctypes.c_ulonglong) for x in ['total','available','p1','p2','v1','v2','extra']]
def free():
    m=Mem();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--components',nargs='+',choices=['fabric','bridge','dispatch','results','programmer','dw7','leases']);ap.add_argument('--timeout',type=int);args=ap.parse_args()
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_missing_resources');run.mkdir(parents=True)
    state=dict(status='RUNNING',method='OOC, flatten_hierarchy none, 1 thread; resource reports only',part='xc7z020clg484-1',components={});out=run/'result.json'
    def save():out.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    save();print('RUN_DIR='+str(run),flush=True)
    cases=[('fabric','20261025_175608_695778_pool_resources_fabric',None,240),('bridge','20261109_191404_753950_soc_resource_audit','bridge',240),('dispatch','20261025_175659_663862_pool_resources_dispatch',None,240),('results','20261025_175823_028191_pool_resources_results',None,240),('programmer','20261025_180208_206018_pool_resources_programmer',None,240),('dw7','20261025_174624_483215_pool_resources_dw7',None,600),('leases','20261025_175800_617034_pool_resources_leases',None,90)]
    for key,old_name,sub,limit in cases:
        if args.components and key not in args.components:continue
        if args.timeout:limit=args.timeout
        # Wait for the previous process's memory to be returned before starting.
        t=time.monotonic()
        while free()<2500*1024**2 and time.monotonic()-t<30:time.sleep(2)
        old=ROOT/'build/runs'/old_name;meta=json.loads((old/'result.json').read_text(encoding='utf-8'));meta=meta['components'][sub] if sub else meta
        srcs=meta.get('source_sha256',meta.get('sources_sha256',{}))
        assert all(sha(ROOT/k)==v for k,v in srcs.items())
        stage=ROOT.parents[1]/'.self_synth_launch'/run.name/key;stage.mkdir(parents=True)
        target=run/key;target.mkdir()
        original=ROOT.parents[1]/'.self_synth_launch'/old_name
        if sub:original=original/sub
        for p in original.glob('*.sv'):(stage/p.name).write_bytes(p.read_bytes())
        tcl=(original/'entry.tcl').read_text()
        # All source contents, parameters and black-box boundaries stay identical.
        tcl=tcl.replace(original.as_posix(),stage.as_posix()).replace(str(original),str(stage))
        for old_out in [old/(sub or ''),old]:
            tcl=tcl.replace(old_out.as_posix(),target.as_posix()).replace(str(old_out),str(target))
        (stage/'clock.xdc').write_bytes((original/'clock.xdc').read_bytes())
        tcl=tcl.replace('general.maxThreads 2','general.maxThreads 1').replace('-flatten_hierarchy rebuilt','-flatten_hierarchy none')
        tcl='\n'.join(x for x in tcl.splitlines() if not x.startswith(('report_timing_summary','write_checkpoint','puts POOL_RESOURCES_COMPLETE','puts SOC_RESOURCE_COMPLETE','exit ')))
        tcl+='\nputs MISSING_RESOURCE_COMPLETE\nexit 0\n';(stage/'entry.tcl').write_text(tcl,newline='\n')
        r=dict(status='RUNNING',source_sha256=srcs,old_run=str(old),staged_sha256={p.name:sha(p) for p in stage.glob('*.sv')},timeout=limit);state['components'][key]=r;save()
        cmd=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(stage/'vivado.log'),'-source',str(stage/'entry.tcl')]
        env=os.environ.copy();env['XILINX_LOCAL_USER_DATA']='no';begin=time.monotonic();reason=None
        with (target/'process.log').open('w',encoding='utf-8') as log:
            p=subprocess.Popen(cmd,cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);r['launcher_pid']=p.pid;save()
            while p.poll() is None:
                if time.monotonic()-begin>limit:reason='TIMEOUT';break
                if free()<1536*1024**2:reason='MEMORY_GUARD';break
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
            if reason:
                killed=subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW);r['kill_returncode']=killed.returncode;p.wait(timeout=30)
        text=(target/'process.log').read_text(encoding='utf-8',errors='replace')
        r.update(status=reason or ('PASS' if p.returncode==0 and 'MISSING_RESOURCE_COMPLETE' in text else 'FAIL'),seconds=round(time.monotonic()-begin,3),errors=[x for x in text.splitlines() if x.startswith('ERROR:')][-6:],sources_unchanged=all(sha(ROOT/k)==v for k,v in srcs.items()))
        if r['status']=='PASS':
            vals={}
            for line in (target/'utilization.rpt').read_text().splitlines():
                c=[v.strip().rstrip('*').strip() for v in line.split('|')[1:-1]]
                if len(c)>=5 and c[0] in ['Slice LUTs','Slice Registers','Block RAM Tile','DSPs']:vals[c[0]]=float(c[1].replace(',',''))
            r['resources']=vals
        save();print(key+' '+r['status']+' '+json.dumps(r.get('resources',r['errors'])),flush=True)
    state['status']='PASS' if all(x['status']=='PASS' for x in state['components'].values()) else 'PARTIAL';save();print('COMPLETE '+str(run),flush=True)
if __name__=='__main__':main()
