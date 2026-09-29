"""Pack exported layer configurations into a RAM-resident task table (ABI v1)."""
from pathlib import Path
import argparse
import json
import struct
from reference import OPS, address, layer_param, output_shape, write_memh


def descriptor(layer):
    if layer['op'] not in ('conv','depthwise'):
        raise ValueError(f"Array-only hardware does not support {layer['op']}; only conv/depthwise are accepted")
    if layer_param(layer) & 0xfff00000:
        raise ValueError('Array-only hardware requires activation/residual/reserved flags [31:20] = 0')
    op=OPS[layer['op']]
    words=[0x100 | op, *[address(layer.get(k,0)) for k in ('input_addr','output_addr','weight_addr','bias_addr')],
           layer['height']<<16 | layer['width'], layer['out_channels']<<16 | layer['in_channels'],layer_param(layer)]
    return struct.pack('<8I',*words)


def pack(folder, base=None):
    folder=Path(folder).resolve()
    config=json.loads((folder/'layer_config.json').read_text(encoding='utf-8'))
    layers=config['layers']
    if not layers:raise ValueError('Queue must contain at least one task')
    memory=bytearray((folder/'ram_init.bin').read_bytes())
    spans=[]
    for x in layers:
        ni=x['in_channels']*x['height']*x['width']
        no=1
        for d in output_shape(x):no*=d
        spans.extend([(address(x['input_addr']),ni),(address(x['output_addr']),no)])
        if x['op'] in ('conv','depthwise'):
            nw=x['out_channels']*(x['in_channels'] if x['op']=='conv' else 1)*x['kernel']**2
            spans.extend([(address(x['weight_addr']),nw),(address(x['bias_addr']),4*x['out_channels'])])
        elif x['op']=='add':spans.append((address(x['weight_addr']),ni))
    if base is None:base=(max(a+n for a,n in spans)+31)&~31
    data=b''.join(descriptor(x) for x in layers)
    if base<0 or base%32 or base+len(data)>2**32:raise ValueError('Queue base must be 32-byte aligned with no 32-bit wrap')
    if any(base<a+n and a<base+len(data) for a,n in spans):raise ValueError('Task table overlaps tensor/parameter memory')
    needed=base+len(data)
    size=max(len(memory),1<<(needed-1).bit_length())
    memory.extend(bytes([0xa5])*(size-len(memory)))
    memory[base:base+len(data)]=data
    (folder/'queue.bin').write_bytes(data)
    (folder/'queue_ram.bin').write_bytes(memory)
    write_memh(folder/'queue_ram.hex',[(0,memory)])
    meta=dict(abi_version=1,descriptor_bytes=32,queue_base=base,task_count=len(layers),ram_bytes=size,
              control_start=61,mmio_input_addr=base,mmio_feature_size=len(layers),
              final_output_addr=address(layers[-1]['output_addr']),
              note='Immutable finite queue. CPU writes INPUT_ADDR, FEATURE_SIZE, then CONTROL=0x3d. DONE is for the whole queue.')
    (folder/'queue_config.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    (folder/'meta.hex').write_text(f'{base:08x}\n{len(layers):08x}\n',encoding='ascii')
    checks=[str(len(layers))]
    for i,x in enumerate(layers):
        n=1
        for d in output_shape(x):n*=d
        golden=(folder/f'layer_{i:03d}.golden.hex').as_posix()
        if any(c.isspace() for c in golden):raise ValueError('Testbench paths must not contain whitespace')
        checks.append(f"{address(x['output_addr']):x} {n:x} {golden}")
    (folder/'queue_checks.txt').write_text('\n'.join(checks)+'\n',encoding='ascii')
    return meta


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('export_dir')
    p.add_argument('--base',type=lambda s:int(s,0));args=p.parse_args()
    result=pack(args.export_dir,args.base)
    print(json.dumps(result,indent=2))
