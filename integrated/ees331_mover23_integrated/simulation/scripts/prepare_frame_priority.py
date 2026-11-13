"""Compare actual full ten-frame RTL runs, including output cadence, not an estimate."""
from pathlib import Path
import csv
import json
import shutil
import statistics
import sys
from PIL import Image, ImageDraw
from prepare_self_ten import ROOT, read, save, sha, local, font, main as prepare_ten

BASE = ROOT/'build/runs/20261024_014153_249128_self_ten'
ALLOWED_SOURCE_CHANGES = {'rtl/cnn_stream/stream_dispatch.sv','rtl/cnn_stream/self_stream_top.sv',
    'rtl/cnn_stream/self_fixed_network_top.sv','tb/self_full_sim_top.sv'}

def analyze(run, manifest):
    r = read(run/'result.json'); m = read(run/'overlap/metrics.json')
    assert r['status']=='PASS' and m==r['scenarios']['overlap']['metrics']
    assert sha(run/'overlap/outputs.bin')==manifest['final_expected_sha256']
    events = list(csv.DictReader((run/'overlap/events.csv').open()))
    end = {int(e['node']):int(e['cycle']) for e in events if e['event']=='done'}
    start = {int(e['node']):int(e['cycle']) for e in events if e['event']=='launch'}
    ack = {int(e['frame']):int(e['cycle']) for e in events if e['event']=='result_ack'}
    assert len(start)==len(end)==1310 and len(ack)==10
    jobs = manifest['jobs']; final = {j['frame']:j for j in jobs if j['result']}
    rows=[]
    for f in m['frames']:
        tag=f['frame']; assert ack[tag]==f['read_complete']
        compute=end[final[tag]['node']]; assert compute<f['read_complete']
        # L2 is the first depthwise layer, after the first convolution + post.
        dw = next(j for j in jobs if j['frame']==tag and j['layer']==1 and j['opcode']==0)
        pad = next(j for j in jobs if j['frame']==tag and j['layer']==1 and j['opcode']==4)
        rows.append(dict(image=tag-99,frame=tag,input_commit_ms=f['input_commit']/1e5,
            compute_complete_ms=compute/1e5,read_complete_ms=f['read_complete']/1e5,
            input_to_read_ms=(f['read_complete']-f['input_commit'])/1e5,
            l2_pad_to_dw3_wait_ms=(start[dw['node']]-end[pad['node']])/1e5))
    ordered=sorted(rows,key=lambda row:row['read_complete_ms'])
    gaps=[b['read_complete_ms']-a['read_complete_ms'] for a,b in zip(ordered,ordered[1:])]
    return dict(run=str(run),result_sha256=sha(run/'result.json'),cycles=m['cycles'],
        batch_ms=m['cycles']/1e5,first_output_ms=ordered[0]['read_complete_ms'],
        first_compute_ms=min(row['compute_complete_ms'] for row in rows),
        output_order=[row['image'] for row in ordered],output_ms=[row['read_complete_ms'] for row in ordered],
        gaps_ms=gaps,gap_min_ms=min(gaps),gap_max_ms=max(gaps),gap_mean_ms=statistics.mean(gaps),
        batch_amortized_ms_per_image=m['cycles']/1e6,frames=rows,
        multi_frame_work_cycles=m['multi_frame_work_cycles'],cross_operator_work_cycles=m['cross_operator_work_cycles'],
        simulation_seconds=m['simulation_seconds'],wall_seconds=r['wall_seconds'],compile_seconds=r['compile_seconds'])

