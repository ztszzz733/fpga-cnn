"""Independent CHW integer reference; no use of RTL counters or internal signals."""
from pathlib import Path
import json
import numpy as np

OPS = {"conv":0,"depthwise":1,"relu6":2,"add":3,"copy":4,"final_output":5}


def address(x):
    return int(x,0) if isinstance(x,str) else int(x)


def int32(x):
    return ((np.asarray(x,dtype=np.int64)+(1<<31)) & 0xffffffff)-(1<<31)


def requantize(value, shift=0, relu=False, relu6=False, relu6_max=96):
    shifted=np.asarray(value,dtype=np.int64) >> min(int(shift),63)
    if relu or relu6:
        shifted=np.maximum(shifted,0)
    if relu6:
        shifted=np.minimum(shifted,relu6_max)
    return np.clip(shifted,-128,127).astype(np.int8)


def convolution(x,weight,bias,stride=1,padding=0,depthwise=False):
    """Weights [OC,IC,K,K] or [C,1,K,K]. Cross-correlation, no kernel flip."""
    k=weight.shape[-1]
    padded=np.pad(np.asarray(x,dtype=np.int64),((0,0),(padding,padding),(padding,padding)))
    windows=np.lib.stride_tricks.sliding_window_view(padded,(k,k),axis=(1,2))[:,::stride,::stride,:,:]
    if depthwise:
        assert weight.shape[:2]==(x.shape[0],1)
        out=np.einsum('ikl,iyxkl->iyx',weight[:,0].astype(np.int64),windows,optimize=False)
    else:
        out=np.stack([np.einsum('ikl,iyxkl->yx',w.astype(np.int64),windows,optimize=False) for w in weight])
    return int32(out+np.asarray(bias,dtype=np.int64)[:,None,None])


def output_shape(layer):
    c,h,w=int(layer['out_channels']),int(layer['height']),int(layer['width'])
    if layer['op'] in ('conv','depthwise'):
        k,s,p=layer['kernel'],layer['stride'],layer['padding']
        h,w=(h+2*p-k)//s+1,(w+2*p-k)//s+1
    return c,h,w


def execute(memory,layer,relu6_max=96):
    ci,h,w=layer['in_channels'],layer['height'],layer['width']
    x=np.frombuffer(memory,dtype=np.int8,count=ci*h*w,offset=address(layer['input_addr'])).reshape(ci,h,w).copy()
    op=layer['op']
    if op in ('conv','depthwise'):
        co,k=layer['out_channels'],layer['kernel']
        channels=1 if op=='depthwise' else ci
        weight=np.frombuffer(memory,dtype=np.int8,count=co*channels*k*k,offset=address(layer['weight_addr'])).reshape(co,channels,k,k)
        bias=np.frombuffer(memory,dtype='<i4',count=co,offset=address(layer['bias_addr']))
        raw=convolution(x,weight,bias,layer['stride'],layer['padding'],op=='depthwise')
    elif op=='add':
        b=np.frombuffer(memory,dtype=np.int8,count=x.size,offset=address(layer['weight_addr'])).reshape(x.shape)
        raw=x.astype(np.int64)+b.astype(np.int64)
    else:
        raw=x
    if op in ('copy','final_output'):
        y=x.copy()
    else:
        y=requantize(raw,layer.get('quant_shift',0),layer.get('relu_enable',False),
                     layer.get('relu6_enable',False) or op=='relu6',relu6_max)
    assert y.shape==output_shape(layer),(layer,y.shape)
    dst=address(layer['output_addr'])
    memory[dst:dst+y.size]=y.tobytes()
    return y


def layer_param(layer):
    return (int(layer.get('kernel',0)) | int(layer.get('stride',0))<<4 | int(layer.get('padding',0))<<8 |
            int(layer.get('quant_shift',0))<<12 | int(layer.get('relu_enable',False))<<20 |
            int(layer.get('relu6_enable',False))<<21 | int(layer.get('residual_enable',False))<<22)


def write_memh(path,segments):
    with Path(path).open('w',encoding='ascii') as f:
        for addr,data in segments:
            f.write(f'@{addr:08x}\n')
            f.write('\n'.join(f'{int(b)&255:02x}' for b in data)+'\n')


def write_golden(path,array):
    Path(path).write_text('\n'.join(f'{int(v)&255:02x}' for v in np.asarray(array).flat)+'\n',encoding='ascii')


def task_line(init,name,layer,golden):
    ci,co,h,w=[int(layer[k]) for k in ('in_channels','out_channels','height','width')]
    count=int(np.prod(output_shape(layer)))
    fields=[OPS[layer['op']],*[address(layer.get(k,0)) for k in ('input_addr','output_addr','weight_addr','bias_addr')],
            h<<16|w,co<<16|ci,layer_param(layer),count]
    return f'{init} {name} '+ ' '.join(f'{v:x}' for v in fields)+f' {golden}'


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('export_dir');args=parser.parse_args()
    folder=Path(args.export_dir)
    config=json.loads((folder/'layer_config.json').read_text())
    memory=bytearray((folder/'ram_init.bin').read_bytes())
    for layer in config['layers']:
        y=execute(memory,layer,config['relu6_max'])
        print(layer['layer_id'],layer['name'],layer['op'],list(y.shape),y.reshape(-1)[:8].tolist())
        write_golden(folder/f"layer_{layer['layer_id']:03d}.golden.hex",y)
    (folder/'features.bin').write_bytes(y.tobytes())
