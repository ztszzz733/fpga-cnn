"""Validate the current fixed-slot compiler contract before programming hardware."""
import argparse,json,struct,hashlib
from pathlib import Path
def validate(path):
 jobs=list(struct.iter_unpack('<16I',(path/'jobs.bin').read_bytes()));blob=(path/'leases.bin').read_bytes()
 mem=(path/'memory.bin').read_bytes();slots=list(struct.iter_unpack('<II',(path/'mutable.bin').read_bytes()))
 assert 0<len(jobs)<=1024 and len(blob)==156*len(jobs) and len(slots)==8
 meta=[(struct.unpack_from('<7I',blob,i*156),int.from_bytes(blob[i*156+28:(i+1)*156],'little')) for i in range(len(jobs))]
 def slot_at(addr):return next((s for s,(a,n) in enumerate(slots) if a<=addr<a+n),None)
 for i,(j,(w,mask)) in enumerate(zip(jobs,meta)):
  uses={w[1+k]:w[4+k] for k in range(3) if w[1+k]!=0xffffffff};allocation=w[0]
  assert len(uses)==sum(w[1+k]!=0xffffffff for k in range(3)),('duplicate input slot',i)
  assert all(dep==0xffffffff or dep<i for dep in j[14:16]),('dependency order',i)
  assert mask>>len(jobs)==0,('hold outside batch',i)
  for s,owner in uses.items():
   assert s<8 and owner<i and meta[owner][0][0]==s,('owner mismatch',i,s)
   assert (meta[owner][1]>>i)&1,('missing consumer',owner,i)
  if allocation!=0xffffffff:
   assert allocation<8 and allocation not in uses and (mask>>i)&1,('allocation',i)
  if j[0]==0:
   assert j[1]+96<=len(mem)
   cfg=struct.unpack_from('<24I',mem,j[1]);addresses=[cfg[1],cfg[2]];output=cfg[2]
  elif j[0] in (1,2,3,4):addresses=[j[1],j[3]]+([j[2]] if j[0]==2 else []);output=j[3]
  else:raise AssertionError('unsupported operator kind')
  for addr in addresses:
   s=slot_at(addr)
   if s is not None:assert s in uses or s==allocation,('undeclared access',i,addr)
  assert slot_at(output) is not None and (allocation==slot_at(output) or slot_at(output) in uses),('unowned output',i)
  if j[11]:
   s=slot_at(j[10]);assert s is not None and j[10]+j[11]<=slots[s][0]+slots[s][1]-64,('payload exceeds guarded slot',i)
 return {'status':'PASS','commands':len(jobs),'slots':len(slots),'pool_bytes':sum(n for a,n in slots),'hashes':{n:hashlib.sha256((path/n).read_bytes()).hexdigest() for n in ['jobs.bin','leases.bin','mutable.bin','memory.bin']}}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('data',type=Path);a=p.parse_args();print(json.dumps(validate(a.data),indent=2))
