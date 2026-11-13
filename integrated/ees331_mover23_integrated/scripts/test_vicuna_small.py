"""Generate real RVV programs, execute the RTL model, check every output word.

Small finite values deliberately have exact FP16/FP32 results. These smoke
tests do NOT constitute exhaustive floating-point/ISA compliance coverage.
"""
from pathlib import Path
import argparse, hashlib, json, os, struct, subprocess, tarfile, time
from run_vicuna_small import ROOT, STAGE, run

ISA='rv32imf_zfh_zve32f_zvfh_zicsr'
LINK='''OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
 .vectors 0 : { *(.vectors) }
 .text 0x1000 : { *(.text*) }
 .data 0x2000 : { *(.data*) }
 .output 0x4000 : { *(.output) }
}
'''
START='''.option norvc
.option norelax
.section .vectors,"ax"
.org 0x70
 j fail
.org 0x74
 j done
.org 0x80
 j _start
.section .text
.global _start
_start:
 li sp, 0x3fff0
 li t0, 0x6600
 csrs mstatus, t0
 csrw fcsr, zero
 la a0, input_a
 la a1, input_b
 li a2, 0x4000
 li a3, 19
'''
END='''
 # The upstream wrapper ties fencei_flush_ack low, and this controller maps
 # FENCE to FENCE.I. Use the wrapper's scalar-read/vector-store interlock in
 # this uncached testbench; full SoC integration must implement flush ack.
 lw t0, -4(a2)
 li t0, 20
wait_drain:
 addi t0, t0, -1
 bnez t0, wait_drain
 sw zero, 0x400(zero)
 li t0, 0x74
 jr t0
fail:
 j fail
done:
 j done
'''

def blob(values,kind):
    return b''.join(struct.pack('<'+kind,v) for v in values)

