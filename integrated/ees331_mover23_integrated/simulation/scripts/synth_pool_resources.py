"""Measure current CNN without altering RTL. Only shared SRAM cells are black boxes."""
import argparse, ctypes, hashlib, json, os, re, shutil, subprocess, time
from datetime import datetime
from pathlib import Path

ROOT=Path('D:/code/FPGA1/cpu_control (2)/cpu_control')
CONFIG=dict(PW4=1,CONV_OVERLAP=1,WIDE_PIPE=1,PW8=1,DW_CACHE=1,POST_GROUP=16,K3_PAR4=1,DW_PRIORITY=0,FRAME_PRIORITY=1,FRAME_CONTEXTS=15,MAX_TASKS=2048,SLOTS=60,K3_UNITS=4,K1_UNITS=12,POST_UNITS=4,SRAM_SIZE=67108864)
class MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(s,ctypes.c_ulonglong) for s in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
def available_memory():
    m=MemoryStatus();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--component',default='full',choices=['full','post','add','dw7','pad','dispatch','leases','results','programmer','fabric']);ap.add_argument('--timeout',type=int,default=900);a=ap.parse_args()
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_pool_resources_'+a.component
    run=ROOT/'build/runs'/stamp;run.mkdir(parents=True)
    stage=ROOT.parents[1]/'.self_synth_launch'/stamp;stage.mkdir(parents=True)
    files=[ROOT/x.strip() for x in (ROOT/'rtl/filelists/cnn_self_stream.f').read_text().splitlines() if x.strip() and not x.startswith('#')]
    result=dict(status='RUNNING',component=a.component,run_dir=str(run),stage_dir=str(stage),configuration=CONFIG,part='xc7z020clg484-1',period_ns=10,source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files},shared_sram_blackboxed=True,place_route_performed=False,started=datetime.now().isoformat())
    def save():(run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    save();print('RUN_DIR='+str(run),flush=True)
    for p in files:
        txt=p.read_text(encoding='utf-8')
        if p.name=='datasram_banked.sv':
            begin=txt.index('module datasram_tdp_bank');head=txt.index(');',begin)+2;end=txt.index('endmodule',head)+len('endmodule')
            txt=txt[:begin]+'(* black_box = "yes" *) '+txt[begin:head]+'\nendmodule'+txt[end:]
        (stage/p.name).write_text(txt,encoding='utf-8',newline='\n')
    top='self_fixed_network_top';params=CONFIG.copy()
    choices={'post':('quant_post_pipe_engine',dict(MAX_CHANNELS=512,GROUP_BYTES=16)),'add':('quant_post_pipe_engine',dict(MAX_CHANNELS=512,GROUP_BYTES=16)), 'dw7':('dw7_cached_engine',dict(MAX_WIDTH=7,MAX_CHANNELS=512,LANES=8)), 'pad':('pad_hwc_engine',{}),'dispatch':('stream_dispatch',dict(FRAME_PRIORITY=1,DW_PRIORITY=0,FRAME_CONTEXTS=15,MAX_TASKS=2048,K3_UNITS=4,K1_UNITS=12,POST_UNITS=4)), 'leases':('stream_buffer_leases',dict(MAX_TASKS=2048,SLOTS=60)), 'results':('stream_result_handoff',dict(MAX_TASKS=2048,SLOTS=60)), 'programmer':('stream_fixed_programmer',dict(FRAME_CONTEXTS=15,MAX_TASKS=2048)), 'fabric':('datasram_banked',dict(SRAM_BASE=0,SRAM_SIZE=67108864,BANKS=4,CLIENTS=23))}
    if a.component!='full':top,params=choices[a.component]
    sources=[stage/p.name for p in files] if a.component=='full' else [stage/(top+'.sv' if a.component!='fabric' else 'datasram_banked.sv')]
    # A source-only wrapper ties the same constants as self_stream_top, while
    # retaining every other port so resource mapping cannot discard work.
    if a.component in ('post','add','dw7'):
        source=(stage/(top+'.sv')).read_text();start=source.index(')(\n')+2;end=source.index(');',start)
        ports=source[start:end];tied='mode_add' if a.component in ('post','add') else 'reuse_weights'
        ports=re.sub(r'\b'+tied+r',','',ports)
        ports=re.sub(','+tied+r'\b','',ports)
        wrapper='resource_wrapper';paramtext=','.join('.%s(%s)'%(k,v) for k,v in params.items())
        (stage/'resource_wrapper.sv').write_text('module '+wrapper+'(\n'+ports+');\n'+top+' #('+paramtext+') dut(.*,.'+tied+"(1'b"+('1' if a.component=='add' else '0')+'));\nendmodule\n',newline='\n')
        sources.append(stage/'resource_wrapper.sv');top=wrapper;params={}
    lines=['set_param general.maxThreads 2','create_project -in_memory -part xc7z020clg484-1']
    lines+=['read_verilog -sv {'+p.as_posix()+'}' for p in sources]
    (stage/'clock.xdc').write_text('create_clock -name clk -period 10 [get_ports clk]\n')
    lines+=['read_xdc {'+(stage/'clock.xdc').as_posix()+'}', 'synth_design -top '+top+' -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt -generic {'+' '.join(k+'='+str(v) for k,v in params.items())+'}', 'report_utilization -file {'+(run/'utilization.rpt').as_posix()+'}','report_utilization -hierarchical -file {'+(run/'utilization_hierarchical.rpt').as_posix()+'}','report_timing_summary -max_paths 5 -file {'+(run/'timing_summary.rpt').as_posix()+'}', 'write_checkpoint -force {'+(run/'synth.dcp').as_posix()+'}', 'puts POOL_RESOURCES_COMPLETE','exit 0']
    (stage/'entry.tcl').write_text('\n'.join(lines)+'\n',newline='\n')
    result['top']=top;result['synthesis_generics']=params;result['staged_sources_sha256']={p.name:sha(p) for p in sources};save()
    command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(stage/'vivado.log'),'-source',str(stage/'entry.tcl')]
    env=os.environ.copy();env['XILINX_LOCAL_USER_DATA']='no';t=time.monotonic();reason=None
    with (run/'process.log').open('w',encoding='utf-8') as log:
        p=subprocess.Popen(command,cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        result['launcher_pid']=p.pid;save()
        while p.poll() is None:
            if time.monotonic()-t>a.timeout:reason='TIMEOUT';break
            if available_memory()<1536*1024**2:reason='MEMORY_GUARD';break
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:pass
        if reason:
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            p.wait(timeout=30)
    text=(run/'process.log').read_text(encoding='utf-8',errors='replace')
    result.update(status=reason or ('PASS' if p.returncode==0 and 'POOL_RESOURCES_COMPLETE' in text else 'FAIL'),returncode=p.returncode,elapsed_seconds=round(time.monotonic()-t,3),finished=datetime.now().isoformat(),errors=[x for x in text.splitlines() if x.startswith('ERROR:')][-12:])
    if (run/'utilization.rpt').exists():
        rows={}
        for line in (run/'utilization.rpt').read_text().splitlines():
            cols=[x.strip().rstrip('*').strip() for x in line.split('|')[1:-1]]
            if len(cols)>=5 and cols[0] in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):
                rows[cols[0]]=dict(used=float(cols[1].replace(',','')),available=float(cols[-2].replace(',','')),percent=float(cols[-1]))
        result['utilization']=rows
    result['sources_unchanged']=all(sha(ROOT/k)==v for k,v in result['source_sha256'].items());save()
    print(json.dumps(result,ensure_ascii=False) if result['status']!='PASS' else json.dumps({k:result[k] for k in ['status','run_dir','elapsed_seconds','utilization']},ensure_ascii=False),flush=True)
    return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
