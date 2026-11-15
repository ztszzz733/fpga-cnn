"""Deterministic signed INT8 convolution oracle; no accelerator model used.

NEureka bit packing / register definitions follow the pinned Apache-2.0
pulp-nnx NeurekaMemoryLayout.py and neureka_task.c (see third_party manifest).
"""
from pathlib import Path
import argparse, json, struct, random
from gen_autoload_demo import Program

def generate(folder, size=18, ci=3, co=8, seed=17, repeats=1):
    if not (4<=size<=1024 and 1<=ci<=32 and 1<=co<=32 and 1<=repeats<=24):
        raise ValueError('This benchmark driver supports size 4..1024, CI/CO 1..32 and repeats 1..24')
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed); h=w=size; oh=ow=size-2; shift=5
    # RGB pixels normalized by >>1 into the common supported input domain.
    # This pinned RTL uses unsigned activations; bit26 is broadcast, NOT sign.
    x=[rng.randrange(0,128) for _ in range(h*w*ci)]
    weight=[rng.randrange(-3,4) for _ in range(co*ci*9)]
    conv=[]
    for oc in range(co):
        for y in range(oh):
            for xx in range(ow):
                acc=0
                for ic in range(ci):
                    for ky in range(3):
                        for kx in range(3):
                            acc+=x[(ic*h+y+ky)*w+xx+kx]*weight[(oc*ci+ic)*9+ky*3+kx]
                conv.append(max(-128,min(127,acc>>shift)))
    relu=[max(0,v) for v in conv]
    pool=[max(relu[(c*oh+y+dy)*ow+xx+dx] for dy in range(2) for dx in range(2))
          for c in range(co) for y in range(0,oh-1,2) for xx in range(0,ow-1,2)]
    capacities=[]
    for new in (False,True):
        case=folder/('neureka' if new else 'baseline');case.mkdir(exist_ok=True)
        mem=bytearray([0xa5]*0x1000);cursor=0x1000
        def alloc(data):
            nonlocal cursor
            a=(cursor+63)&~63;cursor=a+len(data)+64
            mem.extend(bytes([0xa5])*(cursor-len(mem)));mem[a:a+len(data)]=data
            return a
        def bs(v):return bytes(a&255 for a in v)
        ia=alloc(bs(x));wa=alloc(bs(weight));ba=alloc(bytes(co*4));oa=alloc(bytes([0xa5])*len(conv))
        ra=alloc(bytes([0xa5])*len(relu));pa=alloc(bytes([0xa5])*len(pool));tasks=[];names=[]
        def task(name,op,i,o=0,ww=0,b=0,hh=1,wwidth=1,cin=1,cout=1,lp=0):
            tasks.append([0x100|op,i,o,ww,b,hh<<16|wwidth,cout<<16|cin,lp]);names.append(name)
        if new:
            xi=alloc(bytes(len(x)));yo=alloc(bytes(len(conv)))
            packed=bytearray()
            for oc in range(co):
                for cm in range((ci+31)//32):
                    for bit in range(8):
                        for k in range(9):
                            bits=0
                            for minor in range(32):
                                ic=cm*32+minor
                                value=(weight[(oc*ci+ic)*9+k]+128) if ic<ci else 0
                                bits|=((value>>bit)&1)<<minor
                            packed.extend(struct.pack('<I',bits))
            nw=alloc(packed);scale=alloc(struct.pack('<'+'I'*co,*([1]*co)))
            rem=lambda v,t:(v-1)%t+1
            cfg=[nw,xi,yo,scale,0,0,ci,w*ci,0,32,co,ow*co,36,36*8*((ci+31)//32),0,
                 rem(co,32)<<16|rem(ci,32),rem(oh,4)<<16|rem(ow,4),
                 (rem(oh,4)+2)<<16|(rem(ow,4)+2),((co+31)//32)<<16|((ci+31)//32),
                 ((oh+3)//4)<<16|((ow+3)//4),0,0xffffff80,0,
                 # Prefetch sends weights through logical weight streamer 1.
                 # CONF0[9] must select it; both logical streams share our SRAM.
                 (1<<23)|(shift<<16)|(2<<12)|(1<<11)|(1<<10)|(1<<9)|(1<<4)|7]
            config=alloc(struct.pack('<24I',*cfg))
            task('CHW_to_HWC',12,ia,xi,hh=h,wwidth=w,cin=ci,cout=ci)
            task('NEureka_conv',11,config)
            task('HWC_to_CHW',12,yo,oa,hh=oh,wwidth=ow,cin=co,cout=co,lp=1)
        else:
            task('original_conv',0,ia,oa,wa,ba,h,w,ci,co,0x13|(shift<<12))
        task('ReLU',6,oa,ra,hh=oh,wwidth=ow,cin=co,cout=co)
        task('MaxPool2x2',8,ra,pa,hh=oh,wwidth=ow,cin=co,cout=co,lp=0x22)
        if repeats>1:
            tasks=tasks*repeats
            names=[f'{name}_run{r+1}' for r in range(repeats) for name in names]
        for i,t in enumerate(tasks):struct.pack_into('<8I',mem,0x100+i*32,*t)
        # Actual RV32I CPU programs the existing queue registers and polls status.
        p=Program();p.li(1,0x40000000);p.li(2,0x100);p.sw(1,2,8)
        p.li(2,len(tasks));p.sw(1,2,24);p.li(2,0x3d);p.sw(1,2)
        p.label('poll');p.lw(3,1,4);p.i(7,4,3,4,'error');p.branch(1,4,0,'error')
        p.i(7,4,3,2,'done');p.branch(0,4,0,'poll');p.li(3,0x600d);p.jump('finish')
        p.label('error');p.li(3,0xdead);p.label('finish');p.li(2,0x80);p.sw(2,3)
        p.label('halt');p.jump('halt');p.resolve()
        (case/'program.hex').write_text('\n'.join(f'{v:08x}' for v,_ in p.code)+'\n')
        (case/'program.asm').write_text('\n'.join(f'{i*4:04x}: {s}' for i,(_,s) in enumerate(p.code))+'\n')
        (case/'memory.bin').write_bytes(mem)
        (case/'golden.hex').write_text('\n'.join(f'{v&255:02x}' for v in conv+relu+pool)+'\n')
        sram=1
        while sram<len(mem):sram*=2
        capacities.append(sram)
        (case/'bench_config.hex').write_text('\n'.join(f'{v:08x}' for v in [len(mem),oa,ra,pa,len(conv),len(pool)])+'\n')
        (case/'workload.json').write_text(json.dumps(dict(size=size,ci=ci,co=co,kernel=3,shift=shift,seed=seed,
            tasks=names,descriptors=tasks,sram_bytes=sram,macs=oh*ow*ci*co*9,repeats=repeats),indent=2))
    # Both versions have exactly the same physical capacity/banks/latency.
    for name in ('baseline','neureka'):
        capacity=max(4*1024*1024,*capacities)
        path=folder/name/'bench.svh'
        path.write_text(f'localparam SRAM_BYTES={capacity};\n')
        path=folder/name/'workload.json';record=json.loads(path.read_text())
        record['sram_bytes']=capacity;path.write_text(json.dumps(record,indent=2))
    return folder

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--size',type=int,default=18)
    p.add_argument('--ci',type=int,default=3);p.add_argument('--co',type=int,default=8)
    a=p.parse_args();generate(a.folder,a.size,a.ci,a.co)
