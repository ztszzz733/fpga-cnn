"""Frame-by-frame task Gantt views from recorded RTL launch/done events."""
import csv
import json
import hashlib
import argparse
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'build/runs/20261023_215237_self_six'
OUT=ROOT/'deliverables/self_cnn_six_20261023_215237_self_six/task_timeline'
COLORS={'输入':'#94a3b8','3×3':'#51b8fa','DW3':'#ac9aff','1×1':'#ffbc69','DW7':'#df8ed9','后处理':'#64d9a2','Add':'#f38181','补边':'#e2dc83'}
UNITS=['K3#0','K3#1','K1#0','K1#1','K1#2','K1#3','DW7','Post','Add','Pad']
FONT='C:/Windows/Fonts/msyh.ttc'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    global RUN,OUT
    ap=argparse.ArgumentParser()
    ap.add_argument('run',nargs='?',type=Path,default=RUN)
    args=ap.parse_args();RUN=args.run.resolve()
    OUT=ROOT/'deliverables'/('self_cnn_six_'+RUN.name)/'task_timeline'
    result=json.loads((RUN/'result.json').read_text());assert result['status']=='PASS'
    data=ROOT/'build/self_six_full';m=json.loads((data/'manifest.json').read_text())
    assert sha(data/'manifest.json')==result['manifest_sha256']
    jobs={j['node']:j for j in m['jobs']};layers={j['index']:j for j in m['layers']}
    events=list(csv.DictReader((RUN/'overlap/events.csv').open()));pending={};inputs={};rows=[]
    for e in events:
        c=int(e['cycle']);f=int(e['frame']);n=int(e['node']);u=int(e['unit'])
        if e['event']=='input_begin':inputs[f]=c
        if e['event']=='input_commit':rows.append(dict(frame=f,start=inputs[f],end=c,kind='输入',label='图片写入',unit='输入接口',layer=None,node=None))
        if e['event']=='launch':
            assert n not in pending;pending[n]=(c,u,f)
        if e['event']=='done':
            a,unit,frame=pending.pop(n);assert (unit,frame)==(u,f)
            j=jobs[n];l=layers[j['layer']];op=j['opcode']
            kind={0:'DW3' if l.get('depthwise') else '3×3',5:'1×1',3:'DW7',1:'后处理',2:'Add',4:'补边'}[op]
            label=f"L{j['layer']+1} {kind} / {UNITS[u]}"
            if op==1:label+=' '+({'Clip':'量化+ReLU6','Relu':'量化+ReLU'}.get(l['activation'],'量化'))
            rows.append(dict(frame=f,start=a,end=c,kind=kind,label=label,unit=UNITS[u],layer=j['layer']+1,node=n))
    assert not pending and len(rows)==792
    rows.sort(key=lambda x:(x['frame'],x['start']))
    for f in range(100,106):
        a=[x for x in rows if x['frame']==f]
        assert len(a)==132 and all(x['end']<=y['start'] for x,y in zip(a,a[1:]))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'tasks.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'tasks.csv').open('w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    metrics=result['scenarios']['overlap']['metrics']
    totals=metrics['cycles']/100000
    def draw(name,left,right,cursor,title):
        im=Image.new('RGB',(2100,1100),'#101820');d=ImageDraw.Draw(im)
        font=lambda n:ImageFont.truetype(FONT,n)
        d.text((40,20),title,font=font(32),fill='white')
        x=40
        for k,col in COLORS.items():
            d.rectangle((x,83,x+23,106),fill=col);d.text((x+32,77),k,font=font(22),fill='white');x+=245
        x0,x1,y0,dy=160,2040,167,83
        def xx(t):return x0+(t-left)/(right-left)*(x1-x0)
        for i in range(11):
            t=left+(right-left)*i/10;px=xx(t)
            d.line((px,y0-25,px,y0+dy*6-10),fill='#2e414d')
            label=f'{t:.0f}';width=d.textlength(label,font=font(19))
            d.text((min(x1-width,max(x0,px-width/2)),y0-55),label,font=font(19),fill='#bbcbd5')
        d.text((1750,660),'时间 / ms（假设100MHz）',font=font(20),fill='white')
        for f in range(100,106):
            y=y0+(f-100)*dy
            d.text((25,y+10),f'图片 {f-99}',font=font(25),fill='white')
            d.line((x0,y+25,x1,y+25),fill='#53616b',width=2)
            for a in rows:
                if a['frame']!=f:continue
                lo=max(left,a['start']/100000);hi=min(right,a['end']/100000)
                if hi<=lo:continue
                ax,bx=xx(lo),xx(hi);d.rectangle((ax,y,bx,y+53),fill=COLORS[a['kind']])
                texts=[f"L{a['layer']} {a['kind']}",a['unit']] if a['layer'] else ['输入','']
                if bx-ax>max(d.textlength(t,font=font(19)) for t in texts)+12:
                    for k,t in enumerate(texts):d.text((ax+6,y+3+k*23),t,font=font(19),fill='#101820')
        cx=xx(cursor);d.line((cx,y0-10,cx,y0+dy*6-15),fill='white',width=3)
        base=705;d.text((40,base),f'白线处 {cursor:g} ms：六张图片分别在做什么',font=font(26),fill='white')
        for f in range(100,106):
            hit=next((a for a in rows if a['frame']==f and a['start']<=cursor*100000<a['end']),None)
            label=hit['label'] if hit else '无任务执行 / 等待下一任务'
            x=40 if f<103 else 1080;y=base+49+((f-100)%3)*48
            d.text((x,y),f"图片 {f-99}：{label}",font=font(23),fill=COLORS[hit['kind']] if hit else '#a9b5c0')
        d.text((40,945),'横向：同一图片依次执行的任务；纵向：同一时刻不同图片正在使用哪些算子。L为网络层序号（从1开始）。',font=font(23),fill='white')
        d.text((40,986),'色块 = 实际发射到完成，包含算子内部访存等待；灰色空隙 = 没有已发射任务。色块重叠不等于每拍MAC同时有效。',font=font(22),fill='#bbcbd5')
        d.text((40,1027),'细色块在全景中可能无法标字；完整任务与精确起止时间可在交互图中查看。数据来自本次完整RTL事件记录。',font=font(22),fill='#bbcbd5')
        im.save(OUT/name)
    # Choose windows from this run, never reuse an old run's fixed timestamps.
    boundaries=sorted({r[k] for r in rows for k in ('start','end')})
    snapshots=[]
    for a,b in zip(boundaries,boundaries[1:]):
        t=(a+b)/2
        active=[r for r in rows if r['kind']!='输入' and r['start']<=t<r['end']]
        snapshots.append((t/100000,(b-a)/100000,active))
    peak=max(snapshots,key=lambda s:(len(s[2]),sum(r['kind']=='1×1' for r in s[2]),s[1]))
    cross=max(snapshots,key=lambda s:('后处理' in {r['kind'] for r in s[2]} and any(r['kind'] in ('3×3','DW3','1×1') for r in s[2]),len({r['kind'] for r in s[2]}),len(s[2]),s[1]))
    early_end=min(totals,max(100,peak[0]*1.4));cross_width=max(5,min(35,cross[1]*12))
    cross_left=max(0,cross[0]-cross_width/2);cross_right=min(totals,cross_left+cross_width)
    draw('early_tasks.png',0,early_end,peak[0],'六张图片：卷积实例并行执行的代表区间')
    draw('cross_operator.png',cross_left,cross_right,cross[0],'跨算子交接：卷积、后处理、补边如何跨图片并行')
    draw('full_network.png',0,totals,peak[0],'六张图片完整网络：按任务着色的执行全景')
    template=(ROOT/'scripts/self_six_tasks_view.html').read_text(encoding='utf-8')
    html=template.replace('__TASK_DATA__',json.dumps(rows,ensure_ascii=False)).replace('__COLORS__',json.dumps(COLORS,ensure_ascii=False)).replace('__END_MS__',str(totals))
    html=html.replace('前1000ms','卷积并行区间').replace('145–180ms：跨类交接','跨算子交接区间')
    html=html.replace('value="1000"',f'value="{early_end}"').replace('max="1000"',f'max="{early_end}"').replace('value="600"',f'value="{peak[0]}"')
    html=html.replace('let a=0,b=1000,t=600,W=1000;',f'let a=0,b={early_end},t={peak[0]},W=1000;')
    html=html.replace('[145,180]:[0,1000]',f'[{cross_left},{cross_right}]:[0,{early_end}]').replace("?162:600",f'?{cross[0]}:{peak[0]}')
    (OUT/'index.html').write_text(html,encoding='utf-8')
    (OUT/'README.md').write_text('''# 六图逐任务并行图

- [卷积并行区间](early_tasks.png)：从本次真实事件选取多实例同时执行的区间；白线下列出六张图各自的任务。
- [跨算子交接放大](cross_operator.png)：从本次事件选取卷积与后处理等不同类型同时执行的区间。
- [全程](full_network.png)：全部786个真实任务。
- [交互查看](index.html)：选择时间范围、移动时间游标，查看每张图片当前任务、层号、实例和起止时间。独立网页，无网络依赖。
- tasks.csv / tasks.json包含全部任务及六次输入，单位为硬件周期。图中ms按100MHz条件换算。

图中颜色区分运算，K3#0/1是两套3×3引擎（普通/DW3共用），K1#0～3是四套1×1引擎。每张图一条任务线，同一竖直时刻跨行对照即可看到并行。任务块按真实launch/done事件重建，含算子内部等待，不宣称每拍都在MAC；空隙只标等待，不擅自推断具体原因。当前每帧至多一个已发射任务，可跨帧并行，并非同帧多层同时执行。
''',encoding='utf-8')
    (OUT/'provenance.json').write_text(json.dumps(dict(events_sha256=sha(RUN/'overlap/events.csv'),manifest_sha256=sha(data/'manifest.json'),result_sha256=sha(RUN/'result.json'),generator_sha256=sha(Path(__file__)),template_sha256=sha(ROOT/'scripts/self_six_tasks_view.html'),tasks=786,inputs=6,files={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='provenance.json'}),indent=2))
    print(OUT)
if __name__=='__main__':main()
