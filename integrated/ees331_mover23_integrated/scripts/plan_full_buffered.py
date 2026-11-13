"""Compile two full graphs into eight guarded slots; no RTL arithmetic claims.

Each frame is serial, frames may overlap. Lifetimes are derived from actual
operator read/write addresses, including all channel-group writers and Add inputs.
"""
import argparse,bisect,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
U32=0xffffffff
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source_plan(path):
 mem=(path/'memory.bin').read_bytes();gold=(path/'golden.bin').read_bytes()
 jobs=[list(x) for x in struct.iter_unpack('<16I',(path/'jobs.bin').read_bytes())]
 ranges=list(struct.iter_unpack('<II',(path/'mutable.bin').read_bytes()))
 assert ranges==sorted(ranges) and len(mem)==len(gold)
 starts=[a for a,n in ranges]
 def tensor(addr):
  i=bisect.bisect_right(starts,addr)-1
  return i if i>=0 and addr<ranges[i][0]+ranges[i][1] else None
 accesses=[];writers=[[] for _ in ranges];users=[set() for _ in ranges]
 for j,row in enumerate(jobs):
  kind=row[0]
  if kind==0:
   cfg=list(struct.unpack_from('<24I',mem,row[1]));ins=[cfg[1]];output=cfg[2]
  else:
   assert kind in (1,2,3,4);ins=[row[1]]+([row[2]] if kind==2 else []);output=row[3]
  dst=tensor(output);assert dst is not None
  writers[dst].append(j);users[dst].add(j)
  inputs=set()
  for a in ins:
   t=tensor(a)
   if t is not None:users[t].add(j);inputs.add(t)
  assert dst not in inputs,('in-place access unsupported',j)
  accesses.append((inputs,dst))
 tensors=[]
 for i,(a,n) in enumerate(ranges):
  assert writers[i],('unwritten tensor',a)
  tensors.append(dict(id=i,old_address=a,bytes=n,first=min(writers[i]),last=max(users[i]),writers=writers[i],users=sorted(users[i])))
 # No same-command input/output alias: reuse requires strict lifetime separation.
 slots=[dict(end=-1,bytes=0) for _ in range(4)]
 for t in sorted(tensors,key=lambda x:x['first']):
  choices=[i for i,s in enumerate(slots) if s['end']<t['first']]
  assert choices,('more than four live buffers',t)
  i=min(choices,key=lambda i:(max(slots[i]['bytes'],t['bytes'])-slots[i]['bytes'],-slots[i]['bytes']))
  t['slot']=i;slots[i]['end']=t['last'];slots[i]['bytes']=max(slots[i]['bytes'],t['bytes'])
 for a in tensors:
  for b in tensors:
   if a['id']<b['id'] and a['slot']==b['slot']:assert a['last']<b['first'] or b['last']<a['first']
 # Preserve only immutable spans. Drop every original intermediate payload;
 # retain source alignment guards and the old descriptor copy as read-only data.
 readonly=bytearray();spans=[];cursor=0
 for a,n in ranges+[(len(mem),0)]:
  assert a>=cursor
  while len(readonly)%64!=cursor%64:readonly.append(0xa5)
  if a>cursor:spans.append((cursor,a,len(readonly)));readonly.extend(mem[cursor:a])
  cursor=a+n
 return dict(path=path,mem=mem,gold=gold,jobs=jobs,ranges=ranges,tensors=tensors,accesses=accesses,slots=slots,readonly=readonly,spans=spans,tensor=tensor)

