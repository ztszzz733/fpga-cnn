"""Independent and dependent jobs; sequential integer reference remains the oracle."""
from pathlib import Path
import json
import numpy as np
from reference import execute, output_shape, write_golden
from pack_queue import pack

ROOT=Path(__file__).resolve().parents[1]

def generate(case='mixed'):
    folder=ROOT/'build'/'concurrent_vectors'/case;folder.mkdir(parents=True,exist_ok=True)
    mem=bytearray([0xa5])*262144;rng=np.random.default_rng(2909);layers=[]
    wa=0x20000;ba=0x28000
    def layer(op,ia,oa,ci,co,h,w,k=1,s=1,p=0,initialize=True):
        nonlocal wa,ba
        x=dict(layer_id=len(layers),name=f'job{len(layers)}',op=op,input_addr=ia,output_addr=oa,
               weight_addr=wa,bias_addr=ba,width=w,height=h,in_channels=ci,out_channels=co,
               kernel=k,stride=s,padding=p,quant_shift=3)
        if initialize:
            image=rng.integers(-9,10,(ci,h,w),dtype=np.int8);mem[ia:ia+image.size]=image.tobytes()
        weight=rng.integers(-3,4,(co,1 if op=='depthwise' else ci,k,k),dtype=np.int8)
        bias=rng.integers(-100,101,co,dtype=np.int32).astype('<i4')
        mem[wa:wa+weight.size]=weight.tobytes();mem[ba:ba+bias.nbytes]=bias.tobytes()
        wa=(wa+weight.size+3)&~3;ba+=bias.nbytes;layers.append(x)
        return x
    if case=='mixed':
        layer('conv',0x101,0x4001,9,2,1,65)
        layer('conv',0x1001,0x6001,3,9,5,5,3,1,1)
        layer('conv',0x4001,0x8001,2,3,1,65,initialize=False)
        layer('depthwise',0x6001,0xa001,9,9,5,5,3,1,1,False)
        layer('depthwise',0x2001,0xc001,2,2,7,7,7)
        layer('conv',0x1001,0xd001,3,2,5,5,3,2,1,False)
        layer('conv',0xc001,0xe001,2,128,1,1,initialize=False)
    elif case in ('raw','war','waw','word'):
        layer('conv',0x101,0x4001,3,2,1,17)
        if case=='raw':layer('conv',0x4001,0x6001,2,3,1,17,initialize=False)
        elif case=='war':layer('conv',0x1001,0x101,3,3,1,17)
        elif case=='waw':layer('conv',0x1001,0x4001,3,3,1,17)
        else:
            # Last byte of task0 output and first of task1 share a RAM word.
            layer('conv',0x1001,0x4023,3,1,1,1)
    else:raise ValueError(case)
    (folder/'ram_init.bin').write_bytes(mem)
    (folder/'layer_config.json').write_text(json.dumps(dict(profile='streaming_shared',layers=layers),indent=2),encoding='utf-8')
    actual=mem.copy()
    for i,x in enumerate(layers):write_golden(folder/f'layer_{i:03d}.golden.hex',execute(actual,x))
    (folder/'final_ram.bin').write_bytes(actual)
    pack(folder,0x30000)
    return folder

if __name__=='__main__':
    for case in ('mixed','raw','war','waw','word'):print(generate(case))
