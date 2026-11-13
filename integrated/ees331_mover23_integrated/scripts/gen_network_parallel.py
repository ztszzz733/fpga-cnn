"""Relocate verified workloads into independent frame regions; never inject golden.

Small numeric test: two different face ROIs + separate pad/DW7 operator probes.
Full capacity plan: two copies of the same proven full-image workload, NOT run.
"""
import argparse,json,struct,hashlib,contextlib,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def rows(blob):return [list(v) for v in struct.iter_unpack('<16I',blob)]
def combine(sources,out):
 out.mkdir(parents=True,exist_ok=True);mem=bytearray();gold=bytearray();mutable=[];frames=[]
 for frame,(m,g,jobs,ranges) in enumerate(sources):
  base=len(mem);m=bytearray(m);g=bytearray(g);relocated=[]
  for old in jobs:
   j=old.copy();kind=j[0]
   if kind==0:
    for k in range(3):
     address=old[1]+k*4;v=struct.unpack_from('<I',m,address)[0]+base
     struct.pack_into('<I',m,address,v);struct.pack_into('<I',g,address,v)
    fields=[1]
   else:fields={1:[1,3,4],2:[1,2,3,4],3:[1,2,3],4:[1,3]}[kind]
   for k in fields:j[k]+=base
   if j[11]:j[10]+=base
   j[13]=frame;relocated.append(j)
  mem.extend(m);gold.extend(g);mutable.extend((a+base,n) for a,n in ranges);frames.append(relocated)
 jobs=[]
 for index in range(len(frames[0])):
  for frame in range(2):
   j=frames[frame][index];j[14]=(index-1)*2+frame if index else 0xffffffff;j[15]=0xffffffff;jobs.append(j)
 assert len(jobs)<=1024
 for name,data in [('memory.bin',mem),('golden.bin',gold),('jobs.bin',b''.join(struct.pack('<16I',*j) for j in jobs)),('mutable.bin',b''.join(struct.pack('<II',*r) for r in mutable))]:(out/name).write_bytes(data)
 (out/'workload.json').write_text(json.dumps(dict(commands=len(jobs),frames=2,memory_bytes=len(mem),frame_regions_independent=True,serialized_within_each_frame=True),indent=2))

def small_source(chain,dw,frame):
 m=bytearray((chain/'memory.bin').read_bytes());g=bytearray((chain/'golden.bin').read_bytes());jobs=[];ranges=[]
 words=[int(v,16) for v in (chain/'jobs.hex').read_text().split()]
 for i in range(0,len(words),10):
  a=words[i:i+10];j=[a[0],a[1] if a[0]==0 else a[2],a[3],a[4],a[5],a[6],a[7],0,0,0,a[8],a[9],i//10,frame,0,0];jobs.append(j)
  if a[9]:ranges.append((a[8],a[9]))
 # Independent real 7x7x512 feature probe, explicitly not fed by the ROI chain.
 base=len(m);dm=bytearray((dw/'memory.bin').read_bytes());dg=bytearray((dw/'golden.bin').read_bytes())
 v=[int(x,16) for x in (dw/'jobs.hex').read_text().split()][frame*9:frame*9+9]
 ia,wa,ra,da,pp,w,h,c,n=v
 m.extend(dm);g.extend(dg)
 jobs.extend([[3,ia+base,wa+base,ra+base,0,n,c,w,h,0,ra+base,n*4,10,frame,0,0],
              [1,ra+base,0,da+base,pp+base,n,c,0,0,0,da+base,n,11,frame,0,0]])
 ranges.extend([(ra+base,n*4),(da+base,n)])
 # A byte-path border probe with frame-distinct data, independent of convolution.
 src=len(m);x=bytes((i*17+frame*31)%256 for i in range(3*4*3));m.extend(x);g.extend(x)
 dst=len(m);zero=33+frame;pad=bytearray([zero]*(5*6*3))
 for y in range(3):pad[((y+1)*6+1)*3:((y+1)*6+5)*3]=x[y*12:(y+1)*12]
 m.extend(bytes([0xa5])*len(pad));g.extend(pad);ranges.append((dst,len(pad)))
 jobs.append([4,src,0,dst,0,0,3,4,3,zero,dst,len(pad),12,frame,0,0])
 while len(m)%64:m.append(0xa5);g.append(0xa5)
 return m,g,jobs,ranges

def main():
 p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 from gen_mobilefacenet_chain import generate
 scales=None;sources=[]
 for f in range(2):
  d=a.out/f'face{f}'
  with contextlib.redirect_stdout(io.StringIO()):r=generate(d,Path(f'D:/code/facemodel/person_{f+1}.jpg'),scales)
  if scales is None:scales=[v['output_scale'] for v in r['layers']]
  sources.append(small_source(d,ROOT/'build/dw7_cached_data/real512',f))
 combine(sources,a.out/'small')
 full=ROOT/'build/mobilefacenet_full_data'
 source=((full/'memory.bin').read_bytes(),(full/'golden.bin').read_bytes(),rows((full/'jobs.bin').read_bytes()),list(struct.iter_unpack('<II',(full/'mutable.bin').read_bytes())))
 combine([source,source],a.out/'full_plan')
 (a.out/'scope.json').write_text(json.dumps(dict(small='two different real face ROIs; independent real DW7 and pad probes',full_plan='746-command two-frame capacity plan, same source image copied twice; no full parallel numeric run',source_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [full/'jobs.bin',Path(__file__)]}),indent=2))
 print(a.out)
if __name__=='__main__':main()
