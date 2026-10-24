"""Native XSim regression of ping-pong control, with latency-injected handshake models."""
import datetime, hashlib, json
from run_tests import ROOT,tools,tool_env,execute

def main():
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka_pipeline_control')
    out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    sources=[ROOT/'rtl/neureka_pipeline/neureka_tile_scheduler.sv',ROOT/'tb/integration/tb_neureka_tile_scheduler.sv']
    result={'status':'RUNNING','scope':'scheduler RTL; variable-latency handshake models, NOT real convolution/vector arithmetic',
            'sources':{str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}}
    try:
        found=tools();env=tool_env(found)
        execute([found['xvlog'],'-sv',*sources],out,env,out/'compile.log',180)
        execute([found['xelab'],'tb_neureka_tile_scheduler','-s','test','--debug','typical'],out,env,out/'elaborate.log',180)
        execute([found['xsim'],'test','-runall'],out,env,out/'sim.log',180)
        assert 'PASS tb_neureka_tile_scheduler' in (out/'sim.log').read_text()
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
