from pathlib import Path
import datetime,json,os,shutil
from run_nvdla_small import ROOT,STAGE as NV,run
stage=ROOT.parents[1]/'.hybrid_build/adapter_checks';stage.mkdir(parents=True,exist_ok=True)
out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_hybrid_adapters');out.mkdir(parents=True)
files=['rtl/hybrid/vicuna_sram_port.sv','rtl/hybrid/cnn_command_port.sv','tb/integration/tb_hybrid_adapters.sv']
for f in files:shutil.copyfile(ROOT/f,stage/Path(f).name)
vr=NV/'verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
result={'status':'RUNNING'}
try:
    result['compile_seconds']=run([vr/'bin/verilator','--binary','--timing','--assert','-Wno-fatal',
        '--top-module','tb_hybrid_adapters','-j','1','--Mdir',stage/'obj','-CFLAGS','-std=c++20',
        '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3',
        *[stage/Path(f).name for f in files]],stage,out/'compile.log',120,env)
    result['simulation_seconds']=run([stage/'obj/Vtb_hybrid_adapters'],stage,out/'sim.log',15,env)
    assert 'PASS hybrid adapters:' in (out/'sim.log').read_text()
    result['status']='PASS'
except BaseException as e:result.update(status='ERROR',error=str(e));raise
finally:
    (out/'result.json').write_text(json.dumps(result,indent=2));print(out,flush=True)
