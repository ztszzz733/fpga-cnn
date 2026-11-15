"""Numerical regression with actual compact CNN/cache and AXI3 DDR model.

Full uses the frozen four112x112 assets and requires all four small scenarios
from the identical executable. Never labels a reduced graph as full MobileFaceNet.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
from bootstrap_verilator_native import build_native,VERILATOR
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data',type=Path,default=ROOT/'build/self_full_small')
    ap.add_argument('--reuse',action='store_true');ap.add_argument('--full',action='store_true')
    ap.add_argument('--build-only',action='store_true');ap.add_argument('--gate',type=Path)
    ap.add_argument('--cache-bytes',type=int,default=131072)
    ap.add_argument('--modes',nargs='+',choices=['overlap','serial','preloaded','stress'],default=['overlap','serial','preloaded','stress'])
    ap.add_argument('--pace',type=int,default=80)
    a=ap.parse_args()
    sources=[ROOT/x.strip() for x in (ROOT/'rtl/filelists/cnn_ees331.f').read_text().splitlines() if x.strip() and not x.startswith('#')]+[ROOT/'tb/ees331_cnn_ddr_sim_top.sv']
    main=ROOT/'tb/integration/ees331_cnn_ddr_main.cpp';extra=[ROOT/'tb/integration/ees331_axi_ddr_model.hpp',ROOT/'scripts/bootstrap_verilator_native.py']
    flags=['--no-timing','-DSYNTHESIS','--output-split-cfuncs','500',f'-GCACHE_BYTES={a.cache_bytes}']
    signature=dict(sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources+[main]+extra},flags=flags,verilator_sha=sha(VERILATOR))
    cache=ROOT/'.ees331_full_native'/str(a.cache_bytes);stamp=cache/'signature.json';exe=cache/'cppbuild/sim.exe'
    seconds=0
    if a.reuse:
        old=json.loads(stamp.read_text());assert old['signature']==signature and old['exe_sha256']==sha(exe),'Source/tool changed; rebuild required'
    else:
        start=time.monotonic();exe=build_native(sources,'ees331_cnn_ddr_sim_top',cache,main=main,verilator_args=flags,jobs=4);seconds=time.monotonic()-start
        save(stamp,dict(signature=signature,exe_sha256=sha(exe),compile_seconds=seconds))
    if a.build_only:print(exe);return
    manifest=json.loads((a.data/'manifest.json').read_text());assert bool(manifest['full_network'])==a.full,'--full/data mismatch'
    for n,digest in manifest['files_sha256'].items():assert sha(a.data/n)==digest,'Fixture hash mismatch: '+n
    if a.full:
        assert a.gate,'Full run requires matching small gate'
        gate=json.loads((a.gate/'result.json').read_text())
        assert gate['status']=='PASS' and not gate['full_network'] and gate['exe_sha256']==sha(exe) and set(['overlap','serial','preloaded','stress'])<=set(gate['scenarios']),'Incomplete/different small gate'
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_ees331_full');out.mkdir(parents=True)
    record=dict(status='RUNNING',full_network=a.full,frames=4,cache_bytes=a.cache_bytes,misses_in_flight=1,compile_seconds=seconds,exe_sha256=sha(exe),signature=signature,data_manifest_sha256=sha(a.data/'manifest.json'),scenarios={})
    save(out/'result.json',record);print('RUN_DIR='+str(out),flush=True)
    try:
        for mode in a.modes:
            dest=out/mode;dest.mkdir();start=time.monotonic()
            with (dest/'simulation.log').open('w') as f:r=subprocess.run([str(exe),str(a.data.resolve()),str(dest),mode,str(a.pace)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
            assert r.returncode==0,'Simulation failed: '+str(dest/'simulation.log')
            metric=json.loads((dest/'metrics.json').read_text());assert metric['status']=='PASS'
            metric['outputs_sha256']=sha(dest/'outputs.bin');record['scenarios'][mode]=metric
            if a.full:assert metric['outputs_sha256']=='80351fb04be5c55bc45d6e6fcadaef6680b20d0532d15f7bb5bf5c661416a44f','Full output hash changed'
            save(out/'result.json',record);print(mode+' PASS '+str(metric['cycles'])+' cycles '+str(round(time.monotonic()-start,2))+'s',flush=True)
        assert len({v['outputs_sha256'] for v in record['scenarios'].values()})==1,'Scenario outputs differ'
        record['sources_unchanged_during_run']=all(sha(ROOT/n)==h for n,h in signature['sources'].items())
        assert record['sources_unchanged_during_run'],'Source changed during run'
        record['status']='PASS'
    except Exception as e:record.update(status='FAIL',error=str(e));raise
    finally:save(out/'result.json',record)
if __name__=='__main__':main()
