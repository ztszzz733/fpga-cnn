"""Compile/run the real cache and AXI3 bridge against a stalled DDR bus model."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
from bootstrap_verilator_native import build_native, native_environment

ROOT=Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    # CMake's compiler probe otherwise chooses Debug and launches a PDB server.
    # Match the actual Release simulator build, using a process-local setting.
    os.environ['CMAKE_BUILD_TYPE']='Release'
    work=ROOT/'build/runs'/f'{datetime.now():%Y%m%d_%H%M%S_%f}_cnn_ddr_cache'
    work.mkdir(parents=True)
    sources=[ROOT/'rtl/cnn_ddr'/name for name in
             ('cnn_cache.sv','cnn_ddr_bridge.sv','datasram_ddr_subsystem.sv')]
    main=ROOT/'tb/integration/cnn_ddr_cache_main.cpp'
    tracked=sources+[main,Path(__file__).resolve(),ROOT/'scripts/bootstrap_verilator_native.py']
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    start=time.perf_counter()
    exe=build_native(sources,'datasram_ddr_subsystem',work,main=main,jobs=2,
        verilator_args=['--no-timing','-GCACHE_BYTES=1024','-GCPU_RAM_BYTES=1024',
                        '-GLOGICAL_BYTES=65536'])
    built=time.perf_counter()
    with (work/'simulation.log').open('w') as out:
        result=subprocess.run([str(exe)],stdout=out,stderr=subprocess.STDOUT,
            cwd=work,env=native_environment(),timeout=120)
    log=(work/'simulation.log').read_text()
    unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.relative_to(ROOT).as_posix()] for p in tracked)
    passed=result.returncode==0 and 'PASS cnn_ddr_cache' in log and unchanged
    (work/'result.json').write_text(json.dumps({
        'status':'PASS' if passed else 'FAIL','compile_seconds':built-start,
        'simulation_seconds':time.perf_counter()-built,'returncode':result.returncode,
        'cache_bytes':1024,'production_default_cache_bytes':131072,
        'clients':10,'sources_sha256':hashes,'sources_unchanged_during_run':unchanged,
        'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'notes':'Reduced cache geometry forces conflicts. Same RTL, AXI3 eight-beat lines, random channel stalls; not board DDR timing.'
    },indent=2)+'\n')
    print(str(work),flush=True)
    print(log,flush=True)
    if not passed: raise SystemExit(1)
