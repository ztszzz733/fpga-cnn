"""One-image fixtures; bypass DW7 and its Post, retaining 7x7 spatial output.

The unchanged prefix oracle is copied from the independently generated five
image fixture, never from RTL outputs. The changed tail is recomputed here.
Execution memory contains only model data and poison, with input uploaded later.
"""
from pathlib import Path
import json,hashlib,struct,copy
SIM=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def words(p):return [int(v,16) for v in p.read_text().split()]
def save(p,a):p.write_text(''.join('%08x\n'%(v&0xffffffff) for v in a))
def generate(size):
 src=SIM/('build/fixtures/five_'+size);m=json.loads((src/'manifest.json').read_text())
 for name,digest in m['files_sha256'].items():assert sha((src/name).read_bytes())==digest,name
 tm=words(src/'template_commands.hex');meta=words(src/'template_meta.hex');im=words(src/'image_info.hex')
 oldmem=(src/'memory.bin').read_bytes();oldgold=(src/'expected.bin').read_bytes();oldimages=(src/'images.bin').read_bytes()
 bystep={j['local_step']:j for j in m['jobs'] if j['frame']==100}
 removed=[s for s,j in bystep.items() if j['opcode']==3]
 if size=='full':assert removed==[127];removed+=[128]
 keep=[s for s in range(m['template_steps']) if s not in removed];mapping={s:i for i,s in enumerate(keep)}
 alias={128:126} if removed else {}
 def mapped(s):return mapping[alias.get(s,s)]
 blobs={s:oldgold[j['expected_offset']:j['expected_offset']+j['bytes']] for s,j in bystep.items() if s in keep}
 if size=='full':
  x=blobs[126];assert len(x)==7*7*512
  row=tm[129*16:130*16];w=oldmem[row[2]:row[2]+512*128];assert len(w)==65536
  # Independent integer dot products, with no simulator-produced data.
  weights=[[v if v<128 else v-256 for v in w[o*512:(o+1)*512]] for o in range(128)]
  raw=[]
  for pixel in range(49):
   samples=x[pixel*512:(pixel+1)*512]
   raw.extend(sum(int(a)*b for a,b in zip(samples,weights[o])) for o in range(128))
  assert all(-(1<<31)<=v<(1<<31) for v in raw)
  blobs[129]=struct.pack('<'+'i'*len(raw),*raw)
  params=tm[130*16+4];q=[]
  for i,value in enumerate(raw):
   bias,ma,mb,cfg,clamp=struct.unpack_from('<iiiII',oldmem,params+(i%128)*20)
   product=(value+bias)*ma;shift=cfg&63
   rounded=(abs(product)+(0 if shift==0 else 1<<(shift-1)))>>shift
   if product<0:rounded=-rounded
   q.append(max(clamp&255,min((clamp>>8)&255,rounded+((cfg>>24)&255))))
  blobs[130]=bytes(q);assert len(blobs[130])==6272
 out=SIM/('build/fixtures/reduced_single_'+size)
 assert not out.exists(),'select a fresh fixture directory'
 out.mkdir(parents=True)
 steps=len(keep);rows=[];metas=[];consumers=[set() for _ in keep];uses=[]
 for old in keep:
  row=meta[old*18:(old+1)*18];u=[]
  for k in range(3):
   if row[13]>>k&1:
    owner=(row[15]>>(8*k))&255;owner=mapped(owner);slot=(row[14]>>(2*k))&3;u.append((slot,owner));consumers[owner].add(mapping[old])
  uses.append(u)
 init_bytes=m['workspace_bases'][0]+m['workspace_bytes'];memory=bytearray([0xa5])*init_bytes
 model_end=im[0];memory[:model_end]=oldmem[:model_end];workspace=m['workspace_bases'][0]
 payload=oldimages[im[2]:im[2]+im[1]];expected=bytearray();jobs=[];nodeinfo=[];commands=[]
 for new,old in enumerate(keep):
  original=bystep[old];r=meta[old*18:(old+1)*18];cmd=tm[old*16:(old+1)*16].copy();blob=blobs[old]
  if size=='full' and old in (129,130):cmd[7]=cmd[8]=7
  if size=='full' and old==130:cmd[5]=6272
  deps=sorted(set(([new-1] if new else [])+[owner for _,owner in uses[new]]));assert len(deps)<=2
  hold=(1<<new)|sum(1<<c for c in consumers[new]);final=new==steps-1
  ownerbits=sum(owner<<(8*k) for k,(_,owner) in enumerate(uses[new]))
  metas.extend([r[0],(1<<len(deps))-1,*(deps+[0,0])[:2],r[4],*[(hold>>(32*w))&0xffffffff for w in range(8)],r[13],r[14],ownerbits,int(final),len(blob) if final else 0])
  rows.extend(cmd);expanded=cmd.copy()
  for word,mode in ((1,r[0]&3),(2,(r[0]>>2)&3)):
   expanded[word]+=im[0] if mode==1 else workspace if mode==2 else 0
  expanded[3]+=workspace;expanded[13]=100;expanded[14]=0;commands.extend(expanded)
  job=copy.deepcopy(original);job.update(node=new,local_step=new,frame=100,address=expanded[3],bytes=len(blob),expected_offset=len(expected),dependencies=deps,slot=r[4],result=final)
  if size=='full' and old==129:job['macs']=49*512*128
  jobs.append(job);nodeinfo.extend([expanded[3],len(blob),len(expected),original['layer']]);expected.extend(blob)
 info=[1,steps,steps,16*1024*1024,init_bytes,len(expected),m['readonly_end'],len(payload)]
 for slot in m['slots']:info.extend([workspace+slot['offset'],slot['size']])
 for name,data in [('memory.bin',memory),('images.bin',payload),('expected.bin',expected)]: (out/name).write_bytes(data)
 for name,a in [('info.hex',info),('image_info.hex',[im[0],len(payload),0,workspace,100]),('template_commands.hex',rows),('template_meta.hex',metas),('commands.hex',commands),('node_info.hex',nodeinfo)]:save(out/name,a)
 result={'status':'GENERATED_NOT_RTL_PASS','frames':1,'template_steps':steps,'total_tasks':steps,'full_network':size=='full','network_variant':'DW7 and its associated Post bypassed; original tail weights/parameters retained, no substitute pooling','removed_original_steps':removed,'final_shape':[7,7,128] if size=='full' else None,'final_bytes':len(blobs[keep[-1]]),'final_sha256':sha(blobs[keep[-1]]),'expected_bytes':len(expected),'init_bytes':init_bytes,'jobs':jobs,'source_manifest_sha256':sha((src/'manifest.json').read_bytes()),'oracle':'Unchanged independently generated integer prefix; changed 7x7 tail recomputed with Python integer arithmetic; no RTL output used','accuracy_claim':False}
 result['files_sha256']={p.name:sha(p.read_bytes()) for p in out.iterdir() if p.is_file()};(out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
 print(size,steps,len(expected),result['final_bytes'],out)
for size in ('small','full'):generate(size)
