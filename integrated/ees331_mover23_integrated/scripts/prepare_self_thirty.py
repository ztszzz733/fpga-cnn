"""Verify and report one full thirty-frame run; never start or repeat simulation."""
from pathlib import Path
import csv
import json
import shutil
import statistics
import sys
from PIL import Image, ImageDraw
from prepare_self_ten import ROOT, read, save, sha, local, font, COLORS, UNITS, wave_views

BASE=ROOT/'build/runs/20261024_145116_701840_self_ten'

def timing(metric):
    frames=sorted(metric['frames'],key=lambda f:f['read_complete'])
    times=[f['read_complete']/1e5 for f in frames]
    gaps=[b-a for a,b in zip(times,times[1:])]
    return dict(first_ms=times[0],last_ms=times[-1],batch_ms=metric['cycles']/1e5,
        output_order=[f['frame']-99 for f in frames],output_ms=times,gaps_ms=gaps,
        min_gap_ms=min(gaps),max_gap_ms=max(gaps),mean_gap_ms=statistics.mean(gaps),
        median_gap_ms=statistics.median(gaps),batch_ms_per_image=metric['cycles']/1e5/len(frames),
        latencies_ms=[(f['read_complete']-f['input_commit'])/1e5 for f in frames])

def task_views(out,run,m,metric):
    dest=out/'task_timeline';dest.mkdir(exist_ok=True)
    jobs={j['node']:j for j in m['jobs']};layers={j['index']:j for j in m['layers']}
    pending={};inputs={};finished={};rows=[];acks={};unit_end={}
    for e in csv.DictReader((run/'overlap/events.csv').open()):
        c,f,n,u=(int(e[k]) for k in ('cycle','frame','node','unit'))
        if e['event']=='input_begin':assert f not in inputs;inputs[f]=c
        elif e['event']=='input_commit':rows.append(dict(frame=f,start=inputs[f],end=c,kind='输入',label='图片写入',unit='输入接口',layer=None,node=None))
        elif e['event']=='launch':
            assert n not in pending and n not in finished
            assert jobs[n]['frame']==f and all(dep in finished and finished[dep]<=c for dep in jobs[n]['dependencies'])
            assert metric['units'][u]['kind']==jobs[n]['opcode'] and c>=unit_end.get(u,0)
            assert all(p[1]!=u for p in pending.values()),'operator double booking'
            pending[n]=(c,u,f)
        elif e['event']=='done':
            start,unit,frame=pending.pop(n);assert (unit,frame)==(u,f) and c>start
            j=jobs[n];layer=layers[j['layer']];op=j['opcode']
            kind={0:'DW3' if layer.get('depthwise') else '3×3',5:'1×1',3:'DW7',1:'后处理',2:'Add',4:'补边'}[op]
            label=f"L{j['layer']+1} {kind} / {UNITS[u]}"
            rows.append(dict(frame=f,start=start,end=c,kind=kind,label=label,unit=UNITS[u],layer=j['layer']+1,node=n))
            finished[n]=c;unit_end[u]=c
        elif e['event']=='result_ack':assert f not in acks;acks[f]=c
    assert not pending and len(finished)==3930 and len(rows)==3960 and sorted(inputs)==list(range(100,130))
    rows.sort(key=lambda j:(j['frame'],j['start']))
    for f in metric['frames']:
        seq=[r for r in rows if r['frame']==f['frame']]
        assert len(seq)==132 and all(a['end']<=b['start'] for a,b in zip(seq,seq[1:]))
        assert seq[0]['end']==f['input_commit'] and seq[1]['start']==f['first_launch']
        assert seq[-1]['end']<acks[f['frame']]==f['read_complete']
    save(dest/'tasks.json',rows)
    with (dest/'tasks.csv').open('w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    total=metric['cycles']/1e5
    # Select a genuine cross-operator interval without a quadratic scan.
    edges=[]
    for i,r in enumerate(rows):
        if r['node'] is not None:edges.extend([(r['start'],1,i),(r['end'],-1,i)])
    edges.sort();active=set();best=(0,0,0);cross=0;index=0
    while index<len(edges):
        cycle=edges[index][0]
        while index<len(edges) and edges[index][0]==cycle:
            _,change,k=edges[index];active.add(k) if change==1 else active.remove(k);index+=1
        if index<len(edges):
            kinds={rows[k]['kind'] for k in active};score=(len(kinds),len(active),edges[index][0]-cycle)
            if score>best:best=score;cross=(cycle+edges[index][0])/2e5
    left=max(0,cross-10);right=min(total,left+20)
    def draw(filename,frames,a,b,title):
        dy=47 if len(frames)>10 else 73;height=240+len(frames)*dy
        im=Image.new('RGB',(2100,height),'#101820');d=ImageDraw.Draw(im)
        d.text((30,18),title,font=font(29),fill='white')
        for i,(name,color) in enumerate(COLORS.items()):
            x=30+i*245;d.rectangle((x,73,x+20,94),fill=color);d.text((x+30,68),name,font=font(22),fill='white')
        x0,x1,y0=150,2040,155;xx=lambda t:x0+(t-a)/(b-a)*(x1-x0)
        for i in range(11):
            t=a+(b-a)*i/10;x=xx(t);d.line((x,y0-10,x,y0+dy*len(frames)),fill='#30444f')
            s=f'{t:.1f}' if b-a<100 else f'{t:.0f}';width=d.textlength(s,font=font(19))
            d.text((min(x1-width,max(x0,x-width/2)),y0-38),s,font=font(19),fill='#beced8')
        for i,f in enumerate(frames):
            y=y0+i*dy;d.text((18,y+7),f'图片 {f-99}',font=font(22),fill='white')
            d.line((x0,y+dy*.4,x1,y+dy*.4),fill='#53616b')
            for r in rows:
                if r['frame']!=f:continue
                lo=max(a,r['start']/1e5);hi=min(b,r['end']/1e5)
                if hi<=lo:continue
                ax,bx=xx(lo),xx(hi);d.rectangle((ax,y,bx,y+dy-13),fill=COLORS[r['kind']])
                s=f"L{r['layer']} {r['kind']}" if r['layer'] else '输入'
                if bx-ax>d.textlength(s,font=font(18))+12:d.text((ax+5,y+3),s,font=font(18),fill='#101820')
        d.text((30,height-65),'同一竖直时刻跨行看并行；色块含访存等待。横轴ms按100MHz换算，非电脑耗时。',font=font(22),fill='#beced8')
        d.text((30,height-34),'30个独立上下文，现有10张输入重复三遍；不是连续回收上下文。',font=font(20),fill='#beced8')
        im.save(dest/filename)
    draw('full_network.png',list(range(100,130)),0,total,'30张图片：完整MobileFaceNet全部3,930个任务')
    for group in range(3):draw(f'images_{group*10+1}_{group*10+10}.png',list(range(100+group*10,110+group*10)),0,total,f'图片{group*10+1}～{group*10+10}：完整网络，同一时间刻度')
    draw('cross_operator.png',list(range(100,130)),left,right,'30张图片：不同算子并行的20ms代表窗口')
    html=(ROOT/'scripts/self_six_tasks_view.html').read_text(encoding='utf-8')
    html=html.replace('__TASK_DATA__',json.dumps(rows,ensure_ascii=False)).replace('__COLORS__',json.dumps(COLORS,ensure_ascii=False)).replace('__END_MS__',str(total))
    html=html.replace('六图','30图').replace('六张','30张').replace('六行','30行').replace('f<106','f<130')
    html=html.replace('height:540px','height:2268px').replace('${W} 540','${W} 2268').replace('y2:490','y2:2218')
    html=html.replace('前1000ms','首张输出之前').replace('145–180ms：跨类交接','跨算子交接区间')
    first=min(f['read_complete'] for f in metric['frames'])/1e5
    html=html.replace('value="full">','value="full" selected>').replace('value="1000"',f'value="{total}"').replace('max="1000"',f'max="{total}"').replace('value="600"',f'value="{cross}"')
    html=html.replace('let a=0,b=1000,t=600,W=1000;',f'let a=0,b={total},t={cross},W=1000;')
    html=html.replace('[145,180]:[0,1000]',f'[{left},{right}]:[0,{first}]').replace('?162:600',f'?{cross}:{first/2}')
    (dest/'index.html').write_text(html,encoding='utf-8');return rows

def cadence(out,old,new):
    im=Image.new('RGB',(2000,1280),'#101820');d=ImageDraw.Draw(im);x0,x1=150,1930
    d.text((30,20),'10张 vs 30张：结果何时陆续输出',font=font(33),fill='white')
    d.text((30,74),'同一算子池与图片优先调度；30张采用原10张数据重复三遍，各自完整计算。',font=font(24),fill='#c2d1db')
    limit=max(old['batch_ms'],new['batch_ms'])*1.025;xx=lambda t:x0+t/limit*(x1-x0)
    for i in range(7):
        y=640-i*80;d.line((x0,y,x1,y),fill='#30444f');d.text((85,y-12),str(i*5),font=font(22),fill='white')
    for i in range(9):
        t=limit*i/8;x=xx(t);d.line((x,160,x,640),fill='#30444f');d.text((x-20,660),f'{t:.0f}',font=font(20),fill='#c2d1db')
    d.text((30,125),'已输出张数',font=font(23),fill='white')
    for data,color,name in ((old,'#9bacc0','10张'),(new,'#62d7b5','30张')):
        pts=[(x0,640)];count=0
        for t in data['output_ms']:pts.extend([(xx(t),640-count*16),(xx(t),640-(count+1)*16)]);count+=1
        pts.append((x1,640-count*16));d.line(pts,fill=color,width=4)
        d.text((400 if name=='10张' else 1100,120),f"{name}：首张{data['first_ms']:.1f}ms / 整批{data['batch_ms']:.1f}ms",font=font(22),fill=color)
    d.text((1690,704),'时间/ms（100MHz）',font=font(22),fill='white')
    d.text((30,750),'30张：全部29个相邻输出间隔 / ms',font=font(28),fill='white')
    for i,gap in enumerate(new['gaps_ms']):
        x=35+(i%10)*195;y=810+(i//10)*90
        d.text((x,y),f'{i+1}→{i+2}',font=font(20),fill='#beced8');d.text((x,y+30),f'{gap:.2f}',font=font(25),fill='#62d7b5')
    d.text((30,1110),f"平均{new['mean_gap_ms']:.2f}ms；中位数{new['median_gap_ms']:.2f}ms；最小{new['min_gap_ms']:.2f}ms；最大{new['max_gap_ms']:.2f}ms。",font=font(25),fill='white')
    d.text((30,1170),'首张等待与整批时间必须一起看；有限30图只能观察输出节奏，不能证明无限持续吞吐。',font=font(23),fill='#beced8')
    im.save(out/'output_cadence.png')

def main(run):
    run=local(run).resolve();r=read(run/'result.json');assert r['status']=='PASS' and r['frames']==30 and r['full_network']
    assert r['frame_priority'] and r['pw8'] and not r['dw_priority'] and r['max_tasks']==4096
    for name,h in r['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,h in m['files_sha256'].items():assert sha(data/name)==h,name
    gate=read(local(r['gate'])/'result.json');assert gate['status']=='PASS' and not gate['full_network'] and gate['frames']==30
    assert gate['source_signature']==r['source_signature'] and gate['exe_sha256']==r['exe_sha256']
    assert set(gate['scenarios'])=={'overlap','serial','preloaded','stress'}
    b=read(run/'overlap/metrics.json');assert b==r['scenarios']['overlap']['metrics']
    for key,value in dict(commands=3930,expanded_commands=3930,allocations=3930,releases=3930,results=30,macs=7014312960,checked_bytes=580118760).items():assert b[key]==value,key
    assert m['input_shape']==[112,112,3] and m['final_bytes_per_frame']==128 and m['frame_contexts']==30
    raw=(run/'overlap/outputs.bin').read_bytes();assert len(raw)==3840 and sha(run/'overlap/outputs.bin')==m['final_expected_sha256']
    base=read(BASE/'result.json');olddata=read(local(base['data'])/'manifest.json');bm=base['scenarios']['overlap']['metrics']
    assert base['status']=='PASS' and base['frame_priority'] and r['pool']==base['pool'] and r['input_pace']==base['input_pace']
    assert m['model_sha256']==olddata['model_sha256'] and m['quantization']==olddata['quantization']
    assert m['replication']['manifest_sha256']==base['manifest_sha256']
    assert sha(BASE/'overlap/outputs.bin')==olddata['final_expected_sha256'] and raw==(BASE/'overlap/outputs.bin').read_bytes()*3
    for f,s in enumerate(m['input_sources']):assert s['quantized_sha256']==olddata['input_sources'][f%10]['quantized_sha256']
    changed=[name for name,h in base['source_signature']['sources'].items() if r['source_signature']['sources'][name]!=h]
    assert set(changed)<={'tb/integration/self_full_main.cpp'},changed
    with (data/'expected.bin').open('rb') as expected:
        for f,j in enumerate(j for j in m['jobs'] if j['result']):expected.seek(j['expected_offset']);assert expected.read(128)==raw[f*128:(f+1)*128]
    out=ROOT/'deliverables'/('self_cnn_thirty_'+run.name);out.mkdir(exist_ok=True)
    for name in ('outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd'):shutil.copyfile(run/'overlap'/name,out/name)
    shutil.copyfile(run/'result.json',out/'result.json');shutil.copyfile(data/'manifest.json',out/'data_manifest.json')
    save(out/'small_gate.json',gate);save(out/'baseline_ten_result.json',base)
    rows=task_views(out,run,m,b);wave_views(out)
    old=timing(bm);new=timing(b);cadence(out,old,new)
    summary=dict(status='PASS',frames=30,cycles=b['cycles'],hardware_ms_at_100MHz=b['cycles']/1e5,
        simulation_seconds=b['simulation_seconds'],wall_seconds=r['wall_seconds'],compile_seconds=r['compile_seconds'],
        small_compile_seconds=gate['compile_seconds'],small_wall_seconds=gate['wall_seconds'],baseline_ten=old,thirty=new,
        output_sha256=sha(out/'outputs.bin'),matches_ten_repeated_three_times=True,rtl_source_hashes_unchanged=True,changed_sources=changed)
    save(out/'summary.json',summary)
    records=[];previous=None
    for rank,f in enumerate(sorted(b['frames'],key=lambda f:f['read_complete']),1):
        final=next(j for j in m['jobs'] if j['frame']==f['frame'] and j['result'])
        last=next(row for row in rows if row['node']==final['node'])
        records.append(dict(rank=rank,image=f['frame']-99,source_image=(f['frame']-100)%10+1,input_commit_ms=f['input_commit']/1e5,
            compute_complete_ms=last['end']/1e5,read_complete_ms=f['read_complete']/1e5,
            interval_ms=None if previous is None else (f['read_complete']-previous)/1e5,
            response_ms=(f['read_complete']-f['input_commit'])/1e5));previous=f['read_complete']
    with (out/'output_timing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    table='\n'.join(f"|{v['rank']}|{v['image']}|{v['source_image']}|{v['read_complete_ms']:.3f}|{v['interval_ms']:.3f}|{v['response_ms']:.3f}|" if v['interval_ms'] is not None else f"|1|{v['image']}|{v['source_image']}|{v['read_complete_ms']:.3f}|—|{v['response_ms']:.3f}|" for v in records)
    groups=[]
    for lo,hi in ((1,10),(11,20),(21,30)):
        intervals=[v['interval_ms'] for v in records[lo-1:hi] if v['interval_ms'] is not None]
        groups.append(f"|第{lo}～{hi}个结果|{statistics.mean(intervals):.3f}|{min(intervals):.3f}|{max(intervals):.3f}|")
    report=f'''# 30张图片完整MobileFaceNet：较早图片优先

完整RTL PASS。现有10张112×112 RGB合成图按1～10、1～10、1～10输入，各有独立帧号和工作空间，每张都实际执行完整网络，非复用旧计算结果。3930任务、7014312960 MAC、580118760写出字节逐值核验，30份128字节输出共3840字节，与独立整数参考及旧十图输出重复三遍均完全一致。

|指标（100MHz条件）|之前10张|本次30张|
|---|---:|---:|
|首个结果读完|{old['first_ms']:.3f}ms|{new['first_ms']:.3f}ms|
|整批结束|{old['batch_ms']:.3f}ms|{new['batch_ms']:.3f}ms|
|整批时间÷图片数，非单图延迟|{old['batch_ms_per_image']:.3f}ms|{new['batch_ms_per_image']:.3f}ms|
|首张之后平均输出间隔|{old['mean_gap_ms']:.3f}ms|{new['mean_gap_ms']:.3f}ms|
|最小～最大输出间隔|{old['min_gap_ms']:.3f}～{old['max_gap_ms']:.3f}ms|{new['min_gap_ms']:.3f}～{new['max_gap_ms']:.3f}ms|

首张等待不计入“相邻间隔”平均，不能据此单独宣称稳定帧率。以下按实际输出顺序分段；第11～20、21～30段包括从上一段最后一个结果到本段第一个结果的间隔。

|输出区段|平均间隔ms|最小ms|最大ms|
|---|---:|---:|---:|
{chr(10).join(groups)}

## 查看结果

- [输出节奏与10图对比](output_cadence.png)、[所有输出时刻CSV](output_timing.csv)。
- [30行逐图片交互图](task_timeline/index.html)：默认完整网络，游标同一时刻查看各图运行的层和算子。
- [30图全程PNG](task_timeline/full_network.png)；更大字号的[1～10](task_timeline/images_1_10.png)、[11～20](task_timeline/images_11_20.png)、[21～30](task_timeline/images_21_30.png)三图共用同一时间轴。
- [跨算子并行窗口](task_timeline/cross_operator.png)。色块是发射至完成，包含访存等待。
- [真实MAC脉冲](mac_detail.png)、[跨类推进脉冲](pipeline_detail.png)：仅256拍窗口，非全网时间；GTKWave打开同名.gtkw，每个会话10根唯一信号。

## 实际配置、时间和边界

保持K3×2、八空间位置K1×4、DW7/Post/Add/Pad各1，FRAME_PRIORITY=1，输入pace80。算术与调度RTL源未变，参数从10上下文/2048任务/40槽扩大到30上下文/4096任务/120槽；任务表扫描1310→3930条，调度扫描开销也变化。测试台补齐12位任务号及120位缓存分配/释放统计。

仿真SRAM从32MiB扩大为128MiB，仅增加地址容量，未增加端口或改变存储响应协议。初始化{m['init_bytes']:,}字节，约{m['init_bytes']/2**20:.3f}MiB，存储不是板级容量承诺。输入通过实际SRAM接口逐张写入，整图提交后该图才能计算。30个有限上下文不是10上下文循环接30张；没有无限连续接收/CPU/UART/同帧条带/准确率或512KiB适配结论。量化仍诊断尺度，图片重复不作识别准确率测试。

电脑模拟器主体{b['simulation_seconds']:.3f}秒，含初始化收尾{r['wall_seconds']:.3f}秒；全网重编译{r['compile_seconds']:.3f}秒。小门槛编译{gate['compile_seconds']:.3f}秒，四场景{gate['wall_seconds']:.3f}秒另计。硬件{b['cycles']:,}周期，按100MHz为{b['cycles']/1e5:.3f}ms；100MHz没有整机上板时序保证。

实际跨图work重叠{b['multi_frame_work_cycles']:,}拍、跨算子类别work重叠{b['cross_operator_work_cycles']:,}拍；任务busy含等待，不能当作每拍MAC。波形依次为unit_active、operator_work、mem_valid、mem_ready、mem_write、mem_response、frames_ready[29:0]、result_valid、result_ready、completed_count[12:0]；含义沿用上一轮，result_ready是外部已读完确认。

## 逐个结果

|输出序号|图片编号|原十图中的编号|输出时刻ms|距前次ms|输入提交至输出ms|
|---|---:|---:|---:|---:|---:|
{table}

输出SHA256：{sha(out/'outputs.bin')}。完整运行目录：{run}。复现使用gen_self_thirty.py从已验证十图数据复制重定位；run_self_six_wsl.py --frames 30 --pw8 --frame-priority先运行build/self_thirty_small四场景，同源码/同程序通过后--reuse --full --data build/self_thirty_full --gate匹配小门槛目录。
'''
    (out/'README.md').write_text(report,encoding='utf-8')
    save(out/'provenance.json',dict(run=str(run),result_sha256=sha(run/'result.json'),reporter_sha256=sha(__file__),
        files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}))
    print(out);print(json.dumps({k:new[k] for k in ('first_ms','batch_ms','min_gap_ms','max_gap_ms','mean_gap_ms')}))

if __name__=='__main__':main(sys.argv[1])