def programs():
    ints=[(i-9)*4 for i in range(19)]
    other=[3-(i%7) for i in range(19)]
    floats=[(i-9)*0.5 for i in range(19)]
    fb=[(i%5-2)*0.25 for i in range(19)]
    for name,kind,op,expected in [
        ('int32_residual','i','vadd.vv v3, v1, v2',[a+b for a,b in zip(ints,other)]),
        ('int32_mul','i','vmul.vv v3, v1, v2',[a*b for a,b in zip(ints,other)]),
        ('int32_prelu','i','vmslt.vi v0, v1, 0\n vsra.vi v4, v1, 2\n vmerge.vvm v3, v1, v4, v0',[a if a>=0 else a//4 for a in ints]),
        ('fp32_add','f','vfadd.vv v3, v1, v2',[a+b for a,b in zip(floats,fb)]),
        ('fp32_mul','f','vfmul.vv v3, v1, v2',[a*b for a,b in zip(floats,fb)]),
        # For finite FP32 values the sign bit selects the negative branch.
        # This pinned decoder does not implement vmflt.vv; retain its failed
        # diagnostic run separately, rather than claim floating comparisons.
        ('fp32_prelu','f','vmslt.vi v0, v1, 0\n vfmul.vf v4, v1, ft1\n vmerge.vvm v3, v1, v4, v0',[a if a>=0 else a*0.25 for a in floats]),
        ('fp16_add','e','vfadd.vv v3, v1, v2',[a+b for a,b in zip(floats,fb)]),
        ('fp16_mul','e','vfmul.vv v3, v1, v2',[a*b for a,b in zip(floats,fb)]),
    ]:
        bits=16 if kind=='e' else 32
        a,b=(ints,other) if kind=='i' else (floats,fb)
        setup='li t0, 0x3e800000\n fmv.w.x ft1, t0\n' if name=='fp32_prelu' else ''
        body=f'''{setup}
loop:
 vsetvli t1, a3, e{bits}, m1, ta, ma
 vle{bits}.v v1, (a0)
 vle{bits}.v v2, (a1)
 {op}
 vse{bits}.v v3, (a2)
 slli t2, t1, {1 if bits==16 else 2}
 add a0, a0, t2
 add a1, a1, t2
 add a2, a2, t2
 sub a3, a3, t1
 bnez a3, loop
'''
        # a2 may be halfword-aligned at FP16 tail: force drain read aligned.
        end=END.replace('lw t0, -4(a2)','li t0, 0x4000\n lw t0, 0(t0)')
        data='\n.section .data\n.balign 16\ninput_a:\n.byte '+','.join(str(x) for x in blob(a,kind))
        data+='\n.balign 16\ninput_b:\n.byte '+','.join(str(x) for x in blob(b,kind))+'\n'
        yield name,START+body+end+data,blob(expected,kind),expected
    # Integer dot product uses vector multiplication and reduction across chunks.
    body='''li s0, 0
loop:
 vsetvli t1, a3, e32, m1, ta, ma
 vle32.v v1, (a0)
 vle32.v v2, (a1)
 vmul.vv v3, v1, v2
 vmv.s.x v4, zero
 vredsum.vs v5, v3, v4
 vmv.x.s t3, v5
 add s0, s0, t3
 slli t2, t1, 2
 add a0, a0, t2
 add a1, a1, t2
 sub a3, a3, t1
 bnez a3, loop
 sw s0, 0(a2)
 addi a2, a2, 4
'''
    data='\n.section .data\n.balign 16\ninput_a:\n.word '+','.join(map(str,ints))+'\n.balign 16\ninput_b:\n.word '+','.join(map(str,other))+'\n'
    exp=sum(a*b for a,b in zip(ints,other))
    yield 'int32_dot',START+body+END+data,blob([exp],'i'),[exp]

def compiler():
    archive=ROOT/'.tools/downloads/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz'
    checksum=Path(str(archive)+'.sha')
    if not checksum.exists():
        candidates=list(archive.parent.glob(archive.name+'.*'))
        checksum=next(p for p in candidates if 'sha' in p.suffix)
    expected=checksum.read_text().split()[0]
    dest=STAGE/'toolchain'
    gcc=dest/'xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc'
    ready=dest/'ready.sha256'
    # Reuse a completed, previously checksum-verified extraction. Avoid reading
    # the 413 MiB archive over the Windows/WSL file bridge on every test run.
    if gcc.exists() and ready.exists() and ready.read_text().strip()==expected:
        return gcc,expected
    actual=hashlib.sha256(archive.read_bytes()).hexdigest()
    assert actual==expected, 'toolchain checksum mismatch'
    if not ready.exists() or ready.read_text().strip()!=actual:
        dest.mkdir(exist_ok=True)
        # One forward pass: avoid scanning/decompressing the large archive twice.
        with tarfile.open(archive,mode='r:gz' if os.name=='nt' else 'r|gz') as tf:
            for m in tf:
                rel=Path(m.name).parts[1:]
                if not rel: continue
                if not (rel[0] in {'bin','libexec'} or rel[:2]==('riscv-none-elf','bin') or '.so' in m.name or Path(m.name).name=='specs'):
                    continue
                p=(dest/m.name).resolve()
                assert p.is_relative_to(dest.resolve()), m.name
                if m.issym() or m.islnk():
                    target=(p.parent/m.linkname).resolve() if m.issym() else (dest/m.linkname).resolve()
                    assert target.is_relative_to(dest.resolve()),m.linkname
                tf.extract(m,dest)
        assert gcc.exists()
        ready.write_text(actual+'\n')
    return gcc,actual

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run_dir');args=ap.parse_args()
    out=Path(args.run_dir); result=json.loads((out/'result.json').read_text())
    try:
        gcc,digest=compiler(); result['toolchain_sha256']=digest
        result['compiler_version']=subprocess.check_output([gcc,'--version'],text=True).splitlines()[0]
        exe=STAGE/'model/verilated_model'; assert exe.exists()
        result['simulator_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
        result['known_limitations']=[
            'Pinned wrapper ties fencei_flush_ack_i=0; tests use scalar-read/vector-store interlock instead of FENCE.',
            'Pinned vector decoder lacks vmflt.vv; FP32 PReLU uses integer sign mask plus FP multiplication for finite inputs.',
            'Initial diagnostic failures retained in build/runs/20261013_203617_vicuna_small.']
        result['tests']=[]
        for name,src,expected,values in programs():
            case=STAGE/'cases'/name;case.mkdir(parents=True,exist_ok=True)
            saved=out/name;saved.mkdir(exist_ok=True)
            (case/'test.S').write_text(src);(case/'link.ld').write_text(LINK)
            run([gcc,'-march='+ISA,'-mabi=ilp32f','-nostdlib','-nostartfiles','-Wl,--no-relax','-T',case/'link.ld',case/'test.S','-o',case/'test.elf'],saved/'compile.log',120)
            objcopy=gcc.parent/'riscv-none-elf-objcopy'
            run([objcopy,'-O','binary',case/'test.elf',case/'test.bin'],saved/'compile.log',30)
            binary=(case/'test.bin').read_bytes();binary+=b'\0'*((-len(binary))%4)
            (case/'program.hex').write_text(''.join(f'{v[0]:08x}\n' for v in struct.iter_unpack('<I',binary)))
            size=(len(expected)+3)//4*4
            (case/'programs.txt').write_text(f'{case}/program.hex /dev/null 0 0 {case}/output.hex 4000 {0x4000+size:x}\n')
            status={'name':name,'input_elements':19,'expected':values}
            try:
                # Never accept a prior run's SRAM dump as this run's output.
                (case/'output.hex').unlink(missing_ok=True)
                status['wall_seconds']=run([exe,case/'programs.txt','1','32','262144','1','0',name,'128','2','--trace',saved/'wave.vcd'],saved/'sim.log',60)
                words=[int(x,16) for x in (case/'output.hex').read_text().split()]
                actual=b''.join(struct.pack('<I',v) for v in words)[:len(expected)]
                (saved/'actual.bin').write_bytes(actual);(saved/'expected.bin').write_bytes(expected)
                status['actual_hex']=actual.hex();status['expected_hex']=expected.hex()
                assert actual==expected,'output bytes differ from independent Python reference'
                assert 'PROGRAM EXECUTION ENDED CORRECTLY' in (saved/'sim.log').read_text()
                status['status']='PASS'
            except Exception as e:
                status.update(status='FAIL',error=str(e))
            for file in ['test.S','test.elf','test.bin','program.hex','output.hex']:
                if (case/file).exists(): (saved/file).write_bytes((case/file).read_bytes())
            (saved/'result.json').write_text(json.dumps(status,indent=2))
            result['tests'].append(status)
            (out/'result.json').write_text(json.dumps(result,indent=2))
            print(name,status['status'],flush=True)
        result['status']='PASS' if all(t['status']=='PASS' for t in result['tests']) else 'PARTIAL_FAILURE'
    except Exception as e:
        result.update(status='ERROR',error=str(e));raise
    finally: (out/'result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':main()
