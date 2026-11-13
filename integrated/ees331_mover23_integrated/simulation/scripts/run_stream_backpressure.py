"""Directed UART packet-ring backpressure check, separate from six-frame run."""
from pathlib import Path
import tempfile,shutil,json
from datetime import datetime
from run_tests import ROOT,tools,tool_env,execute
run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_stream_backpressure');run.mkdir(parents=True)
env=tool_env(tools())
with tempfile.TemporaryDirectory(prefix='stream_pressure_') as tmp:
    stage=Path(tmp);shutil.copytree(ROOT/'.tools/verilator-linux/verilator',stage/'verilator')
    env['VERILATOR_ROOT']=str(stage/'verilator')
    paths=[]
    for source in ['rtl/soc/autoload/autoload_uart.sv','rtl/stream/image_bridge_stream.sv','tb/integration/tb_stream_backpressure.sv']:
        target=stage/Path(source).name;shutil.copyfile(ROOT/source,target);paths.append(target)
    execute([stage/'verilator/bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','4','-CFLAGS','-std=c++20',
             '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3','--top-module','tb_stream_backpressure','--Mdir',stage/'obj',*paths],
            stage,env,run/'compile.log',timeout=300)
    execute([stage/'obj/Vtb_stream_backpressure'],run,env,run/'sim.log',timeout=60)
log=(run/'sim.log').read_text();assert 'PASS tb_stream_backpressure' in log
(run/'result.json').write_text(json.dumps(dict(status='PASS',case='two packet slots saturated and consumer throttled'),indent=2))
print(run);print(log)
