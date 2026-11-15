"""Real CPU + UART image stream + SRAM results; native Verilator FST output."""
import argparse,json,hashlib,os,re,shutil,tempfile,time
from pathlib import Path
from datetime import datetime
from gen_stream_images import generate
from run_tests import ROOT,tools,tool_env,execute

def main():
    p=argparse.ArgumentParser();p.add_argument('--width',type=int,default=524);p.add_argument('--height',type=int,default=524)
    p.add_argument('--frames',type=int,default=6);p.add_argument('--chunk',type=int,default=1024)
    p.add_argument('--fault',type=int,choices=[0,1,2],default=0);p.add_argument('--waves',action='store_true')
    a=p.parse_args();run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_stream_images');run.mkdir(parents=True)
    print(f'RUN_DIR={run}',flush=True);started=time.monotonic()
    report=dict(status='RUNNING',config=vars(a),run=str(run))
    try:
        manifest=generate(run,a.width,a.height,a.frames);report['manifest']=manifest
        sources=[ROOT/s for s in (ROOT/'rtl/filelists/system_stream.f').read_text().splitlines() if s.strip()]
        sources.append(ROOT/'tb/integration/tb_soc_stream.sv')
        report['source_hashes']={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}
        found=tools();env=tool_env(found);local=ROOT/'.tools/verilator-linux/verilator'
        with tempfile.TemporaryDirectory(prefix='soc_stream_') as temp:
            stage=Path(temp);shutil.copytree(local,stage/'verilator');env['VERILATOR_ROOT']=str(stage/'verilator')
            cflags='-std=c++20';linkflags=[]
            if a.waves:
                zlib=ROOT/'.tools/zlib-linux/usr'
                shutil.copytree(zlib/'include',stage/'zinclude')
                shutil.copyfile(zlib/'lib/x86_64-linux-gnu/libz.a',stage/'libz.a')
                cflags+=' -I'+str(stage/'zinclude')
                linkflags=['-LDFLAGS','-L'+str(stage)]
            staged=[]
            for i,s in enumerate(sources):
                dest=stage/f'{i:03}_{s.name}';shutil.copyfile(s,dest);staged.append(dest)
            execute([stage/'verilator/bin/verilator','--binary','--timing','--assert','-Wno-fatal','-j','4',
                     '-CFLAGS',cflags,*linkflags,'-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3',
                     '--top-module','tb_soc_stream','--Mdir',stage/'obj',
                     *(['--trace-fst','--trace-depth','2','-DDUMP_WAVES'] if a.waves else []),
                     f'-GWIDTH={a.width}',f'-GHEIGHT={a.height}',f'-GFRAMES={a.frames}',f'-GCHUNK={a.chunk}',f'-GFAULT={a.fault}',*staged],
                    stage,env,run/'compile.log',timeout=900)
            print('Compiled; running UART pin-level simulation',flush=True)
            execute([stage/'obj/Vtb_soc_stream'],run,env,run/'sim.log',timeout=900)
        log=(run/'sim.log').read_text();assert 'PASS tb_soc_stream' in log,log[-2000:]
        report['metrics']={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',re.search(r'METRICS (.*)',log)[1])}
        if not a.fault:
            assert (run/'actual.bin').read_bytes()==(run/'expected.bin').read_bytes(),'binary output mismatch'
            report['actual_sha256']=hashlib.sha256((run/'actual.bin').read_bytes()).hexdigest()
        report['status']='PASS';print(log,flush=True)
    except Exception as e:
        report.update(status='FAIL',error=str(e));print(str(e),flush=True)
    report['wall_seconds']=time.monotonic()-started
    (run/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return int(report['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
