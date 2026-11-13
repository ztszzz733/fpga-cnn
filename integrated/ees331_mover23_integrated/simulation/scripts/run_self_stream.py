"""Real bai SRAM, four sequential inputs, selectable physical operator pools."""
from pathlib import Path
from datetime import datetime
import argparse, hashlib, json, os, shutil, time
from gen_self_stream import ROOT, generate
from run_tests import tools, tool_env, execute

CONFIGS={'base':(2,1,1),'k3x3':(3,1,1),'k3x4':(4,1,1),'extra_k1':(3,2,1),'extra_post':(3,1,2),'both':(3,2,2),'four_k1':(4,2,1),'four_post':(4,1,2),'all':(4,2,2)}
MODES=['overlap','serial','cpu_collision_slow_reader','clear_restart','memory_fault_restart','disable_k3_0','preloaded']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',nargs=4,type=Path)
    p.add_argument('--configs',nargs='+',choices=CONFIGS,default=list(CONFIGS))
    p.add_argument('--modes',nargs='+',choices=MODES,default=['overlap'])
    p.add_argument('--reuse',type=Path)
    p.add_argument('--sweep',action='store_true',help='elaborate maximum pools once; disable unused units to compare scheduling throughput')
    a=p.parse_args(); found=tools();env=tool_env(found)
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_self_stream')
    run.mkdir(parents=True);print('RUN_DIR='+str(run),flush=True)
    src=[ROOT/s.strip() for s in (ROOT/'rtl/filelists/cnn_self_stream.f').read_text().splitlines() if s.strip() and not s.strip().startswith(('//','#'))]
    src.append(ROOT/'tb/self_stream_tb.sv')
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in src}
    hashes['scripts/gen_self_stream.py']=hashlib.sha256((ROOT/'scripts/gen_self_stream.py').read_bytes()).hexdigest()
    result=dict(status='RUNNING',source_sha256=hashes,runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),run_dir=str(run),scenarios={},errors=[],scope='Four 7x7 RGB diagnostic graphs; actual arithmetic and bai SRAM; no full MobileFaceNet or board claim')
    def save(): (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    save();started=time.perf_counter()
    try:
        manifest=generate(run/'data',a.images);result['fixture']=manifest
        build=run/'compile';build.mkdir();old={}
        if a.reuse:
            prev=a.reuse.resolve();old=json.loads((prev/'result.json').read_text())
            if old['source_sha256']!=hashes:raise RuntimeError('Changed sources; refusing stale snapshot')
            build=Path(old.get('reused_build',str(prev/'compile')));result['reused_build']=str(build)
        else: execute([found['xvlog'],'-sv',*src],build,env,build/'compile.log',240)
        for name in a.configs:
            config=CONFIGS[name];physical=(4,2,2) if a.sweep else config;snapshot='stream_'+('sweep' if a.sweep else name)
            if not (build/'xsim.dir'/snapshot).exists():
                cmd=[found['xelab'],'self_stream_tb','-s',snapshot,'-debug','typical','-mt','2']
                for key,value in zip(['K3_UNITS','K1_UNITS','POST_UNITS'],physical):cmd+=['-generic_top',key+'='+str(value)]
                execute(cmd,build,env,build/('elab_'+name+'.log'),600)
            for mode in a.modes:
                case=name+'_'+mode;scenario=run/case;scenario.mkdir();tcl=''
                if mode=='overlap':
                    signals='clk clear start unit_enable frame_valid frame_ready frame_slot frames_ready unit_start unit_active operator_work mem_valid mem_write mem_ready mem_response completed_count buffer_live external_hold result_valid result_ready result_accept result_frame compute_done done error'
                    tcl='open_vcd {'+(scenario/'control.vcd').as_posix()+'}\n'
                    # -generic_top gives the root an escaped parameterized name.
                    # Relative lookups use XSim's current top scope correctly.
                    tcl+='set selected [get_objects {'+signals+'}]\n'
                    tcl+='if {[llength $selected] != '+str(len(signals.split()))+'} {error "missing waveform signals"}\nlog_vcd $selected\n'
                tcl+='run all\n'+('close_vcd\n' if mode=='overlap' else '')+'quit\n'
                (scenario/'run.tcl').write_text(tcl,encoding='utf-8')
                for item in ('metrics.json','outputs.hex','events.csv','trace.csv'):
                    if (build/item).exists():(build/item).unlink()
                ts=time.perf_counter()
                pk3,pk1,ppost=physical;ck3,ck1,cpost=config
                dw=pk3+pk1;post=dw+1;add=post+ppost;pad=add+1
                enabled=((1<<ck3)-1)|(((1<<ck1)-1)<<pk3)|(1<<dw)|(((1<<cpost)-1)<<post)|(1<<add)|(1<<pad)
                execute([found['xsim'],snapshot,'-tclbatch',Path(os.path.relpath(scenario/'run.tcl',build)).as_posix(),'-onerror','quit','-testplusarg','DATA='+Path(os.path.relpath(run/'data',build)).as_posix(),'-testplusarg','MODE='+str(MODES.index(mode)),'-testplusarg','ENABLE='+str(enabled)],build,env,scenario/'sim.log',300)
                if 'PASS SELF_STREAM' not in (scenario/'sim.log').read_text(errors='replace') or not (build/'metrics.json').exists():raise RuntimeError('Missing PASS: '+case)
                if mode=='overlap' and (scenario/'control.vcd').read_text().count('$var ')!=len(signals.split()):raise RuntimeError('Incomplete VCD: '+case)
                for item in ('metrics.json','outputs.hex','events.csv','trace.csv'):
                    if (build/item).exists():shutil.move(str(build/item),str(scenario/item))
                metrics=json.loads((scenario/'metrics.json').read_text());metrics['config']=dict(zip(['k3','k1','post'],config))
                metrics['physical_pools']=dict(zip(['k3','k1','post'],physical));metrics['enabled_mask']=enabled
                output=bytes(int(x,16) for x in (scenario/'outputs.hex').read_text().split())
                metrics['output_sha256']=hashlib.sha256(output).hexdigest()
                if metrics['output_sha256']!=manifest['final_expected_sha256'] or metrics['checked_bytes']!=manifest['expected_bytes']:raise RuntimeError('Hash/check count mismatch: '+case)
                metrics['simulation_seconds']=round(time.perf_counter()-ts,3)
                (scenario/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
                result['scenarios'][case]=metrics;save()
                print(case+' PASS cycles='+str(metrics['cycles'])+' peak_frames='+str(metrics['peak_active_frames']),flush=True)
        result['status']='PASS'
    except Exception as exc:result['status']='FAIL';result['errors'].append(str(exc));print(str(exc),flush=True)
    result['elapsed_seconds']=round(time.perf_counter()-started,3);save()
    print(result['status']+' '+str(run/'result.json'),flush=True)
    return int(result['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