def plot(out, old, new):
    im=Image.new('RGB',(1960,1420),'#101820');d=ImageDraw.Draw(im)
    colors=['#9baabd','#62d7b5'];x0,x1=190,1880;limit=max(old['batch_ms'],new['batch_ms'])*1.025
    xx=lambda t:x0+(x1-x0)*t/limit
    d.text((35,20),'十图结果输出节奏：原轮转 vs 较早提交图片优先',font=font(33),fill='white')
    d.text((35,73),'真实RTL事件；时间从仿真起点计，按100MHz换算。输出=外部已读完128字节并确认。',font=font(23),fill='#c3d0dc')
    top,bottom=170,660
    for i in range(11):
        y=bottom-(bottom-top)*i/10;d.line((x0,y,x1,y),fill='#2a3d48')
        d.text((135,y-13),str(i),font=font(20),fill='#c3d0dc')
    for i in range(9):
        t=limit*i/8;x=xx(t);d.line((x,top,x,bottom),fill='#2a3d48')
        d.text((x-20,bottom+15),f'{t:.0f}',font=font(20),fill='#c3d0dc')
    d.text((35,130),'已输出张数',font=font(24),fill='white')
    for data,color in zip((old,new),colors):
        points=[(x0,bottom)];count=0
        for t in data['output_ms']:
            points += [(xx(t),bottom-(bottom-top)*count/10),(xx(t),bottom-(bottom-top)*(count+1)/10)];count+=1
        points.append((x1,top));d.line(points,fill=color,width=4)
    for i,(name,data,color) in enumerate(zip(('原轮转','图片优先'),(old,new),colors)):
        d.text((250+i*750,115),f"{name}：首张 {data['first_output_ms']:.1f}ms / 整批 {data['batch_ms']:.1f}ms",font=font(23),fill=color)
    d.text((1660,715),'时间 / ms',font=font(21),fill='white')
    d.text((35,755),'每次输出间隔（按实际输出顺序，共九个；不包含首次等待）',font=font(27),fill='white')
    y0=825;cols=9;cw=(x1-x0)/cols
    for i in range(cols):
        x=x0+cw*i
        d.text((x+10,y0),f'{i+1} → {i+2}',font=font(22),fill='#c3d0dc')
        d.text((x+10,y0+53),f"{old['gaps_ms'][i]:.2f}",font=font(25),fill=colors[0])
        d.text((x+10,y0+105),f"{new['gaps_ms'][i]:.2f}",font=font(25),fill=colors[1])
    d.text((35,y0+53),'原轮转',font=font(23),fill=colors[0]);d.text((35,y0+105),'图片优先',font=font(23),fill=colors[1])
    lines=[f"图片优先的输出顺序：{' → '.join(map(str,new['output_order']))}",
        f"相邻间隔：平均 {new['gap_mean_ms']:.2f}ms，最小 {new['gap_min_ms']:.2f}ms，最大 {new['gap_max_ms']:.2f}ms。",
        '原轮转末尾集中返回，短间隔不代表稳定高帧率；新策略也要同时观察首张等待和整批时间。',
        '本次是有限十图批次，尚未验证无限连续输入、上下文循环复用或固定100ms输出。',
        '逐图片计算过程见 task_timeline/index.html；不通过扣留结果人为制造均匀节拍。']
    for i,line in enumerate(lines):d.text((35,1035+i*61),line,font=font(25),fill='#c3d0dc')
    im.save(out/'output_cadence.png')

