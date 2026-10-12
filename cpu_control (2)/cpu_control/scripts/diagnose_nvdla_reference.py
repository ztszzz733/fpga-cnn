"""Bounded upstream-only comparison to isolate an adapter vs upstream mismatch."""
from pathlib import Path
import datetime,json,os,re,shutil,struct
from run_nvdla_small import ROOT,STAGE,prepare_trace,run

hw=STAGE/'hw';name='dc_6x8x192_3x3x192x32_int8_0'
out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_nvdla_reference')
out.mkdir(parents=True);local=STAGE/'reference';local.mkdir(exist_ok=True)
obj=local/'verilator';obj.mkdir(exist_ok=True)
(local/'spec/defs').mkdir(parents=True,exist_ok=True)
shutil.copyfile(hw/'outdir/nv_small/spec/defs/project.h',local/'spec/defs/project.h')
shutil.copyfile(hw/'verif/verilator/nvdla.cpp',obj/'nvdla.cpp')
vr=STAGE/'verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
record={'status':'RUNNING','purpose':'upstream AXIResponder without project adapters or banked SRAM'}
try:
    record['compile_seconds']=run([vr/'bin/verilator','--cc','--exe','--build','--no-timing','-j','2','-O1',
        '--output-split','5000','--output-split-cfuncs','100','-Wno-fatal','--top-module','NV_nvdla',
        '--Mdir',obj,'-f',STAGE/'adapter/upstream.f','-CFLAGS','-std=c++20',
        '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1',obj/'nvdla.cpp'],
        local,out/'compile.log',timeout=900,env=env)
    case=local/'case';case.mkdir(exist_ok=True);prepare_trace(hw,name,case)
    regions=json.loads((case/'memory_map.json').read_text())
    def orig(addr):
        for r in regions:
            base=int(r['sram_base'],0)
            if base<=addr<base+r['size']:return int(r['upstream_base'],0)+addr-base
        raise ValueError(addr)
    cfg=(hw/'verif/tests/trace_tests/nv_small'/name/(name+'.cfg')).read_text()
    values=iter(int(v,0) for v in re.findall(r'reg_write\([^,]+,\s*(0x\w+)\)',cfg))
    b=bytearray()
    for line in (case/'commands.txt').read_text().splitlines():
        a=line.split();op=a[0]
        if op in ('Z','L'):
            payload=bytes(int(a[2],16)) if op=='Z' else (case/a[2]).read_bytes()
            b+=struct.pack('<BII',5,orig(int(a[1],16)),len(payload))+payload
        elif op=='W':b+=struct.pack('<BII',2,int(a[1],16)//4,next(values))
        elif op=='P':b+=struct.pack('<BIII',3,int(a[1],16)//4,int(a[3],16),int(a[2],16))
        elif op=='I':
            b+=struct.pack('<BII',7,0x100c//4,0x1004//4)
            b+=struct.pack('<BII',6,0,int(a[1],16))
        elif op=='C':b+=struct.pack('<BIIII',8,0,orig(int(a[1],16)),int(a[2],16),int(a[3],16))
    b+=b'\xff';(case/'trace.bin').write_bytes(b);shutil.copyfile(case/'trace.bin',out/'trace.bin')
    record['simulation_seconds']=run([obj/'VNV_nvdla','trace.bin'],case,out/'sim.log',timeout=120,env=env)
    record['status']='PASS'
except Exception as e:record.update(status='ERROR',error=str(e));raise
finally:
    (out/'result.json').write_text(json.dumps(record,indent=2));print(out,flush=True)
