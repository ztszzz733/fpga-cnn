"""Small nine-task queue spanning all six opcodes, two full batches plus a tail."""
from pathlib import Path
import json
import numpy as np
from reference import execute,write_golden
from pack_queue import pack

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'queue_vectors'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(915)
    initial=bytearray([0xa5])*262144
    x=rng.integers(-8,9,(2,7,7),dtype=np.int8)
    initial[0x101:0x101+x.size]=x.tobytes()
    layers=[];source=0x101;ci=2;h=w=7;wa=0x8000;ba=0x10000
    definitions=[('conv',2,1,0,0x1001),('copy',2,0,0,0x2001),('depthwise',2,3,1,0x3001),
                 ('add',2,0,0,0x1001),('relu6',2,0,0,0x3001),('conv',3,3,1,0x1001),
                 ('depthwise',3,7,0,0x3001),('conv',128,1,0,0x1001),('final_output',128,0,0,0x18001)]
    for i,(op,co,k,p,dst) in enumerate(definitions):
        layer=dict(layer_id=i,name=f'queue_{i}_{op}',op=op,input_addr=source,output_addr=dst,
                   weight_addr=0x2001 if op=='add' else wa,bias_addr=ba,width=w,height=h,
                   in_channels=ci,out_channels=co,kernel=k,stride=1 if k else 0,padding=p,
                   quant_shift=2 if k else 0,relu_enable=False,relu6_enable=False)
        if k:
            weight=rng.integers(-3,4,(co,1 if op=='depthwise' else ci,k,k),dtype=np.int8)
            bias=rng.integers(-40,41,co,dtype=np.int32)
            initial[wa:wa+weight.size]=weight.tobytes();initial[ba:ba+bias.nbytes]=bias.astype('<i4').tobytes()
            wa+=weight.size;ba+=bias.nbytes
        layers.append(layer)
        if k:h,w=h+2*p-k+1,w+2*p-k+1
        if op!='copy':source=dst;ci=co
    (OUT/'ram_init.bin').write_bytes(initial)
    (OUT/'layer_config.json').write_text(json.dumps(dict(layers=layers,relu6_max=96),indent=2),encoding='utf-8')
    memory=initial.copy()
    for i,layer in enumerate(layers):
        y=execute(memory,layer);write_golden(OUT/f'layer_{i:03}.golden.hex',y)
    (OUT/'features.golden.bin').write_bytes(y.tobytes())
    meta=pack(OUT,0x12000)
    (OUT/'meta.hex').write_text(f"{meta['queue_base']:08x}\n{meta['task_count']:08x}\n",encoding='ascii')
    print('Generated nine-task queue: Conv1, COPY, DW3, ADD, ReLU6, Conv3, DW7, Conv1, FINAL128')


if __name__=='__main__':main()