def main(run):
    run=local(run).resolve();r=read(run/'result.json');base=read(BASE/'result.json')
    assert r['frame_priority'] and not r['dw_priority'] and not base.get('frame_priority',False)
    assert r['manifest_sha256']==base['manifest_sha256']
    for key in ('frames','max_tasks','full_network','pw4','conv_overlap','wide_pipe','pw8','pool','sram_capacity','input_pace'):
        assert r[key]==base[key],key
    s0=base['source_signature']['sources'];s1=r['source_signature']['sources'];assert s0.keys()==s1.keys()
    changed=[name for name in s0 if s0[name]!=s1[name]]
    assert set(changed)<=ALLOWED_SOURCE_CHANGES and changed,changed
    assert base['source_signature']['verilator']==r['source_signature']['verilator']
    f0=[f for f in base['source_signature']['flags'] if not f.startswith('-GFRAME_PRIORITY=')]
    f1=[f for f in r['source_signature']['flags'] if not f.startswith('-GFRAME_PRIORITY=')]
    assert f0==f1
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    prepare_ten(str(run))
    out=ROOT/'deliverables'/('self_cnn_ten_'+run.name)
    old=analyze(BASE,m);new=analyze(run,m)
    assert (run/'overlap/outputs.bin').read_bytes()==(BASE/'overlap/outputs.bin').read_bytes()
    evidence=out/'baseline';evidence.mkdir(exist_ok=True)
    for name in ('result.json',):shutil.copyfile(BASE/name,evidence/name)
    for name in ('metrics.json','events.csv','outputs.bin'):shutil.copyfile(BASE/'overlap'/name,evidence/name)
    comparison=dict(status='PASS',scope='Finite ten-frame RTL batch, not a steady-state throughput guarantee',
        changed_sources=changed,arithmetic_and_testbench_hashes_unchanged=True,baseline=old,frame_priority=new,
        output_sha256=sha(out/'outputs.bin'),same_outputs=True,
        first_output_change_percent=(new['first_output_ms']/old['first_output_ms']-1)*100,
        batch_change_percent=(new['batch_ms']/old['batch_ms']-1)*100)
    save(out/'scheduling_comparison.json',comparison);plot(out,old,new)
    with (out/'output_timing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['policy',*new['frames'][0].keys()];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for policy,result in [('round_robin',old),('oldest_frame',new)]:
            for row in result['frames']:w.writerow(dict(policy=policy,**row))
    table='\n'.join(f"|{a['image']}|{a['read_complete_ms']:.3f}|{b['read_complete_ms']:.3f}|{b['input_to_read_ms']:.3f}|{a['l2_pad_to_dw3_wait_ms']:.3f} → {b['l2_pad_to_dw3_wait_ms']:.3f}|" for a,b in zip(old['frames'],new['frames']))
    gate=read(local(r['gate'])/'result.json')
    report=f'''# 十图调度对比：让结果错开返回

同一十张完整MobileFaceNet已通过真实RTL验证，1310任务、2338104320 MAC及1280字节最终输出均正确，输出与原轮转及独立整数参考完全一致。仅改变调度及其参数传递；算术模块、C++测试台、数据、算子数量、输入速度和内存容量均保持一致。

|指标（假设100MHz）|原轮转|较早图片优先|
|---|---:|---:|
|首个结果全部读完|{old['first_output_ms']:.3f}ms|{new['first_output_ms']:.3f}ms|
|首个结果计算完成|{old['first_compute_ms']:.3f}ms|{new['first_compute_ms']:.3f}ms|
|整批十图结束|{old['batch_ms']:.3f}ms|{new['batch_ms']:.3f}ms|
|整批时间÷10（不是单图延迟）|{old['batch_amortized_ms_per_image']:.3f}ms|{new['batch_amortized_ms_per_image']:.3f}ms|
|九个相邻输出间隔平均值|{old['gap_mean_ms']:.3f}ms|{new['gap_mean_ms']:.3f}ms|
|九个间隔的最小～最大|{old['gap_min_ms']:.3f}～{old['gap_max_ms']:.3f}ms|{new['gap_min_ms']:.3f}～{new['gap_max_ms']:.3f}ms|

首个结果时间变化{comparison['first_output_change_percent']:+.2f}%，整批时间变化{comparison['batch_change_percent']:+.2f}%（负数为缩短，正数为增加）。两项必须一起看。原轮转的短输出间隔来自末尾集中出结果，不能称为稳定高吞吐；新策略的九个间隔也仅是本批观测，并不证明持续帧率。

- [输出节奏图](output_cadence.png)：同轴对比累计完成张数及全部九个相邻间隔。
- [逐图片交互图](task_timeline/index.html)：每张图片一行，查看在一段时间内运行了哪层、哪个算子。
- [完整任务PNG](task_timeline/full_network.png)、[跨算子局部PNG](task_timeline/cross_operator.png)。
- [输出时刻CSV](output_timing.csv)、[原始对比数据](scheduling_comparison.json)、[完整仿真与波形说明](README.md)。

## 各图片响应和首次DW3等待

时间从仿真起点计；输入→输出从该图片完整提交起计算。DW3等待是L2补边完成到L2 DW3发射的间隔。

|图片|原输出时刻ms|新输出时刻ms|新输入提交→输出ms|首次DW3等待：旧→新ms|
|---|---:|---:|---:|---:|
{table}

实际输出顺序：{' → '.join(map(str,new['output_order']))}。相邻输出间隔ms：{', '.join(f'{v:.3f}' for v in new['gaps_ms'])}。

较早输入的图在可执行候选中优先；它被依赖、缓存或算子占用阻塞时，其他图仍可使用空闲算子；已经发射的整层不会抢占。没有为美化间隔而扣留完成结果；外部读取仍是原测试台的40拍等待和真实SRAM读取确认。

## 实际电脑时间与范围

本次完整仿真主体{new['simulation_seconds']:.3f}秒，含初始化与收尾总{new['wall_seconds']:.3f}秒；全网复用程序，重新编译{new['compile_seconds']:.3f}秒。小门槛编译{gate['compile_seconds']:.3f}秒、四场景运行{gate['wall_seconds']:.3f}秒另计；开发、控制测试、报告制作另计。硬件{new['cycles']:,}周期，100MHz只作换算，未验证板级频率。

输入仍是十张不同112×112 RGB合成数值图，32MiB仿真SRAM、诊断量化、完整图像提交后开始计算，无CPU/UART或同帧条带输入。不存在识别准确率或512KiB适配结论。

目前没有无限连续上下文回收。下一步若以稳定输出为目标，需要结果消费后循环释放frame_slot、允许新图片接入和入口反压，再跑足够长的连续输入测试。若目标定为100ms/张，则应验证稳定10张/秒及最大间隔；本次不能直接承诺达到它。
'''
    (out/'SCHEDULING.md').write_text(report,encoding='utf-8')
    p=out/'README.md';p.write_text(p.read_text(encoding='utf-8')+'\n调度策略对比、首张时间和输出间隔见[SCHEDULING.md](SCHEDULING.md)。\n',encoding='utf-8')
    print(json.dumps({k:comparison[k] for k in ('first_output_change_percent','batch_change_percent')}))
    print(out)

if __name__=='__main__':main(sys.argv[1])
