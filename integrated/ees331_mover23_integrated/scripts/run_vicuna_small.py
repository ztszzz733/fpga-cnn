"""Bounded independent CV32E40X + Vicuna2 RTL evaluation (run in WSL)."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, time

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT.parents[1] / '.vicuna_build'
UPSTREAM = ROOT / 'third_party/vicuna2_tests'
PIN = '1574ca9c8bbebadb683a7142b5b5d3688bfff655'

def run(cmd, log, timeout=900, env=None):
    t = time.monotonic()
    with log.open('a') as f:
        f.write('\n' + repr([str(x) for x in cmd]) + '\n'); f.flush()
        subprocess.run([str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout, env=env)
    return time.monotonic()-t

def prepare():
    pin = subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()
    assert pin == PIN, pin
    dest = STAGE/'source'
    if not (dest/'stage.ok').exists():
        # Only the simulator and its RTL dependencies; no docs, verification
        # suites, duplicated FPGA systems, or unrelated cores.
        selections=['build_model', 'rtl/cv32e40x/rtl', 'rtl/cv32e40x/bhv',
                    'rtl/fpu_ss/src', 'rtl/vicuna2_core']
        extensions={'.sv','.v','.svh','.vh','.cpp','.h','.cmake','.mk','.txt','.c'}
        for selection in selections:
            src=UPSTREAM/selection
            for directory, dirs, files in os.walk(src):
                dirs[:]=[d for d in dirs if d not in {'.git','build','docs','doc','tb','test','tests','.github'}]
                for name in files:
                    p=Path(directory)/name
                    if p.suffix not in extensions: continue
                    q=dest/p.relative_to(UPSTREAM);q.parent.mkdir(parents=True,exist_ok=True)
                    if not q.exists() or q.stat().st_size!=p.stat().st_size:
                        q.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
        (dest/'stage.ok').write_text(PIN)
    cfg = '''set(RISCV_ARCH "rv32imf_zfh_zve32f_zvfh")
set(SCALAR_CORE "cv32e40x")
set(VMEM_PORTS 1)
set(VMEM_W 32)
set(VREG_W 128)
set(VLANE_W 64)
math(EXPR VMEM_TOTAL_W "${VMEM_PORTS} * ${VMEM_W}")
set(VPROC_PIPELINES "32:VLSU 64:VELEM,VALU,VMUL,VSLD,VDIV,VFPU")
'''
    (dest/'build_model/vector_config.cmake').write_text(cfg)
    buildfile=dest/'build_model/CMakeLists.txt'
    buildfile.write_text(buildfile.read_text().replace('-Wno-IEEEMAYDEPRECATE',''))
    # Keep upstream datapaths unchanged; cap the simulator's unbounded main loop.
    driver=dest/'build_model/cv32e40x/verilator_main.cpp'
    s=driver.read_text()
    s=s.replace('while (true) {','unsigned bounded_cycles = 0;\n    while (true) {\n        if (++bounded_cycles > 200000) { fprintf(stderr, "TIMEOUT\\n"); exit_code=1; break; }') if 'bounded_cycles' not in s else s
    driver.write_text(s)
    return dest

def adapt_generated_headers(dest):
    # Upstream's driver hardcodes a parameter-dependent Verilator class name.
    # Resolve that include against this build, without changing any RTL.
    headers=list((STAGE/'model/CMakeFiles/verilated_model.dir/Vvproc_top.dir').glob('Vvproc_top_fpu_ss__*.h'))
    assert len(headers)==1, headers
    support=dest/'build_model/cv32e40x/verilator_support_cv32e40x.h'
    value=re.sub(r'Vvproc_top_fpu_ss__[^"\n]+\.h',headers[0].name,support.read_text())
    if value!=support.read_text(): support.write_text(value)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--prepare-only',action='store_true'); ap.add_argument('--run-tests',action='store_true')
    args=ap.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_vicuna_small')
    out.mkdir(parents=True); STAGE.mkdir(exist_ok=True)
    print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'independent CV32E40X + Vicuna2, no production SoC changes',
            'upstream_commit':PIN,'configuration':{'VREG_W':128,'VMEM_W':32,'VLANE_W':64,'ISA':'rv32imf_zfh_zve32f_zvfh'}}
    try:
        dest=prepare()
        vr=ROOT.parents[1]/'.nvdla_build/nv_small/verilator'
        env=os.environ.copy();env['VERILATOR_ROOT']=str(vr);env['PATH']=str(vr/'bin')+':'+env['PATH']
        result['dependencies']={p:subprocess.check_output(['git','-C',str(UPSTREAM/p),'rev-parse','HEAD'],text=True).strip()
            for p in ['rtl/cv32e40x','rtl/fpu_ss','rtl/vicuna2_core','rtl/vicuna2_core/cvfpu','rtl/vicuna2_core/pulp_common_cells']}
        if args.prepare_only: result['status']='PREPARED'
        else:
            cmake_dir=STAGE/'verilator-cmake';cmake_dir.mkdir(exist_ok=True)
            template=(ROOT/'.tools/downloads/verilator-5.038-config.cmake.in').read_text()
            template=template.replace('@CFG_LDFLAGS_THREADS_CMAKE@','-pthread')
            template=re.sub(r'@[A-Z_0-9]+@','',template)
            (cmake_dir/'verilator-config.cmake').write_text(template)
            result['configure_seconds']=run(['cmake','-S',dest/'build_model','-B',STAGE/'model',
                '-DTRACE=ON','-DTRACE_FULL=OFF','-Dverilator_DIR='+str(cmake_dir),'-DCMAKE_BUILD_TYPE=Release'],out/'configure.log',env=env)
            adapt_generated_headers(dest)
            result['compile_seconds']=run(['cmake','--build',STAGE/'model','-j','2'],out/'compile.log',env=env)
            result['status']='COMPILED_NOT_TESTED'
            if args.run_tests:
                (out/'result.json').write_text(json.dumps(result,indent=2))
                try:
                    run(['python3',ROOT/'scripts/test_vicuna_small.py',out],out/'tests.log',900,env=env)
                finally:
                    result=json.loads((out/'result.json').read_text())
    except BaseException as e:
        result['status']='ERROR'
        result.setdefault('error',str(e))
        raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__': main()
