"""Six ROI frames, two reusable arenas, real convolutions + synthetic residual join.
Three learned layers are unchanged; the added residual is a lifetime stress graph,
not a claim about the original MobileFaceNet topology.
"""
import json,struct,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 from gen_mobilefacenet_chain import np,rounded
 # A 288-bit load may read a final aligned beat beyond the logical tensor.
 # Reserve a private 64-byte guard per slot; it is not another tensor's data.
 mem=bytearray();alljobs=[];meta=[];expect=bytearray();offsets=[];sizes=[10304,4160,4160,1088]*2
 bases=[];cursor=0x400000
 for n in sizes:bases.append(cursor);cursor+=n
 frames=[];logical_bytes=0
 for f in range(6):
  src=ROOT/f'build/network_parallel_data/face{f%2}';m=bytearray((src/'memory.bin').read_bytes());gold=(src/'golden.bin').read_bytes();base=len(mem)
  words=[int(v,16) for v in (src/'jobs.hex').read_text().split()];jobs=[]
  for i in range(0,90,10):
   v=words[i:i+10];jobs.append([v[0],v[1] if v[0]==0 else v[2],v[3],v[4],v[5],v[6],v[7],0,0,0,v[8],v[9],i//30,f,0,0])
  # raw0,q0,raw1,q1,raw2,q2; raw2 reuses raw0's slot.
  layout=[(1,0,0),(2,1,2),(4,2,3),(5,3,5),(7,0,6),(8,2,8)]
  ranges=[];leases=[]
  for last,slot,producer in layout:
   j=jobs[last];old,n=j[10],j[11];physical=bases[(f%2)*4+slot];assert n<=sizes[(f%2)*4+slot]
   ranges.append((old,n,physical,producer,(f%2)*4+slot));logical_bytes+=n
  def find(addr):return next((r for r in ranges if r[0]<=addr<r[0]+r[1]),None)
  def relocate(addr):
   r=find(addr);return r[2]+addr-r[0] if r else addr+base
  for i,j in enumerate(jobs):
   old=j.copy();uses=set();allocation=None
   if j[0]==0:
    cfg=list(struct.unpack_from('<24I',m,j[1]));input_r=find(cfg[1]);output_r=find(cfg[2])
    if input_r:uses.add((input_r[4],input_r[3]))
    if output_r[3]==i:allocation=output_r[4]
    else:uses.add((output_r[4],output_r[3]))
    cfg[0]+=base;cfg[1]=relocate(cfg[1]);cfg[2]=relocate(cfg[2]);struct.pack_into('<24I',m,j[1],*cfg);j[1]+=base
   else:
    rr=find(j[1]);uses.add((rr[4],rr[3]));out=find(j[3]);allocation=out[4]
    j[1]=relocate(j[1]);j[3]=relocate(j[3]);j[4]+=base
   if j[11]:j[10]=relocate(j[10])
   leases.append(dict(slot=allocation,uses=sorted(uses)))
   offsets.append(len(expect));expect.extend(gold[old[10]:old[10]+old[11]])
  # Residual q1 + q2, with a controlled half-scale add. q1 must survive its
  # convolution consumers AND this later Add, even while q2 is produced.
  n=jobs[8][11];assert jobs[5][11]==n
  x=np.frombuffer(gold[words[5*10+8]:words[5*10+8]+n],np.uint8).astype(np.int64)
  y=np.frombuffer(gold[words[8*10+8]:words[8*10+8]+n],np.uint8).astype(np.int64)
  q=np.clip(rounded(x+y,1),0,255).astype(np.uint8).tobytes()
  while len(m)%64:m.append(0xa5)
  params=len(m)+base;m.extend(b''.join(struct.pack('<5I',0,1,1,1,255<<8) for _ in range(64)))
  jobs.append([2,jobs[5][3],jobs[8][3],bases[(f%2)*4],params,n,64,0,0,0,bases[(f%2)*4],n,3,f,0,0]);logical_bytes+=n
  leases.append(dict(slot=(f%2)*4,uses=[((f%2)*4+3,5),((f%2)*4+2,8)]));offsets.append(len(expect));expect.extend(q)
  while len(m)%64:m.append(0xa5)
  mem.extend(m);frames.append((jobs,leases))
 # Frame-major topological numbering. Two arenas admit two frames concurrently;
 # the next occupant waits for the prior frame's final Add to avoid deadlock.
 for f,(jobs,leases) in enumerate(frames):
  for i,(j,l) in enumerate(zip(jobs,leases)):
   idx=f*10+i;j[14]=idx-1 if i else ((f-2)*10+9 if f>=2 else 0xffffffff);j[15]=f*10+5 if i==9 else 0xffffffff
   uses=[(s,f*10+owner) for s,owner in l['uses']];mask=1<<idx
   if l['slot'] is not None:
    for k,consumer in enumerate(leases):
     if (l['slot'],i) in consumer['uses']:mask|=1<<(f*10+k)
   packed=[l['slot'] if l['slot'] is not None else 0xffffffff]+[s for s,o in uses]+[0xffffffff]*(3-len(uses))+[o for s,o in uses]+[0]*(3-len(uses))
   meta.append(struct.pack('<7I',*packed)+mask.to_bytes(128,'little'));alljobs.append(j)
 assert len(mem)<bases[0];mem.extend(bytes([0xa5])*(cursor-len(mem)))
 (a.out/'memory.bin').write_bytes(mem);(a.out/'golden.bin').write_bytes(mem)
 (a.out/'jobs.bin').write_bytes(b''.join(struct.pack('<16I',*j) for j in alljobs));(a.out/'leases.bin').write_bytes(b''.join(meta))
 (a.out/'expected.bin').write_bytes(expect);(a.out/'expected_offsets.bin').write_bytes(struct.pack('<'+'I'*len(offsets),*offsets))
 (a.out/'mutable.bin').write_bytes(b''.join(struct.pack('<II',b,n) for b,n in zip(bases,sizes)))
 (a.out/'workload.json').write_text(json.dumps(dict(frames=6,distinct_images=2,commands=len(alljobs),buffer_bases=bases,buffer_sizes=sizes,
  intermediate_pool_bytes=sum(sizes),unreused_intermediate_bytes=logical_bytes,final_nodes=[f*10+9 for f in range(6)],
  full_network=False,residual='synthetic q1+q2 stress join after three learned layers',readonly_static_bytes=bases[0],admission='two frames, next same arena waits final Add'),indent=2))
 from validate_buffer_plan import validate
 (a.out/'plan_validation.json').write_text(json.dumps(validate(a.out),indent=2))
 print(a.out)
if __name__=='__main__':main()
