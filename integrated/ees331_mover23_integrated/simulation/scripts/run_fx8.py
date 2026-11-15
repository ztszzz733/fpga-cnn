"""FX8 regression. Real CPU/control/memory, test-only scalar CNN arithmetic.

Results do not establish actual Neureka/Vicuna numerical behavior or board timing.
"""
import argparse,datetime,hashlib,json,re
from run_tests import ROOT,tools,tool_env,execute
from gen_neureka_frames import generate
from run_neureka_frames import build_firmware

FX8_FILES=['fx8_async_fifo.sv','fx8_link.sv','image_load_stream.sv','image_bridge_fx8.sv','face_soc_neureka_fx8_top.sv']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--real-cores',action='store_true');a=ap.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_fx8')
    out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'actual main CPU, FX8 bridge, SRAM, mailbox, scheduler; '+('real pinned CNN cores' if a.real_cores else 'TEST-ONLY scalar CNN cores')}
    try:
        f=tools();env=tool_env(f);generate(out);result['firmware']=build_firmware(out,env)
        cpu=[ROOT/s.strip() for s in (ROOT/'rtl/filelists/system_autoload.f').read_text().splitlines() if s.strip() and not s.startswith('#')]
        cpu=cpu[:cpu.index(ROOT/'rtl/soc/datasram.sv')]
        src=cpu+[ROOT/p for p in ['rtl/soc/clock_unit.sv','rtl/soc/autoload/cpu_core_autoload.sv',
            'rtl/overlap/datasram_banked.sv','rtl/hybrid/cnn_command_port.sv',
            'rtl/neureka_pipeline/neureka_tile_scheduler.sv','tb/integration/neureka_frame_models.sv',
            'rtl/neureka_pipeline/neureka_pipeline_cnn_top.sv']]+[ROOT/'rtl/fx8'/n for n in FX8_FILES]
        benches=['tb_fx8_fifo','tb_fx8_bridge','tb_stream_load_descriptor','tb_neureka_fx8_frames']
        src += [ROOT/'tb/integration'/(b+'.sv') for b in benches]
        evidence=src+[ROOT/'sw/neureka_pipeline'/n for n in ['cnn_frames.h','neureka_pipeline.h']]+[
            ROOT/'firmware/neureka_frames_demo'/n for n in ['main.c','start.S','link.ld']]+[
            ROOT/'scripts'/n for n in ['run_fx8.py','gen_neureka_frames.py','gen_neureka_pipeline.py','run_neureka_frames.py']]
        result['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
        result['assets']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['cpu.hex','sram.hex','external.hex','frames_golden.hex']}
        if a.real_cores:
            from run_neureka_pipeline import compile_real
            compile_real(out,f,env,ROOT/'tb/integration/tb_neureka_fx8_frames.sv',result,snapshot=benches[-1],
                         extra_sources=[ROOT/'rtl/fx8'/n for n in FX8_FILES])
        else:
            execute([f['xvlog'],'-sv',*src],out,env,out/'compile.log',240)
            for b in benches:execute([f['xelab'],b,'-s',b,'--debug','typical'],out,env,out/(b+'_elab.log'),240)
        result['tests']={}
        cases=[(b,None,None) for b in benches[:-1]]+[(benches[-1],0,20000),(benches[-1],0,0),(benches[-1],1,20000)]
        if a.real_cores:cases=[(benches[-1],0,None),(benches[-1],1,None)]
        for bench,mode,delay in cases:
            name=bench+('' if mode is None else f'_{mode}_delay{delay}')
            args=[] if mode is None else ['-testplusarg',f'TEST_MODE={mode}']
            if delay is not None:args+=['-testplusarg',f'CONV_DELAY={delay}']
            log=out/(name+'.log');execute([f['xsim'],bench,'-runall',*args],out,env,log,600)
            text=log.read_text(errors='replace')
            marker='PASS '+bench+('' if mode is None else f' mode={mode}')
            if marker not in text or re.search(r'^(?:Error:|Fatal:|ERROR:|FAIL)',text,re.M):raise RuntimeError('Missing PASS: '+str(log))
            result['tests'][name]='PASS';print('PASS '+name,flush=True)
            metrics=re.search(r'FRAME_METRICS overlap=\s*(\d+) cpu_access_while_cnn=\s*(\d+) three_way_bank_access=\s*(\d+) cpu_result_work=\s*(\d+)',text)
            if metrics:result.setdefault('metrics' if a.real_cores else 'model_metrics',{})[name]=dict(zip(['overlap_cycles','cpu_access_while_cnn','three_way_bank_access','cpu_work_bytes'],map(int,metrics.groups())))
        result['status']='PASS'
    except Exception as exc:result.update(status='FAIL',error=str(exc));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2));print('STATUS='+result['status'],flush=True)

if __name__=='__main__':main()
