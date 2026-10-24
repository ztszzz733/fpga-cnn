"""Independent integer golden for DW7 + Post, max channels and sliding windows."""
from pathlib import Path
from datetime import datetime
import hashlib,json,random,struct,subprocess,time
from bootstrap_verilator_native import build_native,native_environment
ROOT=Path(__file__).resolve().parents[1]
def generate(out,w,h,c):
    out.mkdir(parents=True);rng=random.Random(733+c)
    weights=[rng.randrange(-128,128) for _ in range(49*c)]
    for tap in range(49):weights[tap*c]=-128;weights[tap*c+1]=127
    bias=[rng.randrange(-10000,10000) for _ in range(c)]
    mult=[rng.randrange(1,32) for _ in range(c)]
    mem=bytearray([0xa5]*262144);gold=bytearray(mem);cursor=256
    def alloc(data):
        nonlocal cursor
        a=(cursor+63)&~63;cursor=a+len(data)+64
        assert cursor<len(mem);mem[a:a+len(data)]=data;return a
    wa=alloc(bytes(v&255 for v in weights))
    pa=alloc(b''.join(struct.pack('<5I',b&0xffffffff,m,0,16|(128<<24),255<<8) for b,m in zip(bias,mult)))
    jobs=[]
    for f in range(2):
        x=bytearray(rng.randrange(256) for _ in range(w*h*c))
        for a in range(0,len(x),c):x[a]=255;x[a+1]=255
        values=[];q=[]
        for y in range(h-6):
            for xx in range(w-6):
                for ch in range(c):
                    v=sum(x[((y+ky)*w+xx+kx)*c+ch]*weights[(ky*7+kx)*c+ch] for ky in range(7) for kx in range(7))
                    values.append(v)
                    prod=(v+bias[ch])*mult[ch]
                    rounded=(abs(prod)+(1<<15))>>16
                    if prod<0:rounded=-rounded
                    q.append(max(0,min(255,rounded+128)))
        ia=alloc(x);oa=alloc(bytes([0xa5])*(4*len(values)));qa=alloc(bytes([0xa5])*len(q))
        gold[oa:oa+4*len(values)]=struct.pack('<'+'i'*len(values),*values);gold[qa:qa+len(q)]=bytes(q)
        jobs.append([ia,wa,oa,qa,pa,w,h,c,len(q)])
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes(gold)
    (out/'jobs.hex').write_text(''.join(f'{v:08x}\n' for job in jobs for v in job))
    return {'shape':[h,w,c],'jobs':jobs,'input_sha256':hashlib.sha256(mem).hexdigest(),'golden_sha256':hashlib.sha256(gold).hexdigest()}
names=['rtl/cnn_ddr/dw7_bram_engine.sv','rtl/cnn_ddr/quant_post_bram_engine.sv','tb/integration/tb_dw7_bram.sv']
out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_ees331_bram_operators');out.mkdir(parents=True)
start=time.perf_counter();exe=build_native([ROOT/n for n in names],'tb_dw7_bram',out,jobs=2)
result={'status':'RUNNING','compile_seconds':time.perf_counter()-start,'cases':{},'sources_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}}
for name,w,h,c,opts in [('max512',7,7,512,[]),('max512_stall',7,7,512,['+stall=1']),('overlap16',10,9,16,[]),('overlap16_restart',10,9,16,['+stall=1','+restart'])]:
    case=out/name;spec=generate(case,w,h,c)
    with (case/'simulation.log').open('w') as log:p=subprocess.run([str(exe),*opts],cwd=case,env=native_environment(),stdout=log,stderr=subprocess.STDOUT)
    text=(case/'simulation.log').read_text()
    if p.returncode or 'PASS tb_dw7_bram' not in text:
        result['status']='FAIL';result['error']=name;break
    result['cases'][name]={'fixture':spec,'metrics':json.loads((case/'metrics.json').read_text()),'output_sha256':hashlib.sha256((case/'outputs.bin').read_bytes()).hexdigest()}
else:result['status']='PASS'
result['total_seconds']=time.perf_counter()-start
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'out':str(out),**result},indent=2))
if result['status']!='PASS':raise SystemExit(1)
