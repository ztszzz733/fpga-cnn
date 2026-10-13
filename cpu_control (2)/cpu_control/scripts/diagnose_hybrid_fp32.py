"""Preserve bounded software-only variants to isolate a FP32 instruction hazard."""
import datetime,json,struct
from run_hybrid_soc import ROOT,STAGE,prepare_case,VECTOR_PROGRAM,run
import run_hybrid_soc as test
out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_hybrid_fp32_diagnostic');out.mkdir(parents=True)
original=VECTOR_PROGRAM.replace('vfmul.vf v4,v1,ft1\n vmslt.vi v0,v1,0',
    'vmslt.vi v0,v1,0\n vfmul.vf v4,v1,ft1')
variants={
 'multiply_first':original.replace('vmslt.vi v0,v1,0\n vfmul.vf v4,v1,ft1','vfmul.vf v4,v1,ft1\n vmslt.vi v0,v1,0'),
 'extra_load':original.replace('float_loop:\n vsetvli t1,a3,e32,m1,ta,ma\n vle32.v v1,(a0)',
     'float_loop:\n vsetvli t1,a3,e32,m1,ta,ma\n vle32.v v1,(a0)\n vle32.v v2,(a0)'),
}
results=[]
for name,program in variants.items():
 test.VECTOR_PROGRAM=program
 case,spec,fp=prepare_case(out,name,'pdp_8x8x64_2x2_int8',True)
 try:
  seconds=run([STAGE/'obj/Vhybrid_soc_harness'],case,case/'sim.log',180)
 except Exception as error:
  result={'name':name,'status':'ERROR','error':str(error)}
  results.append(result);print(result,flush=True)
  (out/'result.json').write_text(json.dumps(results,indent=2))
  continue
 b=(case/'sram.bin').read_bytes();bad=[]
 for i,x in enumerate(fp):
  actual=b[0x31000+4*i:0x31004+4*i];expected=struct.pack('<f',x if x>=0 else x*.25)
  if actual!=expected:bad.append({'element':i,'actual':actual.hex(),'expected':expected.hex()})
 result={'name':name,'seconds':seconds,'mismatch_count':len(bad),'first_mismatches':bad[:8]}
 results.append(result);print(result,flush=True)
 (out/'result.json').write_text(json.dumps(results,indent=2))
(out/'result.json').write_text(json.dumps(results,indent=2));print(out,flush=True)
