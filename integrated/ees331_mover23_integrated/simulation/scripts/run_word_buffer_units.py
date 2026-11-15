from pathlib import Path
from datetime import datetime
import hashlib,json,os,subprocess,time
BASE=Path('/mnt/d/code/FPGA1/integrated/ees331_mover23_integrated');SIM=BASE/'simulation';VR=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
def main():
    out=SIM/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_word_buffer_unit');out.mkdir(parents=True)
    files=[BASE/'rtl/cnn_self/compact_word_ram.sv',BASE/'rtl/cnn_self/self_conv_spatial4_engine.sv',SIM/'tb/self_word_buffer_unit_top.sv',SIM/'tb/integration/self_word_buffer_unit_main.cpp']
    j=dict(status='COMPILING',sources_sha256={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},unit='K3 baseline READ_WORD_BUFFER=0 versus optimized =1; same arithmetic',full_network=False)
    def save():(out/'result.json').write_text(json.dumps(j,indent=2))
    save();print('UNIT_RUN='+str(out),flush=True);t=time.monotonic()
    try:
        cmd=[str(VR/'bin/verilator'),'--cc','--exe','--build','--no-timing','--assert','--top-module','self_word_buffer_unit_top','-Wno-fatal','-j','1','--Mdir',str(out/'obj'),'-CFLAGS','-std=c++20 -DCNN_K3_TEST','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2',*map(str,files)]
        with (out/'compile.log').open('w') as f:subprocess.run(cmd,cwd=SIM,env=dict(os.environ,VERILATOR_ROOT=str(VR)),stdout=f,stderr=subprocess.STDOUT,timeout=180,check=True)
        j['compile_seconds']=time.monotonic()-t;j['status']='RUNNING';save();t=time.monotonic()
        with (out/'simulation.log').open('w') as f:subprocess.run([str(out/'obj/Vself_word_buffer_unit_top'),str(out/'metrics.json')],stdout=f,stderr=subprocess.STDOUT,timeout=150,check=True)
        j['test_seconds']=time.monotonic()-t;j['status']='PASS'
    except Exception as e:j['status']='FAIL';j['error']=str(e)
    j['sources_unchanged']=all(hashlib.sha256((BASE/p).read_bytes()).hexdigest()==v for p,v in j['sources_sha256'].items());save();print(j['status'],flush=True)
    return 0 if j['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
