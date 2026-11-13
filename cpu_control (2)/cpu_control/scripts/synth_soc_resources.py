"""Measure existing CPU/peripherals, without presenting old CNN as the new CNN."""
import argparse,ctypes,hashlib,json,os,subprocess,time
from datetime import datetime
from pathlib import Path
ROOT=Path('D:/code/FPGA1/cpu_control (2)/cpu_control')
class MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(s,ctypes.c_ulonglong) for s in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]
def available():
    m=MemoryStatus();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--components',nargs='+',choices=['cpu','bridge','clock'],default=['cpu','bridge','clock']);args=ap.parse_args()
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_soc_resource_audit');run.mkdir(parents=True)
    print('RUN_DIR='+str(run),flush=True)
    manifest=(ROOT/'rtl/filelists/system_partner_datapath_b1.f').read_text().splitlines()
    cpu=manifest[:manifest.index('partners/datapath/delivery/rtl/soc_memory/imem_rom.sv')]+['rtl/soc/cpu_core.sv']
    result=dict(status='RUNNING',part='xc7z020clg484-1',measurement='independent OOC synthesis; not an integrated SoC',period_ns=10,started=datetime.now().isoformat(),components={})
    def save():(run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    for name,top,files,clk in [('cpu','cpu_core',cpu,'clk'),('bridge','image_bridge',['rtl/soc/image_bridge.sv'],'clk'),('clock','clock_unit',['rtl/soc/clock_unit.sv'],'sys_clk')]:
        if name not in args.components:continue
        out=run/name;out.mkdir();stage=ROOT.parents[1]/'.self_synth_launch'/run.name/name;stage.mkdir(parents=True)
        sources=[ROOT/x for x in files];r=dict(status='RUNNING',top=top,source_sha256={x:sha(ROOT/x) for x in files},defaults=True,place_route_performed=False)
        result['components'][name]=r;save()
        lines=['set_param general.maxThreads 2','create_project -in_memory -part xc7z020clg484-1']
        for i,p in enumerate(sources):
            target=stage/(str(i)+'_'+p.name);target.write_bytes(p.read_bytes());lines+=['read_verilog -sv {'+target.as_posix()+'}']
        (stage/'clock.xdc').write_text('create_clock -name clk -period 10 [get_ports '+clk+']\n')
        lines+=['read_xdc {'+(stage/'clock.xdc').as_posix()+'}','synth_design -top '+top+' -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt','report_utilization -file {'+(out/'utilization.rpt').as_posix()+'}','report_utilization -hierarchical -file {'+(out/'hierarchy.rpt').as_posix()+'}','report_timing_summary -max_paths 3 -file {'+(out/'timing.rpt').as_posix()+'}','write_checkpoint -force {'+(out/'synth.dcp').as_posix()+'}','puts SOC_RESOURCE_COMPLETE','exit 0']
        (stage/'entry.tcl').write_text('\n'.join(lines)+'\n',newline='\n')
        cmd=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-nojournal','-log',str(stage/'vivado.log'),'-source',str(stage/'entry.tcl')]
        env=os.environ.copy();env['XILINX_LOCAL_USER_DATA']='no';t=time.monotonic();stop=None
        with (out/'process.log').open('w',encoding='utf-8') as log:
            p=subprocess.Popen(cmd,cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            r['launcher_pid']=p.pid;save()
            while p.poll() is None:
                if time.monotonic()-t>300:stop='TIMEOUT';break
                if available()<1536*1024**2:stop='MEMORY_GUARD';break
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:pass
            if stop:
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW);p.wait(timeout=30)
        log=(out/'process.log').read_text(encoding='utf-8',errors='replace')
        r.update(status=stop or ('PASS' if p.returncode==0 and 'SOC_RESOURCE_COMPLETE' in log else 'FAIL'),seconds=round(time.monotonic()-t,3),errors=[x for x in log.splitlines() if x.startswith('ERROR:')][-8:],source_unchanged=all(sha(ROOT/k)==v for k,v in r['source_sha256'].items()))
        if r['status']=='PASS':
            rows={}
            for line in (out/'utilization.rpt').read_text().splitlines():
                c=[x.strip().rstrip('*').strip() for x in line.split('|')[1:-1]]
                if len(c)>=5 and c[0] in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):rows[c[0]]=float(c[1].replace(',',''))
            r['utilization']=rows
        save();print(name+' '+json.dumps(r.get('utilization',r['errors']))+' '+r['status'],flush=True)
    result.update(status='PASS' if all(x['status']=='PASS' for x in result['components'].values()) else 'PARTIAL',finished=datetime.now().isoformat());save()
    print(result['status']+' '+str(run),flush=True)
if __name__=='__main__':main()
