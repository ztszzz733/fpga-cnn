"""Report only a completed fifteen-frame real RTL run; never launches simulation."""
from pathlib import Path
import argparse,csv,json,shutil,statistics
from PIL import Image,ImageDraw
from prepare_self_ten import ROOT,read,save,sha,local,font,COLORS,UNITS,wave_views
from prepare_self_thirty import timing

def task_views(out,run,m,metric,unit_names=None):
    names=unit_names if unit_names is not None else UNITS
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
            label=f"L{j['layer']+1} {kind} / {names[u]}"
            rows.append(dict(frame=f,start=start,end=c,kind=kind,label=label,unit=names[u],layer=j['layer']+1,node=n))
            finished[n]=c;unit_end[u]=c
        elif e['event']=='result_ack':assert f not in acks;acks[f]=c
    assert not pending and len(finished)==1965 and len(rows)==1980 and sorted(inputs)==list(range(100,115))
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
        d.text((30,height-34),'15个独立上下文，原10张输入加前5张重复；不是连续回收上下文。',font=font(20),fill='#beced8')
        im.save(dest/filename)
    draw('full_network.png',list(range(100,115)),0,total,'15张图片：完整MobileFaceNet全部1,965个任务')
    for group in range(3):draw(f'images_{group*5+1}_{group*5+5}.png',list(range(100+group*5,105+group*5)),0,total,f'图片{group*5+1}～{group*5+5}：完整网络，同一时间刻度')
    draw('cross_operator.png',list(range(100,115)),left,right,'15张图片：不同算子并行的20ms代表窗口')
    html=(ROOT/'scripts/self_six_tasks_view.html').read_text(encoding='utf-8')
    html=html.replace('__TASK_DATA__',json.dumps(rows,ensure_ascii=False)).replace('__COLORS__',json.dumps(COLORS,ensure_ascii=False)).replace('__END_MS__',str(total))
    html=html.replace('六图','15图').replace('六张','15张').replace('六行','15行').replace('f<106','f<115')
    html=html.replace('height:540px','height:1188px').replace('${W} 540','${W} 1188').replace('y2:490','y2:1138')
    html=html.replace('前1000ms','首张输出之前').replace('145–180ms：跨类交接','跨算子交接区间')
    first=min(f['read_complete'] for f in metric['frames'])/1e5
    html=html.replace('value="full">','value="full" selected>').replace('value="1000"',f'value="{total}"').replace('max="1000"',f'max="{total}"').replace('value="600"',f'value="{cross}"')
    html=html.replace('let a=0,b=1000,t=600,W=1000;',f'let a=0,b={total},t={cross},W=1000;')
    html=html.replace('[145,180]:[0,1000]',f'[{left},{right}]:[0,{first}]').replace('?162:600',f'?{cross}:{first/2}')
    (dest/'index.html').write_text(html,encoding='utf-8');return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run');ap.add_argument('--baseline-gate',required=True);a=ap.parse_args()
    run=local(a.run).resolve();r=read(run/'result.json')
    assert r['status']=='PASS' and r['full_network'] and r['frames']==15
    assert r['dw_cache'] and r['post_group']==16 and r['frame_priority'] and r['pw8']
    for name,h in r['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,h in m['files_sha256'].items():assert sha(data/name)==h,name
    g=read(local(r['gate'])/'result.json');bg=read(local(a.baseline_gate)/'result.json')
    assert g['status']==bg['status']=='PASS' and not g['full_network'] and not bg['full_network']
    assert g['frames']==bg['frames']==15 and g['manifest_sha256']==bg['manifest_sha256']
    assert g['source_signature']==r['source_signature'] and g['exe_sha256']==r['exe_sha256']
    assert g['source_signature']['sources']==bg['source_signature']['sources']
    assert not bg['dw_cache'] and bg['post_group']==4
    assert set(g['scenarios'])==set(bg['scenarios'])=={'overlap','serial','preloaded','stress'}
    b=read(run/'overlap/metrics.json');assert b==r['scenarios']['overlap']['metrics']
    for k,v in dict(commands=1965,expanded_commands=1965,allocations=1965,releases=1965,results=15,macs=3507156480,checked_bytes=290059380).items():assert b[k]==v,k
    raw=(run/'overlap/outputs.bin').read_bytes();assert len(raw)==1920 and sha(run/'overlap/outputs.bin')==m['final_expected_sha256']
    prior=ROOT/'build/runs/20261024_145116_701840_self_ten';pr=read(prior/'result.json');old=timing(pr['scenarios']['overlap']['metrics'])
    oldraw=(prior/'overlap/outputs.bin').read_bytes();assert len(oldraw)==1280 and raw==oldraw+oldraw[:640]
    assert sha(prior/'overlap/outputs.bin')==pr['scenarios']['overlap']['outputs_sha256']
    with (data/'expected.bin').open('rb') as f:
        for i,j in enumerate(j for j in m['jobs'] if j['result']):f.seek(j['expected_offset']);assert f.read(128)==raw[i*128:(i+1)*128]
    out=ROOT/'deliverables'/('self_cnn_fifteen_'+run.name);out.mkdir(exist_ok=True)
    for name in ('outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd'):shutil.copyfile(run/'overlap'/name,out/name)
    for name,path in [('result.json',run/'result.json'),('data_manifest.json',data/'manifest.json'),('small_gate.json',local(r['gate'])/'result.json'),('baseline_small_gate.json',local(a.baseline_gate)/'result.json')]:shutil.copyfile(path,out/name)
    rows=task_views(out,run,m,b);wave_views(out);t=timing(b)
    comp={mode:dict(before=bg['scenarios'][mode]['metrics']['cycles'],after=g['scenarios'][mode]['metrics']['cycles']) for mode in g['scenarios']}
    for v in comp.values():v['cycle_reduction_percent']=(1-v['after']/v['before'])*100
    save(out/'summary.json',dict(status='PASS',frames=15,cycles=b['cycles'],timing=t,baseline_ten=old,small_comparison=comp,wall_seconds=r['wall_seconds'],simulation_seconds=b['simulation_seconds'],compile_seconds=r['compile_seconds'],output_sha256=sha(out/'outputs.bin'),same_fifteen_full_baseline=False))
    with (out/'output_timing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['image','read_complete_ms','gap_ms'])
        for i,(im,tm) in enumerate(zip(t['output_order'],t['output_ms'])):w.writerow([im,tm,None if i==0 else t['gaps_ms'][i-1]])
    im=Image.new('RGB',(1900,950),'#101820');d=ImageDraw.Draw(im)
    d.text((30,25),'15张完整MobileFaceNet：结果输出节奏',font=font(32),fill='white')
    d.text((30,83),f"首张 {t['first_ms']:.3f}ms；整批 {t['batch_ms']:.3f}ms；100MHz条件换算",font=font(25),fill='#c5d5df')
    x0,x1,y0,y1=100,1830,185,600;limit=t['batch_ms'];xx=lambda v:x0+(x1-x0)*v/limit
    for i in range(6):
        y=y1-(y1-y0)*i/5;d.line((x0,y,x1,y),fill='#30444f');d.text((40,y-12),str(i*3),font=font(20),fill='white')
    pts=[(x0,y1)]
    for i,tm in enumerate(t['output_ms']):pts.extend([(xx(tm),y1-(y1-y0)*i/15),(xx(tm),y1-(y1-y0)*(i+1)/15)])
    d.line(pts,fill='#64d9a2',width=4)
    for i in range(8):
        v=limit*i/7;d.text((min(x1-70,max(x0,xx(v)-20)),620),f'{v:.0f}',font=font(20),fill='white')
    for i,gap in enumerate(t['gaps_ms']):
        x=30+(i%7)*263;y=680+(i//7)*75;d.text((x,y),f'{i+1}→{i+2}: {gap:.2f}ms',font=font(22),fill='#64d9a2')
    d.text((30,863),f"相邻间隔平均 {t['mean_gap_ms']:.3f}ms，范围 {t['min_gap_ms']:.3f}～{t['max_gap_ms']:.3f}ms；有限批次，非无限稳态。",font=font(24),fill='white')
    im.save(out/'output_cadence.png')
    table='\n'.join(f"|{mode}|{v['before']}|{v['after']}|{v['cycle_reduction_percent']:.2f}%|" for mode,v in comp.items())
    text=f"""# 15张图片完整MobileFaceNet仿真

完整RTL PASS：1965任务、3507156480 MAC、290059380写出字节逐值核验。15份128字节输出共1920字节，与独立整数参考和旧十图输出加前五图完全一致。

本轮优化：DW3整层权重在原有RAM中缓存一次，各空间块复用，每个新命令重新加载；Post/Add将内部结果分组4→16个字节，仍每次32位写出且只有一个未完成外部请求。K3×2、K1×4、DW7/Post/Add/Pad各1保持不变。还修复了宽读取在非对齐、剩余通道不足4时越过像素边界的问题；默认关闭新优化仍保留该正确性修复。

## 查看

- [逐图片交互并行图](task_timeline/index.html)、[完整15图PNG](task_timeline/full_network.png)。
- 分组大字图：[1—5](task_timeline/images_1_5.png)、[6—10](task_timeline/images_6_10.png)、[11—15](task_timeline/images_11_15.png)。
- [跨算子窗口](task_timeline/cross_operator.png)、[输出节奏](output_cadence.png)、[逐结果时间表](output_timing.csv)。
- [MAC推进波形](mac_detail.png)、[跨类推进波形](pipeline_detail.png)，同名VCD/GTKWave各10根唯一信号。

## 时间和对照

整批{b['cycles']:,}周期，假设100MHz为{t['batch_ms']:.3f}ms；首张{t['first_ms']:.3f}ms。14个相邻间隔平均{t['mean_gap_ms']:.3f}ms、最小{t['min_gap_ms']:.3f}、最大{t['max_gap_ms']:.3f}ms。电脑模拟器主体{b['simulation_seconds']:.3f}秒，含初始化收尾{r['wall_seconds']:.3f}秒，本次完整运行编译{r['compile_seconds']:.3f}秒。小门槛编译{g['compile_seconds']:.3f}秒与四场景{g['wall_seconds']:.3f}秒另计。

相同15图小数据、相同源码与接口条件，分别关闭/开启本轮两项优化：

|模式|优化前周期|优化后周期|周期减少|
|---|---:|---:|---:|
{table}

这些百分比只属于小数据回归，不代表全网增速。没有运行同配置优化前15图全网。上一轮10图整批{old['batch_ms']:.3f}ms、首张{old['first_ms']:.3f}ms，仅提供规模不同的历史参照，不直接计算加速比。

输入为原10张合成112×112RGB再重复前5张，15个独立有限上下文，每张实际完整计算；整图经存储接口写完后提交，无CPU/UART/同图条带输入。实验SRAM64MiB，初始化{m['init_bytes']:,}字节；不代表板级存储适配。量化仍使用诊断尺度，不作识别准确率结论。100MHz是周期换算，未证明整机上板时序。色块含等待，实际work跨图重叠{b['multi_frame_work_cycles']:,}拍、跨类{b['cross_operator_work_cycles']:,}拍；有限15图不等于无限稳态输出。

原始run：{run}。输出SHA256：{sha(out/'outputs.bin')}。所有源/输入/输出与小门槛程序哈希核验通过；图像和GTKWave人工视检/实际加载结果以artifact_validation.json为准。
"""
    (out/'README.md').write_text(text,encoding='utf-8')
    save(out/'provenance.json',dict(run=str(run),result_sha256=sha(run/'result.json'),reporter_sha256=sha(Path(__file__)),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}))
    print(out);print(json.dumps(t))

if __name__=='__main__':main()
