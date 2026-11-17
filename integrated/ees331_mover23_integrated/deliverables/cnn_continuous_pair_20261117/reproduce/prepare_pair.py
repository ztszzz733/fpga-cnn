from pathlib import Path
import copy,hashlib,json,struct
R=Path(__file__).resolve().parent
S=Path('D:/code/FPGA1/integrated/ees331_mover23_integrated/simulation/build/fixtures')
sha=lambda b:hashlib.sha256(b).hexdigest()
def words(p):return [int(x,16) for x in p.read_text().split()]
def save(p,ws):p.write_text(''.join(f'{x&0xffffffff:08x}\n' for x in ws))
for size in ['small','full']:
 source=S/f'five_{size}';single=S/f'reduced_single_{size}'
 m=json.loads((source/'manifest.json').read_text());one=json.loads((single/'manifest.json').read_text())
 for src,manifest in [(source,m),(single,one)]:
  for n,h in manifest['files_sha256'].items():assert sha((src/n).read_bytes())==h
 oldgold=(source/'expected.bin').read_bytes();oldmem=(source/'memory.bin').read_bytes();imgs=(source/'images.bin').read_bytes()
 tm=words(single/'template_commands.hex');meta=words(single/'template_meta.hex');im=words(source/'image_info.hex')
 keep=[s for s in range(m['template_steps']) if s not in one['removed_original_steps']]
 steps=len(keep);assert steps==one['template_steps'];out=R/'fixtures'/f'pair_{size}';out.mkdir(parents=True)
 expected=bytearray();nodeinfo=[];expanded=[];jobs=[];blobs=[]
 for f in range(2):
  bystep={j['local_step']:j for j in m['jobs'] if j['frame']==100+f}
  b={s:oldgold[j['expected_offset']:j['expected_offset']+j['bytes']] for s,j in bystep.items() if s in keep}
  if size=='full':
   x=b[126];assert len(x)==7*7*512
   cmd=tm[127*16:128*16];wb=cmd[2];ww=oldmem[wb:wb+65536]
   weights=[[v if v<128 else v-256 for v in ww[o*512:(o+1)*512]] for o in range(128)]
   raw=[sum(int(a)*b for a,b in zip(x[p*512:(p+1)*512],weights[o])) for p in range(49) for o in range(128)]
   b[129]=struct.pack('<'+'i'*len(raw),*raw)
   params=tm[128*16+4];q=[]
   for i,v in enumerate(raw):
    bias,ma,mb,cfg,clamp=struct.unpack_from('<iiiII',oldmem,params+(i%128)*20)
    prod=(v+bias)*ma;shift=cfg&63;rounded=(abs(prod)+(0 if shift==0 else 1<<(shift-1)))>>shift
    if prod<0:rounded=-rounded
    q.append(max(clamp&255,min((clamp>>8)&255,rounded+((cfg>>24)&255))))
   b[130]=bytes(q)
  blobs.append(b)
 # Keep original model/input addresses and first two disjoint workspaces.
 workspace=m['workspace_bases'][:2];model_end=min(im[f*5] for f in range(2));init_bytes=workspace[-1]+m['workspace_bytes']
 memory=bytearray([0xa5])*init_bytes;memory[:model_end]=oldmem[:model_end]
 imageinfo=[];payload=bytearray()
 for f in range(2):
  imageinfo.extend([im[f*5],im[f*5+1],len(payload),workspace[f],100+f]);payload+=imgs[im[f*5+2]:im[f*5+2]+im[f*5+1]]
 for step,old in enumerate(keep):
  for f in range(2):
   cmd=tm[step*16:(step+1)*16].copy();r=meta[step*18:(step+1)*18];b=blobs[f][old]
   for word,mode in [(1,r[0]&3),(2,(r[0]>>2)&3)]:cmd[word]+=im[f*5] if mode==1 else workspace[f] if mode==2 else 0
   cmd[3]+=workspace[f];cmd[13]=100+f;cmd[14]=f;expanded.extend(cmd)
   nodeinfo.extend([cmd[3],len(b),len(expected),m['jobs'][old*5+f]['layer']])
   jobs.append({'node':step*2+f,'local_step':step,'original_step':old,'frame':100+f,'opcode':cmd[0],'address':cmd[3],'bytes':len(b),'expected_offset':len(expected)})
   expected+=b
 info=[2,steps,steps*2,16*1024*1024,init_bytes,len(expected),model_end,len(payload)]
 for f in range(2):
  for slot in m['slots']:info.extend([workspace[f]+slot['offset'],slot['size']])
 for name,data in [('memory.bin',memory),('images.bin',payload),('expected.bin',expected)]: (out/name).write_bytes(data)
 for name,ws in [('info.hex',info),('image_info.hex',imageinfo),('template_commands.hex',tm),('template_meta.hex',meta),('commands.hex',expanded),('node_info.hex',nodeinfo)]:save(out/name,ws)
 final=b''.join(blobs[f][keep[-1]] for f in range(2));assert final[:one['final_bytes']]==(single/'expected.bin').read_bytes()[-one['final_bytes']:]
 result={'status':'GENERATED_NOT_RTL_PASS','frames':2,'template_steps':steps,'total_tasks':steps*2,'expected_bytes':len(expected),'final_bytes':len(final),'final_sha256':sha(final),'input_shape':m['input_shape'],'network_variant':one['network_variant'],'source_manifests':{str(source):sha((source/'manifest.json').read_bytes()),str(single):sha((single/'manifest.json').read_bytes())},'jobs':jobs,'files_sha256':{p.name:sha(p.read_bytes()) for p in out.iterdir() if p.is_file()},'oracle':'Independent prior prefix golden plus independently recomputed 7x7 tail for both images, no RTL used','accuracy_claim':False}
 (out/'manifest.json').write_text(json.dumps(result,indent=2))
 print(size,len(jobs),len(expected),sha(final),flush=True)
