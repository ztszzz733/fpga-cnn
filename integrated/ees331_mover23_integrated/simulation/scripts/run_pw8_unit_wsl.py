"""Independent numeric/protocol checks for prefetch K1 or pipelined K3."""
from pathlib import Path
from datetime import datetime
import argparse,os,subprocess,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1]
VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--k3',action='store_true');a=ap.parse_args()
    build=Path('/mnt/d/code/FPGA1/.pw8_unit_'+('k3' if a.k3 else 'k1'))
    build.mkdir(exist_ok=True)
    files=[ROOT/p for p in ['rtl/cnn_self/self_conv_engine.sv','rtl/cnn_self/self_conv_pipe_engine.sv','rtl/cnn_self/self_pw8_engine.sv','rtl/cnn_self/self_pw4_overlap_engine.sv','tb/self_pw8_unit_top.sv','tb/integration/self_pw8_unit_main.cpp']]
    for p in files:
        content=p.read_bytes()
        if p.suffix=='.cpp':content=content.replace(b'Vself_optimized_unit_top',b'Vself_pw8_unit_top')
        (build/p.name).write_bytes(content)
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_pw8_unit_'+('k3' if a.k3 else 'k1'));out.mkdir()
    result=dict(status='RUNNING',k3=a.k3,sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    print('RUN '+str(out),flush=True)
    begin=time.perf_counter()
    try:
        flags=['--cc','--exe','--build','--no-timing','--top-module','self_pw8_unit_top','-GK3_TEST='+str(int(a.k3)),'-Wno-fatal','-j','2','--Mdir',str(build/'obj'),'-CFLAGS','-std=c++20'+(' -DCNN_K3_TEST' if a.k3 else ''),'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
        with (out/'compile.log').open('w') as f:subprocess.run([str(VR/'bin/verilator'),*flags,*[str(build/p.name) for p in files]],cwd=build,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,check=True)
        result['compile_seconds']=time.perf_counter()-begin
        exe=build/'obj/Vself_pw8_unit_top';result['exe_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest();begin=time.perf_counter()
        with (out/'simulation.log').open('w') as f:subprocess.run([str(exe),str(out/'metrics.json')],stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
        result['simulation_seconds']=time.perf_counter()-begin;result['status']='PASS'
    except Exception as e:result.update(status='FAIL',error=str(e))
    (out/'result.json').write_text(json.dumps(result,indent=2));print(result['status'],flush=True)
    if result['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
