"""HWC row tiles with 3x3 halo; independent integer oracle and real RV32I mailbox firmware."""
import argparse,json,random,struct,hashlib
from pathlib import Path
from gen_autoload_demo import Program
ROOT=Path(__file__).resolve().parents[1]

def generate(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    h,w,ci,co,tile_h,shift=15,9,3,5,4,5
    oh,ow=h-2,w-2
    rng=random.Random(42)
    x=[rng.randrange(128) for _ in range(h*w*ci)]
    weights=[rng.randrange(-3,4) for _ in range(co*ci*9)]
    conv=[]
    for y in range(oh):
        for xx in range(ow):
            for oc in range(co):
                acc=sum(x[((y+ky)*w+xx+kx)*ci+ic]*weights[(oc*ci+ic)*9+ky*3+kx]
                        for ky in range(3) for kx in range(3) for ic in range(ci))
                conv.append(max(-128,min(127,acc>>shift)))
    golden=bytes((v if v>=0 else v//4)&255 for v in conv)
    mem=bytearray([0xa5]*0x40000)
    def put(a,data):mem[a:a+len(data)]=data
    put(0x2000,bytes(x))
    packed=bytearray()
    for oc in range(co):
        for bit in range(8):
            for k in range(9):
                bits=sum((((weights[(oc*ci+ic)*9+k]+128)>>bit)&1)<<ic for ic in range(ci))
                packed+=struct.pack('<I',bits)
    put(0x4000,packed);put(0x4800,struct.pack('<'+'I'*co,*([1]*co)))
    rem=lambda n,t:(n-1)%t+1
    tiles=[]
    for i,y in enumerate(range(0,oh,tile_h)):
        th=min(tile_h,oh-y);count=th*ow*co;config=0x1000+i*96;dst=0x12000+y*ow*co
        # Each tile reads th+2 input rows, retaining the 3x3 vertical halo.
        cfg=[0x4000,0x2000+y*w*ci,0,0x4800,0,0,ci,w*ci,0,32,co,ow*co,36,288,0,
             rem(co,32)<<16|rem(ci,32),rem(th,4)<<16|rem(ow,4),
             (rem(th,4)+2)<<16|(rem(ow,4)+2),1<<16|1,((th+3)//4)<<16|((ow+3)//4),
             0,0xffffff80,0,(1<<23)|(shift<<16)|(2<<12)|(1<<11)|(1<<10)|(1<<9)|(1<<4)|7]
        put(config,struct.pack('<24I',*cfg));put(0x100+i*16,struct.pack('<4I',config,dst,count,0))
        tiles.append(dict(row=y,rows=th,source=cfg[1],destination=dst,bytes=count,config=config,buffer=0x10000+(i%2)*0x1000))
    # Reuse the exact prior INT8/FP32 program binary, not prior simulation outputs.
    source=ROOT/'deliverables/hybrid_soc/tiny_chain/vector.bin'
    vector=source.read_bytes();assert len(vector)%4==0 and len(vector)<=16384
    put(0x20000,vector)
    p=Program();p.li(1,0x40000000);seq=0
    def transaction(cmd):
        nonlocal seq
        label='mb'+str(seq);seq+=1
        p.li(4,cmd);p.sw(1,4,8);p.label(label);p.lw(5,1,12)
        p.i(7,6,5,1,'busy');p.branch(1,6,0,label)
        p.i(7,6,5,4,'mailbox error');p.branch(1,6,0,'error')
    def wr(addr,data):
        p.li(2,addr);p.li(3,data);p.sw(1,2);p.sw(1,3,4);transaction(1)
    def rd(addr):
        p.li(2,addr);p.sw(1,2);transaction(2);p.lw(5,1,16)
    p.li(7,0x20000);p.li(8,0x40041000);p.li(9,len(vector))
    p.label('load_vector');p.lw(3,7);p.sw(1,8);p.sw(1,3,4);transaction(1)
    p.i(0,7,7,4,'next source');p.i(0,8,8,4,'next instruction');p.i(0,9,9,-4,'remaining');p.branch(1,9,0,'load_vector')
    for off,value in [(8,0x100),(12,len(tiles)),(16,0x10000),(20,0x11000),(24,0x400)]:wr(0x40000000+off,value)
    for job,serial in enumerate([1,0]):
        p.li(2,0x84);p.li(3,job+1);p.sw(2,3)
        wr(0x4000001c,serial);wr(0x40000000,1)
        p.label('wait_job'+str(job));rd(0x40000004)
        p.i(7,6,5,12,'pipeline/rejected fault');p.branch(1,6,0,'error')
        p.i(7,6,5,2,'done');p.branch(0,6,0,'wait_job'+str(job))
        for reg,offset in [(36,0),(40,4),(32,8)]:
            rd(0x40000000+reg);p.li(2,0xa0+job*16+offset);p.sw(2,5)
    p.li(3,0x600dcafe);p.jump('finish')
    p.label('error');p.li(3,0xdead0001)
    p.label('finish');p.li(2,0x80);p.sw(2,3);p.label('stop');p.jump('stop');p.resolve()
    words=[word for word,_ in p.code];assert len(words)<16384
    (out/'cpu.hex').write_text(''.join(f'{n:08x}\n' for n in words+[0x13]*(16384-len(words))))
    (out/'cpu.lst').write_text('\n'.join(f'{i*4:04x} {n:08x} {s}' for i,(n,s) in enumerate(p.code)))
    (out/'sram.hex').write_text(''.join(f'{n[0]:08x}\n' for n in struct.iter_unpack('<I',mem)))
    (out/'golden.hex').write_text(''.join(f'{b:02x}\n' for b in golden))
    (out/'golden.bin').write_bytes(golden)
    (out/'vector.bin').write_bytes(vector)
    (out/'vector.S').write_bytes((source.with_suffix('.S')).read_bytes())
    spec=dict(height=h,width=w,ci=ci,co=co,kernel=3,shift=shift,layout='HWC',output=0x12000,output_bytes=len(golden),
        buffers=[0x10000,0x11000],capacity=0x400,tiles=tiles,vector_sha256=hashlib.sha256(vector).hexdigest(),
        scope='unsigned activations 0..127; signed INT8 weights/output; INT8 PReLU alpha=1/4; serial then pipeline without reset')
    (out/'case.json').write_text(json.dumps(spec,indent=2));return spec
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);generate(ap.parse_args().output)
