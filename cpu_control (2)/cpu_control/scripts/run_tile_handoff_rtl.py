"""Check tile arithmetic on the unmodified real CNN/SRAM RTL, not MOVER RTL.

Use --exe for a hash-matched existing simulator, or --build with Verilator.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('bundle',type=Path)
    ap.add_argument('--exe',type=Path);ap.add_argument('--build',action='store_true')
    ap.add_argument('--verilator',default='verilator');ap.add_argument('--verilator-root')
    a=ap.parse_args();root=a.bundle.resolve();signature=read(root/'source_snapshot/build_signature.json')
    assert bool(a.exe)!=a.build,'select --exe or --build'
    for name,h in signature['signature']['sources'].items():assert sha(root/'source_snapshot'/name)==h,name
    compile_seconds=0
    if a.build:
        cache=root/'rebuild';cache.mkdir(exist_ok=True);flags=signature['signature']['flags'].copy()
        files=[root/'source_snapshot'/name for name in signature['signature']['sources']]
        env=dict(os.environ)
        if a.verilator_root:env['VERILATOR_ROOT']=a.verilator_root
        began=time.perf_counter()
        with (cache/'compile.log').open('w') as log:
            subprocess.run([a.verilator,*flags,'--Mdir',str(cache/'obj'),*[str(p) for p in files]],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        compile_seconds=time.perf_counter()-began;exe=cache/'obj/Vself_full_sim_top'
    else:
        exe=a.exe.resolve();assert sha(exe)==signature['exe_sha256'],'simulator is not the checked source/configuration'
    dest=root/'evidence/tile_core_rtl';dest.mkdir(parents=True,exist_ok=False)
    result=dict(status='RUNNING',scope='Real K3/Post/Add and existing SRAM RTL only; no new MOVER/DDR/local-RAM adapter RTL',
        compile_seconds=compile_seconds,exe_sha256=sha(exe),sources=signature['signature']['sources'],scenarios={})
    save(dest/'result.json',result)
    try:
        for case in sorted((root/'cases').iterdir()):
            if not case.is_dir() or not (case/'manifest.json').exists():continue
            manifest=read(case/'manifest.json')
            for mode in ('overlap','preloaded','stress'):
                out=dest/(case.name+'_'+mode);out.mkdir();began=time.perf_counter()
                with (out/'simulation.log').open('w') as log:
                    subprocess.run([str(exe),str(case/'native_fixture'),str(out),mode,'80','5000000'],stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True)
                metrics=read(out/'metrics.json')
                for key,value in dict(status='PASS',commands=3,expanded_commands=3,allocations=3,releases=3,results=1,
                    macs=manifest['macs'],checked_bytes=manifest['checked_output_bytes']).items():assert metrics[key]==value,(case.name,key)
                assert (out/'outputs.bin').read_bytes()==(case/'golden_add_uint8.bin').read_bytes()
                result['scenarios'][out.name]=dict(status='PASS',cycles=metrics['cycles'],wall_seconds=time.perf_counter()-began,
                    checked_bytes=metrics['checked_bytes'],macs=metrics['macs'],output_sha256=sha(out/'outputs.bin'))
                save(dest/'result.json',result);print('PASS '+out.name+' '+str(metrics['cycles'])+' cycles',flush=True)
        assert len(result['scenarios'])==6
        result['status']='PASS'
    except BaseException as exc:
        result['status']='FAIL';result['error']=repr(exc);raise
    finally:save(dest/'result.json',result)

if __name__=='__main__':main()
