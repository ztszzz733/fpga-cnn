"""Continuous-frame regression: actual main CPU/bridge/SRAM/scheduler, scalar cores.

--real-cores uses the pinned actual arithmetic cores and never substitutes models.
The default model regression cannot establish real-core correctness or speedup.
"""
import argparse,datetime,hashlib,json,re,struct
from pathlib import Path
from run_tests import ROOT,tools,tool_env,execute
from gen_neureka_frames import generate


def build_firmware(out,env):
    toolchain=Path('D:/vivado/2026.1/gnu/riscv/nt/x86_64-w64-mingw32/usr/bin/riscv32-xilinx-elf')
    gcc=toolchain/'riscv32-xilinx-elf-gcc.exe'
    # Use the installed cross compiler; no tool download or runtime interpreter.
    import os
    gcc=Path(os.environ.get('RISCV_GCC',str(gcc)))
    if not gcc.is_file():raise RuntimeError('Set RISCV_GCC to an RV32I-capable bare-metal GCC')
    env=env.copy();env['PATH']=str(gcc.parent)+os.pathsep+str(gcc.parent.parent)+os.pathsep+env.get('PATH','')
    prefix=str(gcc).removesuffix('gcc.exe').removesuffix('gcc')
    objcopy=Path(prefix+('objcopy.exe' if gcc.suffix=='.exe' else 'objcopy'))
    objdump=Path(prefix+('objdump.exe' if gcc.suffix=='.exe' else 'objdump'))
    src=ROOT/'firmware/neureka_frames_demo'
    execute([gcc,'-march=rv32i','-mabi=ilp32','-O2','-Wall','-Wextra','-Werror',
        '-ffreestanding','-fno-builtin','--param=min-pagesize=0','-fno-stack-protector','-msmall-data-limit=0','-mno-relax',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-T',src/'link.ld',
        '-I',ROOT/'sw/neureka_pipeline',src/'start.S',src/'main.c','-o',out/'cpu.elf'],out,env,out/'firmware.log')
    execute([objcopy,'-O','binary',out/'cpu.elf',out/'cpu.bin'],out,env,out/'firmware.log')
    execute([objdump,'-d',out/'cpu.elf'],out,env,out/'cpu.lst')
    binary=(out/'cpu.bin').read_bytes();binary+=bytes((-len(binary))%4)
    words=[x[0] for x in struct.iter_unpack('<I',binary)]
    if len(words)>16384:raise RuntimeError('main instruction ROM overflow')
    (out/'cpu.hex').write_text(''.join(f'{w:08x}\n' for w in words+[0x13]*(16384-len(words))))
    return {'compiler':str(gcc),'instruction_words':len(words)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--real-cores',action='store_true');a=ap.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_neureka_frames')
    out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'actual main CPU, bridge, banked SRAM, mailbox and tile scheduler; '+
            ('real pinned arithmetic cores' if a.real_cores else 'TEST-ONLY scalar convolution/PReLU models')}
    try:
        f=tools();env=tool_env(f);generate(out);result['firmware']=build_firmware(out,env)
        result['assets']={name:hashlib.sha256((out/name).read_bytes()).hexdigest()
            for name in ['cpu.hex','sram.hex','external.hex','frames_golden.hex','frames.json','vector.bin']}
        if a.real_cores:
            # Share all real-core XSim compatibility handling, but use this demo.
            from run_neureka_pipeline import compile_real
            compile_real(out,f,env,ROOT/'tb/integration/tb_neureka_frames.sv',result,snapshot='frames')
        else:
            cpu=[ROOT/s.strip() for s in (ROOT/'rtl/filelists/system_autoload.f').read_text().splitlines()
                 if s.strip() and not s.startswith('#')]
            cpu=cpu[:cpu.index(ROOT/'rtl/soc/datasram.sv')]
            src=cpu+[ROOT/p for p in ['rtl/soc/clock_unit.sv','rtl/soc/autoload/autoload_uart.sv',
                'rtl/soc/autoload/cpu_core_autoload.sv','rtl/soc/autoload/image_bridge_autoload.sv',
                'rtl/overlap/datasram_banked.sv','rtl/hybrid/cnn_command_port.sv',
                'rtl/neureka_pipeline/neureka_tile_scheduler.sv','tb/integration/neureka_frame_models.sv',
                'rtl/neureka_pipeline/neureka_pipeline_cnn_top.sv','rtl/neureka_pipeline/face_soc_neureka_pipeline_top.sv',
                'tb/integration/tb_neureka_frames.sv','tb/integration/tb_image_load_descriptor.sv']]
            src += [ROOT/'sw/neureka_pipeline/cnn_frames.h',ROOT/'sw/neureka_pipeline/neureka_pipeline.h',
                    ROOT/'firmware/neureka_frames_demo/main.c',ROOT/'firmware/neureka_frames_demo/start.S',
                    ROOT/'firmware/neureka_frames_demo/link.ld']
            result['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src}
            execute([f['xvlog'],'-sv',*[p for p in src if p.suffix=='.sv']],out,env,out/'compile.log',240)
            execute([f['xelab'],'tb_neureka_frames','-s','frames','--debug','typical'],out,env,out/'elaborate.log',240)
            execute([f['xelab'],'tb_image_load_descriptor','-s','descriptor','--debug','typical'],out,env,out/'elaborate.log',180)
        result['tests']={}
        cases=[('frames',0,20000),('frames',0,0),('frames',1,20000),('descriptor',None,None)] if not a.real_cores else [('frames',0,None),('frames',1,None)]
        for snapshot,mode,delay in cases:
            name=snapshot+('' if mode is None else '_'+str(mode))+('' if delay is None else '_delay'+str(delay));log=out/(name+'.log')
            args=[] if mode is None else ['-testplusarg',f'TEST_MODE={mode}']
            if delay is not None:args+=['-testplusarg',f'CONV_DELAY={delay}']
            execute([f['xsim'],snapshot,'-runall',*args],out,env,log,600)
            text=log.read_text(errors='replace')
            marker='PASS tb_image_load_descriptor' if mode is None else f'PASS tb_neureka_frames mode={mode}'
            if marker not in text or re.search(r'^(?:Error:|Fatal:|ERROR:|FAIL)',text,re.M):raise RuntimeError('Missing PASS: '+str(log))
            result['tests'][name]='PASS';print('PASS '+name,flush=True)
            metrics=re.search(r'FRAME_METRICS overlap=\s*(\d+) cpu_access_while_cnn=\s*(\d+) three_way_bank_access=\s*(\d+) cpu_result_work=\s*(\d+)',text)
            if metrics:result.setdefault('model_metrics' if not a.real_cores else 'metrics',{})[name]=dict(zip(
                ['overlap_cycles','cpu_access_while_cnn','three_way_bank_access','cpu_work_bytes'],map(int,metrics.groups())))
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2));print('STATUS='+result['status'],flush=True)


if __name__=='__main__':main()
