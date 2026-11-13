"""Compile old and four-lane pointwise engines together for independent checking."""
from pathlib import Path
import os,subprocess,hashlib,json,time
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
BUILD=Path('/mnt/d/code/FPGA1/.pw4_unit_build')
def main():
    BUILD.mkdir(exist_ok=True)
    files=[ROOT/p for p in ['rtl/cnn_self/self_conv_engine.sv','rtl/cnn_self/self_pw4_engine.sv','tb/self_pw4_unit_top.sv','tb/integration/self_pw4_unit_main.cpp']]
    for p in files:(BUILD/p.name).write_bytes(p.read_bytes())
    start=time.perf_counter()
    cmd=[str(VR/'bin/verilator'),'--cc','--exe','--build','--no-timing','--top-module','self_pw4_unit_top','-Wno-fatal','-j','2','--Mdir',str(BUILD/'obj'),'-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']+[str(BUILD/p.name) for p in files]
    with (BUILD/'compile.log').open('w') as f:subprocess.run(cmd,cwd=BUILD,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
    compile_seconds=time.perf_counter()-start
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pw4_unit');out.mkdir()
    print('RUN '+str(out),flush=True)
    exe=BUILD/'obj/Vself_pw4_unit_top';start=time.perf_counter()
    with (out/'simulation.log').open('w') as f:result=subprocess.run([str(exe),str(out/'metrics.json')],stdout=f,stderr=subprocess.STDOUT,timeout=180)
    info=dict(status='PASS' if result.returncode==0 else 'FAIL',compile_seconds=compile_seconds,simulation_seconds=time.perf_counter()-start,sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(info,indent=2));print(info['status'],flush=True)
    if result.returncode:raise RuntimeError((out/'simulation.log').read_text())
if __name__=='__main__':main()
