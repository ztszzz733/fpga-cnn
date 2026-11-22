
import ctypes
import hashlib
import json
import subprocess
import time
from pathlib import Path

root=Path(__file__).resolve().parent
vivado=Path('D:/vivado/2025.2/Vivado/bin/vivado.bat')
part='xc7z020clg484-1'
files=[root/f for f in (root/'cnn.f').read_text().splitlines() if f.strip()]
files += [root/'rtl'/f for f in ('tile_local_ram.sv','tile_read_width.sv','tile_local_ram_bank2.sv','data_mover.sv','cnn_paged_mover.sv')]
files += [root/'burst_bank_test.sv']

class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
        (name,ctypes.c_ulonglong) for name in ['total_phys','free_phys','total_page','free_page','total_virtual','free_virtual','free_ext']]

def memory():
    m=Memory()
    m.length=ctypes.sizeof(m)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.free_page/2**30

def run(out,name,lines,marker):
    script=out / f'{name}.tcl'
    script.write_text('\n'.join(lines+[f'puts {marker}','exit 0'])+'\n')
    assert memory()>=4, 'Need at least 4 GiB available commit memory'
    t=time.perf_counter()
    with (out/f'{name}_launcher.log').open('w') as log:
        p=subprocess.Popen([str(vivado),'-mode','batch','-source',str(script),'-log',str(out/f'{name}.log'),'-journal',str(out/f'{name}.jou')],
            cwd=out,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        while p.poll() is None:
            time.sleep(4)
            if memory()<2:
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                p.wait()
                raise RuntimeError(f'Memory guard stopped {name}')
    assert p.returncode==0 and marker in (out/f'{name}.log').read_text(errors='replace'), out/f'{name}_launcher.log'
    return round(time.perf_counter()-t,2)

def brace(f):
    return '{'+f.as_posix()+'}'

def measure(mode):
    out=root/f'vivado_k3_wide_{mode}_192k_256bit'
    out.mkdir(exist_ok=True)
    info=out/'result.json'
    result={'mode':mode,'local_bytes':192*1024,'write_bits':256,'part':part,'clock_ns':10,'top':'burst_bank_test','status':'PREPARING',
            'source_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    def save():
        info.write_text(json.dumps(result,indent=2))
    save()
    xdc=out/'clock.xdc'
    xdc.write_text('create_clock -name cnn_clk -period 10.000 [get_ports clk]\n')
    ckpt=brace(out/'synth.dcp')
    reports=lambda name:[
        f'report_utilization -file {brace(out/(name+"_utilization.rpt"))}',
        f'report_utilization -hierarchical -file {brace(out/(name+"_hierarchy.rpt"))}',
        f'report_timing_summary -delay_type min_max -report_unconstrained -file {brace(out/(name+"_timing.rpt"))}',
        f'report_timing -delay_type max -max_paths 10 -file {brace(out/(name+"_paths.rpt"))}']
    try:
        result['status']='SYNTH'
        save()
        result['synth_seconds']=run(out,'synth',[
            'set_param general.maxThreads 2',f'create_project -in_memory -part {part}',
            *[f'read_verilog -sv {brace(p)}' for p in files],
            f'read_xdc {brace(xdc)}',
            f'synth_design -top burst_bank_test -generic PACKED_WRITE={mode} -mode out_of_context -part {part} -flatten_hierarchy rebuilt -max_bram_cascade_height 1',
            *reports('synth'),f'write_checkpoint -force {ckpt}'],'BANK_SYNTH_DONE')
        result['status']='ROUTE'
        save()
        result['route_seconds']=run(out,'route',[
            'set_param general.maxThreads 2',f'open_checkpoint {ckpt}',
            'set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]',
            'opt_design','place_design','phys_opt_design','route_design',
            f'report_route_status -file {brace(out/"route_status.rpt")}', *reports('route')],'BANK_ROUTE_DONE')
        result['status']='COMPLETE'
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        save()
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}),flush=True)

if __name__=='__main__':
    import sys
    for mode in map(int,sys.argv[1:]):
        assert mode in (0,1)
        measure(mode)

