"""Focused bridge regression and six-module SoC elaboration, after nv_small generation."""
from run_nvdla_small import ROOT,STAGE,run
from pathlib import Path
import argparse,datetime,json,os,shutil

parser=argparse.ArgumentParser();parser.add_argument('--soc-only',action='store_true');args=parser.parse_args()

out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_nvdla_interfaces')
out.mkdir(parents=True);local=STAGE/'interface_checks';local.mkdir(exist_ok=True)
vr=STAGE/'verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
result={'status':'RUNNING'}
try:
    if not args.soc_only:
        sources=['rtl/nvdla/nvdla_sram_bridge.sv','rtl/overlap/datasram_banked.sv','tb/integration/tb_nvdla_sram_bridge.sv']
        for f in sources:shutil.copyfile(ROOT/f,local/Path(f).name)
        run([vr/'bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','2',
             '--top-module','tb_nvdla_sram_bridge','--Mdir',local/'obj','-CFLAGS','-std=c++20',
             '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3',
             *[local/Path(f).name for f in sources]],local,out/'bridge_compile.log',timeout=120,env=env)
        run([local/'obj/Vtb_nvdla_sram_bridge'],local,out/'bridge_sim.log',timeout=10,env=env)
        if 'PASS bridge:' not in (out/'bridge_sim.log').read_text():raise RuntimeError('missing PASS')
        result['bridge']='PASS'
    paths=[]
    for i,f in enumerate((ROOT/'rtl/filelists/system_nvdla_local.f').read_text().splitlines()):
        path=local/(str(i)+'_'+Path(f).name);shutil.copyfile(ROOT/f,path);paths.append(path)
    run([vr/'bin/verilator','--lint-only','--no-timing','-Wno-fatal','--top-module','face_soc_nvdla_top',
         '-f',STAGE/'adapter/upstream.f',*paths],local,out/'soc_lint.log',timeout=120,env=env)
    result['soc_elaboration']='PASS';result['status']='PASS'
except Exception as error:
    result.update(status='ERROR',error=str(error));raise
finally:
    (out/'result.json').write_text(json.dumps(result,indent=2));print(out,flush=True)
