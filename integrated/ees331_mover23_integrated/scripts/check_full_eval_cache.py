"""Compare cached and original generated adapters on existing real 3-layer RTL data."""
import hashlib,json,os,shutil,struct,time
from pathlib import Path
from run_tests import ROOT,execute
from cache_neureka_eval import STAGE

def main():
 out=ROOT/'build/eval_cache_validation';out.mkdir(parents=True,exist_ok=True)
 src=ROOT/'build/mobilefacenet_chain_data_v2';mem=bytearray((src/'memory.bin').read_bytes());gold=bytearray((src/'golden.bin').read_bytes())
 words=[int(s,16) for s in (src/'jobs.hex').read_text().split()];jobs=[];mutable=[]
 for i in range(0,len(words),10):
  a=words[i:i+10];row=[a[0],a[1] if a[0]==0 else a[2],a[3],a[4],a[5],a[6],a[7],0,0,0,a[8],a[9],i//10,0,0,0];jobs.append(row)
  if a[9]:mutable.append((a[8],a[9]))
 table=len(mem);blob=b''.join(struct.pack('<16I',*j) for j in jobs);mem.extend(blob);gold.extend(blob)
 mem.extend(bytes([0xa5])*64);gold.extend(bytes([0xa5])*64)
 result={'status':'RUNNING','purpose':'same RTL, original vs unchanged-input evaluation cache','cases':{}};stamp=time.perf_counter()
 try:
  for name,exe in [('original',STAGE/'obj/Vquant_network_sequential.uncached'),('cached',STAGE/'obj/Vquant_network_sequential')]:
   case=out/name;case.mkdir(exist_ok=True);(case/'memory.bin').write_bytes(mem);(case/'golden.bin').write_bytes(gold);(case/'jobs.bin').write_bytes(blob)
   (case/'mutable.bin').write_bytes(b''.join(struct.pack('<II',*r) for r in mutable))
   start=time.perf_counter();execute([exe,str(table),str(len(jobs)),str(jobs[-1][10]),str(jobs[-1][11]),'1'],case,os.environ.copy(),case/'sim.log',timeout=180)
   m=json.loads((case/'metrics.json').read_text());m['wall_seconds']=time.perf_counter()-start;m['output_sha256']=hashlib.sha256((case/'embedding.bin').read_bytes()).hexdigest();result['cases'][name]=m
   print(name+': '+json.dumps(m),flush=True)
  a,b=result['cases'].values()
  for k in ['cycles','commands','checked_bytes','reads','writes','output_sha256']:assert a[k]==b[k],k
  # Exact control-event identity also proves that host optimization did not
  # silently change command order or insert/remove clock cycles.
  assert (out/'original/control.vcd').read_bytes()==(out/'cached/control.vcd').read_bytes()
  result['status']='PASS'
 except Exception as e:result['status']='FAIL';result['error']=str(e)
 result['total_seconds']=time.perf_counter()-stamp;(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
