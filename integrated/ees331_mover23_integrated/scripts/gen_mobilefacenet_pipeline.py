"""Two real face ROIs, fixed shared quantization, halo dependencies and slots.

Generate full-layer integer goldens first, then independently tile the register
images. No runtime golden injection; initial output planes contain only 0xa5.
"""
import argparse,contextlib,hashlib,json,struct
from pathlib import Path
from gen_mobilefacenet_chain import ROOT,generate

def main():
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
    reports=[];mems=[];golds=[]
    with (out/'generation.log').open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
        scales=None
        for frame in range(2):
            folder=out/f'reference_frame{frame}'
            r=generate(folder,Path(f'D:/code/facemodel/person_{frame+1}.jpg'),scales)
            if scales is None:scales=[v['output_scale'] for v in r['layers']]
            reports.append(r);mems.append((folder/'memory.bin').read_bytes());golds.append((folder/'golden.bin').read_bytes())
    mem=bytearray([0xa5]*262144);gold=bytearray(mem)
    offsets=[0,0x20000]
    for frame,r in enumerate(reports):
        off=offsets[frame];size=r['bytes_used'];mem[off:off+size]=mems[frame][:size];gold[off:off+size]=golds[frame][:size]
    nodes=[];lookup={}
    # Interleave frame submissions so the test exercises both frame tags.
    for layer,rows in enumerate([6,4,4]):
        for y in range(0,rows,2):
            for frame in range(2):
                lookup[frame,layer,y//2]=len(nodes)
                nodes.append(dict(frame=frame,layer=layer,y=y,rows=min(2,rows-y)))
    cfg_cursor=0x34000;scratch=[0x38000,0x3a000]
    for idx,node in enumerate(nodes):
        f,l,y,rows=node['frame'],node['layer'],node['y'],node['rows'];r=reports[f];off=offsets[f]
        lr=r['layers'][l];ow=lr['output_shape'][1];ci=lr['input_shape'][2];iw=lr['input_shape'][1];step=lr['stride'];k=lr['kernel'];co=64
        dependencies=[]
        if l:
            for source_y in range(y,y+rows+k-1):
                dep=lookup[f,l-1,source_y//2]
                if dep not in dependencies:dependencies.append(dep)
        deps=sum(1<<v for v in dependencies);base=cfg_cursor
        for slot in range(2):
            for group in range(2):
                original=r['jobs'][l*3+group][1]
                cfg=list(struct.unpack_from('<24I',mems[f],original))
                cfg[0]+=off;cfg[1]+=off+y*step*iw*ci;cfg[2]=scratch[slot]+group*32*4
                dh=(rows-1)*step+1;dw=(ow-1)*step+1;rem=lambda v:(v-1)%4+1
                cfg[16]=rem(dh)<<16|rem(dw)
                cfg[17]=(rem(dh)+k-1)<<16|(rem(dw)+k-1)
                cfg[19]=((dh+3)//4)<<16|((dw+3)//4)
                struct.pack_into('<24I',mem,cfg_cursor,*cfg);cfg_cursor+=96
        assert cfg_cursor<scratch[0]
        node.update(id=idx,deps=deps,dependency_nodes=dependencies,config_base=base,
                    parameters=lr['parameters_address']+off,destination=lr['output_address']+off+y*ow*co,
                    count=rows*ow*co,channels=co,tag=f<<16|l<<8|y//2,
                    raw_golden=lr['raw_address']+off+y*ow*co*4)
    words=[[n['deps'],n['config_base'],n['parameters'],n['destination'],n['count'],n['channels'],n['tag'],n['layer'],n['raw_golden'],n['y']] for n in nodes]
    (out/'nodes.hex').write_text(''.join(f'{v:08x}\n' for row in words for v in row))
    (out/'meta.hex').write_text(f'{len(nodes):08x}\n')
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes(gold)
    report=dict(nodes=nodes,frames=[dict(image=r['image'],sha256=r['image_sha256'],layers=r['layers'],offset=off) for r,off in zip(reports,offsets)],
                quantization_scales=scales,quantization_source='frame0 local diagnostic ranges, frozen and reused for frame1; not accuracy-calibrated',
                scratch=scratch,scratch_capacity=8192,full_network=False,uart=False,cpu=False,input_preloaded=True,
                activation_storage='Separate retained planes per frame/layer; scratch reused, no circular input line buffer',
                source_scripts={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in ['gen_mobilefacenet_chain.py','gen_mobilefacenet_pipeline.py']})
    (out/'workload.json').write_text(json.dumps(report,indent=2));print(f'Generated {len(nodes)} dependency nodes, 2 frames, 3 layers, shared quantization')
if __name__=='__main__':main()
