"""Real pretrained first three layers on a small spatial ROI, all 64 channels.

Windows Python. Integer golden uses numpy int64 dot products, not RTL models.
This is local per-layer quantization validation, not an accuracy-calibrated net.
"""
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.tools/mobilefacenet-python'))
sys.path.insert(0,str(ROOT/'third_party/neureka/model/deps/pulp-nnx/test'))
import numpy as np
import onnx
import onnxruntime as ort
from onnx import numpy_helper
from PIL import Image
from NeurekaMemoryLayout import NeurekaMemoryLayout


def rounded(v,shift):
    return np.sign(v)*((np.abs(v)+(0 if shift==0 else 1<<(shift-1))) >> shift)


def generate(out, image, output_scales=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    ref=ROOT/'build/runs/20261021_232600_mobilefacenet_reference/mobilefacenet.onnx'
    model=onnx.load(ref); tensors={t.name:numpy_helper.to_array(t) for t in model.graph.initializer}
    layers=[n for n in model.graph.node if n.op_type=='Conv'][:3]
    shaped=onnx.shape_inference.infer_shapes(model)
    vi={v.name:v for v in shaped.graph.value_info}
    activations=[n.output[0] for n in shaped.graph.node if n.op_type in ('Relu','Clip')][:3]
    del shaped.graph.output[:]
    for name in activations:shaped.graph.output.append(vi[name])
    opts=ort.SessionOptions();opts.intra_op_num_threads=2
    reference=ort.InferenceSession(shaped.SerializeToString(),opts,providers=['CPUExecutionProvider'])
    mem=bytearray([0xa5]*262144);gold=bytearray(mem);cursor=0x4000;jobs=[];reports=[];guards=[]
    def alloc(data):
        nonlocal cursor
        a=(cursor+63)&~63;cursor=a+len(data)+64
        assert cursor<len(mem)
        mem[a:a+len(data)]=data;guards.append((a,len(data)))
        return a
    def empty(n):return alloc(bytes([0xa5])*n)
    def conv_job(cfg,checkaddr=0,checkbytes=0):
        ca=alloc(struct.pack('<24I',*cfg));jobs.append([0,ca,0,0,0,0,0,0,checkaddr,checkbytes])
    def post_job(a,b,d,p,n,c,add=False):jobs.append([2 if add else 1,0,a,b,d,p,n,c,d,n])
    def params(bias,ma,mb,za=0,zb=0,zo=0,lo=0,hi=255,shift=24):
        return alloc(b''.join(struct.pack('<5I',int(b)&0xffffffff,int(a)&0xffffffff,int(m)&0xffffffff,
                       shift|(za<<8)|(zb<<16)|(zo<<24),lo|(hi<<8)) for b,a,m in zip(bias,ma,mb)))
    rgb=np.asarray(Image.open(image).convert('RGB'),dtype=np.float32)/255
    assert rgb.shape==(112,112,3)
    normalized=(rgb-np.array([.485,.456,.406]))/np.array([.229,.224,.225])
    full_float=reference.run(None,{'image':normalized.astype(np.float32).transpose(2,0,1)[None]})
    sx=3/127; zp=128
    # First six output positions require input [-1..11]. Padding is real zero,
    # encoded as 128, not RGB black and not byte zero.
    real=np.zeros((13,13,3));real[1:,1:]=normalized[:12,:12]
    float_x=real.copy()
    x=np.clip(np.rint(real/sx)+zp,0,255).astype(np.uint8)
    ia=alloc(x.tobytes())
    for li,node in enumerate(layers):
        w=tensors[node.input[1]].astype(np.float64);bias=tensors[node.input[2]].astype(np.float64)
        k=w.shape[2];co=w.shape[0];ci=x.shape[2];dw=li==1;stride=2 if li==0 else 1
        sw=np.maximum(np.max(np.abs(w),axis=(1,2,3))/127,1e-15)
        qw=np.clip(np.rint(w/sw[:,None,None,None]),-127,127).astype(np.int64)
        oh=(x.shape[0]-k)//stride+1;ow=(x.shape[1]-k)//stride+1
        raw=np.empty((oh,ow,co),dtype=np.int64);fp=np.empty_like(raw,dtype=np.float64);fp_reference=np.empty_like(fp)
        for y in range(oh):
            for xx in range(ow):
                patch=x[y*stride:y*stride+k,xx*stride:xx*stride+k].astype(np.int64).transpose(2,0,1)
                realpatch=(patch-zp)*sx
                refpatch=float_x[y*stride:y*stride+k,xx*stride:xx*stride+k].transpose(2,0,1)
                if dw:
                    raw[y,xx]=(patch*qw[:,0]).sum(axis=(1,2))
                    fp[y,xx]=(realpatch*w[:,0]).sum(axis=(1,2))+bias
                    fp_reference[y,xx]=(refpatch*w[:,0]).sum(axis=(1,2))+bias
                else:
                    raw[y,xx]=np.einsum('ihw,oihw->o',patch,qw)
                    fp[y,xx]=np.einsum('ihw,oihw->o',realpatch,w)+bias
                    fp_reference[y,xx]=np.einsum('ihw,oihw->o',refpatch,w)+bias
        # Layer 0 is ReLU6. Layer 1/2 are ReLU; select a local scale from this
        # sample's float operator on dequantized input, not production calibration.
        sy=6/255 if li==0 else max(float(np.maximum(fp,0).max())/240,1e-6)
        if output_scales is not None:
            sy=float(output_scales[li])
        qb=np.rint(bias/(sx*sw)).astype(np.int64)-zp*qw.sum(axis=(1,2,3))
        mult=np.rint(sx*sw/sy*(1<<24)).astype(np.int64)
        assert np.max(np.abs(qb))<2**31 and np.max(mult)<2**31 and np.min(mult)>=0, (li,float(sw.min()),int(np.max(np.abs(qb))),int(mult.min()),int(mult.max()))
        q=np.clip(rounded((raw+qb)*mult,24),0,255).astype(np.uint8)
        ra=empty(raw.size*4);dst=empty(q.size)
        gold[ra:ra+raw.size*4]=raw.astype('<i4').tobytes();gold[dst:dst+q.size]=q.tobytes()
        for oc in range(0,co,32):
            block=qw[oc:oc+32]
            packed=NeurekaMemoryLayout.weightEncode((block+128).astype(np.uint8),8,depthwise=dw)
            wa=alloc(packed.tobytes());kin=32 if dw else ci;kout=32
            dh=(oh-1)*stride+1;dwidth=(ow-1)*stride+1
            rem=lambda v:(v-1)%4+1
            cfg=[wa,ia+(oc if dw else 0),ra+oc*4,0,0,0,
                 ci,x.shape[1]*ci,0,32,co*4//stride,ow*co*4//stride,
                 32 if k==1 else 36,(32*((kin+31)//32) if k==1 else (0 if dw else 288*((kin+31)//32))),0,
                 kout<<16|((kin-1)%32+1),rem(dh)<<16|rem(dwidth),
                 (rem(dh)+k-1)<<16|(rem(dwidth)+k-1),1<<16|((kin+31)//32),
                 ((dh+3)//4)<<16|((dwidth+3)//4),0,0xffffff80,0,
                 (2<<21)|(1<<23)|(1<<9)|7|(2<<5 if k==1 else (1<<5 if dw else 0))|(1<<8 if stride==2 else 0)]
            # Internal prefetch off for the initial integration baseline; outer
            # graph/stripe overlap is a separate scheduling decision.
            conv_job(cfg,ra if oc+32==co else 0,raw.size*4 if oc+32==co else 0)
        pp=params(qb,mult,np.zeros(co,dtype=np.int64))
        post_job(ra,0,dst,pp,q.size,co)
        target=np.minimum(np.maximum(fp,0),6) if li==0 else np.maximum(fp,0)
        float_x=np.minimum(np.maximum(fp_reference,0),6) if li==0 else np.maximum(fp_reference,0)
        offset=0 if li==0 else 1
        ort_roi=full_float[li][0,:,offset:offset+oh,offset:offset+ow].transpose(1,2,0)
        np.testing.assert_allclose(float_x,ort_roi,rtol=1e-4,atol=2e-5)
        reports.append(dict(layer=node.name,kernel=k,depthwise=dw,stride=stride,input_shape=list(x.shape),output_shape=list(q.shape),
                            input_scale=sx,input_zero=zp,output_scale=sy,output_zero=0,
                            float_local_rmse=float(np.sqrt(np.mean((q*sy-target)**2))),
                            accumulated_quantization_rmse=float(np.sqrt(np.mean((q*sy-float_x)**2))),
                            float_roi_onnx_max_error=float(np.max(np.abs(float_x-ort_roi))),
                            raw_address=ra,output_address=dst,parameters_address=pp,
                            raw_min=int(raw.min()),raw_max=int(raw.max())))
        x=q;ia=dst;sx=sy;zp=0
    # Independent edge-vector test for residual scale alignment / rounding /
    # saturation. This is not a residual edge in the first three model layers.
    a=np.array([0,1,127,128,129,254,255,3]*2+[130]*4+[126]*4+[128]*8,dtype=np.uint8)
    b=np.array([255,128,0,128,127,255,0,1]*2+[127]*16,dtype=np.uint8)
    channels=4;ma=np.array([1,3,31,7]);mb=np.array([1,5,2,-3]);shift=2
    g=np.clip(rounded((a.astype(np.int64)-128)*np.tile(ma,8)+(b.astype(np.int64)-127)*np.tile(mb,8),shift)+128,0,255).astype(np.uint8)
    aa=alloc(a.tobytes());bb=alloc(b.tobytes());dd=empty(len(g));gold[dd:dd+len(g)]=g.tobytes()
    pp=params(np.zeros(channels,dtype=int),ma,mb,128,127,128,shift=shift);post_job(aa,bb,dd,pp,len(g),channels,True)
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes(gold)
    (out/'jobs.hex').write_text(''.join(f'{v:08x}\n' for j in jobs for v in j))
    (out/'meta.hex').write_text(f'{len(jobs):08x}\n')
    (out/'guards.hex').write_text(''.join(f'{v:08x}\n' for pair in guards for v in pair))
    (out/'guard_count.hex').write_text(f'{len(guards):08x}\n')
    report=dict(image=str(image),image_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest(),onnx_sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),
                layers=reports,jobs=jobs,bytes_used=cursor,network_channels_preserved=True,
                roi='conv1 top-left 6x6; DW/PW coordinates [1:5,1:5] of full feature map',
                full_image=False,full_network=False,calibrated_accuracy=False,uart=False,cpu=False,prefetch=False)
    (out/'workload.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('--image',type=Path,default=Path('D:/code/facemodel/person_1.jpg'))
    a=p.parse_args();generate(a.out,a.image)
