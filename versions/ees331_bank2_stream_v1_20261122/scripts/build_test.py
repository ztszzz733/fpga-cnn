import argparse
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
p.add_argument('variant')
p.add_argument('test', choices=['dma','pager','cnn','bridge','integration'])
a=p.parse_args()
root=Path(__file__).resolve().parent.parent
variants={'final':'project','stage3_cnn_stream':'project','baseline':'reference/baseline',
          'stage1_local_stream':'reference/stage1_local_stream','stage2_axi_stream':'reference/stage2_axi_stream'}
if a.variant not in variants:raise SystemExit('Unknown variant: '+a.variant)
project=root / variants[a.variant]
out=root / 'build' / a.variant / a.test
out.mkdir(parents=True,exist_ok=True)
tests=root / 'tests'
top={'dma':'data_mover','pager':'cnn_paged_mover','cnn':'cnn_simple_top','bridge':'simple_mem_bridge','integration':'cnn_storage_top'}[a.test]
if a.test=='integration':
    sources=[project/'simple_cnn/rtl'/x for x in ['compact_word_ram.sv','simple_k3_engine.sv',
             'simple_k1_engine.sv','simple_mem_bridge.sv','cnn_simple_top.sv']]
    sources += [project/'source'/x for x in ['rtl/cnn_ddr/cnn_paged_mover.sv','storage_v2/rtl/data_mover.sv',
                'storage_v2/rtl/tile_local_ram.sv','storage_v2/rtl/tile_local_ram_bank2.sv']]
    sources.append(tests/'cnn_storage_top.sv')
    test=tests/'simple_cnn/test_storage.cpp'
    params=[]
elif a.test=='bridge':
    sources=[project/'simple_cnn/rtl/simple_mem_bridge.sv']
    test=tests/'bridge_stream.cpp'
    params=[]
elif a.test=='dma':
    sources=[project / 'source/storage_v2/rtl/data_mover.sv']
    test=tests / 'dma_stream.cpp'
    params=['-GTIMEOUT_CYCLES=32']
elif a.test=='pager':
    sources=[project / 'source' / x for x in ['rtl/cnn_ddr/cnn_paged_mover.sv',
             'storage_v2/rtl/data_mover.sv','storage_v2/rtl/tile_local_ram.sv','storage_v2/rtl/tile_local_ram_bank2.sv']]
    test=tests / 'arm_schedule/pager_regression.cpp'
    params=['-GCLIENTS=10','-GLOCAL_BYTES=401408']
else:
    sources=[project / 'simple_cnn/rtl' / x for x in ['compact_word_ram.sv','simple_k3_engine.sv',
             'simple_k1_engine.sv','simple_mem_bridge.sv','cnn_simple_top.sv']]
    test=tests / 'simple_cnn/test_stream.cpp'
    params=[]
env=os.environ.copy()
env['VERILATOR_ROOT']='C:/msys64/ucrt64/share/verilator'
env['PATH']='C:/msys64/ucrt64/bin;'+env['PATH']
cmd=['C:/msys64/ucrt64/bin/verilator_bin.exe','--cc','--exe','--assert','--no-timing',
     '--top-module',top,'-Wno-fatal','-O1','--output-split','25000','--Mdir',out.as_posix(),
     *params,*[x.as_posix() for x in sources],test.as_posix()]
with (out / 'verilator.log').open('w') as log:
    rc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60).returncode
if rc:
    print((out / 'verilator.log').read_text(errors='replace')[-6000:]);raise SystemExit(rc)
print('Verilator translation complete',flush=True)
inc=Path(env['VERILATOR_ROOT']) / 'include'
stub=tests / 'time_stub.cpp'
stub.write_text('double sc_time_stamp() { return 0.0; }\n')
cmd=['C:/msys64/ucrt64/bin/g++.exe','-std=c++20','-O1','-w',
     '-I'+inc.as_posix(),'-I'+(inc / 'vltstd').as_posix(),'-I'+out.as_posix(),
     '-I'+(tests / 'arm_schedule').as_posix(),
     *[x.as_posix() for x in sorted(out.glob('*.cpp'))],
     (inc / 'verilated.cpp').as_posix(),(inc / 'verilated_threads.cpp').as_posix(),
     test.as_posix(),stub.as_posix(),'-o',(out / (top+'.exe')).as_posix()]
with (out / 'compiler.log').open('w') as log:
    rc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180).returncode
if rc:print((out / 'compiler.log').read_text(errors='replace')[-6000:])
print('Native compile complete, rc='+str(rc),flush=True)
raise SystemExit(rc)
