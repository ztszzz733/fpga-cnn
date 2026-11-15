"""Check address-driven fixed-graph expansion for one through four images."""
from datetime import datetime
import hashlib,json
from run_tests import ROOT,tools,tool_env,execute

def main():
    found=tools();env=tool_env(found)
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_stream_programmer');run.mkdir(parents=True)
    src=[ROOT/'rtl/cnn_stream/stream_fixed_programmer.sv',ROOT/'tb/stream_programmer_tb.sv']
    result={'status':'RUNNING','source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in src}}
    try:
        execute([found['xvlog'],'-sv',*src],run,env,run/'compile.log',90)
        execute([found['xelab'],'stream_programmer_tb','-s','programmer','-debug','typical'],run,env,run/'compile.log',90)
        (run/'run.tcl').write_text('run all\nquit\n')
        execute([found['xsim'],'programmer','-tclbatch','run.tcl','-onerror','quit'],run,env,run/'sim.log',90)
        if 'PASS STREAM_PROGRAMMER' not in (run/'sim.log').read_text(errors='replace'):raise RuntimeError('missing PASS')
        result['status']='PASS'
    except Exception as exc:result['status']='FAIL';result['error']=str(exc)
    (run/'result.json').write_text(json.dumps(result,indent=2));print(result['status'],run,flush=True)
    return int(result['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
