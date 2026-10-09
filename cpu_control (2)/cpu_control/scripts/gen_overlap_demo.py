"""Independent integer oracle, guarded data and real RV32I multi-task firmware."""
from pathlib import Path
import json
import random
import struct
import zlib
from gen_autoload_demo import Program

BASE, SIZE = 0x100, 8192


def generate(out, seed=1):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    image = bytearray([0xa5] * SIZE)
    golden = bytearray(image)
    cursor = 0x400
    tasks, descriptions = [], []

    def allocate(data, align=4, skew=0):
        nonlocal cursor
        cursor = (cursor + 15) & ~15
        address = cursor + skew
        assert address % align == 0
        offset = address - BASE
        image[offset:offset + len(data)] = data
        golden[offset:offset + len(data)] = data
        cursor = address + len(data) + 8
        return address

    def ints(values):
        return bytes(x & 255 for x in values)

    def samples(n):
        return [rng.randrange(-5, 6) for _ in range(n)]

    def read8(address, n):
        return [x if x < 128 else x - 256 for x in golden[address-BASE:address-BASE+n]]

    def write(address, values, wide=False):
        data = b''.join(struct.pack('<i', x) for x in values) if wide else ints(values)
        golden[address-BASE:address-BASE+len(data)] = data

    def clamp(x):
        return max(-128, min(127, x))

    def task(name, op, ia, oa, wa, ba, h, w, ci, co, lp):
        tasks.append((0x100 | op, ia, oa, wa, ba, h << 16 | w, co << 16 | ci, lp))
        descriptions.append({'id': len(tasks)-1, 'name': name, 'opcode': op,
                             'input': ia, 'output': oa, 'shape': [h, w, ci, co]})

    def conv(name, h, w, ci, co, kernel=1, pad=0, dw=False, wide=False, matrix=False):
        inputs, weights = samples(h*w*ci), samples(co*(1 if dw else ci)*kernel*kernel)
        biases = [rng.randrange(-3, 4) for _ in range(co)]
        ia = allocate(ints(inputs), align=1, skew=1)
        wa = allocate(ints(weights), align=1, skew=3)
        ba = allocate(b''.join(struct.pack('<i', x) for x in biases))
        oh, ow = h+2*pad-kernel+1, w+2*pad-kernel+1
        oa = allocate(bytes([0xa5] * (oh*ow*co*(4 if wide else 1))), align=4 if wide else 1, skew=0 if wide else 1)
        values = []
        for oc in range(co):
            for y in range(oh):
                for x in range(ow):
                    total = biases[oc]
                    for ic in ([oc] if dw else range(ci)):
                        for ky in range(kernel):
                            for kx in range(kernel):
                                iy, ix = y+ky-pad, x+kx-pad
                                if 0 <= iy < h and 0 <= ix < w:
                                    wi = ((oc*(1 if dw else ci)+(0 if dw else ic))*kernel+ky)*kernel+kx
                                    total += inputs[(ic*h+iy)*w+ix]*weights[wi]
                    values.append(total if wide else clamp(total))
        lp = kernel | 1 << 4 | pad << 8 | (int(wide) << 23)
        task(name, 9 if matrix else 1 if dw else 0, ia, oa, wa, ba, h, w, ci, co, lp)
        write(oa, values, wide)
        return oa, oh, ow, co

    def vector(name, op, n=32, source=None, dest=None, second=None, wide=False, h=1, channels=1):
        if source is None:
            values = samples(n)
            source = allocate(b''.join(struct.pack('<i', x*100) for x in values) if wide else ints(values))
        a = list(struct.unpack('<'+'i'*n, golden[source-BASE:source-BASE+4*n])) if wide else read8(source,n)
        wa, ba, lp = 0, 0, (1 << 20 if wide else 0)
        if op==3:
            wa = second if second is not None else allocate(ints(samples(n)))
            b = read8(wa,n)
            result = [clamp(x+y) for x,y in zip(a,b)]
        elif op==7:
            ba=allocate(struct.pack('<6i',1,1,2,0,0,96))
            result=[x if x>=0 else x>>2 for x in a]
        elif op==10:
            ba=allocate(struct.pack('<6i',3,1,2,0,-1,96))
            result=[clamp((x*3>>2)-1) for x in a]
        elif op==8:
            width=n//h//channels
            lp=0x22
            result=[max(a[(c*h+y+dy)*width+x+dx] for dy in range(2) for dx in range(2))
                    for c in range(channels) for y in range(0,h-1,2) for x in range(0,width-1,2)]
        else:
            result=[min(96,max(0,x)) if op==2 else max(0,x) for x in a]
        dest=dest if dest is not None else allocate(bytes([0xa5]*len(result)),align=1,skew=1)
        task(name,op,source,dest,wa,ba,h,n//h//channels,channels,channels,lp)
        write(dest,result)
        return dest

    first=conv('conv1x1_tail_reduction',3,5,9,3)
    second=conv('conv3x3_int32',3,5,3,3,kernel=3,pad=1,wide=True)
    relu=vector('relu_after_conv_RAW',6,n=45,source=first[0],h=3,channels=3)
    vector('independent_add',3)
    vector('independent_prelu',7)
    conv('depthwise3x3',4,5,2,2,kernel=3,pad=1,dw=True)
    vector('requant_after_conv_RAW',10,n=45,source=second[0],wide=True,h=3,channels=3)
    vector('maxpool2x2',8,n=16,h=4)
    vector('independent_relu6',2)
    vector('independent_relu',6)
    conv('depthwise7x7',3,3,1,1,kernel=7,pad=3,dw=True)
    conv('matmul_9x9x11',1,11,9,9,matrix=True)
    vector('add_after_relu_RAW',3,n=45,source=relu,second=relu,h=3,channels=3)
    vector('independent_int32_requant',10,wide=True)
    hazard_input=allocate(ints(samples(64)))
    z=vector('hazard_original_read',6,n=64,source=hazard_input)
    vector('hazard_consume_before_overwrite',2,n=64,source=z)
    vector('hazard_WAR_input_overwrite',7,n=64,dest=hazard_input)
    vector('hazard_WAW_output_overwrite',3,n=64,dest=z)
    conv('store_overlap_wide_output',1,64,1,8)
    queue=0x100
    assert len(tasks)*32 <= 0x300 and cursor <= BASE+SIZE
    for i, words in enumerate(tasks):
        struct.pack_into('<8I', image, queue-BASE+i*32, *words)
        struct.pack_into('<8I', golden, queue-BASE+i*32, *words)
    checksum=sum(struct.unpack('<'+'I'*(SIZE//4),golden)) & 0xffffffff
    p=Program()
    p.li(1,0x40000000);p.li(2,0x40);p.li(3,0x80)
    p.sw(3,0,8);p.sw(3,0,16) # finish mailbox and contention read word
    p.li(4,1);p.sw(2,4);p.li(6,4000000)
    p.label('load_poll');p.lw(4,2,4);p.i(7,5,4,1,'load complete')
    p.branch(1,5,0,'load_done');p.i(0,6,6,-1,'timeout count');p.branch(1,6,0,'load_poll');p.jump('fail')
    p.label('load_done');p.i(7,7,4,2,'load error');p.sw(2,0);p.branch(1,7,0,'fail')
    p.label('ack_poll');p.lw(4,2,4);p.branch(1,4,0,'ack_poll')
    p.li(4,queue);p.sw(1,4,8);p.li(4,len(tasks));p.sw(1,4,24);p.li(4,0x3d);p.sw(1,4)
    p.li(6,4000000)
    p.label('cnn_poll');p.lw(8,3,16);p.lw(4,1,4);p.i(7,5,4,4,'CNN error');p.branch(1,5,0,'fail')
    p.i(7,5,4,2,'CNN done');p.branch(1,5,0,'verify');p.i(0,6,6,-1,'timeout count');p.branch(1,6,0,'cnn_poll');p.jump('fail')
    p.label('verify');p.li(10,BASE);p.li(11,SIZE//4);p.li(12,0)
    p.label('checksum');p.lw(13,10);p.emit((13<<20)|(12<<15)|(12<<7)|0x33,'add x12,x12,x13')
    p.i(0,10,10,4,'next word');p.i(0,11,11,-1,'count');p.branch(1,11,0,'checksum')
    p.li(14,checksum);p.branch(1,12,14,'fail');p.sw(3,12);p.li(4,0x600d);p.sw(3,4,8);p.jump('halt')
    p.label('fail');p.li(4,0xdead0001);p.sw(3,4,8)
    p.label('halt');p.emit(0x6f,'halt');p.resolve()
    assert len(p.code)<=1024
    (out/'program.mem').write_text(''.join(f'{w:08x}\n' for w,_ in p.code)+('00000013\n'*(1024-len(p.code))))
    (out/'program.lst').write_text('\n'.join(f'{i*4:04x} {w:08x} {s}' for i,(w,s) in enumerate(p.code)))
    (out/'external.mem').write_text(''.join(f'{x:02x}\n' for x in image))
    (out/'expected.mem').write_text(''.join(f'{x:08x}\n' for x in struct.unpack('<'+'I'*(SIZE//4),golden)))
    crc=zlib.crc32(image)
    (out/'overlap_vectors.svh').write_text(f'localparam integer LOAD_BYTES={SIZE}, TASKS={len(tasks)};\nlocalparam [31:0] DEMO_CRC=32\'h{crc:08x};\n')
    manifest={'seed':seed,'tasks':descriptions,'load_bytes':SIZE,'used_end':cursor,'queue':queue,
              'crc32':f'{crc:08x}','expected_checksum':f'{checksum:08x}', 'instruction_count':len(p.code)}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    generate(Path(__file__).resolve().parents[1]/'firmware/overlap_demo')
