"""Compile once; replay small real-weight chain cases. Run under WSL Python."""
import argparse,datetime,hashlib,json,os,shutil,time
from pathlib import Path
from run_neureka_benchmark import sources
from run_tests import ROOT,execute
STAGE=ROOT.parents[1]/'.neureka_chain_build'
SIGNALS=[('rst_n',1),('job',32),('conv_start',1),('core_state',6),('core_busy',1),('accum_done',1),('prefetch_done',1),
         ('conv_read_fire',1),('conv_write_fire',1),('cdone',1),('post_start',1),('mode_add',1),('pbusy',1),
         ('post_read_fire',1),('post_write_fire',1),('pdone',1),('memory_fault',1)]
def monitor():
    lines=['initial begin wave=$fopen("control.vcd","w");', '$fwrite(wave,"$timescale 1ns $end\\n$scope module chain $end\\n");']
    for i,(n,w) in enumerate(SIGNALS):lines.append(f'$fwrite(wave,"$var wire {w} s{i} {n} $end\\n");')
    lines+=['$fwrite(wave,"$upscope $end\\n$enddefinitions $end\\n");end','logic first=1;']
    for n,w in SIGNALS:lines.append(f'logic [{w-1}:0] prev_{n};')
    lines+=['always @(posedge clk) begin','$fwrite(wave,"#%0d\\n",$time);']
    for i,(n,w) in enumerate(SIGNALS):lines += [f'if(first || prev_{n}!=={n})$fwrite(wave,"b%b s{i}\\n",{n});',f'prev_{n}={n};']
    return '\n'.join(lines+['first=0;end'])
def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--reuse',action='store_true');a=p.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_mobilefacenet_chain');out.mkdir(parents=True)
    print('RUN_DIR='+str(out),flush=True);start=time.perf_counter()
    result=dict(status='RUNNING',timing_seconds={},cases={},data_source=str(a.data))
    def save():(out/'result.json').write_text(json.dumps(result,indent=2))
    src=[s for s in sources() if s.name!='tb_neureka_benchmark.sv']+[ROOT/'rtl/cnn_quant/quant_post_engine.sv',ROOT/'tb/integration/tb_mobilefacenet_chain.sv']
    key=dict(hashes={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src},monitor=hashlib.sha256(monitor().encode()).hexdigest(),flags_version=1)
    result['build_inputs']=key;save()
    STAGE.mkdir(parents=True,exist_ok=True);exe=STAGE/'obj/Vtb_mobilefacenet_chain';manifest=STAGE/'build_inputs.json'
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
            (STAGE/'chain_monitor.svh').write_text(monitor())
            execute([vr/'bin/verilator','--binary','--timing','--assert','--timescale-override','1ns/1ps','-Wno-fatal','-O1','-j','4',
                     '-CFLAGS','-std=c++20','-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1',
                     '--top-module','tb_mobilefacenet_chain','--Mdir',STAGE/'obj','-I'+str(STAGE),*staged],STAGE,env,out/'compile.log',timeout=1800)
            manifest.write_text(json.dumps(key,indent=2));result['timing_seconds']['compile']=time.perf_counter()-stamp
        save()
        for name,stall in [('normal',0),('backpressure',1)]:
            case=out/name;case.mkdir()
            for f in a.data.iterdir():
                if f.is_file():shutil.copyfile(f,case/f.name)
            stamp=time.perf_counter();execute([exe,f'+stall={stall}'],case,env,case/'sim.log',timeout=300)
            assert 'PASS tb_mobilefacenet_chain' in (case/'sim.log').read_text()
            result['cases'][name]=json.loads((case/'metrics.json').read_text());result['timing_seconds'][name]=time.perf_counter()-stamp;save()
            print(name+': '+json.dumps(result['cases'][name]),flush=True)
        result['status']='PASS'
    except Exception as e:result['status']='FAIL';result['error']=str(e);print(str(e),flush=True)
    result['timing_seconds']['total']=time.perf_counter()-start;save()
    return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
