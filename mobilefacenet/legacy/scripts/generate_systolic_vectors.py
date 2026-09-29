"""Deterministic tile-edge cases; scalar RAM ABI and NumPy golden unchanged."""
from pathlib import Path
import json
import numpy as np
from reference import execute,write_memh,write_golden,task_line
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'systolic_vectors'

def main():
    OUT.mkdir(parents=True,exist_ok=True);rng=np.random.default_rng(917);lines=[];manifest=[]
    specs=[('conv1_exact8','conv',8,1,8,8,1,1,0),
           ('conv1_tail','conv',10,1,17,9,1,1,0),
           ('conv3_tail','conv',5,4,9,10,3,2,1),
           ('conv3_pad2','conv',2,2,3,9,3,1,2),
           ('dw3_tail','depthwise',5,3,11,11,3,1,1),
           ('dw7_tail','depthwise',8,8,9,9,7,1,0),
           ('dw7_stride_pad','depthwise',9,8,9,9,7,2,3)]
    for i,(name,op,w,h,ci,co,k,s,p) in enumerate(specs):
        layer=dict(layer_id=i,name=name,op=op,width=w,height=h,in_channels=ci,out_channels=co,
                   kernel=k,stride=s,padding=p,quant_shift=9,relu_enable=False,relu6_enable=False,
                   input_addr=0x101,output_addr=0x10001,weight_addr=0x20003,bias_addr=0x30000)
        x=rng.integers(-128,128,(ci,h,w),dtype=np.int8)
        wt=rng.integers(-128,128,(co,1 if op=='depthwise' else ci,k,k),dtype=np.int8)
        bias=rng.integers(-2000,2001,co,dtype=np.int32)
        segments=[(0x101,x.tobytes()),(0x20003,wt.tobytes()),(0x30000,bias.astype('<i4').tobytes())]
        memory=bytearray([0xa5])*262144
        for addr,data in segments:memory[addr:addr+len(data)]=data
        y=execute(memory,layer)
        source=OUT/f'{name}.memh';target=OUT/f'{name}.hex'
        write_memh(source,segments);write_golden(target,y)
        lines.append(task_line(source.as_posix(),name,layer,target.as_posix()))
        manifest.append(dict(**layer,shape=list(y.shape)))
    (OUT/'tasks.txt').write_text(str(len(lines))+'\n'+'\n'.join(lines)+'\n',encoding='ascii')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Generated seven tile-boundary convolution cases')
if __name__=='__main__':main()
