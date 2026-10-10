from pathlib import Path
import os,shutil,datetime
from run_tests import ROOT,execute
run=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka_bridge')
run.mkdir(parents=True);stage=ROOT.parents[1]/'.neureka_build/bridge';stage.mkdir(parents=True,exist_ok=True)
shutil.copytree(ROOT/'.tools/verilator-linux/verilator',stage/'verilator',dirs_exist_ok=True)
src=['third_party/hwpe-stream/rtl/hwpe_stream_package.sv','third_party/hci/rtl/common/hci_package.sv','third_party/hci/rtl/common/hci_interfaces.sv',
     'rtl/neureka/neureka_banked_bridge.sv','rtl/overlap/datasram_banked.sv','tb/integration/tb_neureka_bridge.sv']
for f in src:shutil.copyfile(ROOT/f,stage/Path(f).name)
for f in (ROOT/'third_party/hci/rtl/common').glob('*.svh'):shutil.copyfile(f,stage/f.name)
env=os.environ.copy();env['VERILATOR_ROOT']=str(stage/'verilator')
print('RUN_DIR='+str(run),flush=True)
execute([stage/'verilator/bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','4',
 '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3','--top-module','tb_neureka_bridge',
 '--Mdir',stage/'obj','-I'+str(stage),*[stage/Path(f).name for f in src]],stage,env,run/'compile.log',timeout=300)
execute([stage/'obj/Vtb_neureka_bridge'],run,env,run/'sim.log',timeout=60)
print((run/'sim.log').read_text())