def compile_plan(paths,out,small=False):
 assert not out.exists() or not any(out.iterdir()),'preserve existing generated data'
 out.mkdir(parents=True,exist_ok=True)
 srcs=[source_plan(p) for p in paths];assert len(srcs)==2
 per_frame=len(srcs[0]['jobs']);total=per_frame*2
 assert per_frame==len(srcs[1]['jobs']) and 0<total<=1024
 if not small:assert per_frame==373
 reports=[json.loads((p/'workload.json').read_text()) for p in paths]
 assert reports[0]['image_sha256']!=reports[1]['image_sha256'],'two distinct images required'
 assert [l['scale'] for l in reports[0]['layers']]==[l['scale'] for l in reports[1]['layers']],'fixed quantization scales required'
 mem=bytearray();ro_bases=[]
 for s in srcs:
  while len(mem)%64:mem.append(0xa5)
  ro_bases.append(len(mem));mem.extend(s['readonly'])
 while len(mem)%4096:mem.append(0xa5)
 pool_start=len(mem);slot_bases=[];slot_sizes=[]
 for s in srcs:
  for slot in s['slots']:
   n=((slot['bytes']+63)//64)*64+64;slot_bases.append(len(mem));slot_sizes.append(n);mem.extend(bytes([0xa5])*n)
 alljobs=[None]*total;lease=[None]*total;result_meta=[None]*total;expected_parts=[None]*total
 tensors_report=[]
 for f,s in enumerate(srcs):
  def node(j):return j*2+f
  def relocate(addr):
   t=s['tensor'](addr)
   if t is not None:return slot_bases[f*4+s['tensors'][t]['slot']]+addr-s['ranges'][t][0]
   for lo,hi,base in s['spans']:
    if lo<=addr<hi:return ro_bases[f]+base+addr-lo
   raise AssertionError(('unmapped address',addr))
  for t in s['tensors']:
   tensors_report.append(t | dict(frame=f,slot=f*4+t['slot'],producer=node(t['first']),consumers=[node(j) for j in t['users']],address=relocate(t['old_address'])))
  for j,old in enumerate(s['jobs']):
   row=old.copy();kind=row[0];inputs,dst=s['accesses'][j];out_t=s['tensors'][dst]
   alloc=out_t['first']==j;uses=set(inputs)
   if not alloc:uses.add(dst)
   if kind==0:
    cfg=list(struct.unpack_from('<24I',s['mem'],row[1]));cfg[:3]=[relocate(a) for a in cfg[:3]]
    row[1]=relocate(row[1]);struct.pack_into('<24I',mem,row[1],*cfg)
   else:
    for k in {1:[1,3,4],2:[1,2,3,4],3:[1,2,3],4:[1,3]}[kind]:row[k]=relocate(row[k])
   if row[11]:row[10]=relocate(row[10])
   row[13]=f;row[14]=node(j-1) if j else U32;row[15]=U32
   alljobs[node(j)]=row
   used=sorted((f*4+s['tensors'][t]['slot'],node(s['tensors'][t]['first'])) for t in uses)
   assert len(used)<=3 and len(set(x[0] for x in used))==len(used)
   mask=sum(1<<node(k) for k in out_t['users']) if alloc else 1<<node(j)
   words=[f*4+out_t['slot'] if alloc else U32]+[x[0] for x in used]+[U32]*(3-len(used))+[x[1] for x in used]+[0]*(3-len(used))
   lease[node(j)]=struct.pack('<7I',*words)+mask.to_bytes(128,'little')
   final=j==len(s['jobs'])-1
   if final:assert alloc and old[11]>0 and out_t['last']==j
   if final and not small:assert old[11]==128
   result_meta[node(j)]=struct.pack('<4I',int(final),f,row[10] if final else 0,row[11] if final else 0)
   expected_parts[node(j)]=s['gold'][old[10]:old[10]+old[11]] if old[11] else b''
 offsets=[];expected=bytearray()
 for b in expected_parts:offsets.append(len(expected));expected.extend(b)
 for name,blob in [('memory.bin',mem),('jobs.bin',b''.join(struct.pack('<16I',*j) for j in alljobs)),('leases.bin',b''.join(lease)),('results.bin',b''.join(result_meta)),('expected.bin',expected),('expected_offsets.bin',struct.pack('<'+'I'*total,*offsets)),('mutable.bin',b''.join(struct.pack('<II',a,n) for a,n in zip(slot_bases,slot_sizes)))]:
  (out/name).write_bytes(blob)
 (out/'commands.hex').write_text('\n'.join(''.join(f'{w:08x}' for w in reversed(j)) for j in alljobs)+'\n')
 (out/'leases.hex').write_text('\n'.join(x[::-1].hex() for x in lease)+'\n')
 (out/'results.hex').write_text('\n'.join(x[::-1].hex() for x in result_meta)+'\n')
 report=dict(status='PLANNED_NOT_RTL_NUMERIC_PASS',frames=2,commands=total,full_image=not small,input_shape=None if small else [112,112,3],final_nodes=[total-2,total-1],final_bytes_per_frame=srcs[0]['jobs'][-1][11],
  source_paths=[str(p) for p in paths],image_hashes=[r['image_sha256'] for r in reports],fixed_scales=True,calibrated_accuracy=False,
  slot_bases=slot_bases,slot_sizes=slot_sizes,pool_bytes=sum(slot_sizes),readonly_bytes=pool_start,memory_bytes=len(mem),
  unreused_payload_bytes=sum(sum(n for a,n in s['ranges']) for s in srcs),peak_live_per_frame=[max(sum(t['first']<=j<=t['last'] for t in s['tensors']) for j in range(per_frame)) for s in srcs],
  allocations=len(tensors_report),tensors=tensors_report,source_hashes={str(p/n):sha(p/n) for p in paths for n in ['memory.bin','golden.bin','jobs.bin','mutable.bin','workload.json']})
 (out/'workload.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['tensors','source_hashes']},indent=2))
 return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source0',type=Path);p.add_argument('source1',type=Path);p.add_argument('out',type=Path);a=p.parse_args();compile_plan([a.source0,a.source1],a.out)
