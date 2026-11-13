"""Full 112x112 MobileFaceNet integer graph, SRAM workload and independent golden.

One image, diagnostic scales derived from its floating reference; not calibrated
recognition accuracy. Intermediate SRAM contains poison, never golden tensors.
"""
import argparse, hashlib, json, struct, time
from pathlib import Path
from gen_mobilefacenet_chain import ROOT,np,onnx,ort,numpy_helper,Image,rounded,NeurekaMemoryLayout

def generate(out,image,output_scales=None):
    started=time.perf_counter();out.mkdir(parents=True,exist_ok=True)
    ref=ROOT/'build/runs/20261021_232600_mobilefacenet_reference/mobilefacenet.onnx'
    model=onnx.shape_inference.infer_shapes(onnx.load(ref))
    weights={t.name:numpy_helper.to_array(t) for t in model.graph.initializer}
    values={v.name:v for v in list(model.graph.value_info)+list(model.graph.output)}
    ops=list(model.graph.node);consumers={}
    for n in ops:
        for x in n.input:consumers.setdefault(x,[]).append(n)
    selected=[n for n in ops if n.op_type in ('Conv','Add')]
    fused={}
    for n in selected:
        c=consumers.get(n.output[0],[])
        fused[n.name]=c[0] if len(c)==1 and c[0].op_type in ('Relu','Clip') else None
    float_model=onnx.ModelProto();float_model.CopyFrom(model);del float_model.graph.output[:]
    names=[(fused[n.name] or n).output[0] for n in selected]
    for name in names:float_model.graph.output.append(values[name])
    rgb=np.asarray(Image.open(image).convert('RGB'),np.float32)/255
    assert rgb.shape==(112,112,3)
    norm=((rgb-np.array([.485,.456,.406]))/np.array([.229,.224,.225])).astype(np.float32)
    options=ort.SessionOptions();options.intra_op_num_threads=2
    session=ort.InferenceSession(float_model.SerializeToString(),options,providers=['CPUExecutionProvider'])
    floats=dict(zip(names,session.run(None,{'image':norm.transpose(2,0,1)[None]})))
    mem=bytearray([0xa5]*4096);gold=bytearray(mem);jobs=[];reports=[];ranges=[]
    def alloc(data,mutable=False):
        address=(len(mem)+63)&~63
        mem.extend(bytes([0xa5])*(address-len(mem)));gold.extend(bytes([0xa5])*(address-len(gold)))
        mem.extend(data);gold.extend(data)
        mem.extend(bytes([0xa5])*64);gold.extend(bytes([0xa5])*64)
        if mutable:ranges.append((address,len(data)))
        return address
    def empty(data):
        a=alloc(bytes([0xa5])*len(data),True);gold[a:a+len(data)]=data;return a
    # 16 words: kind, config/srcA, srcB/weights, dst, params, count,
    # channels, width, height, fill, check_addr, check_bytes, layer, reserved*3.
    def job(kind,layer,**kw):
        row=[0]*16;row[0]=kind;row[12]=layer
        for k,v in kw.items():row[int(k[1:])]=int(v)
        jobs.append(row)
    def params(b,ma,mb,za,zb,zo):
        assert max(abs(int(v)) for v in b)<2**31
        assert all(0<=int(v)<2**31 for v in list(ma)+list(mb))
        return alloc(b''.join(struct.pack('<5I',int(x)&0xffffffff,int(y),int(z),24|(za<<8)|(zb<<16)|(zo<<24),255<<8) for x,y,z in zip(b,ma,mb)))
    sx=3/127;zx=128;x=np.clip(np.rint(norm/sx)+zx,0,255).astype(np.uint8)
    ia=alloc(x.tobytes());initial_address=ia;records={'image':(x,sx,zx,ia)};macs=0
    for li,n in enumerate(selected):
        f=fused[n.name];output=(f or n).output[0]
        target=floats[output][0].transpose(1,2,0).astype(np.float64)
        relu=f is not None;sy=6/255 if f is not None and f.op_type=='Clip' else max(float((target.max() if relu else np.abs(target).max()))/(240 if relu else 110),1e-7)
        if output_scales is not None:
            sy=float(output_scales[li]);assert np.isfinite(sy) and sy>0
        zy=0 if relu else 128;x,sx,zx,ia=records[n.input[0]];first=len(jobs)
        if n.op_type=='Add':
            b,sb,zb,ba=records[n.input[1]];assert b.shape==x.shape
            co=x.shape[2];ma=np.full(co,round(sx/sy*(1<<24)),np.int64);mb=np.full(co,round(sb/sy*(1<<24)),np.int64)
            q=np.clip(rounded((x.astype(np.int64)-zx)*ma+(b.astype(np.int64)-zb)*mb,24)+zy,0,255).astype(np.uint8)
            pp=params(np.zeros(co,np.int64),ma,mb,zx,zb,zy);dst=empty(q.tobytes())
            job(2,li,a1=ia,a2=ba,a3=dst,a4=pp,a5=q.size,a6=co,a10=dst,a11=q.size)
            extra={}
        else:
            at={a.name:onnx.helper.get_attribute_value(a) for a in n.attribute}
            w=weights[n.input[1]].astype(np.float64);bias=weights[n.input[2]].astype(np.float64)
            co,_,k,_=w.shape;ci=x.shape[2];dw=at['group']==ci and ci>1;stride=at['strides'][0]
            assert at['dilations']==[1,1] and at['strides']==[stride,stride]
            pads=at['pads'];assert pads in ([0,0,0,0],[1,1,1,1])
            if pads[0]:
                padded=np.pad(x,((1,1),(1,1),(0,0)),constant_values=zx)
                pa=empty(padded.tobytes())
                job(4,li,a1=ia,a3=pa,a6=ci,a7=x.shape[1],a8=x.shape[0],a9=zx,a10=pa,a11=padded.size)
                x=padded;ia=pa
            oh=(x.shape[0]-k)//stride+1;ow=(x.shape[1]-k)//stride+1
            sw=np.maximum(np.abs(w).max((1,2,3))/127,1e-15)
            qw=np.clip(np.rint(w/sw[:,None,None,None]),-127,127).astype(np.int64)
            patch=np.lib.stride_tricks.sliding_window_view(x,(k,k),axis=(0,1))[::stride,::stride].astype(np.int64)
            if dw:raw=(patch*qw[:,0]).sum((3,4))
            else:raw=patch.reshape(oh*ow,-1) @ qw.reshape(co,-1).T;raw=raw.reshape(oh,ow,co)
            macs+=int(raw.size*(k*k if dw else ci*k*k))
            assert raw.min()>=-2**31 and raw.max()<2**31
            qb=np.rint(bias/(sx*sw)).astype(np.int64)-zx*qw.sum((1,2,3))
            ma=np.rint(sx*sw/sy*(1<<24)).astype(np.int64)
            q=np.clip(rounded((raw+qb)*ma,24)+zy,0,255).astype(np.uint8)
            ra=empty(raw.astype('<i4').tobytes());dst=empty(q.tobytes());pp=params(qb,ma,np.zeros(co,np.int64),0,0,zy)
            if k==7:
                assert dw and stride==1 and ci==512
                wa=alloc(qw[:,0].transpose(1,2,0).astype('i1').tobytes())
                job(3,li,a1=ia,a2=wa,a3=ra,a6=ci,a7=x.shape[1],a8=x.shape[0],a10=ra,a11=raw.size*4)
            else:
                for oc in range(0,co,32):
                    wa=alloc(NeurekaMemoryLayout.weightEncode((qw[oc:oc+32]+128).astype(np.uint8),8,depthwise=dw).tobytes())
                    kin=32 if dw else ci;dh=(oh-1)*stride+1;dwidth=(ow-1)*stride+1;rem=lambda v:(v-1)%4+1
                    cfg=[wa,ia+(oc if dw else 0),ra+oc*4,0,0,0,ci,x.shape[1]*ci,0,32,co*4//stride,ow*co*4//stride,
                         32 if k==1 else 36,32*((kin+31)//32) if k==1 else (0 if dw else 288*((kin+31)//32)),0,
                         32<<16|((kin-1)%32+1),rem(dh)<<16|rem(dwidth),(rem(dh)+k-1)<<16|(rem(dwidth)+k-1),
                         1<<16|((kin+31)//32),((dh+3)//4)<<16|((dwidth+3)//4),0,0xffffff80,0,
                         (2<<21)|(1<<23)|(1<<9)|7|(2<<5 if k==1 else (1<<5 if dw else 0))|(1<<8 if stride==2 else 0)]
                    ca=alloc(struct.pack('<24I',*cfg))
                    job(0,li,a1=ca,a10=ra if oc+32==co else 0,a11=raw.size*4 if oc+32==co else 0)
            job(1,li,a1=ra,a3=dst,a4=pp,a5=q.size,a6=co,a10=dst,a11=q.size)
            extra=dict(kernel=k,depthwise=dw,stride=stride,raw_address=ra,raw_bytes=raw.size*4)
        assert q.shape==target.shape,(n.name,q.shape,target.shape)
        records[output]=(q,sy,zy,dst)
        reports.append(dict(index=li,name=n.name,operation=n.op_type,activation=f.op_type if f else None,
            shape=list(q.shape),output_address=dst,output_bytes=q.size,scale=sy,zero=zy,
            first_job=first,end_job=len(jobs),rmse_float=float(np.sqrt(np.mean(((q.astype(np.float64)-zy)*sy-target)**2))),**extra))
        print(f'{li:02} {n.name}: {list(q.shape)} jobs={len(jobs)-first}',flush=True)
    assert len(reports)==63 and q.size==128
    # A 64-byte tail permits aligned wide reads past the end of the last tensor;
    # all tensor guards remain immutable and are checked by the RTL harness.
    table=alloc(b''.join(struct.pack('<16I',*j) for j in jobs))
    size=(len(mem)+4095)&~4095;mem.extend(bytes([0xa5])*(size-len(mem)));gold.extend(bytes([0xa5])*(size-len(gold)))
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes(gold)
    (out/'jobs.bin').write_bytes(b''.join(struct.pack('<16I',*j) for j in jobs))
    (out/'mutable.bin').write_bytes(b''.join(struct.pack('<II',*r) for r in ranges))
    vector=(q.astype(np.float64).reshape(-1)-zy)*sy;floatvec=target.reshape(-1)
    cosine=float(np.dot(vector,floatvec)/(np.linalg.norm(vector)*np.linalg.norm(floatvec)))
    report=dict(status='GENERATED',image=str(image),image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        model_sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        full_image=True,input_shape=[112,112,3],input_address=initial_address,layers=reports,jobs=jobs,
        descriptor_base=table,job_count=len(jobs),memory_bytes=size,macs=macs,final_address=dst,final_bytes=128,
        final_scale=sy,final_zero=zy,diagnostic_float_cosine=cosine,calibrated_accuracy=False,
        scale_policy='provided_fixed_scales' if output_scales is not None else 'single_image_diagnostic',
        uart=False,cpu=False,software_intermediate_injection=False,generation_seconds=time.perf_counter()-started)
    (out/'workload.json').write_text(json.dumps(report,indent=2));np.savetxt(out/'embedding_reference.csv',np.column_stack([np.arange(128),q.reshape(-1),vector,floatvec]),delimiter=',',header='index,uint8,dequantized,float',comments='')
    print(f'Generated {len(jobs)} commands, {size} bytes, {macs} MACs, diagnostic cosine={cosine:.6f}')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('--image',type=Path,default=Path('D:/code/facemodel/person_1.jpg'))
    p.add_argument('--scales-from',type=Path,help='Reuse all layer scales from a prior workload.json')
    a=p.parse_args();scales=None if a.scales_from is None else [l['scale'] for l in json.loads(a.scales_from.read_text())['layers']]
    generate(a.out,a.image,scales)
