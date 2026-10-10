"""Six image-only UART fixtures and an independent direct-convolution oracle."""
from pathlib import Path
import json,random,hashlib
from gen_autoload_demo import Program

def generate(out,width=524,height=524,frames=6):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    images=[];features=[];rng=random.Random(524)
    names=['smooth_ramp','checkerboard','concentric_rings','diagonal_stripes','geometric_shapes','seeded_texture']
    kx=[[-1,0,1],[-2,0,2],[-1,0,1]]
    ky=[[-1,-2,-1],[0,0,0],[1,2,1]]
    for f in range(frames):
        data=bytearray()
        for y in range(height):
            for x in range(width):
                dx=x-width//2;dy=y-height//2
                values=[(x*170//max(1,width-1)+y*85//max(1,height-1)),
                        235 if ((x//17+y//23)&1) else 20,
                        220 if (int((dx*dx+dy*dy)**0.5)//13)&1 else 25,
                        240 if ((x+2*y)//19)&1 else 15,
                        230 if (width//5<x<width//2 and height//6<y<height*3//4) or dx*dx+dy*dy<(min(width,height)//5)**2 else 30,
                        rng.randrange(256)]
                data.append(values[f%6])
        images.append(data)
        (out/f'input_{f+1:02}.pgm').write_bytes(f'P5\n{width} {height}\n255\n'.encode()+data)
        # Direct per-output 3x3 convolution then max over four spatial outputs.
        # This does not share the RTL's rolling line buffers or window state.
        channels=[bytearray(),bytearray()]
        for oy in range((height-2)//2):
            for ox in range((width-2)//2):
                for ci,kernel in enumerate([kx,ky]):
                    best=0
                    for py in range(2):
                        for px in range(2):
                            value=sum(data[(oy*2+py+j)*width+ox*2+px+i]*kernel[j][i]
                                      for j in range(3) for i in range(3))
                            best=max(best,abs(value)//4)
                    channels[ci].append(best)
        packed=bytearray(v for pair in zip(*channels) for v in pair)
        features.append(packed)
        for ci,channel in enumerate(channels):
            (out/f'expected_{f+1:02}_{"x" if ci==0 else "y"}.pgm').write_bytes(
                f'P5\n{(width-2)//2} {(height-2)//2}\n255\n'.encode()+channel)
    external=b''.join(images);expected=b''.join(features)
    (out/'external.mem').write_text(''.join(f'{b:02x}\n' for b in external))
    (out/'expected.mem').write_text(''.join(f'{b:02x}\n' for b in expected))
    (out/'expected.bin').write_bytes(expected)
    checksum=sum(expected[i]|expected[i+1]<<8 for i in range(0,len(expected),2)) & 0xffffffff
    p=Program();p.li(1,0x40000000);p.li(2,0x40);p.li(3,0x80)
    p.sw(3,0);p.sw(3,0,8)
    p.li(4,0x1000);p.sw(1,4,8) # Fixed program, no task/weight upload over UART.
    p.li(4,1);p.sw(1,4);p.sw(2,4) # Arm CNN BEFORE requesting image stream.
    p.label('load_poll');p.lw(4,2,4);p.i(7,5,4,1,'load finished');p.branch(0,5,0,'load_poll')
    p.i(7,7,4,2,'load failed');p.sw(2,0);p.branch(1,7,0,'fail')
    p.label('cnn_poll');p.lw(4,1,4);p.i(7,5,4,4,'CNN error');p.branch(1,5,0,'fail')
    p.i(7,5,4,2,'CNN complete');p.branch(0,5,0,'cnn_poll')
    p.lw(5,1,12);p.li(6,frames);p.branch(1,5,6,'fail')
    p.li(10,0x1000);p.li(11,len(expected)//2);p.li(12,0)
    p.label('checksum');p.i(5,13,10,0,'lhu feature pair',0x03)
    p.emit((13<<20)|(12<<15)|(12<<7)|0x33,'add checksum')
    p.i(0,10,10,2,'next pair');p.i(0,11,11,-1,'remaining pairs');p.branch(1,11,0,'checksum')
    p.sw(3,12);p.li(4,0x600d);p.sw(3,4,8);p.jump('halt')
    p.label('fail');p.li(4,0xdead0001);p.sw(3,4,8)
    p.label('halt');p.emit(0x6f,'halt');p.resolve()
    (out/'program.mem').write_text(''.join(f'{w:08x}\n' for w,_ in p.code)+'00000013\n'*(1024-len(p.code)))
    (out/'program.lst').write_text('\n'.join(f'{i*4:04x} {w:08x} {c}' for i,(w,c) in enumerate(p.code)))
    manifest=dict(width=width,height=height,frames=frames,format='GRAY8 row-major',
                  frame_pixels=width*height,output_width=(width-2)//2,output_height=(height-2)//2,
                  channels=['abs(Sobel X)/4','abs(Sobel Y)/4'],pool='2x2 max, stride 2',padding='valid',
                  output_base=4096,output_frame_bytes=len(features[0]),output_total_bytes=len(expected),
                  input_names=names[:frames],input_sha256=hashlib.sha256(external).hexdigest(),
                  expected_sha256=hashlib.sha256(expected).hexdigest(),expected_checksum=checksum)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
