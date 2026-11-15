"""Small standalone GDConv/cache verification; does not rebuild either NEureka."""
import argparse,datetime,hashlib,json,os,shutil,time
from pathlib import Path
from run_tests import ROOT,execute

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--reuse',action='store_true');a=p.parse_args()
    run=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_dw7_cached');run.mkdir(parents=True)
    print('RUN_DIR='+str(run),flush=True);beg=time.perf_counter()
    r=dict(status='RUNNING',cases={},timing_seconds={});save=lambda:(run/'result.json').write_text(json.dumps(r,indent=2))
    src=[ROOT/'rtl/cnn_quant/dw7_cached_engine.sv',ROOT/'rtl/cnn_quant/quant_post_engine.sv',ROOT/'tb/integration/tb_dw7_cached.sv']
    r['source_hashes']={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src}
    r['data_hashes']={str(s.relative_to(a.data)):hashlib.sha256(s.read_bytes()).hexdigest() for s in a.data.rglob('*') if s.is_file()}
    save();stage=ROOT.parents[1]/'.dw7_cached_build';stage.mkdir(exist_ok=True)
    vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
    exe=stage/'obj/Vtb_dw7_cached';manifest=stage/'manifest.json';key=dict(hashes=r['source_hashes'],flags=1)
    try:
        stamp=time.perf_counter()
        if a.reuse:assert exe.exists() and json.loads(manifest.read_text())==key,'stale cache'
        else:
            for s in src:shutil.copyfile(s,stage/s.name)
            execute([vr/'bin/verilator','--binary','--timing','--assert','--trace','--trace-max-array','1','-Wno-fatal','-O1','-j','4',
                     '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1',
                     '--top-module','tb_dw7_cached','--Mdir',stage/'obj',*[stage/s.name for s in src]],stage,env,run/'compile.log',timeout=300)
            manifest.write_text(json.dumps(key,indent=2))
        r['timing_seconds']['compile']=0 if a.reuse else time.perf_counter()-stamp;save()
        for name,data,opts in [('real512','real512',[]),('real512_stall','real512',['+stall=1']),
                               ('overlap16','overlap16',[]),('overlap16_stall','overlap16',['+stall=1']),
                               ('overlap16_restart','overlap16',['+stall=1','+restart'])]:
            case=run/name;case.mkdir()
            for s in (a.data/data).iterdir():
                if s.is_file():
                    assert hashlib.sha256(s.read_bytes()).hexdigest()==r['data_hashes'][str(s.relative_to(a.data))]
                    shutil.copyfile(s,case/s.name)
            stamp=time.perf_counter();execute([exe,*opts],case,env,case/'sim.log',timeout=120)
            assert 'PASS tb_dw7_cached' in (case/'sim.log').read_text()
            m=json.loads((case/'metrics.json').read_text());m['output_sha256']=hashlib.sha256((case/'outputs.bin').read_bytes()).hexdigest()
            m['workload']=data;r['cases'][name]=m;r['timing_seconds'][name]=time.perf_counter()-stamp;save();print(name+': '+json.dumps(m),flush=True)
        for group in ['real512','overlap16']:assert len({m['output_sha256'] for m in r['cases'].values() if m['workload']==group})==1
        r['status']='PASS'
    except Exception as e:r['status']='FAIL';r['error']=str(e);print(str(e),flush=True)
    r['timing_seconds']['total']=time.perf_counter()-beg;save();return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
