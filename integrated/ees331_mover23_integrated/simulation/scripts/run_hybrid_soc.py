"""Actual RV32I SoC + NVDLA + CV32E40X/Vicuna, bounded small SRAM-preload tests.

Run with WSL Python; preserves NVDLA timed RAM. No host MMIO injection.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, shlex, shutil, struct, time, zlib
from run_nvdla_small import ROOT, STAGE as NV, run, prepare_trace
from test_vicuna_small import compiler

STAGE=ROOT.parents[1]/'.hybrid_build'
VIC=ROOT.parents[1]/'.vicuna_build'
VECTOR_PROGRAM=r'''.option norvc
.option norelax
.section .vectors,"ax"
j fail
.section .text
.global _start
_start:
 li t0,0x6600
 csrs mstatus,t0
 csrw fcsr,zero
 li t0,0xffff0010
 lw a0,0(t0)
 lw a2,4(t0)
 lw a3,8(t0)
 lw a4,12(t0)
 beqz a3,finish
 bnez a4,float_setup
int_loop:
 vsetvli t1,a3,e8,m1,ta,ma
 vle8.v v1,(a0)
 vmslt.vi v0,v1,0
 vsra.vi v4,v1,2
 vmerge.vvm v3,v1,v4,v0
 vse8.v v3,(a2)
 add a0,a0,t1
 add a2,a2,t1
 sub a3,a3,t1
 bnez a3,int_loop
 j finish
float_setup:
 li t0,0x3e800000
 fmv.w.x ft1,t0
float_loop:
 vsetvli t1,a3,e32,m1,ta,ma
 vle32.v v1,(a0)
 # This pinned core needs multiply before comparison in the integrated setup;
 # the reverse order fails a preserved diagnostic, see integration notes.
 vfmul.vf v4,v1,ft1
 vmslt.vi v0,v1,0
 vmerge.vvm v3,v1,v4,v0
 vse32.v v3,(a2)
 slli t2,t1,2
 add a0,a0,t2
 add a2,a2,t2
 sub a3,a3,t1
 bnez a3,float_loop
finish:
 fence
 li t0,0xffff0000
 sw zero,0(t0)
stop:
 j stop
fail:
 li t0,0xffff0000
 li t1,1
 sw t1,0(t0)
 j stop
'''
CPU_COMMON=r'''
typedef unsigned int u32;
#define REG(a) (*(volatile u32 *)(a))
#define PORT 0x40000000u
#define VEC 0x40040000u
__attribute__((noreturn)) void fail(u32 n) { REG(0x80)=0xbad00000u|n; for(;;){} }
static u32 transaction(u32 address,u32 value,u32 command) {
 REG(PORT)=address; REG(PORT+4)=value; REG(PORT+8)=command;
 for(u32 n=0;n<100000;n++) {
  u32 s=REG(PORT+12);
  if(s&4)fail(1);
  if((s&3)==2)return REG(PORT+16);
 }
 fail(2);
}
static void wr(u32 a,u32 d){transaction(a,d,1);}
static u32 rd(u32 a){return transaction(a,0,2);}
static void poll(u32 a,u32 value,u32 mask) {
 for(u32 n=0;n<20000;n++)if((rd(a)&mask)==value)return;
 fail(3);
}
static void vec_setup(u32 src,u32 dst,u32 count,u32 mode) {
 wr(VEC+4,src);wr(VEC+8,dst);wr(VEC+12,count);wr(VEC+16,mode);
}
static void vec_wait(void){poll(VEC,2,3);if(rd(VEC)&12)fail(4);if(rd(VEC+20))fail(5);}
'''

def hexwords(path,data,size):
    assert len(data)<=size
    data=data+bytes(size-len(data))
    path.write_text(''.join(f'{v[0]:08x}\n' for v in struct.iter_unpack('<I',data)))

def compile_program(gcc,folder,name,source,isa,abi,link):
    src=folder/(name+('.c' if name=='cpu' else '.S'));src.write_text(source)
    (folder/(name+'.ld')).write_text(link)
    extra=[]
    if name=='cpu':
        startup=folder/'start.S'
        startup.write_text('.option norvc\n.option norelax\n.section .start,"ax"\n.global _start\n_start:\n li sp,0x3fff0\n call main\n1: j 1b\n')
        extra=[startup]
    run([gcc,'-march='+isa,'-mabi='+abi,'-O1','-nostdlib','-nostartfiles','-ffreestanding',
         '-fno-builtin','-fno-pic','-msmall-data-limit=0','-mno-relax','-Wl,--no-relax',
         '-T',folder/(name+'.ld'),*extra,src,'-o',folder/(name+'.elf')],folder,folder/'firmware_compile.log',60)
    objcopy=gcc.with_name('riscv-none-elf-objcopy')
    run([objcopy,'-O','binary',folder/(name+'.elf'),folder/(name+'.bin')],folder,folder/'firmware_compile.log',30)
    return (folder/(name+'.bin')).read_bytes()

def prepare_case(out,name,official,parallel=False):
    case=out/name;case.mkdir()
    prepare_trace(NV/'hw',official,case)
    gcc,_=compiler()
    vector=compile_program(gcc,case,'vector',VECTOR_PROGRAM,'rv32imf_zfh_zve32f_zvfh_zicsr','ilp32f',
        'OUTPUT_ARCH(riscv)\nENTRY(_start)\nSECTIONS { .vectors 0 : { *(.vectors) } .text 0x80 : { *(.text*) } }\n')
    assert len(vector)<=0x4000
    vector+=bytes((-len(vector))%4)
    memory=bytearray(0x40000)
    memory[0x20000:0x20000+len(vector)]=vector
    memory[0x18000:0x1c000]=bytes([0xa5])*0x4000
    fp=[((i%37)-18)*0.5 for i in range(256)]
    memory[0x30000:0x30400]=b''.join(struct.pack('<f',x) for x in fp)
    lines=(case/'commands.txt').read_text().splitlines()
    ops=[];check=None
    for line in lines:
        p=line.split();op=p[0]
        if op=='Z':
            a,n=[int(x,16) for x in p[1:]];memory[a:a+n]=bytes(n)
        elif op=='L':
            a=int(p[1],16);data=(case/p[2]).read_bytes();memory[a:a+len(data)]=data
        elif op=='W':ops.append(f'wr(0x{0x40000000+int(p[1],16):x}u,0x{p[2]}u);')
        elif op=='P':ops.append(f'poll(0x{0x40000000+int(p[1],16):x}u,0x{p[2]}u,0x{p[3]}u);')
        elif op=='I':ops.append(f'REG(0x84)=3; poll(PORT+0x100c,0x{p[1]}u,0x{p[1]}u);')
        elif op=='C':check=tuple(int(x,16) for x in p[1:])
    assert check
    src,n,crc=check
    if parallel:
        # Launch immediately before enabling PDP RDMA; buffers are disjoint.
        ix=next(i for i,x in enumerate(ops) if '0x4000a008u,0x1u' in x)
        ops.insert(ix,'wr(VEC,1);')
    chain_n=7 if n==8 else n # partial byte mask + guard byte in the tiny test
    body='\n'.join(ops)
    code=CPU_COMMON+f'''
void main(void) {{
 REG(0x84)=1;
 for(u32 i=0;i<{len(vector)};i+=4)wr(VEC+0x1000+i,REG(0x20000+i));
 {'vec_setup(0x30000,0x31000,256,1);' if parallel else ''}
 REG(0x84)=2;
 {body}
 {'REG(0x84)=4;vec_wait();' if parallel else ''}
 REG(0x84)=5;
 vec_setup(0x{src:x},0x18000,{chain_n},0);wr(VEC,1);vec_wait();
 // Repeat without resetting SoC; verify per-job done clearing and core restart.
 REG(0x84)=6;
 vec_setup(0x{src:x},0x1a000,3,0);wr(VEC,1);vec_wait();
 REG(0x84)=7;
 REG(0x80)=0x600dcafe;
 for(;;){{}}
}}
'''
    cpu=compile_program(gcc,case,'cpu',code,'rv32i','ilp32',
        'OUTPUT_ARCH(riscv)\nENTRY(_start)\nSECTIONS { .text 0 : { *(.start) *(.text*) *(.rodata*) } /DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n')
    hexwords(case/'cpu.hex',cpu,0x10000);hexwords(case/'sram.hex',memory,0x40000)
    spec={'official':official,'nvdla_output':src,'output_size':n,'crc32':f'{crc:08x}',
          'chain_count':chain_n,'parallel':parallel,'expected_vector_jobs':3 if parallel else 2,
          'program_words':len(vector)//4,'cpu_words':(len(cpu)+3)//4}
    (case/'case.json').write_text(json.dumps(spec,indent=2))
    return case,spec,fp

def vicuna_inputs():
    # Reuse the exact successful dependency/config selection, not the old binary.
    dat=VIC/'model/CMakeFiles/verilated_model.dir/Vvproc_top.dir/Vvproc_top__verFiles.dat'
    line=next(l for l in dat.read_text().splitlines() if l.startswith('C "'))
    args=shlex.split(line[3:-1]);result=[];i=0
    while i<len(args):
        a=args[i]
        if a=='-y':result+=args[i:i+2];i+=2;continue
        if a.startswith('-D') or a.startswith('-Wno-'):result.append(a)
        elif a.endswith(('.sv','.v')) and not a.endswith('/vproc_top.sv'):result.append(a)
        i+=1
    return result

def build(out,reuse):
    local=STAGE/'local';local.mkdir(parents=True,exist_ok=True)
    files=(ROOT/'rtl/filelists/system_hybrid_local.f').read_text().splitlines()
    files+=['tb/integration/hybrid_soc_harness.sv','tb/integration/hybrid_soc_driver.cpp']
    paths=[]
    for i,f in enumerate(files):
        p=local/(str(i)+'_'+Path(f).name);shutil.copyfile(ROOT/f,p);paths.append(p)
    vi=vicuna_inputs()
    hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
    hashes.update({str(Path(x).relative_to(VIC)):hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in vi if x.endswith(('.sv','.v'))})
    key={'hashes':hashes,'timed_ram':True,'flags_version':1}
    obj=STAGE/'obj';exe=obj/'Vhybrid_soc_harness';manifest=STAGE/'build_inputs.json'
    vr=NV/'verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
    cmd=[vr/'bin/verilator','--timing','--timescale-override','1ns/1ps','--assert',
         '-Wno-fatal','-DDISABLE_TESTPOINTS','--unroll-count','1024','--top-module','hybrid_soc_harness',
         '-f',NV/'adapter/upstream.f',*vi,*paths]
    if reuse:
        if not exe.exists() or not manifest.exists() or json.loads(manifest.read_text())!=key:
            raise RuntimeError('--reuse requires matching sources/configuration')
        seconds=0
    else:
        print('Elaborating integrated SoC...',flush=True)
        run([*cmd,'--lint-only'],local,out/'elaborate.log',120,env)
        print('Compiling integrated RTL (two compiler processes)...',flush=True)
        seconds=run([*cmd,'--cc','--exe','--build','-j','2','-O1','--output-split','5000',
            '--output-split-cfuncs','100','--Mdir',obj,'-CFLAGS','-std=c++20',
            '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1'],local,out/'compile.log',1200,env)
        manifest.write_text(json.dumps(key,indent=2))
    return exe,seconds,hashes

def check(case,spec,fp):
    data=(case/'sram.bin').read_bytes()
    raw=data[spec['nvdla_output']:spec['nvdla_output']+spec['output_size']]
    crc=f'{zlib.crc32(raw):08x}';assert crc==spec['crc32'],(crc,spec['crc32'])
    def prelu(b):
        v=b if b<128 else b-256
        return (v if v>=0 else v//4)&255
    n=spec['chain_count'];expected=bytes(prelu(b) for b in raw[:n])
    assert data[0x18000:0x18000+n]==expected,'chain PReLU output mismatch'
    assert data[0x18000+n:0x18004+n]==bytes([0xa5])*4,'tail guard overwritten'
    assert data[0x1a000:0x1a003]==bytes(prelu(b) for b in raw[:3]),'restart mismatch'
    assert data[0x1a003]==0xa5,'restart byte guard overwritten'
    (case/'nvdla_output.bin').write_bytes(raw)
    (case/'vector_expected.bin').write_bytes(expected)
    (case/'vector_output.bin').write_bytes(data[0x18000:0x18000+n])
    m=json.loads((case/'metrics.json').read_text())
    assert m['vector_jobs']==spec['expected_vector_jobs']
    if spec['parallel']:
        expected_fp=b''.join(struct.pack('<f',x if x>=0 else x*.25) for x in fp)
        assert data[0x31000:0x31000+len(expected_fp)]==expected_fp,'parallel FP32 mismatch'
        assert m['vector_busy_nvdla_request_cycles']>0,'no actual overlapping activity'
        assert m['both_request_cycles']>0,'no concurrent memory requests'
        (case/'fp32_output.bin').write_bytes(expected_fp)
    return {'status':'PASS','nvdla_crc32':crc,'byte_comparisons':'PASS','tail_guards':'PASS',**m}

def main():
    p=argparse.ArgumentParser();p.add_argument('--reuse',action='store_true');p.add_argument('--cases',nargs='+',default=['tiny_chain','conv_chain','pool_parallel']);a=p.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_hybrid_soc');out.mkdir(parents=True)
    print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'real RV32I CPU executes firmware; NVDLA and Vicuna RTL share SRAM; preloaded memory, UART idle',
            'nvdla_pin':'1a65f1f5b48268accaa47c95f95c2601918be095',
            'vicuna_tests_pin':'1574ca9c8bbebadb683a7142b5b5d3688bfff655',
            'known_limitations':['FP32 PReLU uses multiply-before-compare order; reverse order produced wrong results in integrated pinned core. Not full ISA compliance.'],
            'tests':[]}
    try:
        exe,seconds,hashes=build(out,a.reuse);result.update(compile_seconds=seconds,source_sha256=hashes,simulator_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
        (out/'result.json').write_text(json.dumps(result,indent=2))
        cases={'tiny_chain':('dc_1x1x8_1x1x8x1_int8_0',False),'conv_chain':('dc_6x8x192_3x3x192x32_int8_0',False),'pool_parallel':('pdp_8x8x64_2x2_int8',True)}
        for name in a.cases:
            case,spec,fp=prepare_case(out,name,*cases[name]);print('Simulating '+name,flush=True)
            secs=run([exe],case,case/'sim.log',180)
            entry={'name':name,'simulation_seconds':secs,**check(case,spec,fp)}
            result['tests'].append(entry);print(json.dumps(entry),flush=True)
            (out/'result.json').write_text(json.dumps(result,indent=2))
        result['status']='PASS'
    except BaseException as e:
        result.update(status='ERROR',error=str(e));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
