"""Independent 128-bit integer reference and bus protocol post tests."""
from pathlib import Path
from datetime import datetime
import os,subprocess,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1]
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
def main():
    build=Path('/mnt/d/code/FPGA1/.post_pipe_unit');build.mkdir(exist_ok=True)
    files=[ROOT/p for p in ['rtl/cnn_quant/quant_post_engine.sv','rtl/cnn_quant/quant_post_pipe_engine.sv','tb/post_pipe_unit_top.sv','tb/integration/post_pipe_unit_main.cpp']]
    for p in files:(build/p.name).write_bytes(p.read_bytes())
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_post_pipe_unit');out.mkdir()
    result=dict(status='RUNNING',sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    print('RUN '+str(out),flush=True);begin=time.perf_counter()
    try:
        flags=['--cc','--exe','--build','--no-timing','--top-module','post_pipe_unit_top','-Wno-fatal','-j','2','--Mdir',str(build/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
        with (out/'compile.log').open('w') as f:subprocess.run([str(VR/'bin/verilator'),*flags,*[str(build/p.name) for p in files]],cwd=build,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
        result['compile_seconds']=time.perf_counter()-begin;exe=build/'obj/Vpost_pipe_unit_top';result['exe_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest();begin=time.perf_counter()
        with (out/'simulation.log').open('w') as f:subprocess.run([str(exe),str(out/'metrics.json')],stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
        result.update(simulation_seconds=time.perf_counter()-begin,status='PASS')
    except Exception as e:result.update(status='FAIL',error=str(e))
    (out/'result.json').write_text(json.dumps(result,indent=2));print(result['status'],flush=True)
    if result['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
