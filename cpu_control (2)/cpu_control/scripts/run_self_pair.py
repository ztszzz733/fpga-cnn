"""Build once and validate two concurrent small images with real self CNN RTL."""
from pathlib import Path
from datetime import datetime
import argparse, hashlib, json, os, shutil, time
from gen_self_pair import ROOT, generate
from run_tests import tools, tool_env, execute

MODES=['dual','stalls_slow_reader','only_conv3_0','only_conv3_1','skew_conv3_0','clear_restart','memory_fault_restart','illegal_opcode','illegal_dependency','illegal_result']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',nargs=2,type=Path)
    p.add_argument('--modes',nargs='+',choices=MODES,default=MODES)
    p.add_argument('--reuse',type=Path,help='previous run with source-hash matched compiled XSim snapshot')
    a=p.parse_args()
    found=tools();env=tool_env(found)
    if not all(found.get(x) for x in ('xvlog','xelab','xsim')):raise SystemExit('Existing XSim installation required')
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_self_pair')
    run.mkdir(parents=True);print('RUN_DIR='+str(run),flush=True)
    src=[ROOT/s.strip() for s in (ROOT/'rtl/filelists/cnn_self.f').read_text().splitlines() if s.strip() and not s.strip().startswith(('//','#'))]
    src.append(ROOT/'tb/self_pair_tb.sv')
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in src}
    hashes['scripts/gen_self_pair.py']=hashlib.sha256((ROOT/'scripts/gen_self_pair.py').read_bytes()).hexdigest()
    result=dict(status='RUNNING',source_sha256=hashes,run_dir=str(run),scenarios={},scope='small synthetic diagnostic two-image graph; all actual RTL operators; no NEureka',errors=[])
    (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    start=time.perf_counter()
    try:
        manifest=generate(run/'data',a.images);result['fixture']=manifest
        if manifest['task_count']!=22:raise ValueError('TB expects 22 tasks')
        compile_start=time.perf_counter()
        build=run/'compile';build.mkdir()
        if a.reuse:
            prev=a.reuse.resolve();old=json.loads((prev/'result.json').read_text())
            if old['source_sha256']!=hashes:raise RuntimeError('Source hashes differ: refuse cached simulation')
            # Run the existing snapshot in its original build directory. XSim
            # support files can contain absolute paths; never copy stale binaries.
            build=Path(old.get('reused_build',str(prev/'compile')));result['reused_build']=str(build)
        else:
            execute([found['xvlog'],'-sv',*src],build,env,build/'compile.log',180)
            execute([found['xelab'],'self_pair_tb','-s','self_pair_sim','-debug','typical','-mt','2'],build,env,build/'compile.log',180)
        result['compile_seconds']=0 if a.reuse else round(time.perf_counter()-compile_start,3)
        for mode in a.modes:
            scenario=run/mode;scenario.mkdir()
            # XSim snapshot is located from cwd. Testbench artifacts are written
            # here first then moved into a unique scenario folder after exit.
            tcl=''
            if mode=='dual':
                signals='clk clear start engine_enable unit_start unit_active operator_busy operator_work completion_pulse completed_count mem_valid mem_write mem_ready mem_response buffer_live buffer_release external_hold result_valid result_ready result_accept result_frame result_addr result_bytes compute_done done error'
                tcl='open_vcd {'+str((scenario/'control.vcd').as_posix())+'}\n'
                tcl+='log_vcd [get_objects {'+' '.join('/self_pair_tb/'+s for s in signals.split())+'}]\n'
            tcl+='run all\n'+('close_vcd\n' if mode=='dual' else '')+'quit\n'
            (scenario/'run.tcl').write_text(tcl,encoding='utf-8')
            for name in ('metrics.json','outputs.hex','events.csv','trace.csv'):
                stale=build/name
                if stale.exists():stale.unlink()
            ts=time.perf_counter()
            data_arg=Path(os.path.relpath(run/'data',build)).as_posix()
            script_arg=Path(os.path.relpath(scenario/'run.tcl',build)).as_posix()
            execute([found['xsim'],'self_pair_sim','-tclbatch',script_arg,'-onerror','quit','-testplusarg','DATA='+data_arg,'-testplusarg','MODE='+str(MODES.index(mode))],build,env,scenario/'sim.log',240)
            log=(scenario/'sim.log').read_text(encoding='utf-8',errors='replace')
            if 'PASS SELF_PAIR' not in log or not (build/'metrics.json').exists():raise RuntimeError('No valid PASS for '+mode+'; inspect '+str(scenario/'sim.log'))
            for name in ('metrics.json','outputs.hex','events.csv','trace.csv'):
                if (build/name).exists():shutil.move(str(build/name),str(scenario/name))
            metrics=json.loads((scenario/'metrics.json').read_text())
            output=bytes(int(x,16) for x in (scenario/'outputs.hex').read_text().split())
            metrics['output_sha256']=hashlib.sha256(output).hexdigest()
            if metrics['output_sha256']!=manifest['final_expected_sha256']:raise RuntimeError('Final SHA mismatch')
            if metrics['checked_bytes']!=manifest['expected_bytes']:raise RuntimeError('Missing checkpoint checks')
            metrics['simulation_seconds']=round(time.perf_counter()-ts,3)
            (scenario/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
            result['scenarios'][mode]=metrics
            print(mode+' PASS cycles='+str(metrics['cycles'])+' dual_mac='+str(metrics['dual_mac_cycles']),flush=True)
            (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        result['status']='PASS'
    except Exception as exc:
        result['status']='FAIL';result['errors'].append(str(exc));print(str(exc),flush=True)
    result['elapsed_seconds']=round(time.perf_counter()-start,3)
    (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result['status']+' '+str(run/'result.json'),flush=True)
    return int(result['status']!='PASS')

if __name__=='__main__':raise SystemExit(main())
