"""Real Conv_5 -> Conv_6 -> Conv_7 -> Conv_8 + skip, two small face ROIs.
The preceding network is software-only. All block intermediate values come from RTL.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from gen_mobilefacenet_chain import ROOT, np, onnx, ort, numpy_helper, Image, NeurekaMemoryLayout, rounded

def main():
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
    ref=ROOT/'build/runs/20261021_232600_mobilefacenet_reference/mobilefacenet.onnx'
    model=onnx.shape_inference.infer_shapes(onnx.load(ref));t={v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
    vi={v.name:v for v in model.graph.value_info};del model.graph.output[:]
    names=['/Clip_2_output_0','/Conv_5_output_0','/Clip_3_output_0','/Clip_4_output_0','/Conv_8_output_0','/Add_output_0']
    for name in names:model.graph.output.append(vi[name])
    opts=ort.SessionOptions();opts.intra_op_num_threads=2
    session=ort.InferenceSession(model.SerializeToString(),opts,providers=['CPUExecutionProvider'])
    convs=[n for n in model.graph.node if n.op_type=='Conv'][5:9]
    mem=bytearray([0xa5]*524288);gold=bytearray(mem);frames=[];scales=None
    for f in range(2):
        cursor=0x1000+f*0x30000
        def alloc(data):
            nonlocal cursor
            address=(cursor+63)&~63;cursor=address+len(data)+64
            assert cursor < (0x30000 if f==0 else 0x60000)
            mem[address:address+len(data)]=data
            return address
        def empty(n):return alloc(bytes([0xa5])*n)
        def params(b,m,mb,za=0,zb=0,zo=0):
            return alloc(b''.join(struct.pack('<5I',int(bb)&0xffffffff,int(mm)&0xffffffff,int(nn)&0xffffffff,
                         24|(za<<8)|(zb<<16)|(zo<<24),255<<8) for bb,mm,nn in zip(b,m,mb)))
        image=Path(f'D:/code/facemodel/person_{f+1}.jpg')
        rgb=np.asarray(Image.open(image).convert('RGB'),dtype=np.float32)/255
        norm=(rgb-np.array([.485,.456,.406]))/np.array([.229,.224,.225])
        full=session.run(None,{'image':norm.astype(np.float32).transpose(2,0,1)[None]})
        # Interior coordinates [2:8] avoid padding. DW output corresponds [3:7].
        fx=full[0][0,:,2:8,2:8].transpose(1,2,0).astype(np.float64)
        sx=6/255;zx=0;x=np.clip(np.rint(fx/sx),0,255).astype(np.uint8);ia=alloc(x.tobytes())
        initial_address=ia;reports=[];qs=[];fs=[];local_scales=[]
        for li,node in enumerate(convs):
            w=t[node.input[1]].astype(np.float64);bias=t[node.input[2]].astype(np.float64)
            co,_,k,_=w.shape;ci=x.shape[2];dw=li==2;oh=x.shape[0]-k+1;ow=x.shape[1]-k+1
            sw=np.maximum(np.max(np.abs(w),axis=(1,2,3))/127,1e-15)
            qw=np.clip(np.rint(w/sw[:,None,None,None]),-127,127).astype(np.int64)
            raw=np.empty((oh,ow,co),np.int64);floating=np.empty(raw.shape,np.float64)
            for y in range(oh):
                for xx in range(ow):
                    patch=x[y:y+k,xx:xx+k].astype(np.int64).transpose(2,0,1)
                    fp=fx[y:y+k,xx:xx+k].transpose(2,0,1)
                    if dw:
                        raw[y,xx]=(patch*qw[:,0]).sum((1,2));floating[y,xx]=(fp*w[:,0]).sum((1,2))+bias
                    else:
                        raw[y,xx]=np.einsum('ihw,oihw->o',patch,qw);floating[y,xx]=np.einsum('ihw,oihw->o',fp,w)+bias
            activation=li in (1,2);zy=0 if activation else 128
            target=np.clip(floating,0,6) if activation else floating
            sy=6/255 if activation else max(float(np.abs(target).max())/110,1e-6)
            if scales is not None:sy=scales[li]
            local_scales.append(sy)
            qb=np.rint(bias/(sx*sw)).astype(np.int64)-zx*qw.sum((1,2,3));mult=np.rint(sx*sw/sy*(1<<24)).astype(np.int64)
            assert np.max(np.abs(qb))<2**31 and np.max(mult)<2**31
            q=np.clip(rounded((raw+qb)*mult,24)+zy,0,255).astype(np.uint8)
            ra=empty(raw.size*4);dst=empty(q.size);pp=params(qb,mult,np.zeros(co),zo=zy)
            gold[ra:ra+raw.size*4]=raw.astype('<i4').tobytes();gold[dst:dst+q.size]=q.tobytes()
            weights=[]
            for oc in range(0,co,32):weights.append(alloc(NeurekaMemoryLayout.weightEncode((qw[oc:oc+32]+128).astype(np.uint8),8,depthwise=dw).tobytes()))
            origin=2 if li<2 else 3;expected=full[li+1][0,:,origin:origin+oh,origin:origin+ow].transpose(1,2,0)
            np.testing.assert_allclose(target,expected,rtol=2e-4,atol=3e-5)
            reports.append(dict(layer=node.name,kernel=k,depthwise=dw,input_shape=list(x.shape),output_shape=list(q.shape),
                input_address=ia,output_address=dst,raw_address=ra,parameters_address=pp,weights=weights,
                input_scale=sx,input_zero=zx,output_scale=sy,output_zero=zy,
                float_roi_onnx_max_error=float(np.max(np.abs(target-expected)))))
            qs.append(q);fs.append(target);x=q;fx=target;ia=dst;sx=sy;zx=zy
        sy=max(float(np.abs(fs[0][1:5,1:5]+fs[3]).max())/110,1e-6) if scales is None else scales[4]
        local_scales.append(sy);ma=round(local_scales[0]/sy*(1<<24));mb=round(local_scales[3]/sy*(1<<24))
        added=np.clip(rounded((qs[0][1:5,1:5].astype(np.int64)-128)*ma+(qs[3].astype(np.int64)-128)*mb,24)+128,0,255).astype(np.uint8)
        np.testing.assert_allclose(fs[0][1:5,1:5]+fs[3],full[5][0,:,3:7,3:7].transpose(1,2,0),rtol=2e-4,atol=3e-5)
        ad=empty(added.size);ap=params(np.zeros(64),np.full(64,ma),np.full(64,mb),128,128,128)
        gold[ad:ad+added.size]=added.tobytes()
        frames.append(dict(image=str(image),image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),layers=reports,add_address=ad,add_params=ap,input_address=initial_address))
        if scales is None:scales=local_scales
    nodes=[];lookup={};cfg_cursor=0x68000;scratch=[0x70000,0x72000,0x74000]
    for l,rows in enumerate([6,6,4,4,4]):
        step=1 if l==4 else 2
        for y in range(0,rows,step):
            for f in range(2):
                lookup[f,l,y//step]=len(nodes);nodes.append(dict(id=len(nodes),frame=f,layer=l,y=y,rows=step))
    for n in nodes:
        f,l,y,rows=n['frame'],n['layer'],n['y'],n['rows'];fr=frames[f];dependencies=[];isadd=l==4
        if isadd:
            dependencies=[lookup[f,0,(y+1)//2],lookup[f,3,y//2]]
            count=4*64;channels=64;dst=fr['add_address']+y*count;pp=fr['add_params'];raw=0;base=0
            sa=fr['layers'][0]['output_address']+((y+1)*6+1)*64;sb=fr['layers'][3]['output_address']+y*count
        else:
            lr=fr['layers'][l];k=lr['kernel'];ci=lr['input_shape'][2];iw=lr['input_shape'][1];ow=lr['output_shape'][1];channels=lr['output_shape'][2]
            count=rows*ow*channels;assert count*4<=8192
            if l:dependencies=sorted({lookup[f,l-1,source_y//2] for source_y in range(y,y+rows+k-1)})
            dst=lr['output_address']+y*ow*channels;raw=lr['raw_address']+y*ow*channels*4;pp=lr['parameters_address'];base=cfg_cursor;sa=sb=0
            for s in scratch:
                for group,wa in enumerate(lr['weights']):
                    kin=32 if lr['depthwise'] else ci;rem=lambda v:(v-1)%4+1
                    cfg=[wa,lr['input_address']+y*iw*ci+(group*32 if lr['depthwise'] else 0),s+group*128,0,0,0,
                        ci,iw*ci,0,32,channels*4,ow*channels*4,32 if k==1 else 36,
                        32*((kin+31)//32) if k==1 else 0,0,32<<16|((kin-1)%32+1),rem(rows)<<16|rem(ow),
                        (rem(rows)+k-1)<<16|(rem(ow)+k-1),1<<16|((kin+31)//32),((rows+3)//4)<<16|((ow+3)//4),
                        0,0xffffff80,0,(2<<21)|(1<<23)|(1<<9)|7|(2<<5 if k==1 else 1<<5)]
                    struct.pack_into('<24I',mem,cfg_cursor,*cfg);cfg_cursor+=96
        n.update(deps=sum(1<<d for d in dependencies),dependency_nodes=dependencies,config_base=base,parameters=pp,destination=dst,
                 count=count,channels=channels,tag=f<<16|l<<8|y,raw_golden=raw,add=int(isadd),src_a=sa,src_b=sb,keep=int(isadd))
    assert cfg_cursor<scratch[0] and len(nodes)<=32
    keys=['deps','config_base','parameters','destination','count','channels','tag','layer','raw_golden','y','add','src_a','src_b','keep']
    (out/'nodes.hex').write_text(''.join(f'{n[k]:08x}\n' for n in nodes for k in keys));(out/'meta.hex').write_text(f'{len(nodes):08x}\n')
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes(gold)
    report=dict(nodes=nodes,frames=frames,scratch=scratch,scratch_capacity=8192,memory_size=len(mem),quantization_scales=scales,
        quantization_source='frame0 diagnostic scales frozen for both images; not accuracy calibrated',
        onnx_sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_preloaded=True,full_network=False,uart=False,cpu=False,roi='Conv_5 / Conv_6 [2:8,2:8]; Conv_7 / Conv_8 / Add [3:7,3:7]')
    (out/'workload.json').write_text(json.dumps(report,indent=2));print(f'Generated {len(nodes)} nodes, two actual residual blocks, 64/128 channels')

if __name__=='__main__':main()
