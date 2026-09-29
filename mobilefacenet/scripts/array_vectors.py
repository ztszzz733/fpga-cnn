"""Shared deterministic Conv/DW-only queue for regression and timing waves."""
import json
from pathlib import Path
import numpy as np
from reference import execute, output_shape, write_golden
from pack_queue import pack


def generate_queue(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(915)
    initial=bytearray([0xa5])*262144
    image=rng.integers(-8,9,(3,13,13),dtype=np.int8)
    initial[0x101:0x101+image.size]=image.tobytes()
    specs=[('conv',2,3,2,1),('depthwise',2,3,1,1),('conv',4,1,1,0),
           ('depthwise',4,3,1,1),('conv',2,1,1,0),('conv',3,3,1,1),
           ('depthwise',3,7,1,0),('conv',16,1,1,0),('conv',128,1,1,0)]
    source=0x101;ci,h,w=image.shape;wa=0x8000;ba=0x10000;layers=[]
    for i,(op,co,k,stride,pad) in enumerate(specs):
        dst=0x18001 if i==len(specs)-1 else (0x3001 if source==0x1001 else 0x1001)
        layer=dict(layer_id=i,name=f'array_{i}_{op}',op=op,input_addr=source,output_addr=dst,
                   weight_addr=wa,bias_addr=ba,width=w,height=h,in_channels=ci,out_channels=co,
                   kernel=k,stride=stride,padding=pad,quant_shift=2,relu_enable=False,relu6_enable=False)
        weights=rng.integers(-3,4,(co,1 if op=='depthwise' else ci,k,k),dtype=np.int8)
        bias=rng.integers(-40,41,co,dtype=np.int32)
        initial[wa:wa+weights.size]=weights.tobytes();initial[ba:ba+bias.nbytes]=bias.astype('<i4').tobytes()
        wa+=weights.size;ba+=bias.nbytes;layers.append(layer)
        source=dst;ci,h,w=output_shape(layer)
    (folder/'ram_init.bin').write_bytes(initial)
    (folder/'layer_config.json').write_text(json.dumps({'profile':'queue_only_array','layers':layers},indent=2),encoding='utf-8')
    memory=initial.copy();results=[]
    for i,layer in enumerate(layers):
        y=execute(memory,layer);results.append(y.copy());write_golden(folder/f'layer_{i:03d}.golden.hex',y)
    (folder/'features.golden.bin').write_bytes(results[-1].tobytes())
    pack(folder,0x12000)
    return folder,layers,results
