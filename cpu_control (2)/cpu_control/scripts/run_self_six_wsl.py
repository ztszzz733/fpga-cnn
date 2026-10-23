"""Six/ten-context reproducible WSL runner; arithmetic and checking use real RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('/mnt/d/code/FPGA1/.self_six_pw4_baseline_build')
VR = Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator')
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, v):
    p.write_text(json.dumps(v, indent=2) + '\n')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--frames', type=int, choices=(6, 10), default=6)
    ap.add_argument('--pw4', action='store_true')
    ap.add_argument('--conv-overlap', action='store_true')
    ap.add_argument('--wide-pipe', action='store_true')
    ap.add_argument('--pw8', action='store_true')
    ap.add_argument('--dw-priority', action='store_true')
    ap.add_argument('--reuse', action='store_true')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--gate', type=Path)
    args = ap.parse_args()
    if args.pw8: args.wide_pipe = True
    if args.wide_pipe: args.conv_overlap = True
    if args.conv_overlap: args.pw4 = True
    global CACHE
    if args.pw4: CACHE = CACHE.with_name('.self_six_pw4_build')
    if args.conv_overlap: CACHE = CACHE.with_name('.self_six_overlap_build')
    if args.wide_pipe: CACHE = CACHE.with_name('.self_six_wide_build')
    if args.pw8: CACHE = CACHE.with_name('.self_six_pw8_build')
    if args.dw_priority: CACHE = CACHE.with_name(CACHE.name+'_priority')
    max_tasks = 2048 if args.frames == 10 else 1024
    label = 'self_ten' if args.frames == 10 else 'self_six'
    if args.frames == 10: CACHE = CACHE.with_name(CACHE.name.replace('self_six', 'self_ten'))
    data=args.data.resolve()
    manifest=json.loads((data/'manifest.json').read_text())
    assert manifest['frames']==args.frames and manifest['frame_contexts']==args.frames and manifest['full_network']==args.full
    assert manifest['max_tasks']==max_tasks
    assert manifest['init_bytes']<=33554432 and manifest['total_tasks']<=max_tasks
    for name,digest in manifest['files_sha256'].items():
        assert sha(data/name)==digest, name
    files = [ROOT / s.strip() for s in (ROOT/'rtl/filelists/cnn_self_stream.f').read_text().splitlines() if s.strip() and not s.startswith('#')]
    files += [ROOT/'tb/self_full_sim_top.sv', ROOT/'tb/integration/self_full_main.cpp']
    flags = ['--cc','--exe','--build','--top-module','self_full_sim_top','--no-timing','-DSYNTHESIS','--output-split-cfuncs','500','-Wno-fatal','-O1','-j','2','-GFRAME_CONTEXTS=6','-GK3_UNITS=2','-GK1_UNITS=4','-GPOST_UNITS=1','-GSRAM_SIZE=33554432','-CFLAGS','-std=c++20 -DCNN_FRAMES=6 -DCNN_SRAM=33554432 -DCNN_K3=2 -DCNN_K1=4 -DCNN_POST=1','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2']
    flags += ['-GPW4='+str(int(args.pw4)), '-GCONV_OVERLAP='+str(int(args.conv_overlap)), '-GWIDE_PIPE='+str(int(args.wide_pipe)), '-GPW8='+str(int(args.pw8)), '-GDW_PRIORITY='+str(int(args.dw_priority))]
    flags[flags.index('-GFRAME_CONTEXTS=6')]='-GFRAME_CONTEXTS='+str(args.frames)
    flags += ['-GMAX_TASKS='+str(max_tasks)]
    cflag=flags.index('-CFLAGS')+1
    flags[cflag]=flags[cflag].replace('-DCNN_FRAMES=6','-DCNN_FRAMES='+str(args.frames))+' -DCNN_MAX_TASKS='+str(max_tasks)
    signature = dict(sources={str(p.relative_to(ROOT)):sha(p) for p in files}, flags=flags, verilator=sha(VR/'bin/verilator_bin'))
    CACHE.mkdir(exist_ok=True)
    exe = CACHE/'obj/Vself_full_sim_top'
    stamp = CACHE/'signature.json'
    compile_seconds=0
    if args.reuse:
        old=json.loads(stamp.read_text())
        assert old['signature']==signature and old['exe_sha256']==sha(exe), 'cache mismatch'
    else:
        staged=[]
        for p in files:
            dest=CACHE/p.name
            shutil.copyfile(p,dest)
            staged.append(str(dest))
        env=dict(os.environ, VERILATOR_ROOT=str(VR))
        begin=time.perf_counter()
        with (CACHE/'compile.log').open('w') as log:
            subprocess.run([str(VR/'bin/verilator'),*flags,'--Mdir',str(CACHE/'obj'),*staged],cwd=CACHE,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        compile_seconds=time.perf_counter()-begin
        save(stamp,dict(signature=signature,exe_sha256=sha(exe),compile_seconds=compile_seconds))
    if args.full:
        assert args.gate, 'full-network execution requires a matching small gate'
        gate=json.loads((args.gate/'result.json').read_text())
        assert gate['status']=='PASS' and not gate['full_network'] and gate['frames']==args.frames and gate['exe_sha256']==sha(exe) and gate.get('pw4',False)==args.pw4
        assert gate['source_signature']==signature
        assert gate.get('conv_overlap',False)==args.conv_overlap
        assert gate.get('wide_pipe',False)==args.wide_pipe
        assert gate.get('pw8',False)==args.pw8 and gate.get('dw_priority',False)==args.dw_priority
        assert set(gate['scenarios'])=={'overlap','serial','preloaded','stress'}
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+label)
    out.mkdir()
    result=dict(status='RUNNING',frames=args.frames,max_tasks=max_tasks,full_network=args.full,data=str(data),manifest_sha256=sha(data/'manifest.json'),source_signature=signature,exe_sha256=sha(exe),pw4=args.pw4,conv_overlap=args.conv_overlap,wide_pipe=args.wide_pipe,pw8=args.pw8,dw_priority=args.dw_priority,compile_seconds=compile_seconds,pool=dict(K3=2,K1=4,Post=1,Add=1,DW7=1,Pad=1),sram_capacity=33554432,input_pace=80,scenarios={},runner_sha256=sha(__file__),started_at=datetime.now().isoformat(),gate=str(args.gate.resolve()) if args.gate else None)
    save(out/'result.json',result)
    print('RUN '+str(out),flush=True)
    began=time.perf_counter()
    try:
        for mode in (['overlap'] if args.full else ['overlap','serial','preloaded','stress']):
            dest=out/mode;dest.mkdir()
            result['active_mode']=mode;save(out/'result.json',result)
            start=time.perf_counter()
            with (dest/'simulation.log').open('w') as log:
                subprocess.run([str(exe),str(data),str(dest),mode,'80'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=86400)
            metrics=json.loads((dest/'metrics.json').read_text())
            assert metrics['status']=='PASS' and metrics['commands']==manifest['total_tasks'] and metrics['macs']==manifest['total_macs']
            assert len(metrics['frames'])==args.frames and len((dest/'outputs.bin').read_bytes())==args.frames*manifest['final_bytes_per_frame']
            assert sha(dest/'outputs.bin')==manifest['final_expected_sha256']
            result['scenarios'][mode]=dict(metrics=metrics,wall_seconds=time.perf_counter()-start,outputs_sha256=sha(dest/'outputs.bin'))
            save(out/'result.json',result)
            print('PASS '+mode+' '+str(metrics['cycles'])+' cycles',flush=True)
        result['status']='PASS'
    except BaseException as exc:
        result['status']='FAIL';result['error']=str(exc)
        raise
    finally:
        result['wall_seconds']=time.perf_counter()-began
        result['finished_at']=datetime.now().isoformat()
        save(out/'result.json',result)
    print('PASS RUN '+str(out),flush=True)
if __name__=='__main__':
    main()
