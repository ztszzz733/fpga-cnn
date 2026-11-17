from pathlib import Path
import datetime, hashlib, json, os, subprocess, time
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'conv_perf'
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
RUN=ROOT/'performance_runs'/datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
RUN.mkdir(parents=True,exist_ok=False)
(ROOT/'active_performance_run.txt').write_text(str(RUN)+'\n')
names=['rtl/cnn_self/compact_word_ram.sv','rtl/cnn_self/self_pw8_engine.sv','rtl/cnn_self/self_conv_spatial4_engine.sv','storage_v2/rtl/data_mover.sv','storage_v2/rtl/tile_local_ram.sv','storage_v2/rtl/tile_local_ram_bank4.sv','rtl/cnn_ddr/cnn_paged_mover.sv','rtl/cnn_ddr/cnn_plan_storage.sv','rtl/cnn_ddr/storage_plan_queue.sv','conv_memory_perf_top.sv']
sources=[SRC/name for name in names]+[ROOT/'conv_perf_main.cpp']
env=os.environ.copy()
env['VERILATOR_ROOT']=str(VR)
env['MAKEFLAGS']=''
env['PATH']=str(ROOT/'local_tools')+os.pathsep+env['PATH']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=dict(status='COMPILING',new_storage_commit=json.loads((ROOT/'remote.json').read_text())['commit'],scope='Two real convolution operators, two synthetic images per layer, same current production operators/MOVER/local RAM in both modes. Includes input/weight transfer and output DDR visibility; excludes CPU/UART and full network.',sources={str(p):sha(p) for p in sources},common_sources=json.loads((SRC/'source_manifest.json').read_text()),variants={})
def save():
    (RUN/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
def call(command,log,timeout):
    before=time.perf_counter()
    with log.open('w') as output:
        r=subprocess.run([str(x) for x in command],cwd=SRC,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
    if r.returncode:
        raise RuntimeError(f'exit {r.returncode}; see {log}')
    return time.perf_counter()-before
save()
started=time.perf_counter()
try:
    for variant,plan in [('legacy',0),('explicit',1)]:
        dest=RUN/variant;dest.mkdir();obj=dest/'obj'
        command=[VR/'bin/verilator','--cc','--exe','--build','--assert','--no-timing','--top-module','conv_memory_perf_top',f'-GPLAN={plan}','-Wno-fatal','--threads','1','-j','2','-O1','--output-split-cfuncs','500','--Mdir',obj,'-CFLAGS',f'-std=c++20 -O2 -I{SRC/"simulation/tb/integration"}','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*sources]
        (dest/'command.json').write_text(json.dumps([str(x) for x in command],indent=2)+'\n')
        print('Compiling matched convolution benchmark:',variant,flush=True)
        compile_seconds=call(command,dest/'compile.log',600)
        print('Running real convolutions:',variant,flush=True)
        simulation_seconds=call([obj/'Vconv_memory_perf_top',variant],dest/'simulation.log',180)
        logs=(dest/'simulation.log').read_text()
        measurements=[json.loads(line[5:]) for line in logs.splitlines() if line.startswith('PERF ')]
        assert len(measurements)==2 and all(x['status']=='PASS' for x in measurements),logs
        result['variants'][variant]=dict(compile_seconds=compile_seconds,simulation_seconds=simulation_seconds,measurements=measurements)
        save()
        print(logs.strip(),flush=True)
    comparisons=[]
    for old,new in zip(result['variants']['legacy']['measurements'],result['variants']['explicit']['measurements']):
        assert (old['kernel'],old['width'],old['height'],old['ci'],old['co'],old['checked_bytes'])==(new['kernel'],new['width'],new['height'],new['ci'],new['co'],new['checked_bytes'])
        comparisons.append(dict(kernel=old['kernel'],old_cycles=old['cycles'],new_cycles=new['cycles'],saved_percent=100*(1-new['cycles']/old['cycles']),speedup=old['cycles']/new['cycles']))
    result['comparisons']=comparisons
    for path,expected in result['sources'].items():assert sha(Path(path))==expected,path
    result['status']='PASS'
except Exception as error:
    result['status']='FAIL';result['error']=str(error)
    raise
finally:
    result['wall_seconds']=time.perf_counter()-started
    save()
    print('Performance result:',RUN/'result.json',result['status'],flush=True)
