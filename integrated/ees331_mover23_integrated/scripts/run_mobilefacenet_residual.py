"""Real residual branch joins, safe feature release and overlapping execution.
Run in WSL. A new isolated simulator is built once and hash-checked on reuse.
"""
import argparse,datetime,hashlib,json,os,shutil,time
from pathlib import Path
from run_neureka_benchmark import sources
from run_tests import ROOT,execute
STAGE=ROOT.parents[1]/'.neureka_residual_build'
SIGNALS=[('rst_n',1),('clear',1),('start',1),('busy',1),('done',1),('error',1),('completed_mask',32),('slot_states',9),('slot_limit',2),('slot0_state',3),('slot1_state',3),('slot2_state',3),('engine_enable',2),('both_compute',1)]
for e in range(2):
    SIGNALS += [(f'{n}[{e}]',w) for n,w in [('conv_start',1),('conv_node',5),('conv_frame',8),('conv_layer',8),('conv_stripe',8),('conv_slot',2),('engine_busy',1),('core_busy',1),('core_state',6),('compute_active',1),('conv_read_fire',1),('conv_write_fire',1),('conv_tile_done',1)]]
SIGNALS += [('post_start',1),('post_node',5),('post_frame',8),('post_layer',8),('post_stripe',8),('post_slot',2),('post_busy',1),('post_read_fire',1),('post_write_fire',1),('post_address',32),('post_done',1),('compute_post_overlap',1),('memory_fault',1),('triple_active',1),('triple_write',1),('wait_slot',1),('wait_dependency',1),('wait_engine',1),('wait_post',1),('mem_wait0',1),('mem_wait1',1),('mem_wait_post',1),('post_add',1),('released_mask',32),('release_pulse',32),('live_mask',32)]
def label(n):return n.replace('[','').replace(']','')

def monitor():
    lines=['initial begin wave=$fopen("control.vcd","w");','$fwrite(wave,"$timescale 1ns $end\\n$scope module pipeline $end\\n");']
    for i,(n,w) in enumerate(SIGNALS):lines.append(f'$fwrite(wave,"$var wire {w} s{i} {label(n)} $end\\n");')
    lines+=['$fwrite(wave,"$upscope $end\\n$enddefinitions $end\\n");end','logic first=1;']
    for n,w in SIGNALS:lines.append(f'logic [{w-1}:0] prev_{label(n)};')
    lines+=['always @(posedge clk) begin','$fwrite(wave,"#%0d\\n",$time);']
    for i,(n,w) in enumerate(SIGNALS):lines += [f'if(first || prev_{label(n)}!=={n})$fwrite(wave,"b%b s{i}\\n",{n});',f'prev_{label(n)}={n};']
    return '\n'.join(lines+['first=0;end'])
def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--reuse',action='store_true')
    a=p.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_mobilefacenet_residual');out.mkdir(parents=True)
    print('RUN_DIR='+str(out),flush=True);start=time.perf_counter()
    result=dict(status='RUNNING',timing_seconds={},cases={},data_source=str(a.data))
    result['data_hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.data.iterdir() if f.is_file()}
    def save():(out/'result.json').write_text(json.dumps(result,indent=2))
    src=[s for s in sources() if s.name!='tb_neureka_benchmark.sv']+[ROOT/'rtl/cnn_quant/quant_post_engine.sv',ROOT/'rtl/cnn_quant/quant_residual_scheduler.sv',ROOT/'tb/integration/tb_mobilefacenet_residual.sv']
    key=dict(hashes={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src},monitor=hashlib.sha256(monitor().encode()).hexdigest(),flags_version=1)
    key['include_hashes']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for repo in ['hci','hwpe-stream','hwpe-ctrl'] for f in (ROOT/'third_party'/repo).rglob('*.svh')}
    result['build_inputs']=key;save()
    STAGE.mkdir(parents=True,exist_ok=True);exe=STAGE/'obj/Vtb_mobilefacenet_residual';manifest=STAGE/'build_inputs.json'
    vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
    try:
        stamp=time.perf_counter()
        if a.reuse:
            assert exe.exists() and json.loads(manifest.read_text())==key,'stale simulator: rebuild required'
            result['timing_seconds']['compile']=0
        else:
            staged=[]
            for i,s in enumerate(src):
                d=STAGE/f'{i:03}_{s.name}'
                if not d.exists() or d.read_bytes()!=s.read_bytes():shutil.copyfile(s,d)
                staged.append(d)
            for repo in ['hci','hwpe-stream','hwpe-ctrl']:
                for inc in (ROOT/'third_party'/repo).rglob('*.svh'):shutil.copyfile(inc,STAGE/inc.name)
            (STAGE/'residual_monitor.svh').write_text(monitor())
            execute([vr/'bin/verilator','--binary','--timing','--assert','--timescale-override','1ns/1ps','-Wno-fatal','-O1','-j','4',
                     '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1',
                     '--top-module','tb_mobilefacenet_residual','--Mdir',STAGE/'obj','-I'+str(STAGE),*staged],STAGE,env,out/'compile.log',timeout=1800)
            manifest.write_text(json.dumps(key,indent=2));result['timing_seconds']['compile']=time.perf_counter()-stamp
        save()
        for name,opts in [('residual',[]),('recycle_stall',['+poison','+stall=1']),('restart',['+restart'])]:
            case=out/name;case.mkdir()
            for f in a.data.iterdir():
                if f.is_file():
                    assert hashlib.sha256(f.read_bytes()).hexdigest()==result['data_hashes'][f.name],'data changed during build'
                    shutil.copyfile(f,case/f.name)
            stamp=time.perf_counter();execute([exe,*opts],case,env,case/'sim.log',timeout=600)
            assert 'PASS tb_mobilefacenet_residual' in (case/'sim.log').read_text()
            m=json.loads((case/'metrics.json').read_text());m['output_sha256']=hashlib.sha256((case/'outputs.bin').read_bytes()).hexdigest()
            result['cases'][name]=m;result['timing_seconds'][name]=time.perf_counter()-stamp;save()
            print(name+': '+json.dumps(m),flush=True)
        assert len({m['output_sha256'] for m in result['cases'].values()})==1,'residual output mismatch across stress cases'
        result['status']='PASS'
    except Exception as e:result['status']='FAIL';result['error']=str(e);print(str(e),flush=True)
    result['timing_seconds']['total']=time.perf_counter()-start;save()
    return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
