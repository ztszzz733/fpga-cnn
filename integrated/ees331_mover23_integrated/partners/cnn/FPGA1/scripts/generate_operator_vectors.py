"""Deterministic mixed-unit queues; independent Python integer golden per task."""
from pathlib import Path
import json, struct
import numpy as np
from reference import execute, write_golden, output_shape
from pack_queue import pack
ROOT=Path(__file__).resolve().parents[1]
def generate():
    folder=ROOT/'build/operator_vectors';folder.mkdir(parents=True,exist_ok=True)
    mem=bytearray([0xa5])*524288;rng=np.random.default_rng(6102026);cursor=0x1000;layers=[]
    def reserve(data,unaligned=False):
        nonlocal cursor
        addr=(cursor+63)&~63
        if unaligned:addr+=1
        mem[addr:addr+len(data)]=data;cursor=addr+len(data)+64
        return addr
    def vector(op,ci=1,h=1,w=384,source=None,second=None,per_channel=False,wide=False,shift=0,params=None):
        x=dict(layer_id=len(layers),name=f'{len(layers)}_{op}',op=op,width=w,height=h,
               in_channels=ci,out_channels=ci,kernel=2 if op=='maxpool' else 0,
               stride=2 if op=='maxpool' else 0,padding=0,quant_shift=shift,
               per_channel=per_channel,input_int32=wide,round_nearest=params is not None)
        count=ci*h*w
        data=(rng.integers(-200000,200001,count,dtype=np.int32).astype('<i4') if wide else
              rng.integers(-128,128,count,dtype=np.int16).astype(np.int8)).tobytes()
        x['input_addr']=reserve(data,not wide) if source is None else source
        x['weight_addr']=0
        if op=='add':
            x['weight_addr']=reserve(rng.integers(-128,128,count,dtype=np.int16).astype(np.int8).tobytes(),True) if second is None else second
        if params is None:x['bias_addr']=0
        else:
            records=params if per_channel else [params]
            x['bias_addr']=reserve(b''.join(struct.pack('<iiIIiI',*record) for record in records))
        no=int(np.prod(output_shape(x)));x['output_addr']=reserve(bytes([0xa5])*no,True)
        layers.append(x);return x
    def mat(op,ci,co,n,source=None,wide_output=False):
        x=dict(layer_id=len(layers),name=f'{len(layers)}_{op}',op=op,width=n,height=1,
               in_channels=ci,out_channels=co,kernel=1,stride=1,padding=0,quant_shift=0 if wide_output else 4,output_int32=wide_output)
        x['input_addr']=reserve(rng.integers(-16,17,ci*n,dtype=np.int8).tobytes(),True) if source is None else source
        x['weight_addr']=reserve(rng.integers(-7,8,co*ci,dtype=np.int8).tobytes(),True)
        x['bias_addr']=reserve(rng.integers(-200,201,co,dtype=np.int32).astype('<i4').tobytes())
        x['output_addr']=reserve(bytes([0xa5])*(co*n)*(4 if wide_output else 1),not wide_output)
        layers.append(x);return x
    a=vector('relu')
    vector('relu',w=17)  # blocked unit; independent younger ADD must bypass it
    vector('add',ci=2,w=192,per_channel=True,params=[(3,5,2,3,-4,96),(7,1,3,1,5,96)])
    vector('prelu',ci=3,w=128,per_channel=True,params=[(1,1,2,0,0,96),(3,1,3,0,0,96),(-1,1,1,0,0,96)])
    vector('relu6',w=384,params=(1,1,0,0,0,47))
    vector('maxpool',ci=2,h=25,w=27)
    vector('requant',ci=3,w=128,wide=True,per_channel=True,
           params=[(13,1,12,0,3,96),(-7,1,11,0,-5,96),(31,1,10,0,0,96)])
    mat('conv',9,2,65)
    mat('matmul',13,9,11)
    # Dependent pipeline, different engine types, with a saved skip branch.
    c=mat('conv',3,4,8)
    r=vector('relu',ci=4,w=8,source=c['output_addr'])
    d=vector('add',ci=4,w=8,source=r['output_addr'],second=c['output_addr'])
    p=vector('prelu',ci=4,w=8,source=d['output_addr'],params=(1,1,2,0,0,96))
    final=mat('matmul',32,128,1,p['output_addr'])
    vector('relu6',ci=128,w=1,source=final['output_addr'])
    wide=mat('matmul',13,128,1,wide_output=True)
    vector('requant',ci=128,w=1,source=wide['output_addr'],wide=True,params=(7,1,5,0,2,96))
    (folder/'ram_init.bin').write_bytes(mem)
    actual=mem.copy()
    for i,x in enumerate(layers):write_golden(folder/f'layer_{i:03d}.golden.hex',execute(actual,x))
    (folder/'layer_config.json').write_text(json.dumps(dict(layers=layers),indent=2),encoding='utf-8')
    (folder/'final_ram.bin').write_bytes(actual)
    (folder/'features.golden.bin').write_bytes(actual[layers[-1]['output_addr']:layers[-1]['output_addr']+128])
    pack(folder,0x70000)
    return folder
if __name__=='__main__':print(generate())
