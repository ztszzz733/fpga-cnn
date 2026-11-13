"""Build pinned upstream nv_small RTL and run bounded, small adapter tests in WSL.

Run using Linux Python. No Java/UVM/C-model build: checked-in register RTL is
preprocessed with upstream vcp/eperl, using the upstream nv_small defines.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, time
from nvdla_cfgrom_header import generate as generate_cfgrom_header

ROOT = Path(__file__).resolve().parents[1]
PIN = '1a65f1f5b48268accaa47c95f95c2601918be095'
# This host may discard Linux /tmp between invocations. Keep the cache on D:.
STAGE = ROOT.parents[1]/'.nvdla_build/nv_small'

def run(cmd, cwd, log, timeout=600, env=None):
    start = time.monotonic()
    with open(log, 'a') as f:
        f.write('\n' + repr([str(x) for x in cmd]) + '\n'); f.flush()
        p = subprocess.run([str(x) for x in cmd], cwd=cwd, stdout=f,
                           stderr=subprocess.STDOUT, timeout=timeout, env=env)
    if p.returncode:
        raise RuntimeError(f'command exited {p.returncode}; see {log}')
    return time.monotonic() - start

def prepare(out):
    src = ROOT/'third_party/nvdla'
    actual = subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()
    if actual != PIN: raise RuntimeError(f'upstream pin mismatch: {actual}')
    dest = STAGE/'hw'
    if not (dest/'generation.ok').exists():
        shutil.copytree(src,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','outdir'))
        for p in dest.rglob('*'):
            if p.is_file() and p.suffix not in ('.jar','.pdf','.png','.jpg','.gz'):
                b=p.read_bytes()
                if b'\x00' not in b: p.write_bytes(b.replace(b'\r\n',b'\n'))
        for p in (dest/'tools/bin').iterdir():
            if p.is_file(): p.chmod(0o755)
        (dest/'tree.make').write_text('PROJECTS := nv_small\nCPP := /usr/bin/cpp\nPERL := /usr/bin/perl\nPYTHON := /usr/bin/python3\nUSE_DESIGNWARE := 0\n')
        run(['make','-C','spec/defs'],dest,out/'generate.log')
        generate_cfgrom_header(dest)
        # The upstream file list uses checked-in register RTL, not generated UVM.
        dirs = ['vmod/include','vmod/vlibs','vmod/rams/model','vmod/rams/synth','vmod/fifos']
        dirs += [str(p.relative_to(dest)) for p in sorted((dest/'vmod/nvdla').iterdir()) if (p/'Makefile').exists()]
        for directory in dirs:
            run(['make','-j','2','-C',directory],dest,out/'generate.log')
        (dest/'generation.ok').write_text(PIN)
    # vcp upstream does not propagate a failing C preprocessor exit code.
    rom=dest/'outdir/nv_small/vmod/nvdla/cfgrom/NV_NVDLA_CFGROM_rom.v'
    header=dest/'outdir/nv_small/spec/manual/NVDLA_CFGROM.vh'
    previous=header.read_text() if header.exists() else ''
    generate_cfgrom_header(dest)
    if previous!=header.read_text() or not rom.exists() or 'module NV_NVDLA_CFGROM_rom' not in rom.read_text():
        run(['make','-B','-C','vmod/nvdla/cfgrom'],dest,out/'generate.log')
    if (out/'generate.log').exists() and 'fatal error:' in (out/'generate.log').read_text():
        raise RuntimeError('upstream preprocessor error; see generate.log')
    return dest

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--prepare-only',action='store_true'); ap.add_argument('--reuse',action='store_true')
    ap.add_argument('--cases',nargs='+',default=['dc_1x1x8_1x1x8x1_int8_0','dc_6x8x192_3x3x192x32_int8_0','pdp_8x8x64_2x2_int8'])
    ap.add_argument('--timed-ram',action=argparse.BooleanOptionalAction,default=True,
                    help='retain upstream RAM delays; disabling is diagnostic only and fails multi-channel golden checks')
    args=ap.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_nvdla_small')
    out.mkdir(parents=True); STAGE.mkdir(parents=True,exist_ok=True)
    print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','upstream_commit':PIN,'configuration':'nv_small','scope':'small RTL adapter tests, no UART, no CPU instruction execution'}
    (out/'result.json').write_text(json.dumps(result,indent=2))
    try:
        t=time.monotonic(); hw=prepare(out); result['generation_seconds']=time.monotonic()-t
        if args.prepare_only:
            result['status']='GENERATED'
        else:
            execute_tests(hw,out,args.reuse,result,args.cases,args.timed_ram)
    except Exception as e:
        result.update(status='ERROR',error=str(e)); raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2))

def execute_tests(hw,out,reuse,result,cases,timed_ram=True):
    local=STAGE/'adapter';local.mkdir(exist_ok=True)
    sources=['rtl/nvdla/nvdla_csb_adapter.sv','rtl/nvdla/nvdla_sram_bridge.sv',
             'rtl/nvdla/nvdla_cnn_top.sv','rtl/overlap/datasram_banked.sv',
             'tb/integration/nvdla_small_harness.sv','tb/integration/nvdla_small_driver.cpp']
    hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in sources}
    for f in sources: shutil.copyfile(ROOT/f,local/Path(f).name)
    result['source_sha256']=hashes
    vr=STAGE/'verilator'
    if not vr.exists(): shutil.copytree(ROOT/'.tools/verilator-linux/verilator',vr)
    for f in (vr/'bin').iterdir(): f.chmod(0o755)
    env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
    fl=(hw/'verif/verilator/verilator_nv_small.f').read_text()
    fl=fl.replace('--top-module NV_nvdla','').replace('../../outdir',str(hw/'outdir'))
    # Upstream's checked-in Verilator list omits these generated library dirs.
    fl+='\n-I'+str(hw/'outdir/nv_small/vmod/fifos')+'\n-I'+str(hw/'outdir/nv_small/vmod/rams/model')+'\n'
    # Generated FIFO module names include width/depth suffixes absent in filenames.
    fl+=''.join('-v '+str(p)+'\n' for p in sorted((hw/'outdir/nv_small/vmod/fifos').glob('*.v')))
    (local/'upstream.f').write_text(fl)
    obj=STAGE/'obj';exe=obj/'Vnvdla_small_harness'
    manifest=STAGE/'build_inputs.json'
    key={'hashes':hashes,'pin':PIN,'flags_version':2,'timed_ram':timed_ram}
    result['timed_ram']=timed_ram
    if reuse:
        if not exe.exists() or not manifest.exists() or json.loads(manifest.read_text())!=key:
            raise RuntimeError('--reuse requires matching source hashes and existing executable')
        result['compile_seconds']=0
    else:
        cmd=[vr/'bin/verilator','--cc','--exe','--build',*(['--timing','--timescale-override','1ns/1ps'] if timed_ram else ['--no-timing']),'-j','2','-O1','--output-split','5000',
             '--output-split-cfuncs','100','-Wno-fatal','--top-module','nvdla_small_harness',
             '--Mdir',obj,'-f',local/'upstream.f','-CFLAGS','-std=c++20'+(' -DTIMED_RAM' if timed_ram else ''),
             '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1',
             *[local/Path(f).name for f in sources]]
        result['compile_seconds']=run(cmd,local,out/'compile.log',timeout=900,env=env)
        manifest.write_text(json.dumps(key,indent=2))
    shutil.copyfile(exe,out/'simulator');(out/'simulator').chmod(0o755)
    result['simulator_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
    result['tests']=[]
    for name in cases:
        case=STAGE/'tests'/out.name/name;case.mkdir(parents=True)
        prepare_trace(hw,name,case)
        target=out/name;target.mkdir()
        try:
            seconds=run([exe,'commands.txt'],case,target/'sim.log',timeout=120,env=env)
        finally:
            for file in case.iterdir():
                if file.is_file(): shutil.copyfile(file,target/file.name)
        if 'PASS cycles=' not in (target/'sim.log').read_text(): raise RuntimeError('missing PASS marker')
        metrics=json.loads((target/'metrics.json').read_text())
        result['tests'].append({'name':name,'status':'PASS','simulation_seconds':seconds,**metrics})
        print(name+' PASS '+str(round(seconds,3))+' seconds',flush=True)
    result['status']='PASS'

def prepare_trace(hw,name,case):
    registers={}
    for p in (hw/'spec/manual').glob('NVDLA_*.rdl'):
        text=p.read_text();base=re.search(r'regs_(\w+)\s+\w+\s+@\s*(0x[0-9a-fA-F]+)',text)
        if base:
            for reg,offset in re.findall(r'}\s*([SD]_\w+)\s*@\s*(0x[0-9a-fA-F]+)',text):
                registers[base[1]+'.'+reg+'_0']=int(base[2],16)+int(offset,16)
    folder=hw/'verif/tests/trace_tests/nv_small'/name
    cfg=(folder/(name+'.cfg')).read_text()
    regions=[];cursor=0x1000
    for base,size in re.findall(r'mem_init\(pri_mem,\s*(0x\w+),\s*(0x\w+),\s*ALL_ZERO\)',cfg):
        size=int(size,16);regions.append((int(base,16),size,cursor));cursor=(cursor+size+4095)&~4095
    if cursor>0x40000: raise RuntimeError('small test exceeds SRAM capacity')
    def relocate(address):
        for old,size,new in regions:
            if old<=address<old+size:return new+address-old
        raise RuntimeError(f'unmapped memory address {address:x}')
    commands=[];payload_count=0
    for line in cfg.splitlines():
        line=line.split('//')[0].strip()
        if not line:continue
        m=re.fullmatch(r'(\w+)\((.*?)\);',line)
        if not m:raise RuntimeError('unparsed trace: '+line)
        op=m[1];a=[v.strip().strip('"') for v in m[2].split(',')]
        if op=='mem_init':commands.append(f'Z {relocate(int(a[1],0)):x} {int(a[2],0):x}')
        elif op=='mem_load':
            entries=re.findall(r'offset:(0x\w+),\s*size:(\d+),\s*payload:([^}]+)',(folder/a[2]).read_text())
            payload=bytearray(max(int(offset,0)+int(size) for offset,size,data in entries))
            for offset,size,data in entries:
                b=bytes(int(x,16) for x in data.split());assert len(b)==int(size)
                payload[int(offset,0):int(offset,0)+len(b)]=b
            file=f'payload_{payload_count}.bin';payload_count+=1;(case/file).write_bytes(payload)
            commands.append(f'L {relocate(int(a[1],0)):x} {file}')
        elif op=='reg_write':
            v=int(a[1],0)
            # Relocate only memory pointer registers; preserve all arithmetic config.
            if any(word in a[0] for word in ('ADDR_LOW','ADDR_0_LOW','D_DAIN_ADDR_LOW','D_WEIGHT_ADDR_LOW')):
                try:v=relocate(v)
                except RuntimeError:pass # unused disabled plane pointers may be randomized
            commands.append(f'W {registers[a[0]]:x} {v:x}')
        elif op=='poll_reg_equal':commands.append(f'P {registers[a[0]]:x} {int(a[1],0):x} ffffffff')
        elif op=='intr_notify':commands.append('I '+{'SDP_0':'1','PDP_0':'10'}[a[0]])
        elif op=='check_crc':commands.append(f'C {relocate(int(a[2],0)):x} {int(a[3],0):x} {int(a[4],0):x}')
        else:raise RuntimeError('unsupported official trace command '+op)
    (case/'commands.txt').write_text('\n'.join(commands)+'\n')
    (case/'memory_map.json').write_text(json.dumps([{'upstream_base':hex(a),'size':s,'sram_base':hex(n)} for a,s,n in regions],indent=2))

if __name__=='__main__': main()
