"""Small real-NEureka stripe/ReLU experiment. Run with WSL Python.

No neural-network inference claim: deterministic pixels/weights, independent
whole-image integer oracle, real banked SRAM and RTL arithmetic. No UART/CPU.
"""
import argparse, datetime, hashlib, json, os, random, shutil, struct, time
from pathlib import Path
from run_tests import ROOT, execute
from run_neureka_benchmark import sources

STAGE = ROOT.parents[1] / '.neureka_stripes_build'


def generate(folder, h, w, ci, co, frames=2, seed=42):
    rng = random.Random(seed)
    oh, ow, stripe = h-2, w-2, 4
    assert 3 <= h <= 24 and 3 <= w <= 24 and 1 <= ci <= 8 and 1 <= co <= 16
    memory = bytearray([0xa5]*65536)
    source = bytearray(memory)
    conv_gold = bytearray(memory)
    relu_gold = bytearray(memory)
    xbase, xpitch, obase, opitch = 0x4000, 0x1000, 0x8000, 0x2000
    raw = [0x2000, 0x2800]
    assert 1 <= frames <= 2 and h*w*ci <= xpitch and oh*ow*co <= opitch
    assert stripe*ow*co <= raw[1]-raw[0]
    weight = [rng.randrange(-3,4) for _ in range(co*ci*9)]
    packed = bytearray()
    for oc in range(co):
        for bit in range(8):
            for k in range(9):
                bits = sum((((weight[(oc*ci+ic)*9+k]+128)>>bit)&1)<<ic for ic in range(ci))
                packed.extend(struct.pack('<I', bits))
    wa, scale, shift = 0x1000, 0x0800, 5
    assert wa+len(packed)<=raw[0], 'weight image must not overlap scratch slots'
    memory[wa:wa+len(packed)] = packed
    memory[scale:scale+co*4] = struct.pack('<'+'I'*co,*([1]*co))
    jobs=[]; negatives=positives=0
    rem=lambda v,t:(v-1)%t+1
    for frame in range(frames):
        pixels=[rng.randrange(128) for _ in range(h*w*ci)]
        source[xbase+frame*xpitch:xbase+frame*xpitch+len(pixels)] = bytes(pixels)
        # Whole-image HWC oracle: independent of the hardware strip scheduling.
        full=[]
        for y in range(oh):
            for x in range(ow):
                for oc in range(co):
                    acc=sum(pixels[((y+ky)*w+x+kx)*ci+ic]*weight[(oc*ci+ic)*9+ky*3+kx]
                            for ic in range(ci) for ky in range(3) for kx in range(3))
                    full.append(max(-128,min(127,acc>>shift)))
        negatives += sum(v<0 for v in full); positives += sum(v>0 for v in full)
        out=obase+frame*opitch
        conv_gold[out:out+len(full)]=bytes(v&255 for v in full)
        relu_gold[out:out+len(full)]=bytes(max(0,v) for v in full)
        for y in range(0,oh,stripe):
            rows=min(stripe,oh-y); idx=len(jobs); slot=idx%2
            cfgaddr=0x100+idx*96
            ia=xbase+frame*xpitch+y*w*ci
            dst=out+y*ow*co
            cfg=[wa,ia,raw[slot],scale,0,0,ci,w*ci,0,32,co,ow*co,36,36*8,0,
                 rem(co,32)<<16|rem(ci,32),rem(rows,4)<<16|rem(ow,4),
                 (rem(rows,4)+2)<<16|(rem(ow,4)+2),1<<16|1,
                 ((rows+3)//4)<<16|((ow+3)//4),0,0xffffff80,0,
                 (1<<23)|(shift<<16)|(2<<12)|(1<<11)|(1<<10)|(1<<9)|(1<<4)|7]
            struct.pack_into('<24I',memory,cfgaddr,*cfg)
            # Flat elementwise ReLU is valid for HWC with no channel parameters.
            desc=[0x106,raw[slot],dst,0,0,rows<<16|ow,co<<16|co,0]
            jobs.append([cfgaddr,slot,(y+rows+2)*w*ci,frame,raw[slot],rows*ow*co,dst,y,*desc])
    assert negatives and positives, 'must exercise both ReLU branches'
    assert len(jobs)<=12 and 0x100+len(jobs)*96<=scale
    (folder/'memory.bin').write_bytes(memory)
    (folder/'source.bin').write_bytes(source)
    for name,data in [('conv.hex',conv_gold),('relu.hex',relu_gold)]:
        (folder/name).write_text(''.join(f'{x:02x}\n' for x in data))
    (folder/'jobs.hex').write_text(''.join(f'{x:08x}\n' for j in jobs for x in j))
    meta=[h,w,ci,co,xbase,xpitch,obase,opitch,frames,len(jobs),oh*ow*co]
    (folder/'meta.hex').write_text(''.join(f'{x:08x}\n' for x in meta))
    spec=dict(height=h,width=w,ci=ci,co=co,frames=frames,stripe_output_rows=stripe,
              input_layout='HWC',input_range=[0,127],shift=shift,jobs=jobs,
              negative_conv_values=negatives,positive_conv_values=positives,
              uart=False,cpu=False,trained_network=False)
    (folder/'workload.json').write_text(json.dumps(spec,indent=2))
    return spec


SIGNALS=[('rst_n',1),('input_active',1),('input_frame',32),('input_bytes',32),('pixel_eof',1),
         ('input_write_fire',1),('tile_valid',1),('tile_ready',1),('tile_slot',1),
         ('accepted_tiles',32),('completed_tiles',32),('slot_states',6),
         ('conv_start',1),('conv_tile',32),('core_busy',1),('core_state',6),('compute_active',1),
         ('conv_read_fire',1),('conv_write_fire',1),('conv_done',1),
         ('post_start',1),('post_tile',32),('post_busy',1),('post_read_fire',1),('post_write_fire',1),
         ('post_addr',32),('post_done',1),('compute_post_overlap',1),('input_compute_overlap',1),
         ('busy',1),('done',1),('error',1),('memory_fault',1)]


def monitor():
    lines=['integer wave_fd;','initial begin', ' wave_fd=$fopen("control.vcd","w");',
           ' $fwrite(wave_fd,"$timescale 1ns $end\\n$scope module stripe $end\\n");']
    for i,(name,width) in enumerate(SIGNALS):
        lines.append(f' $fwrite(wave_fd,"$var wire {width} s{i} {name} $end\\n");')
    lines+=[' $fwrite(wave_fd,"$upscope $end\\n$enddefinitions $end\\n");','end']
    for name,width in SIGNALS: lines.append(f'logic [{width-1}:0] previous_{name};')
    lines+=['logic wave_first=1;','always @(posedge clk) begin', ' $fwrite(wave_fd,"#%0d\\n",$time);']
    for i,(name,width) in enumerate(SIGNALS):
        lines += [f' if(wave_first || previous_{name} !== {name}) $fwrite(wave_fd,"b%b s{i}\\n",{name});',
                  f' previous_{name}={name};']
    lines+=[' wave_first=0;','end']
    return '\n'.join(lines)+'\n'


def build(folder, reuse=False):
    STAGE.mkdir(parents=True,exist_ok=True)
    # Existing dependency list; unused CPU/old CNN modules are not elaborated.
    src=[s for s in sources() if s.name!='tb_neureka_benchmark.sv']
    src += [ROOT/'tb/integration/tb_neureka_stripes.sv']
    hashes={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src}
    key=dict(hashes=hashes,monitor=hashlib.sha256(monitor().encode()).hexdigest(),flags_version=1)
    exe=STAGE/'obj/Vtb_neureka_stripes';manifest=STAGE/'build_inputs.json'
    vr=ROOT.parents[1]/'.neureka_build/neureka/verilator'
    env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
    if reuse:
        if not exe.exists() or not manifest.exists() or json.loads(manifest.read_text())!=key:
            raise RuntimeError('Reuse refused: sources/flags do not match the built simulator')
        elapsed=0.0
    else:
        staged=[]
        for i,s in enumerate(src):
            dest=STAGE/f'{i:03}_{s.name}';shutil.copyfile(s,dest);staged.append(dest)
        for repo in ['hci','hwpe-stream','hwpe-ctrl']:
            for inc in (ROOT/'third_party'/repo).rglob('*.svh'):shutil.copyfile(inc,STAGE/inc.name)
        (STAGE/'stripe_monitor.svh').write_text(monitor())
        stamp=time.perf_counter()
        execute([vr/'bin/verilator','--binary','--timing','--assert','--timescale-override','1ns/1ps',
                 '-Wno-fatal','-O1','-j','4','-CFLAGS','-std=c++20',
                 '-MAKEFLAGS','CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O1',
                 '--top-module','tb_neureka_stripes','--Mdir',STAGE/'obj','-I'+str(STAGE),*staged],
                 STAGE,env,folder/'compile.log',timeout=1800)
        elapsed=time.perf_counter()-stamp;manifest.write_text(json.dumps(key,indent=2))
    return exe,env,elapsed,key


def main():
    p=argparse.ArgumentParser();p.add_argument('--reuse',action='store_true');a=p.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka_stripes')
    out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    record=dict(status='RUNNING',clock_hz=100000000,cases={},timing_seconds={})
    start=time.perf_counter()
    def save(): (out/'result.json').write_text(json.dumps(record,indent=2))
    save()
    try:
        exe,env,seconds,key=build(out,a.reuse)
        record['timing_seconds']['compile']=seconds;record['build_inputs']=key;save()
        # One binary, four bounded runs: same workload serial vs pipelined,
        # non-multiple tails, randomized admission stalls and reset/restart.
        cases=[('parallel',14,11,3,8,False,0,False),('serial',14,11,3,8,True,0,False),
               ('tail_stalls',13,9,3,5,False,17,False),('reset_restart',14,11,3,8,False,3,True)]
        for name,h,w,ci,co,serial,stall,restart in cases:
            case=out/name;case.mkdir();generate(case,h,w,ci,co)
            stamp=time.perf_counter()
            execute([exe,*(['+serial'] if serial else []),f'+stall={stall}',*(['+restart'] if restart else [])],
                    case,env,case/'sim.log',timeout=240)
            elapsed=time.perf_counter()-stamp
            assert 'PASS tb_neureka_stripes' in (case/'sim.log').read_text()
            record['cases'][name]=json.loads((case/'metrics.json').read_text())
            record['timing_seconds'][name+'_simulation']=elapsed;save()
            print(name+': '+json.dumps(record['cases'][name]),flush=True)
        assert record['cases']['parallel']['compute_post_overlap_cycles']>0
        assert record['cases']['serial']['compute_post_overlap_cycles']==0
        record['status']='PASS'
    except Exception as e:
        record['status']='FAIL';record['error']=str(e);print(str(e),flush=True)
    record['timing_seconds']['total']=time.perf_counter()-start;save()
    return record['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
