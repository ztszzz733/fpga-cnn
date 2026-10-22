"""Compare identical CPU/UART/multi-task workloads, with independent golden data."""
import argparse
from datetime import datetime
import hashlib
import json
import re
import os
import shutil
import tempfile
import csv
from pathlib import Path
from gen_overlap_demo import generate
from run_tests import ROOT, tools, tool_env, execute


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',nargs='+',choices=['original','serial','overlap','one_bank','memory','memory21','restart','observer_fault','uart_baseline'],
                        default=['original','serial','overlap','one_bank','memory','memory21','restart'])
    parser.add_argument('--seed',type=int,default=1)
    parser.add_argument('--simulator',choices=['auto','verilator','xsim'],default='auto')
    parser.add_argument('--waves',action='store_true')
    parser.add_argument('--top-waves',action='store_true',help='Trace top module I/O from reset, with limited hierarchy depth')
    parser.add_argument('--uart-baud',type=int,choices=[12500000,25000000],default=25000000)
    parser.add_argument('--chunk-bytes',type=int,choices=[64,255,256],default=256)
    args=parser.parse_args()
    if args.top_waves: args.waves=True
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_overlap_integration')
    run.mkdir(parents=True)
    print(f'RUN_DIR={run}',flush=True)
    found=tools();env=tool_env(found)
    local=ROOT/'.tools/verilator-linux/verilator'
    if os.name!='nt' and (local/'bin/verilator').exists():
        found['verilator']=str(local/'bin/verilator');env['VERILATOR_ROOT']=str(local)
    simulator=args.simulator
    if simulator=='auto': simulator='verilator' if found.get('verilator') else 'xsim'
    result={'status':'RUNNING','seed':args.seed,'simulator':simulator,'tests':{},'run_dir':str(run),
            'uart_config':{'baud':args.uart_baud,'chunk_bytes':args.chunk_bytes}}
    try:
        for case in args.cases:
            folder=run/case;folder.mkdir()
            generate(folder,args.seed)
            original=case=='original'
            filelist=ROOT/'rtl/filelists'/('system_autoload.f' if original else 'system_overlap.f')
            sources=[ROOT/x.strip() for x in filelist.read_text().splitlines() if x.strip()]
            top={'memory':'tb_datasram_banked','memory21':'tb_datasram_banked','restart':'tb_overlap_restart'}.get(case,'tb_soc_overlap')
            baud=12500000 if case=='uart_baseline' else args.uart_baud
            chunk=64 if case=='uart_baseline' else args.chunk_bytes
            sources.append(ROOT/f'tb/integration/{top}.sv')
            hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
            if simulator=='verilator':
                # Build on Linux's native filesystem; make cannot handle project paths containing spaces.
                with tempfile.TemporaryDirectory(prefix='soc_overlap_') as temp:
                    stage=Path(temp)
                    compiler=found['verilator']
                    build_env=env.copy()
                    if 'VERILATOR_ROOT' in env:
                        shutil.copytree(env['VERILATOR_ROOT'],stage/'verilator')
                        build_env['VERILATOR_ROOT']=str(stage/'verilator')
                        compiler=str(stage/'verilator/bin/verilator')
                    staged=[]
                    for i,source in enumerate(sources):
                        dest=stage/f'{i:03}_{source.name}';shutil.copyfile(source,dest);staged.append(dest)
                    shutil.copyfile(folder/'overlap_vectors.svh',stage/'overlap_vectors.svh')
                    params=[] if original else [f'-GENABLE_OVERLAP={0 if case=="serial" else 1}',f'-GBANKS={1 if case=="one_bank" else 4}']
                    if case=='memory21':params+=['-GCLIENTS=21']
                    if case=='observer_fault':params+=['-GOBSERVE_FAULT=1']
                    if top=='tb_soc_overlap':params += [f'-GUART_BAUD={baud}',f'-GUART_CHUNK_BYTES={chunk}']
                    make_python=Path(os.sys.executable).as_posix()
                    execute([compiler,'--binary','--timing','--assert','-Wno-fatal','-j','4','-CFLAGS','-std=c++20',
                             '-MAKEFLAGS',f'CFG_CXXFLAGS_PCH_I=-include PYTHON3={make_python}',
                             '--top-module',top,'--Mdir',stage/'obj','-I'+str(stage),
                             *(['--trace','-DDUMP_WAVES'] if args.waves else []),
                             *(['--trace-depth','2','-DTOP_WAVES'] if args.top_waves else []),
                             *(['-DORIGINAL_SOC'] if original else []),*params,*staged],stage,build_env,folder/'compile.log',timeout=900)
                    execute([stage/f'obj/V{top}'],folder,env,folder/'sim.log',timeout=300)
            else:
                execute([found['xvlog'],'-sv','-i',folder,*(['-d','ORIGINAL_SOC'] if original else []),*sources],folder,env,folder/'compile.log',timeout=180)
                params=[] if original else ['-generic_top',f'ENABLE_OVERLAP={0 if case=="serial" else 1}',
                                       '-generic_top',f'BANKS={1 if case=="one_bank" else 4}']
                if case=='memory21':params+=['-generic_top','CLIENTS=21']
                if case=='observer_fault':params+=['-generic_top','OBSERVE_FAULT=1']
                if top=='tb_soc_overlap':params+=['-generic_top',f'UART_BAUD={baud}','-generic_top',f'UART_CHUNK_BYTES={chunk}']
                execute([found['xelab'],top,'-s','overlap','-debug','typical','-mt','2',*params],folder,env,folder/'compile.log',timeout=300)
                tcl=f'open_vcd {{wave.vcd}}\nlog_vcd [get_objects /{top}/*]\nrun all\nclose_vcd\nquit\n'
                (folder/'run.tcl').write_text(tcl)
                execute([found['xsim'],'overlap','-tclbatch','run.tcl','-onerror','quit'],folder,env,folder/'sim.log',timeout=300)
            content=(folder/'sim.log').read_text(errors='replace')
            if f'PASS {top}' not in content or re.search(r'^(Error:|Fatal:|ERROR:|FAIL)',content,re.M):
                raise RuntimeError(f'{case} failed: {folder}/sim.log')
            line=re.search(r'METRICS (.*)',content).group(1)
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
            if top=='tb_soc_overlap' and case!='observer_fault':
                events=list(csv.DictReader((folder/'events.csv').open()))
                issued={int(e['task_id']):int(e['cycle']) for e in events if e['event']=='dispatch'}
                finished={int(e['task_id']):int(e['cycle']) for e in events if e['event']=='complete'}
                for before,after in [(0,2),(1,6),(2,12),(14,15),(14,16),(14,17),(15,17)]:
                    if issued[after]<finished[before]: raise RuntimeError(f'Dependency violated: {before}->{after}')
                if issued[3]>=finished[0]: raise RuntimeError('Independent ADD failed to bypass dependent task')
            result['tests'][case]={'status':'PASS','metrics':metrics,'source_hashes':hashes}
            print(f'PASS {case}: {line}',flush=True)
            (run/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        tests=result['tests']
        if 'overlap' in tests and 'serial' in tests:
            a=tests['overlap']['metrics']['cnn_cycles'];b=tests['serial']['metrics']['cnn_cycles']
            if a>=b: raise RuntimeError(f'Overlap did not reduce workload cycles: {a} >= {b}')
            result['overlap_vs_serial_speedup']=b/a
        if 'overlap' in tests and 'original' in tests:
            result['new_vs_original_speedup']=tests['original']['metrics']['cnn_cycles']/tests['overlap']['metrics']['cnn_cycles']
        if 'overlap' in tests and 'uart_baseline' in tests:
            result['uart_load_speedup']=tests['uart_baseline']['metrics']['load_cycles']/tests['overlap']['metrics']['load_cycles']
            result['uart_end_to_end_speedup']=tests['uart_baseline']['metrics']['total_cycles']/tests['overlap']['metrics']['total_cycles']
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc));print(str(exc),flush=True)
    (run/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return int(result['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
