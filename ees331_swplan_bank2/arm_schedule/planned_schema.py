"""Software-owned K3 read geometry; wire layout matches k3_plan.h."""
PLANNED=0x80000000
INPUT_WORD=0x100
WEIGHT_WORD=0x200
REUSE=0x400
WEIGHT_BYTES=9*512

def plan_k3(command):
    r=list(command)
    if r[0] != 0:
        return r
    ci,w,h,co,stride=r[6:11]
    dw=r[11]&1
    if not (0<ci<=512 and 0<co<=512 and 3<=w<=65535 and 3<=h<=65535 and stride in (1,2)):
        raise ValueError('invalid K3 shape')
    if dw and ci!=co:
        raise ValueError('depthwise channel mismatch')
    per=9*(1 if dw else ci)
    ow,oh=(w-3)//stride+1,(h-3)//stride+1
    row=w*ci
    extent=row*h
    weights=per*co
    if max(row,extent,weights,ow*oh*co*4)>0xffffffff:
        raise ValueError('K3 span overflow')
    reuse=bool(dw or ((ow>2 or oh>2) and weights<=WEIGHT_BYTES))
    loaded=weights if reuse else per
    if loaded>WEIGHT_BYTES:
        raise ValueError('K3 weights exceed local memory')
    flags=PLANNED|dw|(REUSE if reuse else 0)
    if r[1]%4==0 and ci%4==0:
        flags|=INPUT_WORD
    if r[2]%4==0 and loaded%4==0:
        flags|=WEIGHT_WORD
    r[4],r[5],r[11],r[12],r[15]=row,per,flags,extent,weights
    return r

def convert_binary(payload):
    import struct
    data=bytearray(payload)
    magic,frames,steps,*_=struct.unpack_from('<8I',data)
    if magic!=0x31435345:
        raise ValueError('unknown PLAN format')
    first=32+frames*24
    converted=0
    for step in range(steps):
        at=first+step*80
        row=list(struct.unpack_from('<20I',data,at))
        if row[0]==0:
            row=plan_k3(row)
            struct.pack_into('<20I',data,at,*row)
            converted+=1
    return bytes(data),converted

if __name__=='__main__':
    from pathlib import Path
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    args=parser.parse_args()
    data,count=convert_binary(args.plan.read_bytes())
    args.plan.write_bytes(data)
    print('Prepared software read plans for',count,'K3 task templates')
