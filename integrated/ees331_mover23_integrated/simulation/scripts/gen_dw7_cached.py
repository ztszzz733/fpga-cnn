"""Two actual MobileFaceNet GDConv inputs/weights plus overlapping-window probes."""
import argparse,hashlib,json,struct
from pathlib import Path
from gen_mobilefacenet_chain import ROOT,np,onnx,ort,numpy_helper,Image,rounded

def emit(out,xs,qw,bias,mult,scales,source):
    out.mkdir(parents=True,exist_ok=True);h,w,c=xs[0].shape;oh,ow=h-6,w-6
    mem=bytearray([0xa5]*262144);gold=bytearray(mem);cursor=256
    def alloc(data):
        nonlocal cursor
        a=(cursor+63)&~63;cursor=a+len(data)+64;assert cursor<len(mem)
        mem[a:a+len(data)]=data;return a
    wa=alloc(qw.transpose(1,2,0).astype('i1').tobytes()) # tap,channel, not NEureka bit planes
    pp=alloc(b''.join(struct.pack('<5I',int(b)&0xffffffff,int(m)&0xffffffff,0,24|(128<<24),255<<8) for b,m in zip(bias,mult)))
    jobs=[]
    for x in xs:
        raw=np.empty((oh,ow,c),np.int64)
        for y in range(oh):
            for xx in range(ow):raw[y,xx]=(x[y:y+7,xx:xx+7].astype(np.int64)*qw.transpose(1,2,0)).sum((0,1))
        q=np.clip(rounded((raw+bias)*mult,24)+128,0,255).astype(np.uint8)
        ia=alloc(x.tobytes());ra=alloc(bytes([0xa5])*raw.size*4);da=alloc(bytes([0xa5])*q.size)
        gold[ra:ra+raw.size*4]=raw.astype('<i4').tobytes();gold[da:da+q.size]=q.tobytes()
        jobs.append([ia,wa,ra,da,pp,w,h,c,q.size])
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes(gold)
    (out/'jobs.hex').write_text(''.join(f'{v:08x}\n' for j in jobs for v in j))
    (out/'workload.json').write_text(json.dumps(dict(source=source,jobs=jobs,input_shape=[h,w,c],output_shape=[oh,ow,c],
        quantization=scales,input_reads_per_frame=h*w*c//4,weight_reads_first_frame=49*c//4,weight_reads_second_frame=0,
        naive_input_bytes=oh*ow*c*49,actual_input_bytes=h*w*c,weights_layout='tap-major signed INT8, [ky][kx][channel]',
        full_network_rtl=False,source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    ref=ROOT/'build/runs/20261021_232600_mobilefacenet_reference/mobilefacenet.onnx'
    model=onnx.shape_inference.infer_shapes(onnx.load(ref));t={v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
    node=next(n for n in model.graph.node if n.op_type=='Conv' and t[n.input[1]].shape[-1]==7)
    vi={v.name:v for v in model.graph.value_info};del model.graph.output[:]
    for name in [node.input[0],node.output[0]]:model.graph.output.append(vi[name])
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;ss=ort.InferenceSession(model.SerializeToString(),opts,providers=['CPUExecutionProvider'])
    ww=t[node.input[1]][:,0].astype(np.float64);bb=t[node.input[2]].astype(np.float64)
    sw=np.maximum(np.abs(ww).max((1,2))/127,1e-15);qw=np.clip(np.rint(ww/sw[:,None,None]),-127,127).astype(np.int64)
    xs=[];maxerr=0;sy=None;sx=6/255
    for f in range(2):
        rgb=np.asarray(Image.open(f'D:/code/facemodel/person_{f+1}.jpg').convert('RGB'),np.float32)/255
        xx=((rgb-np.array([.485,.456,.406]))/np.array([.229,.224,.225])).astype(np.float32)
        fx,fy=ss.run(None,{'image':xx.transpose(2,0,1)[None]});fx=fx[0].transpose(1,2,0)
        assert fx.shape==(7,7,512) and fx.min()>=-1e-6 and fx.max()<=6.00001
        expected=(fx.astype(np.float64)*ww.transpose(1,2,0)).sum((0,1))+bb
        np.testing.assert_allclose(expected,fy.reshape(-1),rtol=2e-4,atol=3e-5);maxerr=max(maxerr,float(np.max(np.abs(expected-fy.reshape(-1)))))
        if sy is None:sy=max(float(np.abs(expected).max())/110,1e-6)
        xs.append(np.clip(np.rint(fx/sx),0,255).astype(np.uint8))
    bias=np.rint(bb/(sx*sw)).astype(np.int64);mult=np.rint(sx*sw/sy*(1<<24)).astype(np.int64)
    assert np.max(np.abs(bias))<2**31 and np.max(mult)<2**31
    emit(a.out/'real512',xs,qw,bias,mult,dict(sx=sx,zx=0,sy=sy,zy=128,calibrated=False),
         dict(layer=node.name,onnx_sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),float_max_error=maxerr,
              images=[dict(path=f'D:/code/facemodel/person_{i+1}.jpg',sha256=hashlib.sha256(Path(f'D:/code/facemodel/person_{i+1}.jpg').read_bytes()).hexdigest()) for i in range(2)]))
    rng=np.random.default_rng(7049);c=16
    xs=[rng.integers(0,256,(9,10,c),dtype=np.uint8) for _ in range(2)];qw=rng.integers(-128,128,(c,7,7),dtype=np.int64)
    # Deliberately include signed extremes and full-scale unsigned inputs.
    qw[0]=-128;qw[1]=127;xs[0][:,:,0:2]=255
    emit(a.out/'overlap16',xs,qw,np.zeros(c,np.int64),np.full(c,1<<9,np.int64),dict(shift=24,zy=128),dict(kind='deterministic signed-edge and overlapping-window probe'))
    print('Generated real 7x7x512 and overlapping 9x10x16 two-frame probes')
if __name__=='__main__':main()
