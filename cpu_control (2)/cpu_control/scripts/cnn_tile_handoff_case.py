"""Portable, standard-library-only CNN tile fixtures and independent integer oracle.

The byte-copy verifier is a software contract model, never DATA MOVER RTL proof.
"""
import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

POISON=0xA5
DDR_POISON=0xD7
def align(n,a=64):return (n+a-1)//a*a
def digest(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def words(p,values):Path(p).write_text(''.join(f'{v&0xffffffff:08x}\n' for v in values),encoding='ascii')
def round_away(value,shift):
    return value if shift==0 else (1 if value>=0 else -1)*((abs(value)+(1<<(shift-1)))>>shift)
def i32(value):return value if value<0x80000000 else value-0x100000000

def reference(x,weights,post,add,residual,h,w,ci,co):
    """Scalar HWC/O_KY_KX_I conv, then one-round affine Post and residual Add."""
    oh,ow=h-2,w-2;raw=[]
    for y in range(oh):
        for col in range(ow):
            for o in range(co):
                value=0
                for ky in range(3):
                    for kx in range(3):
                        for c in range(ci):
                            value+=x[((y+ky)*w+col+kx)*ci+c]*weights[((o*3+ky)*3+kx)*ci+c]
                assert -(1<<31)<=value<(1<<31)
                raw.append(value)
    quant=[];summed=[]
    for index,value in enumerate(raw):
        p=post[index%co];bias,ma,_,cfg,clamp=p
        value=round_away((value+i32(bias))*i32(ma),cfg&255)+(cfg>>24)
        quant.append(max(clamp&255,min((clamp>>8)&255,value)))
    for index,(a,b) in enumerate(zip(quant,residual)):
        _,ma,mb,cfg,clamp=add[index%co]
        value=round_away((a-((cfg>>8)&255))*i32(ma)+(b-((cfg>>16)&255))*i32(mb),cfg&255)+(cfg>>24)
        summed.append(max(clamp&255,min((clamp>>8)&255,value)))
    return struct.pack('<'+'i'*len(raw),*raw),bytes(quant),bytes(summed)

def generate(root,name,h,w,ci,co):
    out=Path(root)/name
    assert not out.exists(),'preserve existing fixtures: '+str(out)
    out.mkdir(parents=True)
    oh,ow=h-2,w-2;n=oh*ow*co
    x=bytes(((y*31+col*17+c*43)^((y+1)*(col+3)*7+c*13))&255 for y in range(h) for col in range(w) for c in range(ci))
    weights=[((o*17+ky*11+kx*7+c*5)%7)-3 for o in range(co) for ky in range(3) for kx in range(3) for c in range(ci)]
    residual=bytes((index*37+(index//co)*19+83)&255 for index in range(n))
    shift=6 if ci==32 else 3
    post=[((-128*sum(weights[o*9*ci:(o+1)*9*ci])+(o%7-3)*11)&0xffffffff,o%3+1,0,shift|(128<<24),255<<8) for o in range(co)]
    add=[(0,3,2,2|(128<<8)|(128<<16)|(128<<24),255<<8) for _ in range(co)]
    raw,quant,summed=reference(x,weights,post,add,residual,h,w,ci,co)
    payloads={'input_with_halo':x,'weights':bytes(v&255 for v in weights),
        'post_params':b''.join(struct.pack('<5I',*p) for p in post),
        'add_params':b''.join(struct.pack('<5I',*p) for p in add),'residual':residual,
        'conv_raw':raw,'post_output':quant,'add_output':summed}
    regions={};cursor=0
    for key in ('input_with_halo','weights','post_params','add_params','residual'):
        cursor=align(cursor);regions[key]=dict(local_address=cursor,bytes=len(payloads[key]),role='input');cursor+=len(payloads[key])
    readonly_end=align(cursor)
    # Guarded outputs preserve adjacent memory and the existing real-RTL harness.
    slots=[];cursor=readonly_end
    for key in ('conv_raw','post_output','add_output'):
        size=align(len(payloads[key]))+64
        regions[key]=dict(local_address=cursor,bytes=len(payloads[key]),role='output',slot_bytes=size)
        slots.append((cursor,size));cursor+=size
    for _ in range(40-len(slots)):slots.append((cursor,64));cursor+=64
    assert cursor<=32768
    local=bytearray([POISON])*32768
    ddr=bytearray([DDR_POISON])*65536;ddr_expected=bytearray(ddr)
    moves=[];ddr_cursor=0x1000
    def move(phase,direction,src,dst,length,region,row=None):
        moves.append(dict(sequence=len(moves),phase=phase,direction=direction,src=src,dst=dst,bytes=length,
            flags_proposed=0 if direction=='DDR_TO_LOCAL' else 1,region=region,row='' if row is None else row))
    for key in ('input_with_halo','weights','post_params','add_params','residual'):
        blob=payloads[key];la=regions[key]['local_address'];ddr_cursor=align(ddr_cursor)
        rows=h if key=='input_with_halo' else oh if key=='residual' else 1
        rowbytes=len(blob)//rows;pitch=align(rowbytes+8,8) if rows>1 else rowbytes
        regions[key].update(ddr_offset=ddr_cursor,ddr_row_stride=pitch,rows=rows,row_bytes=rowbytes)
        for row in range(rows):
            address=ddr_cursor+row*pitch;chunk=blob[row*rowbytes:(row+1)*rowbytes]
            ddr[address:address+rowbytes]=chunk
            move('load','DDR_TO_LOCAL',address,la+row*rowbytes,rowbytes,key,row)
        ddr_cursor+=rows*pitch+64
    assert ddr_cursor<0x8000
    pitch=align(ow*co+4,8)
    regions['add_output'].update(ddr_offset=0x8000,ddr_row_stride=pitch,rows=oh,row_bytes=ow*co)
    for row in range(oh):
        move('store','LOCAL_TO_DDR',regions['add_output']['local_address']+row*ow*co,0x8000+row*pitch,ow*co,'add_output',row)
    ddr_expected[:]=ddr
    for row in range(oh):ddr_expected[0x8000+row*pitch:0x8000+row*pitch+ow*co]=summed[row*ow*co:(row+1)*ow*co]
    for key in ('input_with_halo','weights','post_params','add_params','residual'):(out/(key+'.bin')).write_bytes(payloads[key])
    for key,blob in [('conv_int32',raw),('post_uint8',quant),('add_uint8',summed)]:(out/('golden_'+key+'.bin')).write_bytes(blob)
    (out/'local_initial.bin').write_bytes(local);(out/'ddr_initial.bin').write_bytes(ddr);(out/'ddr_expected.bin').write_bytes(ddr_expected)
    shape=dict(input_h=h,input_w=w,in_channels=ci,out_channels=co,output_h=oh,output_w=ow,kernel=3,stride=1,padding=0)
    save(out/'layout.json',dict(address_unit='byte',local_bytes=32768,ddr_test_region_bytes=65536,ddr_base='Configured by storage/PS, not assigned here',
        local_unaligned_requirement='arbitrary byte start, including offsets 1..7 modulo8',ddr_start_alignment_in_this_case=8,
        features='HWC_UINT8',weights='INT8_O_KY_KX_I',raw='little_endian_INT32_HWC',input_zero=128,output_zero=128,
        parameter_words=['signed bias','signed multiplierA','signed multiplierB','outputZero[31:24],inputBZero[23:16],inputAZero[15:8],shift[7:0]','clampHigh[15:8],clampLow[7:0]'],
        shift_range= '0..63 for current Post pipeline',shape=shape,regions=regions,
        guards_note='Three real output slots plus 37 unused context slots have poison tails for the unchanged 10-context RTL harness; this is not the new local RAM RTL'))
    with (out/'moves.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(moves[0]));writer.writeheader();writer.writerows(moves)
    commands=[]
    def command(op,src,dst):
        c=[0]*16;c[0]=op;c[1]=regions[src]['local_address'];c[3]=regions[dst]['local_address'];return c
    conv=command(0,'input_with_halo','conv_raw');conv[2]=regions['weights']['local_address'];conv[6:11]=[ci,w,h,co,1]
    pp=command(1,'conv_raw','post_output');pp[4:7]=[regions['post_params']['local_address'],n,co]
    ap=command(2,'post_output','add_output');ap[2]=regions['residual']['local_address'];ap[4:7]=[regions['add_params']['local_address'],n,co]
    commands=[conv,pp,ap]
    tasks=[dict(node=i,operation=op,dependencies=[] if i==0 else [i-1],native_command_words=c,
                output_region=region,required_loaded_regions=loaded)
        for i,(op,c,region,loaded) in enumerate(zip(['K3','Post','Add'],commands,['conv_raw','post_output','add_output'],
            [['input_with_halo','weights'],['post_params'],['add_params','residual']]))]
    save(out/'tasks.json',dict(tasks=tasks,store_after_node=2,mover_command_limit=1,active_tile_limit=1,
        note='Native 512-bit CNN commands plus a proposed MOVER plan; no new mover adapter RTL is supplied'))
    native=out/'native_fixture';native.mkdir()
    memory=bytearray(local)
    for key in ('weights','post_params','add_params','residual'):
        address=regions[key]['local_address'];memory[address:address+len(payloads[key])]=payloads[key]
    (native/'memory.bin').write_bytes(memory);(native/'images.bin').write_bytes(x);(native/'expected.bin').write_bytes(raw+quant+summed)
    words(native/'info.hex',[1,3,3,32768,len(memory),len(raw)+len(quant)+len(summed),readonly_end,len(x)]+[v for pair in slots for v in pair])
    words(native/'image_info.hex',[regions['input_with_halo']['local_address'],len(x),0,0,100])
    words(native/'template_commands.hex',[v for c in commands for v in c])
    expanded=[];meta=[];node_info=[];offset=0
    for i,c in enumerate(commands):
        row=c.copy();row[13]=100;expanded.extend(row)
        hold=[3,6,4][i];uses=[0,1,1][i];use_slots=[0,0,1][i];owners=[0,0,1][i]
        meta.extend([0,0 if i==0 else 1,max(0,i-1),0,i]+[hold]+[0]*15+[uses,use_slots,owners,int(i==2),len(summed) if i==2 else 0])
        blob=(raw,quant,summed)[i];node_info.extend([c[3],len(blob),offset,i]);offset+=len(blob)
    words(native/'template_meta.hex',meta);words(native/'commands.hex',expanded);words(native/'node_info.hex',node_info)
    save(out/'manifest.json',dict(format='cnn-storage-tile-v0.2',name=name,status='GENERATED_NOT_MOVER_RTL_PASS',
        fixture_kind='deterministic synthetic arithmetic/transport diagnostic, not trained-model accuracy evidence',shape=shape,
        payload_bytes=sum(map(len,payloads.values())),local_bytes=32768,local_guarded_used_end=cursor,
        macs=oh*ow*co*9*ci,checked_output_bytes=len(raw)+len(quant)+len(summed),final_bytes=len(summed),
        expected_final_sha256=digest(summed),proposed_flags='bit0: 0 DDR_TO_LOCAL, 1 LOCAL_TO_DDR; bits31:1 zero; awaiting storage ACK',
        native_check=dict(configured_frame_contexts=10,active_frames=1,pool=dict(K3=4,K1=6,Post=3,Add=1,DW7=1,Pad=1),
            native_sram_parameter_bytes=33554432,checker_address_limit_bytes=32768,
            scope='Existing real CNN/SRAM RTL only; native preload bypasses DDR/MOVER; NOT new32KiB RAM synthesis or MOVER validation'),
        files={str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in sorted(out.rglob('*')) if p.is_file()}))
    return out

def verify(case):
    case=Path(case);m=read(case/'manifest.json');layout=read(case/'layout.json');regions=layout['regions'];s=m['shape']
    for name,info in m['files'].items():
        blob=(case/name).read_bytes();assert len(blob)==info['bytes'] and digest(blob)==info['sha256'],name
    def params(name):
        blob=(case/(name+'.bin')).read_bytes();return [struct.unpack_from('<5I',blob,i) for i in range(0,len(blob),20)]
    x=(case/'input_with_halo.bin').read_bytes();wb=(case/'weights.bin').read_bytes();weights=[v if v<128 else v-256 for v in wb]
    outputs=reference(x,weights,params('post_params'),params('add_params'),(case/'residual.bin').read_bytes(),s['input_h'],s['input_w'],s['in_channels'],s['out_channels'])
    for name,blob in zip(['conv_int32','post_uint8','add_uint8'],outputs):assert blob==(case/('golden_'+name+'.bin')).read_bytes(),name
    local=bytearray((case/'local_initial.bin').read_bytes());ddr=bytearray((case/'ddr_initial.bin').read_bytes())
    assert all(v==POISON for v in local),'local initial contains precomputed output'
    moves=list(csv.DictReader((case/'moves.csv').open(encoding='utf-8')))
    with (case/'native_fixture/memory.bin').open('rb') as f:native=f.read()
    for name in ('conv_raw','post_output','add_output'):
        r=regions[name];assert all(v==POISON for v in native[r['local_address']:r['local_address']+r['bytes']])
    def copy(move):
        a,b,n=(int(move[key]) for key in ('src','dst','bytes'))
        source,target=(ddr,local) if move['direction']=='DDR_TO_LOCAL' else (local,ddr)
        assert n>0 and a>=0 and b>=0 and a+n<=len(source) and b+n<=len(target)
        assert (a if move['direction']=='DDR_TO_LOCAL' else b)%8==0
        target[b:b+n]=source[a:a+n]
    for move in moves:
        if move['phase']=='load':copy(move)
    for name in ('input_with_halo','weights','post_params','add_params','residual'):
        r=regions[name];assert local[r['local_address']:r['local_address']+r['bytes']]==(case/(name+'.bin')).read_bytes()
    # Software injects the oracle for transport-contract checking only; real RTL
    # arithmetic is checked separately against native_fixture/expected.bin.
    for name,blob in zip(['conv_raw','post_output','add_output'],outputs):
        r=regions[name];local[r['local_address']:r['local_address']+len(blob)]=blob
    for move in moves:
        if move['phase']=='store':copy(move)
    assert ddr==(case/'ddr_expected.bin').read_bytes(),'DDR payload or adjacent bytes differ'
    ordered=sorted((r['local_address'],r['local_address']+r['bytes']) for r in regions.values())
    assert all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:]))
    result=dict(status='PASS',scope='Software scalar oracle, file/layout and byte-copy contract model; not MOVER RTL',
        moves=len(moves),non_8_aligned_local_starts=sum((int(x['dst']) if x['direction']=='DDR_TO_LOCAL' else int(x['src']))%8!=0 for x in moves),
        adjacent_ddr_bytes='Entire DDR image compared, including padding and guards',golden_not_in_initial_output=True)
    save(case/'software_validation.json',result);return result

def verify_unaligned_lanes(out):
    """Emit explicit storage-side acceptance vectors for all modulo8 lane starts."""
    rows=[]
    for direction in ('DDR_TO_LOCAL','LOCAL_TO_DDR'):
        for lane in range(8):
            for n in (1,3,4,7,9,17):
                local=bytearray([POISON])*64;ddr=bytearray([DDR_POISON])*64;payload=bytes((i*19+lane*7+3)&255 for i in range(n))
                if direction=='DDR_TO_LOCAL':ddr[16:16+n]=payload;source,target=ddr,local;a,b=16,16+lane
                else:local[16+lane:16+lane+n]=payload;source,target=local,ddr;a,b=16+lane,16
                before=bytes(target);target[b:b+n]=source[a:a+n]
                assert target[b:b+n]==payload and target[:b]==before[:b] and target[b+n:]==before[b+n:]
                rows.append(dict(direction=direction,local_lane=lane,bytes=n,local_start=16+lane,ddr_start=16,
                    payload_hex=payload.hex(),initial_source_hex=bytes(source).hex(),expected_destination_hex=bytes(target).hex(),initial_destination_hex=before.hex()))
    save(Path(out)/'unaligned_lane_vectors.json',dict(status='SOFTWARE_EXPECTED_VECTORS',cases=rows,
        scope='96 expected cases for storage RTL; generated/model-checked only, no MOVER implementation'))
    return len(rows)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('--generate',action='store_true');args=ap.parse_args()
    if args.generate:
        generate(args.root,'tile_8x8x32',10,10,32,32)
        generate(args.root,'short_row_2x2x2',4,4,2,2)
        verify_unaligned_lanes(args.root)
    results={p.name:verify(p) for p in sorted(args.root.iterdir()) if p.is_dir() and (p/'manifest.json').exists()}
    assert len(results)==2
    print(json.dumps(results,ensure_ascii=False,indent=2))
