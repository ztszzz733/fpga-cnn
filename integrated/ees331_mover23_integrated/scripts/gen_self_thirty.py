"""Repeat the verified ten-input fixtures three times with independent addresses.

Copies the independent integer reference, never RTL output or intermediates into
execution SRAM. Rebuilds relocations, dependency indices and 4096-task metadata.
"""
from pathlib import Path
import copy
import hashlib
import json
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def words(p):return [int(s,16) for s in p.read_text().split()]
def save_words(p,a):p.write_text(''.join(f'{v:08x}\n' for v in a),encoding='ascii')
def align(n,a=64):return (n+a-1)//a*a

def generate(source,out):
    began=time.perf_counter();m=read(source/'manifest.json')
    assert m['frames']==m['frame_contexts']==10 and m['max_tasks']==2048
    for name,h in m['files_sha256'].items():assert sha(source/name)==h,name
    assert not out.exists() or not any(out.iterdir()),'preserve existing fixtures'
    out.mkdir(parents=True,exist_ok=True)
    nf=30;tasks=4096;hw=tasks//4//32;oldhw=m['template_capacity']//32;oldlw=m['lw'];lw=10
    oldim=words(source/'image_info.hex');oldmeta=words(source/'template_meta.hex');tm=words(source/'template_commands.hex')
    oldcmd=words(source/'commands.hex');oldnodes=words(source/'node_info.hex')
    oldimages=(source/'images.bin').read_bytes();oldexpected=(source/'expected.bin').read_bytes()
    oldmemory=(source/'memory.bin').read_bytes();jobs=m['jobs'];steps=m['template_steps'];assert nf*steps<=tasks
    cursor=oldim[0];image_addrs=[];image_info=[];payload=bytearray();sources=[]
    for f in range(nf):
        src=f%10;base,n,off,_,_=oldim[5*src:5*src+5]
        image_addrs.append(align(cursor));cursor=image_addrs[-1]+n+64
        blob=oldimages[off:off+n];assert digest(blob)==m['input_sources'][src]['quantized_sha256']
        image_info.extend([image_addrs[-1],n,len(payload),0,100+f]);payload.extend(blob)
        s=copy.deepcopy(m['input_sources'][src]);s.update(frame=100+f,repeated_from_frame=100+src)
        sources.append(s);(out/f'image{f}.ppm').write_bytes((source/f'image{src}.ppm').read_bytes())
    readonly_end=align(cursor,4096);workspaces=[readonly_end+f*m['workspace_bytes'] for f in range(nf)]
    init_bytes=workspaces[-1]+m['workspace_bytes'];capacity=128*1024*1024
    assert init_bytes<=capacity
    memory=bytearray([0xa5])*init_bytes;memory[:oldim[0]]=oldmemory[:oldim[0]]
    for f in range(nf):image_info[5*f+3]=workspaces[f]
    for r in m['immutable']:assert digest(memory[r['address']:r['address']+r['bytes']])==r['sha256']
    # Inputs and all scratch bytes remain poison, never reference outputs.
    assert all(v==0xa5 for v in memory[oldim[0]:])
    metas=[];commands=[];nodes=[];reports=[];finals=[]
    with (out/'expected.bin').open('wb') as expected:
        for step in range(steps):
            meta=oldmeta[step*m['template_meta_words']:(step+1)*m['template_meta_words']]
            tail=meta[5+oldhw:];oldowner=tail[2]
            tail[2]=sum(((oldowner>>(u*oldlw))&((1<<oldlw)-1))<<(u*lw) for u in range(3))
            metas.extend(meta[:5]+meta[5:5+oldhw]+[0]*(hw-oldhw)+tail)
            for f in range(nf):
                src=f%10;oldnode=step*10+src;j=jobs[oldnode];assert j['node']==oldnode
                row=tm[step*16:(step+1)*16].copy()
                for w,mode in ((1,meta[0]&3),(2,(meta[0]>>2)&3)):
                    row[w]+=image_addrs[f] if mode==1 else workspaces[f] if mode==2 else 0
                row[3]+=workspaces[f];row[13]=100+f;row[14]=f
                # Separately relocate old expanded commands to cross-check the template.
                prior=oldcmd[oldnode*16:(oldnode+1)*16].copy()
                for w,mode in ((1,meta[0]&3),(2,(meta[0]>>2)&3)):
                    prior[w]+=(image_addrs[f]-oldim[5*src]) if mode==1 else (workspaces[f]-m['workspace_bases'][src]) if mode==2 else 0
                prior[3]+=workspaces[f]-m['workspace_bases'][src];prior[13]=100+f;prior[14]=f
                assert row==prior
                blob=oldexpected[j['expected_offset']:j['expected_offset']+j['bytes']];assert len(blob)==j['bytes']
                assert oldnodes[oldnode*4:oldnode*4+4]==[j['address'],j['bytes'],j['expected_offset'],j['layer']]
                new=copy.deepcopy(j);new.update(node=step*nf+f,frame=100+f,address=row[3],
                    expected_offset=expected.tell(),dependencies=[(d//10)*nf+f for d in j['dependencies']],slot=f*4+j['slot']%4)
                assert all(d<new['node'] and d%nf==f for d in new['dependencies'])
                reports.append(new);nodes.extend([row[3],len(blob),expected.tell(),j['layer']]);commands.extend(row);expected.write(blob)
                if j['result']:finals.append(blob)
    assert len(finals)==nf and all(digest(b)==m['final_frame_sha256'][f%10] for f,b in enumerate(finals))
    slot_pairs=[(workspaces[f]+s['offset'],s['size']) for f in range(nf) for s in m['slots']]
    expected_bytes=(out/'expected.bin').stat().st_size;assert expected_bytes==3*m['expected_bytes']
    info=[nf,steps,nf*steps,capacity,init_bytes,expected_bytes,readonly_end,len(payload)]+[x for pair in slot_pairs for x in pair]
    (out/'memory.bin').write_bytes(memory);(out/'images.bin').write_bytes(payload)
    for name,a in [('info.hex',info),('image_info.hex',image_info),('template_commands.hex',tm),('template_meta.hex',metas),('commands.hex',commands),('node_info.hex',nodes)]:save_words(out/name,a)
    new=copy.deepcopy(m);new.update(frames=nf,frame_contexts=nf,total_tasks=nf*steps,max_tasks=tasks,iw=12,template_capacity=1024,lw=lw,
        template_meta_words=10+hw,input_sources=sources,jobs=reports,total_macs=m['macs_per_frame']*nf,memory_bytes=capacity,init_bytes=init_bytes,
        readonly_end=readonly_end,expected_bytes=expected_bytes,workspace_bases=workspaces,
        slot_bases=[b for b,n in slot_pairs],slot_sizes=[n for b,n in slot_pairs],
        final_addresses=[j['address'] for j in reports if j['result']],final_expected_sha256=digest(b''.join(finals)),
        final_frame_sha256=[digest(b) for b in finals],generator_sha256=sha(__file__),generation_seconds=time.perf_counter()-began,
        replication=dict(source=str(source),manifest_sha256=sha(source/'manifest.json'),source_frames=10,repeats=3,order=[f%10+1 for f in range(nf)],
            reference='copied independent integer oracle per task; not old RTL outputs',distinct_contexts=True),
        scope='Thirty finite contexts, existing ten synthetic images repeated three times; not continuous context recycling or accuracy evidence')
    new['files_sha256']={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:new[k] for k in ('frames','full_network','total_tasks','total_macs','init_bytes','expected_bytes','final_expected_sha256')}) ,flush=True)

if __name__=='__main__':
    for size in ('small','full'):generate(ROOT/('build/self_ten_'+size),ROOT/('build/self_thirty_'+size))
