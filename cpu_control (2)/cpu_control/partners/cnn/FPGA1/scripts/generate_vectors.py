"""Array-only Conv/DW cases plus a synthetic 112x112 -> 128 graph.
This fixture has deterministic random weights; it is NOT a trained face model.
"""
from pathlib import Path
import json
import numpy as np
from reference import execute,write_memh,write_golden,task_line,output_shape
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'vectors'
RAM_BYTES=262144


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(20260912)
    lines=[];manifest=[]
    cases=[
        ('conv3', 'conv',5,4,2,3,3,1,1,2,0,0),
        ('conv_stride','conv',7,6,3,2,3,2,1,3,0,0),
        ('conv1','conv',4,3,3,5,1,1,0,2,0,0),
        ('dw3','depthwise',5,4,3,3,3,1,1,1,0,0),
        ('dw_stride','depthwise',7,6,2,2,3,2,1,2,0,0),
        ('dw7','depthwise',7,7,3,3,7,1,0,3,0,0),
        ('dw7_pad','depthwise',8,7,2,2,7,2,3,2,0,0),
        ('negative_add','add',7,1,1,1,0,0,0,0,0,0),
        ('shift_add','add',7,1,1,1,0,0,0,1,0,0),
        ('relu6','relu6',8,1,1,1,0,0,0,0,0,0),
        ('relu','conv',3,3,1,1,1,1,0,0,1,0),
        ('shift255','conv',1,1,1,2,1,1,0,255,0,0),
        ('wrap','conv',3,3,1,2,3,1,0,0,0,0),
        ('copy','copy',5,3,2,2,0,0,0,0,0,0),
        ('final','final_output',1,1,128,128,0,0,0,0,0,0),
    ]
    cases=[x for x in cases if x[1] in ('conv','depthwise') and not x[-2] and not x[-1]]
    for num,(name,op,w,h,ci,co,k,s,p,q,relu,relu6) in enumerate(cases):
        layer=dict(layer_id=num,name=name,op=op,width=w,height=h,in_channels=ci,out_channels=co,
                   kernel=k,stride=s,padding=p,quant_shift=q,relu_enable=relu,relu6_enable=relu6,
                   input_addr=0x101,output_addr=0x10001,weight_addr=0x20003,bias_addr=0x30000)
        x=rng.integers(-12,13,(ci,h,w),dtype=np.int8)
        if op=='relu6':x=np.array([-128,-1,0,1,95,96,97,127],dtype=np.int8).reshape(ci,h,w)
        if op=='final_output':x=np.arange(-64,64,dtype=np.int8).reshape(ci,h,w)
        segments=[(0x101,x.tobytes())]
        if op in ('conv','depthwise'):
            wt=rng.integers(-4,5,(co,1 if op=='depthwise' else ci,k,k),dtype=np.int8)
            bias=rng.integers(-20,21,co,dtype=np.int32)
            if name=='dw3':
                x=np.stack([np.full((h,w),v,dtype=np.int8) for v in [2,-3,5]])
                wt=np.stack([np.full((1,k,k),v,dtype=np.int8) for v in [1,2,-1]])
                bias=np.array([7,-8,9],dtype=np.int32);segments[0]=(0x101,x.tobytes())
            if name=='wrap':
                segments[0]=(0x101,bytes([127]*9));wt=np.array([1]*9+[-1]*9,dtype=np.int8).reshape(2,1,3,3)
                bias=np.array([2147483647,-2147483648],dtype=np.int32)
            if name=='shift255':wt.fill(0);bias=np.array([100,-100],dtype=np.int32)
            segments.extend([(0x20003,wt.tobytes()),(0x30000,bias.astype('<i4').tobytes())])
        elif op=='add':
            segments[0]=(0x101,np.array([-128,127,-3,50,-60,0,127],dtype=np.int8).tobytes())
            segments.append((0x20003,np.array([-128,127,0,80,-80,-1,-128],dtype=np.int8).tobytes()))
        memory=bytearray([0xa5])*RAM_BYTES
        for addr,data in segments:memory[addr:addr+len(data)]=data
        y=execute(memory,layer)
        write_memh(OUT/f'{name}.memh',segments);write_golden(OUT/f'{name}.hex',y)
        lines.append(task_line(f'build/vectors/{name}.memh',name,layer,f'build/vectors/{name}.hex'))
        manifest.append(dict(**layer,output_shape=list(y.shape),first_outputs=y.reshape(-1)[:16].tolist()))
    # Pure Conv/DW chain, no residual or activation. Final Conv writes FINAL directly.
    A,B,FINAL=0x10001,0x18001,0x28001
    specs=[('conv',2,3,2,1,3,0),('depthwise',2,3,2,1,2,0),('conv',4,1,1,0,2,0),
           ('depthwise',4,3,2,1,2,0),('conv',4,1,1,0,2,0),('depthwise',4,3,2,1,2,0),
           ('conv',8,1,1,0,2,0),('depthwise',8,3,1,1,2,0),('conv',4,1,1,0,2,0),
           ('conv',8,1,1,0,2,0),('depthwise',8,7,1,0,3,0),('conv',128,1,1,0,1,0)]
    x=rng.integers(-16,17,(3,112,112),dtype=np.int8)
    segments=[(0x101,x.tobytes())];layers=[];source=0x101;ci,h,w=x.shape;wa,ba=0x30003,0x3e000
    for index,(op,co,k,s,p,q,r6) in enumerate(specs):
        dst=FINAL if index==len(specs)-1 else B if source==A else A
        layer=dict(layer_id=index,name=f'chain_{index:02d}_{op}',op=op,input_addr=source,output_addr=dst,
            weight_addr=wa,bias_addr=ba,width=w,height=h,in_channels=ci,out_channels=co,
            kernel=k,stride=s,padding=p,quant_shift=q,relu6_enable=r6)
        if op in ('conv','depthwise'):
            weight=rng.integers(-3,4,(co,1 if op=='depthwise' else ci,k,k),dtype=np.int8)
            bias=rng.integers(-30,31,co,dtype=np.int32)
            segments.extend([(wa,weight.tobytes()),(ba,bias.astype('<i4').tobytes())])
            wa+=weight.size;ba+=bias.nbytes
        layers.append(layer)
        if op!='copy':source=dst;ci,h,w=output_shape(layer)
    memory=bytearray([0xa5])*RAM_BYTES
    for addr,data in segments:memory[addr:addr+len(data)]=data
    write_memh(OUT/'chain.memh',segments)
    for n,layer in enumerate(layers):
        y=execute(memory,layer);path=f"build/vectors/{layer['name']}.hex";write_golden(ROOT/path,y)
        lines.append(task_line('build/vectors/chain.memh' if n==0 else '-',layer['name'],layer,path))
        manifest.append(dict(**layer,output_shape=list(y.shape),first_outputs=y.reshape(-1)[:16].tolist()))
    assert y.size==128 and np.any(y!=0)
    (OUT/'final_features.golden.bin').write_bytes(y.tobytes())
    (OUT/'tasks.txt').write_text(str(len(lines))+'\n'+'\n'.join(lines)+'\n')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Generated {len(lines)} tasks; synthetic 112x112 chain -> 128 INT8 outputs')


if __name__=='__main__':main()
