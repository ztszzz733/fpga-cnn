"""Four distinct UART frames, two input/output slots, true INT8 scalar oracle."""
import json, struct, zlib
from pathlib import Path
from gen_neureka_pipeline import generate as generate_tiles


def generate(out):
    out=Path(out);spec=generate_tiles(out)
    words=[int(x,16) for x in (out/'sram.hex').read_text().split()]
    mem=bytearray(struct.pack('<65536I',*words))
    original=bytes(mem[0x2000:0x2000+405])
    def put(a,data): mem[a:a+len(data)]=data
    # Clone each native config/descriptor table, adjusting only input/output.
    for tile in spec['tiles']:
        i=tile['row']//4
        cfg=list(struct.unpack_from('<24I',mem,tile['config']))
        cfg[1]+=0x1000
        put(0x1200+i*96,struct.pack('<24I',*cfg))
        put(0x200+i*16,struct.pack('<4I',0x1200+i*96,tile['destination']+0x1000,tile['bytes'],0))
    def weight(oc,ic,k):
        value=sum(((struct.unpack_from('<I',mem,0x4000+(oc*8*9+bit*9+k)*4)[0]>>ic)&1)<<bit for bit in range(8))
        return value-128
    weights=[[[weight(oc,ic,k) for k in range(9)] for ic in range(3)] for oc in range(5)]
    frames=[];external=bytearray();golden=bytearray()
    for frame in range(4):
        image=bytes((x+frame*7)&127 for x in original)
        result=[]
        for y in range(13):
            for x in range(7):
                for oc in range(5):
                    acc=sum(image[((y+ky)*9+x+kx)*3+ic]*weights[oc][ic][ky*3+kx]
                            for ky in range(3) for kx in range(3) for ic in range(3))
                    value=max(-128,min(127,acc>>5))
                    result.append((value if value>=0 else value//4)&255)
        frames.append(dict(source=len(external),bytes=len(image),crc32=zlib.crc32(image),checksum=sum(result),input_sum=sum(image)))
        external+=image;golden+=bytes(result)
    for address in (0x2000,0x3000):put(address,bytes([0xa5])*405)
    put(0x60,bytes(20));put(0x80,bytes(20))
    put(0x5000,struct.pack('<4I',(out/'vector.bin').stat().st_size,4,405,455))
    for i,f in enumerate(frames):put(0x5010+i*16,struct.pack('<4I',f['source'],f['crc32'],f['checksum'],f['input_sum']))
    (out/'sram.hex').write_text(''.join(f'{n[0]:08x}\n' for n in struct.iter_unpack('<I',mem)))
    (out/'external.hex').write_text(''.join(f'{b:02x}\n' for b in external))
    (out/'frames_golden.hex').write_text(''.join(f'{b:02x}\n' for b in golden))
    spec.update(frames=frames,input_slots=[0x2000,0x3000],output_slots=[0x12000,0x13000],
                bridge_descriptor=0x60,frame_descriptors=[0x100,0x200],native_configs=[0x1000,0x1200])
    (out/'frames.json').write_text(json.dumps(spec,indent=2))
    return spec


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);generate(ap.parse_args().output)
