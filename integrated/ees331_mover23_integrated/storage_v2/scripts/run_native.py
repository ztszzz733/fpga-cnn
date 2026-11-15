from pathlib import Path
import sys, json, subprocess, hashlib, time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'baseline/scripts'))
import bootstrap_verilator_native as b
b.VS=Path('D:/VIsual Studio/visual studio 2022')
b.VCVARS=b.VS/'VC/Auxiliary/Build/vcvars64.bat'
b.CMAKE=b.VS/'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
b.NINJA=b.VS/'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
b.VERILATOR_ROOT=Path('C:/msys64/ucrt64/share/verilator')
b.VERILATOR=Path('C:/msys64/ucrt64/bin/verilator_bin.exe')
def run(name,top,sources,main,flags=(),args=(),defines=()):
    # Fresh build root avoids absolute CMake paths copied from the source tree.
    out=ROOT/'build/formal_runs'/name;out.mkdir(parents=True,exist_ok=True)
    record={'status':'RUNNING','sources':{str(p.relative_to(ROOT)):b.sha(p) for p in sources+[main]},'flags':list(flags),'cpp_defines':list(defines),'verilator':str(b.VERILATOR),'verilator_sha256':b.sha(b.VERILATOR)}
    start=time.monotonic()
    try:
        exe=b.build_native(sources,top,out,main=main,verilator_args=['--no-timing',*flags],jobs=2,cpp_defines=list(defines))
        record['compile_seconds']=time.monotonic()-start
        with (out/'simulation.log').open('w') as f:
            r=subprocess.run([str(exe),*map(str,args)],cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        record['returncode']=r.returncode
        assert r.returncode==0,(out/'simulation.log').read_text()
        record['status']='PASS';record['exe_sha256']=b.sha(exe)
    except Exception as e:
        record.update(status='FAIL',error=str(e));raise
    finally:
        record['total_seconds']=time.monotonic()-start
        (out/'result.json').write_text(json.dumps(record,indent=2))
    print(name,record['status'],(out/'simulation.log').read_text(),flush=True)
if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='cache':
        base=ROOT/'baseline'
        run('cache','datasram_ddr_subsystem',[base/'rtl/cnn_ddr'/n for n in ['cnn_cache.sv','cnn_ddr_bridge.sv','datasram_ddr_subsystem.sv']],base/'tb/integration/cnn_ddr_cache_main.cpp',['-GCACHE_BYTES=1024','-GCPU_RAM_BYTES=1024','-GLOGICAL_BYTES=65536'])
    elif mode=='memory':
        for size,base,rom in [(8192,0,1),(16384,0,1),(65536,0,1),(16384,65536,0)]:
            run(f'ram_{size}_{base}','download_ram',[ROOT/'rtl/download_ram.sv'],ROOT/'tb/download_ram.cpp',flags=[f'-GBYTES={size}',f'-GBASE={base}',f'-GREAD_ONLY_CPU={rom}'],defines=[f'RAM_BYTES={size}',f'RAM_BASE={base}',f'ROM_CPU={rom}'])
    elif mode=='cpu':
        sources=[ROOT/'baseline'/n for n in json.loads((ROOT/'baseline/cpu_sources.json').read_text())]
        run('cpu_download','cpu_download',sources+[ROOT/'rtl/download_ram.sv',ROOT/'tb/cpu_download.sv'],ROOT/'tb/cpu_download.cpp')
    elif mode=='tile_dma_system':
        sources=[ROOT/'rtl'/f'{n}.sv' for n in ['tile_row_dma','tile_local_ram','data_mover','tile_dma_system']]
        run(mode,mode,sources,ROOT/'tb/tile_dma_system.cpp',args=[ROOT/'incoming/CNN_storage_handoff_v0.2/cases'])
    elif mode=='program_loader_top':
        sources=[ROOT/'rtl/download_ram.sv',ROOT/'rtl/program_loader_csr.sv',ROOT/'tb/program_loader_top.sv']
        run(mode,mode,sources,ROOT/'tb/program_loader_top.cpp')
    else:
        run(mode,mode,[ROOT/'rtl'/f'{mode}.sv'],ROOT/'tb'/f'{mode}.cpp',args=[ROOT/'build/vectors'])
