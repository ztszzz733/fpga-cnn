"""Independent small two-image fixture for the NEureka-free CNN entry.

Only immutable images/weights/parameters populate memory.hex. Expected intermediate
values go to a separate checker file and are NEVER copied into execution memory.
"""
from pathlib import Path
import argparse, hashlib, json, random, struct

ROOT = Path(__file__).resolve().parents[1]
MEM_BYTES = 65536
SLOT_BASE, SLOT_PITCH, SLOT_BYTES = 32768, 2112, 2048

def round_away(x, shift):
    return x if shift == 0 else (1 if x >= 0 else -1) * ((abs(x) + (1 << (shift-1))) >> shift)

def conv(x, h, w, ci, weights, co, k, stride=1, dw=False):
    oh, ow = (h-k)//stride+1, (w-k)//stride+1
    out = []
    for y in range(oh):
        for xx in range(ow):
            for o in range(co):
                value = 0
                for ky in range(k):
                    for kx in range(k):
                        for c in ([o] if dw else range(ci)):
                            wi = (o*k+ky)*k+kx if dw else ((o*k+ky)*k+kx)*ci+c
                            value += x[((y*stride+ky)*w+xx*stride+kx)*ci+c]*weights[wi]
                assert -(1<<31) <= value < (1<<31)
                out.append(value)
    return out, oh, ow

