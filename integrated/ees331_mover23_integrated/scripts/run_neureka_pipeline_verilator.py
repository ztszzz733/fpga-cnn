"""Portable real-core regression (Linux/WSL or native Verilator toolchain).
No compiler download, no old build-cache dependency, no arithmetic test doubles.
"""
import datetime,hashlib,json,os,shutil
from pathlib import Path
from run_tests import ROOT,execute
from neureka_pipeline_sources import sources
from gen_neureka_pipeline import generate

def main():
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka_pipeline_verilator'
    out=ROOT/'build/runs'/stamp;out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'real CPU/NEureka/Vicuna/SRAM; preloaded memory, UART idle'}
    try:
        verilator=os.environ.get('VERILATOR') or shutil.which('verilator')
        if not verilator:raise RuntimeError('Install/provide Verilator and a C++ build toolchain, or set VERILATOR; no fake core fallback')
        generate(out);src,inc,defs=sources();src.append(ROOT/'tb/integration/tb_neureka_pipeline.sv')
        result['sources']={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src}
        stage=ROOT.parents[1]/'.neureka_pipeline_build'/stamp;stage.mkdir(parents=True)
        if ' ' in str(stage):raise RuntimeError('Verilator make staging path must not contain spaces: '+str(stage))
        staged=[]
        for i,s in enumerate(src):
            dest=stage/(str(i)+'_'+s.name);dest.write_bytes(s.read_bytes());staged.append(dest)
        includes=[]
        for i,d in enumerate(inc):
            dest=stage/('include'+str(i));dest.mkdir()
            for suffix in ['*.svh','*.vh']:
                for header in d.rglob(suffix):
                    target=dest/header.relative_to(d);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(header.read_bytes())
            includes+=['-I'+str(dest)]
        env=os.environ.copy()
        execute([verilator,'--binary','--timing','--assert','-Wno-fatal','-Wno-ENUMVALUE','-Wno-BLKANDNBLK',
            '--unroll-count','1024','-j','2','--top-module','tb_neureka_pipeline','--Mdir',stage/'obj',
            *['-D'+d for d in defs],*includes,*staged],stage,env,out/'compile.log',7200)
        result['compiled']=True
        exe=stage/'obj'/('Vtb_neureka_pipeline.exe' if os.name=='nt' else 'Vtb_neureka_pipeline')
        result['simulator_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
        execute([exe],out,env,out/'sim.log',1200)
        assert 'PASS tb_neureka_pipeline' in (out/'sim.log').read_text()
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2));print('STATUS='+result['status'],flush=True)
if __name__=='__main__':main()
