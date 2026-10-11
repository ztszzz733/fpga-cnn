"""Build genuine pinned NEureka RTL with Verilator; compare to existing CNN."""
import argparse,datetime,json,re,os,shutil,tempfile,hashlib,csv,subprocess,contextlib,time
from pathlib import Path
from gen_neureka_benchmark import generate
from run_tests import ROOT,execute

def sources():
    paths=[]
    for repo in ['tech_cells_generic','hwpe-stream','hwpe-ctrl','hci','neureka']:
        base=ROOT/'third_party'/repo
        if repo=='tech_cells_generic':
            files=['src/rtl/tc_clk.sv','src/deprecated/pulp_clk_cells.sv','src/deprecated/cluster_clk_cells.sv']
        else:
            files=re.findall(r'^\s*- (rtl/[\w/.-]+\.sv)\s*(?:#.*)?$',(base/'Bender.yml').read_text(),re.M)
            files=[s for s in files if '/verif/' not in s and '/interco/' not in s and s!='rtl/hci_interconnect.sv']
        paths.extend(base/f for f in files)
    paths.extend(ROOT/l for l in (ROOT/'rtl/filelists/system_overlap.f').read_text().splitlines() if l)
    paths.extend(sorted((ROOT/'rtl/neureka').glob('*.sv')))
    paths.append(ROOT/'tb/integration/tb_neureka_benchmark.sv')
    return list(dict.fromkeys(paths))

def main():
    p=argparse.ArgumentParser();p.add_argument('--size',type=int,default=18);p.add_argument('--ci',type=int,default=3);p.add_argument('--co',type=int,default=8)
    p.add_argument('--cases',nargs='+',default=['baseline','neureka']);p.add_argument('--waves',action='store_true');p.add_argument('--reuse',type=Path)
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--control-waves',action='store_true',help='bounded directly sampled RTL control VCD; no full array trace')
    p.add_argument('--opt-level',type=int,choices=[0,1,2,3],default=3)
    p.add_argument('--cxx-opt',choices=['-Os','-O2','-O3'],default='-O3',help='host C++ optimization; does not change RTL cycles')
    p.add_argument('--native-build',action='store_true')
    a=p.parse_args();started=time.perf_counter();run=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka')
    generate(run,a.size,a.ci,a.co,repeats=a.repeats);print('RUN_DIR='+str(run),flush=True)
    result={'status':'RUNNING','size':a.size,'ci':a.ci,'co':a.co,'clock_hz':100000000,'banks':4,'tests':{},'timing_seconds':{},'control_waves':a.control_waves}
    (run/'result.json').write_text(json.dumps(result,indent=2))
    try:
        for case in a.cases:
            folder=run/case;src=sources()
            result['source_hashes']={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src}
            monitor=ROOT/'tb/integration/neureka_control_monitor.svh'
            if a.control_waves:
                result['source_hashes'][str(monitor.relative_to(ROOT))]=hashlib.sha256(monitor.read_bytes()).hexdigest()
            # Persistent no-space path on the authorized workspace drive. /tmp
            # is cleaned between tool sessions on this host, so cannot be a cache.
            cache=ROOT.parents[1]/'.neureka_build'/case
            if a.native_build:cache=Path(tempfile.gettempdir())/'fpga1_neureka_native'/case
            cache.mkdir(parents=True,exist_ok=True)
            with contextlib.nullcontext(cache) as stage:
                shutil.copytree(ROOT/'.tools/verilator-linux/verilator',stage/'verilator',dirs_exist_ok=True)
                env=os.environ.copy();env['VERILATOR_ROOT']=str(stage/'verilator')
                staged=[]
                for i,s in enumerate(src):
                    dest=stage/f'{i:03}_{s.name}';shutil.copyfile(s,dest);staged.append(dest)
                for repo in ['hci','hwpe-stream','hwpe-ctrl']:
                    for inc in (ROOT/'third_party'/repo).rglob('*.svh'):shutil.copyfile(inc,stage/inc.name)
                shutil.copyfile(folder/'bench.svh',stage/'bench.svh')
                if a.control_waves:shutil.copyfile(monitor,stage/monitor.name)
                binary=stage/'obj/Vtb_neureka_benchmark'
                if a.reuse:
                    previous=json.loads((a.reuse/'result.json').read_text())
                    if a.control_waves and not previous.get('control_waves'):raise ValueError('reused binary has no control monitor')
                    result['timing_seconds'][case+'_compile']=0.0
                    result['reused_build_compile_seconds']=previous.get('reused_build_compile_seconds',previous.get('timing_seconds',{}).get(case+'_compile'))
                    if (a.reuse/case/'bench.svh').read_text().strip()!=(folder/'bench.svh').read_text().strip():
                        raise ValueError('reuse requires identical compile-time tensor/memory dimensions')
                    shutil.copyfile(a.reuse/case/'simulator',folder/'simulator');binary=folder/'simulator';binary.chmod(0o755)
                    # Report the sources actually compiled into the reused binary.
                    result['source_hashes']=json.loads((a.reuse/'result.json').read_text())['source_hashes']
                    result['reused_binary_from']=str(a.reuse)
                else:
                    stamp=time.perf_counter()
                    execute([stage/'verilator/bin/verilator','--binary','--timing','--assert','-Wno-fatal',f'-O{a.opt_level}','-j','4',
                        '-CFLAGS','-std=c++20','-MAKEFLAGS',f'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST={a.cxx_opt}',
                        '--top-module','tb_neureka_benchmark','--Mdir',stage/'obj','-I'+str(stage),
                        *(['-DNEW_NEUREKA'] if case=='neureka' else []),
                        *(['-DCONTROL_WAVES'] if a.control_waves else []),
                        *(['--trace','--trace-depth','2','-DDUMP_WAVES'] if a.waves else []),*staged],stage,env,folder/'compile.log',timeout=7200)
                    result['timing_seconds'][case+'_compile']=time.perf_counter()-stamp
                if binary!=folder/'simulator':shutil.copyfile(binary,folder/'simulator')
                (run/'result.json').write_text(json.dumps(result,indent=2))
                stamp=time.perf_counter()
                execute([binary,*(['+waves'] if a.waves else [])],folder,env,folder/'sim.log',timeout=10800)
                result['timing_seconds'][case+'_simulation']=time.perf_counter()-stamp
            log=(folder/'sim.log').read_text();assert 'PASS tb_neureka_benchmark' in log
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',re.search(r'METRICS (.*)',log).group(1))}
            events=list(csv.DictReader((folder/'events.csv').open()));tasks=json.loads((folder/'workload.json').read_text())['tasks']
            starts={int(e['task']):int(e['cycle']) for e in events if e['event']=='dispatch'}
            metrics['stages']={tasks[int(e['task'])]:int(e['cycle'])-starts[int(e['task'])] for e in events if e['event']=='complete'}
            result['tests'][case]=metrics;print(case+': '+json.dumps(metrics),flush=True)
            (run/'result.json').write_text(json.dumps(result,indent=2))
        if len(result['tests'])==2:result['speedup']=result['tests']['baseline']['cnn_cycles']/result['tests']['neureka']['cnn_cycles']
        result['status']='PASS'
    except Exception as e:
        result['status']='FAIL';result['error']=str(e);print(str(e),flush=True)
    result['timing_seconds']['total']=time.perf_counter()-started
    (run/'result.json').write_text(json.dumps(result,indent=2))
    return result['status']!='PASS'

if __name__=='__main__':raise SystemExit(main())