def generate(out, images=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    mem = bytearray([0xA5])*MEM_BYTES
    cursor = 1024
    immutable = []
    def alloc(data, name):
        nonlocal cursor
        a = (cursor+63)&~63
        assert a+len(data)+64 < SLOT_BASE
        mem[a:a+len(data)] = data
        cursor = a+len(data)+64
        immutable.append(dict(name=name, address=a, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        return a
    rng = random.Random(733)
    layers = {}
    for name, ci, co, k, dw, shift in [('conv3',3,8,3,False,5), ('dw3',8,8,3,True,3), ('conv1',8,8,1,False,3), ('dw7',8,8,7,True,5)]:
        weights = [rng.randint(-3,3) for _ in range(co*k*k*(1 if dw else ci))]
        # Existing DW7 uses [ky,kx,c]; new K1/K3 uses OHWI or [c,ky,kx].
        packed = [weights[c*49+t] for t in range(49) for c in range(co)] if k==7 else weights
        wa = alloc(bytes(v&255 for v in packed), name+'_weights')
        size = k*k*(1 if dw else ci)
        bias = [-128*sum(weights[o*size:(o+1)*size]) for o in range(co)]
        # Conv3 uses ReLU at output zero=128. DW3 exercises a bounded
        # activation (128..192; a ReLU6 encoding when output scale=6/64).
        lo,hi = (128,255) if name=='conv3' else ((128,192) if name=='dw3' else (0,255))
        pp = alloc(b''.join(struct.pack('<5I', b&0xffffffff,1,0,shift|(128<<24),lo|(hi<<8)) for b in bias), name+'_parameters')
        layers[name] = (weights, wa, bias, pp, shift,lo,hi)
    addp = alloc(b''.join(struct.pack('<5I',0,3,2,2|(128<<8)|(128<<16)|(128<<24),255<<8) for _ in range(8)), 'add_parameters')
    frames = []
    for f in range(2):
        if images:
            from PIL import Image
            im = Image.open(images[f]).convert('RGB').resize((7,7), Image.Resampling.BOX)
            x = list(im.tobytes())
            source = str(Path(images[f]).resolve())
        else:
            x = [((31*y+17*xx+43*c+f*79) ^ (f*(y+1)*(xx+3)*7))&255 for y in range(7) for xx in range(7) for c in range(3)]
            source = 'deterministic synthetic RGB test image; not a face recognition fixture'
        (out/f'image{f}.ppm').write_bytes(b'P6\n7 7\n255\n'+bytes(x))
        try:
            from PIL import Image
            Image.frombytes('RGB',(7,7),bytes(x)).resize((224,224),Image.Resampling.NEAREST).save(out/f'image{f}.png')
        except ImportError:
            pass
        ia = alloc(bytes(x), f'image{f}')
        tensors = {'input':dict(data=x, h=7,w=7,c=3,addr=ia,producer=None)}
        jobs = []
        def add(name, op, srcs, data, h,w,c, **extra):
            t=dict(data=data,h=h,w=w,c=c,producer=len(jobs))
            tensors[name]=t
            jobs.append(dict(name=name,op=op,srcs=srcs,out=name,**extra))
        def pad(src, name):
            t=tensors[src]; h,w,c=t['h'],t['w'],t['c']
            a=[128]*((h+2)*(w+2)*c)
            for y in range(h):
                a[((y+1)*(w+2)+1)*c:((y+1)*(w+2)+1+w)*c]=t['data'][y*w*c:(y+1)*w*c]
            add(name,4,[src],a,h+2,w+2,c)
        def cv(src,name,layer):
            t=tensors[src]; weights,wa,bias,pp,shift,lo,hi=layers[layer]
            k={'conv3':3,'dw3':3,'conv1':1,'dw7':7}[layer]
            dw=layer.startswith('dw'); co=8
            a,h,w=conv(t['data'],t['h'],t['w'],t['c'],weights,co,k,dw=dw)
            add(name,3 if k==7 else (5 if k==1 else 0),[src],a,h,w,co,wa=wa,k=k,dw=dw)
            q=[max(lo,min(hi,round_away(v+bias[i%co],shift)+128)) for i,v in enumerate(a)]
            add(name+'_q',1,[name],q,h,w,co,pp=pp)
        pad('input','pad0'); cv('pad0','c3','conv3')
        pad('c3_q','pad1'); cv('pad1','d3','dw3')
        cv('d3_q','c1','conv1')
        a=tensors['c1_q']; b=tensors['c3_q']
        summed=[max(0,min(255,round_away((v-128)*3+(z-128)*2,2)+128)) for v,z in zip(a['data'],b['data'])]
        add('residual',2,['c1_q','c3_q'],summed,7,7,8,pp=addp)
        cv('residual','d7','dw7')
        # Four reusable slots per image. Lifetimes include every reader and producer.
        last={n:t['producer'] for n,t in tensors.items() if t['producer'] is not None}
        consumers={n:[] for n in tensors}
        for i,j in enumerate(jobs):
            for n in j['srcs']:
                consumers[n].append(i)
                if n in last:last[n]=max(last[n],i)
        slots={}; ends=[-1]*4
        for i,j in enumerate(jobs):
            s=next(s for s in range(4) if ends[s]<i)
            n=j['out']; slots[n]=s+4*f; ends[s]=last[n]
            tensors[n]['addr']=SLOT_BASE+(s+4*f)*SLOT_PITCH
            assert len(tensors[n]['data'])*(4 if j['op'] in (0,3,5) else 1)<=SLOT_BYTES
        frames.append(dict(tensors=tensors,jobs=jobs,slots=slots,consumers=consumers,source=source))
    jobs=[]; expected=bytearray(); command_words=[]; metadata=[]
    count=len(frames[0]['jobs'])*2
    for local in range(len(frames[0]['jobs'])):
        for f in range(2):
            fr=frames[f]; j=fr['jobs'][local]; ts=fr['tensors']; t=ts[j['out']]; src=ts[j['srcs'][0]]
            index=local*2+f
            cmd=[0]*16
            cmd[0]=j['op']; cmd[1]=src['addr']; cmd[3]=t['addr']; cmd[6]=src['c']; cmd[7]=src['w']; cmd[8]=src['h']; cmd[13]=100+f
            if j['op'] in (0,3,5):
                cmd[2]=j['wa'];cmd[9]=t['c'];cmd[10]=1;cmd[11]=int(j['dw'])
                data=b''.join(struct.pack('<i',v) for v in t['data'])
            else:
                data=bytes(t['data'])
                if j['op']==4:cmd[9]=128
                else:
                    cmd[4]=j['pp'];cmd[5]=len(t['data']);cmd[6]=t['c']
                    if j['op']==2:cmd[2]=ts[j['srcs'][1]]['addr']
            deps=[] if local==0 else [(local-1)*2+f]
            if j['op']==2:deps.append(ts[j['srcs'][1]]['producer']*2+f)
            hold=(1<<index)
            for c in fr['consumers'][j['out']]:hold|=1<<(c*2+f)
            uses=[]
            for name in j['srcs']:
                if ts[name]['producer'] is not None:uses.append((fr['slots'][name],ts[name]['producer']*2+f))
            use_slots=sum(s<<(3*i) for i,(s,_) in enumerate(uses));use_owners=sum(o<<(6*i) for i,(_,o) in enumerate(uses))
            final=local==len(fr['jobs'])-1
            meta=[(1<<len(deps))-1,*(deps+[0,0])[:2],fr['slots'][j['out']],hold&0xffffffff,hold>>32,(1<<len(uses))-1,use_slots,use_owners,int(final),100+f,t['addr'],len(data),len(expected)]
            metadata.extend(meta);command_words.extend(cmd);expected.extend(data)
            jobs.append(dict(index=index,frame=100+f,name=j['name'],opcode=j['op'],dependencies=deps,slot=meta[3],address=t['addr'],bytes=len(data),expected_offset=meta[-1],result=final))
    def hexfile(name, vals, width): (out/name).write_text(''.join(f'{v:0{width}x}\n' for v in vals),encoding='ascii')
    hexfile('memory.hex',mem,2);hexfile('expected.hex',expected,2)
    hexfile('commands.hex',command_words,8);hexfile('metadata.hex',metadata,8)
    manifest=dict(format='self-cnn-command-v1',task_count=count,memory_bytes=MEM_BYTES,expected_bytes=len(expected),slot_base=SLOT_BASE,slot_pitch=SLOT_PITCH,slot_bytes=SLOT_BYTES,immutable=immutable,jobs=jobs,input_sources=[fr['source'] for fr in frames],images_sha256=[hashlib.sha256(bytes(fr['tensors']['input']['data'])).hexdigest() for fr in frames],final_expected_sha256=hashlib.sha256(b''.join(bytes(fr['tensors']['d7_q']['data']) for fr in frames)).hexdigest(),scope='two small 7x7 RGB images, all operator types, synthetic diagnostic weights; not full MobileFaceNet')
    manifest['files_sha256']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('memory.hex','expected.hex','commands.hex','metadata.hex')}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);p.add_argument('--images',nargs=2,type=Path)
    a=p.parse_args();print(json.dumps(generate(a.out,a.images),indent=2))
