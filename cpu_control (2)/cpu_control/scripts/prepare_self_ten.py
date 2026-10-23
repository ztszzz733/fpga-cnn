"""Verify and deliver the ten-frame MobileFaceNet run; never rerun simulation."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import sys
from PIL import Image, ImageDraw, ImageFont
from plot_waveforms import read_vcd

ROOT = Path(__file__).resolve().parents[1]
COLORS = {'输入':'#94a3b8','3×3':'#51b8fa','DW3':'#ac9aff','1×1':'#ffbc69',
          'DW7':'#df8ed9','后处理':'#64d9a2','Add':'#f38181','补边':'#e2dc83'}
UNITS = ['K3#0','K3#1','K1#0','K1#1','K1#2','K1#3','DW7','Post','Add','Pad']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def local(p):
    s=str(p)
    return Path('D:/'+s[7:]) if s.startswith('/mnt/d/') else Path(s)
def font(n): return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)

def task_views(out, run, m, metric):
    dest=out/'task_timeline';dest.mkdir(exist_ok=True)
    jobs={j['node']:j for j in m['jobs']};layers={j['index']:j for j in m['layers']}
    pending={};inputs={};rows=[];finished={}
    for e in csv.DictReader((run/'overlap/events.csv').open()):
        c,f,n,u=(int(e[k]) for k in ('cycle','frame','node','unit'))
        if e['event']=='input_begin':
            assert f not in inputs;inputs[f]=c
        elif e['event']=='input_commit':
            rows.append(dict(frame=f,start=inputs[f],end=c,kind='输入',label='图片写入',unit='输入接口',layer=None,node=None))
        elif e['event']=='launch':
            assert n not in pending and n not in finished
            assert jobs[n]['frame']==f and all(dep in finished and finished[dep]<=c for dep in jobs[n]['dependencies'])
            pending[n]=(c,u,f)
        elif e['event']=='done':
            start,unit,frame=pending.pop(n);assert (unit,frame)==(u,f) and c>start
            j=jobs[n];layer=layers[j['layer']];op=j['opcode']
            kind={0:'DW3' if layer.get('depthwise') else '3×3',5:'1×1',3:'DW7',1:'后处理',2:'Add',4:'补边'}[op]
            label=f"L{j['layer']+1} {kind} / {UNITS[u]}"
            if op==1:label+=' '+{'Clip':'量化+ReLU6','Relu':'量化+ReLU'}.get(layer['activation'],'量化')
            rows.append(dict(frame=f,start=start,end=c,kind=kind,label=label,unit=UNITS[u],layer=j['layer']+1,node=n))
            finished[n]=c
    assert not pending and len(finished)==1310 and len(rows)==1320
    frames=sorted(inputs);assert frames==list(range(100,110))
    rows.sort(key=lambda j:(j['frame'],j['start']))
    for f in frames:
        frame_rows=[j for j in rows if j['frame']==f]
        assert len(frame_rows)==132 and all(a['end']<=b['start'] for a,b in zip(frame_rows,frame_rows[1:]))
    save(dest/'tasks.json',rows)
    with (dest/'tasks.csv').open('w',encoding='utf-8-sig',newline='') as h:
        writer=csv.DictWriter(h,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    total=metric['cycles']/100000
    bounds=sorted({r[k] for r in rows for k in ('start','end')})
    snapshots=[]
    for a,b in zip(bounds,bounds[1:]):
        t=(a+b)/2
        active=[r for r in rows if r['kind']!='输入' and r['start']<=t<r['end']]
        snapshots.append((t/100000,(b-a)/100000,active))
    peak=max(snapshots,key=lambda s:(len(s[2]),sum(r['kind']=='1×1' for r in s[2]),s[1]))
    cross=max(snapshots,key=lambda s:('后处理' in {r['kind'] for r in s[2]} and any(r['kind'] in ('3×3','DW3','1×1') for r in s[2]),len({r['kind'] for r in s[2]}),len(s[2]),s[1]))
    early=min(total,max(100,peak[0]*1.4));width=max(5,min(35,cross[1]*12))
    left=max(0,cross[0]-width/2);right=min(total,left+width)
    def draw(name,a,b,cursor,title):
        im=Image.new('RGB',(2100,1430),'#101820');d=ImageDraw.Draw(im)
        d.text((32,20),title,font=font(32),fill='white')
        for i,(label,color) in enumerate(COLORS.items()):
            x=32+i*245;d.rectangle((x,83,x+23,106),fill=color);d.text((x+32,77),label,font=font(22),fill='white')
        x0,x1,y0,dy=160,2040,170,72
        xx=lambda t:x0+(t-a)/(b-a)*(x1-x0)
        for i in range(11):
            t=a+(b-a)*i/10;x=xx(t);d.line((x,y0-25,x,y0+dy*10-10),fill='#2e414d')
            label=f'{t:.1f}' if b-a<100 else f'{t:.0f}'
            w=d.textlength(label,font=font(19));d.text((min(x1-w,max(x0,x-w/2)),y0-55),label,font=font(19),fill='#bbcbd5')
        for f in frames:
            y=y0+(f-100)*dy;d.text((25,y+10),f'图片 {f-99}',font=font(25),fill='white')
            d.line((x0,y+25,x1,y+25),fill='#53616b')
            for r in rows:
                if r['frame']!=f:continue
                lo=max(a,r['start']/100000);hi=min(b,r['end']/100000)
                if hi<=lo:continue
                ax,bx=xx(lo),xx(hi);d.rectangle((ax,y,bx,y+50),fill=COLORS[r['kind']])
                text=[f"L{r['layer']} {r['kind']}",r['unit']] if r['layer'] else ['输入','']
                if bx-ax>max(d.textlength(t,font=font(19)) for t in text)+12:
                    for k,t in enumerate(text):d.text((ax+6,y+2+23*k),t,font=font(19),fill='#101820')
        d.line((xx(cursor),y0-10,xx(cursor),y0+dy*10-15),fill='white',width=3)
        d.text((1740,895),'时间 / ms（假设100MHz）',font=font(20),fill='white')
        base=940;d.text((32,base),f'白线处 {cursor:.3f} ms：十张图片分别在做什么',font=font(26),fill='white')
        for f in frames:
            hit=next((r for r in rows if r['frame']==f and r['start']<=cursor*100000<r['end']),None)
            text=hit['label'] if hit else '无任务执行 / 等待下一任务'
            x=32 if f<105 else 1070;y=base+50+((f-100)%5)*46
            d.text((x,y),f'图片 {f-99}：{text}',font=font(23),fill=COLORS[hit['kind']] if hit else '#a9b5c0')
        for i,text in enumerate(['每张图片一行；同一竖直时刻跨行对照即可看到并行。L为网络层序号。',
             '色块是真实任务发射到完成，包含访存等待；不表示每拍都在MAC。灰色空隙表示没有已发射任务。',
             '本图显示范围见横轴；交互图默认完整网络，可放大任意区间。硬件时间按100MHz换算。']):
            d.text((32,1280+42*i),text,font=font(23),fill='#bbcbd5')
        im.save(dest/name)
    draw('full_network.png',0,total,peak[0],'十张图片完整MobileFaceNet：全部1,310个任务')
    draw('early_tasks.png',0,early,peak[0],'十张图片：多实例并行执行的代表区间')
    draw('cross_operator.png',left,right,cross[0],'十张图片：卷积、后处理等不同算子的并行区间')
    template=(ROOT/'scripts/self_six_tasks_view.html').read_text(encoding='utf-8')
    html=template.replace('__TASK_DATA__',json.dumps(rows,ensure_ascii=False)).replace('__COLORS__',json.dumps(COLORS,ensure_ascii=False)).replace('__END_MS__',str(total))
    html=html.replace('六图','十图').replace('六张','十张').replace('六行','十行').replace('f<106','f<110')
    html=html.replace('height:540px','height:828px').replace('${W} 540','${W} 828').replace('y2:490','y2:778')
    html=html.replace('前1000ms','卷积并行区间').replace('145–180ms：跨类交接','跨算子交接区间')
    html=html.replace('value="full">','value="full" selected>').replace('value="1000"',f'value="{total}"').replace('max="1000"',f'max="{total}"').replace('value="600"',f'value="{peak[0]}"')
    html=html.replace('let a=0,b=1000,t=600,W=1000;',f'let a=0,b={total},t={peak[0]},W=1000;')
    html=html.replace('[145,180]:[0,1000]',f'[{left},{right}]:[0,{early}]').replace('?162:600',f'?{cross[0]}:{peak[0]}')
    (dest/'index.html').write_text(html,encoding='utf-8')
    save(dest/'view_ranges.json',dict(full=[0,total],early=[0,early],cross=[left,right],peak_ms=peak[0],cross_ms=cross[0]))

def wave_views(out):
    labels=['K3#0 MAC','K3#1 MAC',*[f'K1#{i} MAC (8 lanes)' for i in range(4)],'DW7 MAC (8 lanes)','Post accepted write','Add accepted write','Pad accepted write']
    for name in ('mac_detail','pipeline_detail'):
        names=[]
        for line in (out/(name+'.vcd')).read_text().splitlines():
            if line.startswith('$var '):
                words=line.split();names.append('cnn_full.'+words[4]+(f'[{int(words[2])-1}:0]' if int(words[2])>1 else ''))
        assert len(names)==len(set(names))==10
        colors=[7,4,1,1,3,3,6,5,5,2]
        (out/(name+'.gtkw')).write_text('[dumpfile] "'+(out/(name+'.vcd')).as_posix()+'"\n'+''.join(('@22' if '[' in s else '@28')+f'\n[color] {c}\n{s}\n' for s,c in zip(names,colors)))
        (out/('verify_'+name+'.tcl')).write_text('set log [open validation_'+name+'.log w]\nset failure [catch {\nset shown [gtkwave::getDisplayedSignals]\nputs $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\nif {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing/duplicate signals"}\nputs $log "PASS"\n} message]\nif {$failure} {puts $log "FAIL $message"}\nclose $log\ngtkwave::/File/Quit\n')
        v=read_vcd(out/(name+'.vcd'));assert len(v.signals)==10
        events=v.signals['cnn_full.operator_work'].events
        im=Image.new('RGB',(1900,1000),'#101820');d=ImageDraw.Draw(im)
        d.text((30,20),'真实MAC / 接受写请求：局部256拍窗口',font=font(27),fill='white')
        x0,x1,y0,dy=370,1840,110,76
        for c in range(0,257,32):
            x=x0+(x1-x0)*c/256;d.line((x,y0-20,x,y0+10*dy),fill='#354957');d.text((x-15,y0-55),str(c),font=font(20),fill='#c6d5e1')
        ev=events+[(v.end_ns,events[-1][1])]
        for bit in range(10):
            y=y0+bit*dy;d.text((25,y+12),labels[bit],font=font(22),fill='white');points=[]
            for (t,value),(end,nxt) in zip(ev,ev[1:]):
                level=(int(value,2)>>bit)&1;py=y+40*(1-level)
                points.extend([(x0+(x1-x0)*t/v.end_ns,py),(x0+(x1-x0)*end/v.end_ns,py)])
            d.line(points,fill='#63bbef' if bit<7 else '#64d9a2',width=2)
        d.text((30,925),'横轴为窗口相对周期；高=本拍推进，低=未推进。Post/Add一次写入可含四个字节。全程见逐任务图。',font=font(23),fill='white')
        im.save(out/(name+'.png'))
    validator=(ROOT/'scripts/prepare_self_full.py').read_text(encoding='utf-8').split("(out / 'validate_gtkwave.ps1').write_text(r'''",1)[1].split("''', encoding='utf-8')",1)[0]
    validator=validator.replace("('evidence/'+$view+'.vcd')","($view+'.vcd')").replace("$contents.Contains('PASS '+$view)","$contents.Contains('PASS')")
    (out/'validate_gtkwave.ps1').write_text(validator,encoding='utf-8')

def main(run):
    run=local(run).resolve();r=read(run/'result.json')
    assert r['status']=='PASS' and r['full_network'] and r['frames']==10 and r['max_tasks']==2048
    assert r['pw8'] and r['wide_pipe'] and r['conv_overlap']
    assert isinstance(r['dw_priority'], bool)
    for name,digest in r['source_signature']['sources'].items():assert sha(ROOT/name)==digest,name
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,digest in m['files_sha256'].items():assert sha(data/name)==digest,name
    gate=local(r['gate']);g=read(gate/'result.json')
    assert g['status']=='PASS' and g['frames']==10 and not g['full_network']
    assert g['source_signature']==r['source_signature'] and g['exe_sha256']==r['exe_sha256']
    assert all(g[key]==r[key] for key in ('pw4','conv_overlap','wide_pipe','pw8','dw_priority','pool','max_tasks','frames','sram_capacity','input_pace'))
    assert set(g['scenarios'])=={'overlap','serial','preloaded','stress'}
    b=r['scenarios']['overlap']['metrics'];assert read(run/'overlap/metrics.json')==b
    for key,value in dict(commands=1310,expanded_commands=1310,allocations=1310,releases=1310,results=10,macs=2338104320,checked_bytes=193372920).items():assert b[key]==value,key
    assert m['input_shape']==[112,112,3] and m['final_bytes_per_frame']==128
    assert b['multi_frame_work_cycles']>0 and b['cross_operator_work_cycles']>0
    raw=(run/'overlap/outputs.bin').read_bytes();assert len(raw)==1280 and sha(run/'overlap/outputs.bin')==m['final_expected_sha256']
    prior=ROOT/'build/runs/20261024_003528_447842_self_six'
    old=read(prior/'result.json');old_data=read(ROOT/'build/self_six_full/manifest.json')
    assert old['status']=='PASS' and old_data['model_sha256']==m['model_sha256'] and old_data['quantization']==m['quantization']
    assert [s['quantized_sha256'] for s in old_data['input_sources']]==[s['quantized_sha256'] for s in m['input_sources'][:6]]
    assert sha(prior/'overlap/outputs.bin')==old_data['final_expected_sha256']
    assert raw[:768]==(prior/'overlap/outputs.bin').read_bytes()
    expected=(data/'expected.bin').read_bytes()
    for f,j in enumerate(j for j in m['jobs'] if j['result']):assert raw[f*128:(f+1)*128]==expected[j['expected_offset']:j['expected_offset']+j['bytes']]
    out=ROOT/'deliverables'/('self_cnn_ten_'+run.name);out.mkdir(exist_ok=True)
    for name in ('outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd'):shutil.copyfile(run/'overlap'/name,out/name)
    shutil.copyfile(run/'result.json',out/'result.json');shutil.copyfile(gate/'result.json',out/'small_gate.json')
    shutil.copyfile(data/'manifest.json',out/'data_manifest.json')
    task_views(out,run,m,b);wave_views(out)
    save(out/'summary.json',dict(status='PASS',frames=10,cycles=b['cycles'],hardware_ms_at_100MHz=b['cycles']/100000,
        simulation_seconds=b['simulation_seconds'],wall_seconds=r['wall_seconds'],compile_seconds=r['compile_seconds'],gate_compile_seconds=g['compile_seconds'],
        output_sha256=sha(out/'outputs.bin'),multi_frame_work_cycles=b['multi_frame_work_cycles'],cross_operator_work_cycles=b['cross_operator_work_cycles']))
    policy='DW3有限优先：连续两次DW3后给普通3×3优先机会；没有就绪任务时扫描回退，不抢占整层任务' if r['dw_priority'] else '原轮转调度，DW3优先关闭'
    policy_arg=' --dw-priority' if r['dw_priority'] else ''
    report=f'''# 十张图片完整MobileFaceNet仿真

完整RTL PASS：十张不同112×112 RGB合成测试图，同一批次交错执行；1,310任务、2,338,104,320 MAC、193,372,920个写出字节逐值核对。十份128字节输出合计1,280字节，与独立整数参考完全一致；前六张输出也与上一轮完整六图RTL输出逐字节相同。

|时间口径|本次实测|
|---|---:|
|硬件周期|{b['cycles']:,}拍|
|假设100MHz的整批时间|{b['cycles']/100000:.5f}ms|
|电脑模拟器主体|{b['simulation_seconds']:.3f}秒|
|电脑运行总耗时，含初始化/收尾|{r['wall_seconds']:.3f}秒|
|本次全网重新编译|{r['compile_seconds']:.3f}秒|
|小门槛首次编译，另计|{g['compile_seconds']:.3f}秒|

电脑时间与硬件时间不同；100MHz只是换算条件，未进行整机布局布线或板级频率验证。生成输入与整数参考、报告处理时间另计。

## 查看十张图的并行

- [逐图片交互图](task_timeline/index.html)：**默认显示完整网络**。每张图片一行，拖动游标查看所有图片当时的层、算子和实例；可切换或自定义放大区间。
- [全部1,310任务](task_timeline/full_network.png)、[多实例并行放大](task_timeline/early_tasks.png)、[跨算子交接放大](task_timeline/cross_operator.png)。
- [真实MAC脉冲](mac_detail.png)、[跨类推进脉冲](pipeline_detail.png)，来自实际VCD，只有256拍局部窗口。
- GTKWave打开mac_detail.gtkw或pipeline_detail.gtkw；每个会话10根唯一信号。实际载入验证见gtkwave_validation.json。

跨图实际work重叠{b['multi_frame_work_cycles']:,}拍；跨算子类别work重叠{b['cross_operator_work_cycles']:,}拍。任务条包含访存等待，不能视为每拍MAC；实际work的K3/K1/DW7表示MAC推进，Post/Add/Pad表示接受写请求。八位置K1每拍可有1～8次MAC，Post/Add一次写最多四字节。

## 本次配置与数据流

两套K3（普通3×3/DW3共享）、四套八空间位置1×1、DW7/Post/Add/Pad各一套。本次使用{policy}。十个在途上下文、40个工作缓冲槽、2,048条任务容量；CNN从单图131步模板和十份地址描述在RTL中展开1,310条任务，不是两批五图。

输入由TB经真实SRAM接口逐张写入，整张提交后该图计算，可与后续图片输入重叠；CPU固件、UART及同一图片的条带输入不在此测试内。每帧仍按层依赖顺序执行，多张图片共享算子池交错运行。中间结果经过SRAM，尚非层间直接流式融合。

仿真SRAM32MiB，初始化地址区{m['init_bytes']:,}字节，尚未适配512KiB板级存储。前六张沿用之前的合成输入，新增四张确定性数值测试图。模型预训练权重不变，诊断量化尺度取首图并固定复用；不能据此宣称人脸识别准确率。图片数与K1结构同时改变，不能拿旧六图总耗时直接计算此次加速比。

## 波形信号

|信号|含义|
|---|---|
|unit_active[9:0]|调度器分配给各算子的任务仍在途，含内部访存等待|
|operator_work[9:0]|算子本拍MAC或写结果推进，位顺序K3#0/1、K1#0～3、DW7、Post、Add、Pad|
|mem_valid / mem_ready|各算子发起访存/互连接受请求，同拍为握手|
|mem_write|该请求为写回；低为读取输入、权重或参数|
|mem_response|互连向算子返回访存完成响应|
|frames_ready[9:0]|输入图像已写完并提交的十个标志|
|result_valid / result_ready|CNN发布结果描述/外部已读完结果并确认|
|completed_count[11:0]|已完成任务数，全程最终为1,310|

局部VCD时间从窗口起点计0，全程时间以events.csv和逐任务图为准，不能把窗口长度当整批计算时间。

输出SHA256：`{sha(out/'outputs.bin')}`。运行目录：`{run}`。
复现：scripts/gen_self_ten.py生成独立数据目录；run_self_six_wsl.py --frames 10 --pw8{policy_arg}先跑build/self_ten_small四场景，完整通过后同程序--reuse --full --data build/self_ten_full --gate匹配小门槛目录。不得混用旧六图gate或不同调度策略gate。
'''
    (out/'README.md').write_text(report,encoding='utf-8')
    save(out/'provenance.json',dict(run=str(run),result_sha256=sha(run/'result.json'),reporter_sha256=sha(Path(__file__)),
        template_sha256=sha(ROOT/'scripts/self_six_tasks_view.html'),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}))
    print(out)

if __name__=='__main__':main(sys.argv[1])
