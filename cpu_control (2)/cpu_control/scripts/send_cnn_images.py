"""Prepare or send frozen four-frame CNN fixtures over J3 / PS UART1.

Run without --port to validate and prepare the upload package without hardware.
Input is already quantized images.bin plus its frozen model/template manifest;
this tool does not silently change image preprocessing or quantization.
"""
from __future__ import annotations
import argparse,hashlib,json,struct,time,zlib
from pathlib import Path
from uart_image_transfer import HEADER,read_exact
ROOT=Path(__file__).resolve().parents[1]

def words(p):return [int(x,16) for x in p.read_text().split()]
def sha(b):return hashlib.sha256(b).hexdigest()

def prepare(data:Path,out:Path):
    manifest=json.loads((data/'manifest.json').read_text())
    for name,digest in manifest['files_sha256'].items():
        if sha((data/name).read_bytes())!=digest:raise ValueError(f'Frozen fixture hash changed: {name}')
    nf=manifest['frames'];steps=manifest['template_steps']
    if nf!=4 or not 1<=steps<=256:raise ValueError('Requires a validated four-frame, <=256-step fixture')
    commands=words(data/'template_commands.hex');meta=words(data/'template_meta.hex')
    if len(commands)!=steps*16 or len(meta)!=steps*18:raise ValueError('Template length mismatch')
    packed=[]
    for s in range(steps):
        m=meta[s*18:(s+1)*18]
        hold=sum(m[5+w]<<(32*w) for w in range(8))&~(1<<s)
        consumers=[i for i in range(256) if hold>>i&1]
        if len(consumers)>2:raise ValueError('Compact scheduler permits two consumers per producer')
        consumers += [0]*(2-len(consumers))
        packed.append(commands[s*16:(s+1)*16]+[
            m[0]|m[4]<<4|m[13]<<6|m[14]<<9|m[16]<<15|m[1]<<16|m[2]<<18,
            m[3]|m[15]<<8,
            consumers[0]|consumers[1]<<8|hold.bit_count()<<16,m[17]])
    im=words(data/'image_info.hex');info=words(data/'info.hex')
    if len(im)!=20:raise ValueError('Four image descriptors required')
    model_end=min(im[f*5] for f in range(4));memory=(data/'memory.bin').read_bytes();images=(data/'images.bin').read_bytes()
    if model_end%64 or model_end>len(memory):raise ValueError('Model prefix must end at a cache-line boundary')
    frames=[]
    for f in range(4):
        address,length,offset,workspace,frame=im[f*5:f*5+5]
        work_end=im[(f+1)*5+3] if f<3 else info[4]
        blob=images[offset:offset+length]
        if len(blob)!=length or (address|length|workspace|work_end)&63:raise ValueError('Invalid aligned descriptor')
        frames.append(dict(slot=f,id=frame,input=address,length=length,workspace=workspace,
            workspace_bytes=work_end-workspace,crc32=zlib.crc32(blob),image_offset=offset))
    out.mkdir(parents=True,exist_ok=True)
    model=memory[:model_end];(out/'model.bin').write_bytes(model)
    (out/'templates.bin').write_bytes(b''.join(struct.pack('<20I',*t) for t in packed))
    for f in frames:(out/f"image_{f['slot']}.bin").write_bytes(images[f['image_offset']:f['image_offset']+f['length']])
    plan=dict(format='ees331-upload-v1',source=str(data),frames=frames,steps=steps,model_end=model_end,
        model_crc32=zlib.crc32(model),model_version=int(sha(model)[:8],16),
        model_sha256=sha(model),templates_sha256=sha((out/'templates.bin').read_bytes()),
        expected_final_sha256=manifest['final_expected_sha256'],
        final_bytes_per_frame=manifest['final_bytes_per_frame'],full_network=manifest['full_network'])
    (out/'upload.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return plan,packed

class DeviceError(RuntimeError):
    def __init__(self,status):self.status=status;super().__init__(f'PS image server status {status}')
class Link:
    def __init__(self,port):self.port=port;self.tag=0;self.tx_bytes=0;self.rx_bytes=0
    def call(self,op,address,payload=b'',read_length=0):
        size=read_length if op==2 else len(payload)
        if size>256:raise ValueError('Packet exceeds 256 bytes')
        packet=HEADER.pack(b'IMIO',op,self.tag,size,address)+payload
        packet+=struct.pack('<I',zlib.crc32(packet))
        if self.port.write(packet)!=len(packet):raise IOError('Partial UART write; outcome unknown')
        self.port.flush();self.tx_bytes+=len(packet)
        head=read_exact(self.port,12);magic,status,tag,n,addr=HEADER.unpack(head)
        if magic!=b'IMOR' or tag!=self.tag or addr!=address or n>256:raise ValueError('Unexpected reply; reconnect before continuing')
        tail=read_exact(self.port,n+4);self.rx_bytes+=16+n;self.tag=(self.tag+1)&255
        if zlib.crc32(head+tail[:-4])!=struct.unpack('<I',tail[-4:])[0]:raise ValueError('Reply CRC mismatch; transaction outcome unknown')
        if status:raise DeviceError(status)
        return tail[:-4]
    def rpc(self,cmd,*args):return self.call(3,cmd,struct.pack('<'+'I'*len(args),*args))
    def upload(self,address,blob,verify=False):
        for offset in range(0,len(blob),256):
            part=blob[offset:offset+256];self.call(1,address+offset,part)
            if verify and self.call(2,address+offset,read_length=len(part))!=part:raise ValueError('DDR readback mismatch')

def run(link:Link,plan,templates,package:Path,out:Path,verify,timeout):
    timing={};begin=time.perf_counter();cap=link.rpc(0)
    if len(cap)!=24 or struct.unpack('<6I',cap)[:4]!=(0x45455332,1,0x1000000,4):raise ValueError('Incompatible image server')
    link.rpc(1,plan['model_end'],plan['model_version'])
    link.upload(0,(package/'model.bin').read_bytes(),verify);link.rpc(2,plan['model_crc32'])
    timing['model_seconds']=time.perf_counter()-begin
    for i,t in enumerate(templates):
        link.rpc(3,0x14,i);link.rpc(3,0x18,0)
        for word in t:link.rpc(3,0x1c,word)
        link.rpc(4)
    for f in plan['frames']:link.rpc(5,f['slot'],f['input'],f['workspace'],f['id'],f['length'],f['workspace_bytes'])
    link.rpc(6,4);timing['configuration_seconds']=time.perf_counter()-begin-timing['model_seconds']
    started=time.perf_counter();frames=[]
    for f in plan['frames']:
        t=time.perf_counter();blob=(package/f"image_{f['slot']}.bin").read_bytes()
        link.upload(f['input'],blob,verify);link.rpc(7,f['slot'],f['crc32'],plan['model_version'])
        frames.append(dict(frame=f['id'],upload_seconds=time.perf_counter()-t,commit_seconds=time.perf_counter()-started))
    outputs={};deadline=time.perf_counter()+timeout
    while len(outputs)<4:
        if time.perf_counter()>deadline:raise TimeoutError('CNN results deadline; inspect STATUS before reset')
        try:payload=link.rpc(8,0)
        except DeviceError as e:
            if e.status!=6:raise
            status=struct.unpack('<6I',link.rpc(10))
            if status[0]&8 or status[2]&12:raise RuntimeError(f'CNN/cache error: {status}')
            time.sleep(.02);continue
        frame,address,length,epoch=struct.unpack('<4I',payload[:16]);result=bytearray(payload[16:])
        if frame in outputs or frame not in [f['id'] for f in plan['frames']] or length!=plan['final_bytes_per_frame']:raise ValueError('Result descriptor mismatch')
        while len(result)<length:
            more=link.rpc(8,len(result))
            if struct.unpack('<4I',more[:16])!=(frame,address,length,epoch):raise ValueError('Result changed while held')
            result.extend(more[16:])
        if len(result)!=length:raise ValueError('Result length mismatch')
        outputs[frame]=bytes(result);link.rpc(9,frame,epoch)
    result=b''.join(outputs[f['id']] for f in plan['frames'])
    digest=sha(result)
    out.mkdir(parents=True,exist_ok=True);(out/'outputs.bin').write_bytes(result)
    report=dict(status='PASS' if digest==plan['expected_final_sha256'] else 'FAIL',outputs_sha256=digest,
        expected_sha256=plan['expected_final_sha256'],frames=frames,timing=timing,
        batch_seconds=time.perf_counter()-started,total_seconds=time.perf_counter()-begin,
        tx_bytes=link.tx_bytes,rx_bytes=link.rx_bytes,source=plan['source'])
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['status']!='PASS':raise ValueError('Real board results differ from frozen integer golden')
    print(json.dumps(report,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,default=ROOT/'build/self_full_data')
    p.add_argument('--package',type=Path,default=ROOT/'build/ees331_upload');p.add_argument('--port')
    p.add_argument('--baud',type=int,default=115200);p.add_argument('--verify',action='store_true');p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--out',type=Path,default=ROOT/'build/ees331_board_results');args=p.parse_args()
    plan,templates=prepare(args.data.resolve(),args.package.resolve());print(f"Prepared {plan['steps']} steps / four images at {args.package}")
    if not args.port:print('No --port: package validation only; no board transaction.');return
    import serial
    with serial.Serial(args.port,args.baud,timeout=15,write_timeout=15) as port:
        port.reset_input_buffer();run(Link(port),plan,templates,args.package,args.out,args.verify,args.timeout)
if __name__=='__main__':main()
