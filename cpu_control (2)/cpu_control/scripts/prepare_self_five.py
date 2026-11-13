"""Validate and report the requested five-image, 4/6/3-pool RTL run."""
from pathlib import Path
import argparse
import csv
import json
import shutil
from PIL import Image,ImageDraw
from prepare_self_ten import ROOT,read,save,sha,local,font,wave_views
from prepare_self_fifteen import task_views
from prepare_self_thirty import timing

POOL=dict(K3=4,K1=6,Post=3,Add=1,DW7=1,Pad=1)
PRIOR=ROOT/'build/runs/20261025_165454_362193_pool_scale_fifteen'

def main(expected_frames=5):
    ap=argparse.ArgumentParser();ap.add_argument('run');a=ap.parse_args()
    run=local(a.run).resolve();r=read(run/'result.json')
    nf=expected_frames;assert nf in (5,10)
    assert r['status']=='PASS' and r['full_network'] and r['frames']==nf and r['pool']==POOL
    assert r['max_tasks']==(1024 if nf==5 else 2048) and r['sram_capacity']==32*1024*1024
    assert r['pw8'] and r['k3_par4'] and r['dw_cache'] and r['post_group']==16 and r['frame_priority']
    assert not r['dw_priority'] and r['input_pace']==80
    for name,h in r['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,h in m['files_sha256'].items():assert sha(data/name)==h,name
    source=local(m['replication']['source']) if nf==5 else data;sm=read(source/'manifest.json')
    if nf==5:
        assert sha(source/'manifest.json')==m['replication']['manifest_sha256']
        assert m['replication']['order']==[1,2,3,4,5] and m['replication']['distinct_contexts']
    assert m['input_shape']==[112,112,3] and m['template_steps']==131 and m['final_bytes_per_frame']==128
    assert m['final_frame_sha256']==sm['final_frame_sha256'][:nf]
    assert [s['quantized_sha256'] for s in m['input_sources']]==[s['quantized_sha256'] for s in sm['input_sources'][:nf]]
    g=read(local(r['gate'])/'result.json');assert g['status']=='PASS' and not g['full_network'] and g['frames']==nf
    assert g['source_signature']==r['source_signature'] and g['exe_sha256']==r['exe_sha256'] and g['pool']==POOL
    assert set(g['scenarios'])=={'overlap','serial','preloaded','stress'}
    gate_data=local(g['data']);gm=read(gate_data/'manifest.json')
    assert sha(gate_data/'manifest.json')==g['manifest_sha256']
    for name,h in gm['files_sha256'].items():assert sha(gate_data/name)==h,name
    for scenario in g['scenarios'].values():
        b=scenario['metrics']
        assert b['status']=='PASS' and b['pool']==POOL and b['commands']==8*nf and b['macs']==102400*nf
        assert b['checked_bytes']==17964*nf and b['results']==nf
        assert scenario['outputs_sha256']==gm['final_expected_sha256']
    b=read(run/'overlap/metrics.json');assert b==r['scenarios']['overlap']['metrics']
    expected=dict(commands=131*nf,expanded_commands=131*nf,allocations=131*nf,releases=131*nf,
                  results=nf,macs=233810432*nf,checked_bytes=19337292*nf)
    for key,value in expected.items():assert b[key]==value,key
    assert b['multi_frame_work_cycles']>0 and b['cross_operator_work_cycles']>0
    raw=(run/'overlap/outputs.bin').read_bytes()
    assert len(raw)==128*nf and sha(run/'overlap/outputs.bin')==m['final_expected_sha256']
    with (data/'expected.bin').open('rb') as reference:
        for i,j in enumerate(j for j in m['jobs'] if j['result']):
            reference.seek(j['expected_offset']);assert reference.read(128)==raw[i*128:(i+1)*128]
    prior=read(PRIOR/'result.json');assert prior['status']=='PASS'
    assert sha(PRIOR/'overlap/outputs.bin')==prior['scenarios']['overlap']['outputs_sha256']
    assert raw==(PRIOR/'overlap/outputs.bin').read_bytes()[:128*nf]
    # This run changes only instance counts and finite-context/capacity parameters.
    assert r['source_signature']['sources']==prior['source_signature']['sources']
    label='five' if nf==5 else 'ten_reduced'
    out=ROOT/'deliverables'/('self_cnn_'+label+'_'+run.name);out.mkdir(exist_ok=True)
    for name in ('outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd'):
        shutil.copyfile(run/'overlap'/name,out/name)
    for name,path in [('result.json',run/'result.json'),('data_manifest.json',data/'manifest.json'),
                      ('small_gate.json',local(r['gate'])/'result.json')]:shutil.copyfile(path,out/name)
    names=[*[f'K3#{i}' for i in range(4)],*[f'K1#{i}' for i in range(6)],'DW7',
           *[f'Post#{i}' for i in range(3)],'Add','Pad']
    assert len(names)==len(b['units'])==16 and b['pool']==POOL
    assert all(u['tasks']>0 for u in b['units'])
    rows=task_views(out,run,m,b,unit_names=names);wave_views(out,k3_lanes=4,pool=POOL)
    t=timing(b)
    traffic=sum(u['read_bytes']+u['write_bytes'] for u in b['units'])
    assert traffic==73234748*nf
    comparison=None;comparison_text=''
    if nf==10:
        five_root=ROOT/'deliverables/self_cnn_five_20261109_201316_587166_self_five'
        five=read(five_root/'summary.json');fr=read(five_root/'result.json')
        assert five['status']=='PASS' and five['pool']==POOL
        assert fr['source_signature']['sources']==r['source_signature']['sources']
        assert raw[:640]==(five_root/'outputs.bin').read_bytes()
        comparison=dict(five=five['timing'],ten=t,scope='Same 16 operators, different finite-context count; not a hardware speedup comparison')
        comparison_text=f"""\n## 同16算子：五图与十图观察\n\n|指标（100MHz条件）|五图|十图|\n|---|---:|---:|\n|首张ms|{five['timing']['first_ms']:.5f}|{t['first_ms']:.5f}|\n|相邻结果平均间隔ms|{five['timing']['mean_gap_ms']:.5f}|{t['mean_gap_ms']:.5f}|\n|最长相邻间隔ms|{five['timing']['max_gap_ms']:.5f}|{t['max_gap_ms']:.5f}|\n|整批ms|{five['timing']['batch_ms']:.5f}|{t['batch_ms']:.5f}|\n|整批/图片数 ms/张|{five['timing']['batch_ms_per_image']:.5f}|{t['batch_ms_per_image']:.5f}|\n\n算子数及算术实现相同，上下文/任务表容量随批次改变；该表仅展示批次行为，不能视作算子加速比或无限稳态结果。\n"""
    checkpoint=dict(interval_minutes=r.get('checkpoint_interval_minutes'),records=r.get('checkpoints',[]),
        finished_before_first_checkpoint=bool(r.get('checkpoint_interval_minutes') and not r.get('checkpoints') and r['wall_seconds']<60*r['checkpoint_interval_minutes']),
        elapsed_wall_seconds=r['wall_seconds'],finished_at=r['finished_at'],
        scope='Progress observations, not resumable simulator state')
    if nf==10:assert checkpoint['interval_minutes']==15
    for name in checkpoint['records']:shutil.copyfile(run/name,out/name)
    save(out/'checkpoint_summary.json',checkpoint)
    save(out/'summary.json',dict(status='PASS',frames=nf,pool=POOL,cycles=b['cycles'],timing=t,
        counters=expected,traffic_bytes=traffic,simulation_seconds=b['simulation_seconds'],
        wall_seconds=r['wall_seconds'],compile_seconds=r['compile_seconds'],
        gate_compile_seconds=g['compile_seconds'],gate_wall_seconds=g['wall_seconds'],
        output_sha256=sha(out/'outputs.bin'),matches_previous_output_prefix=True,
        same_batch_23_operator_baseline=False,five_vs_ten=comparison,checkpoint=checkpoint))
    with (out/'output_timing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['output_index','image','input_commit_ms','read_complete_ms','gap_ms','latency_ms'])
        frames=sorted(b['frames'],key=lambda x:x['read_complete'])
        for i,frame in enumerate(frames):
            writer.writerow([i+1,frame['frame']-99,frame['input_commit']/1e5,frame['read_complete']/1e5,
                             None if i==0 else t['gaps_ms'][i-1],t['latencies_ms'][i]])
    im=Image.new('RGB',(1700,850 if nf==5 else 1000),'#101820');d=ImageDraw.Draw(im)
    d.text((35,25),f'{nf}张完整MobileFaceNet：K3×4 / K1×6 / Post×3',font=font(30),fill='white')
    d.text((35,80),f"首张 {t['first_ms']:.3f}ms；整批 {t['batch_ms']:.3f}ms；100MHz条件换算",font=font(24),fill='#c5d5df')
    x0,x1,y0,y1=110,1630,170,570;limit=t['batch_ms'];xx=lambda v:x0+(x1-x0)*v/limit
    for i in range(6):
        y=y1-(y1-y0)*i/5;d.line((x0,y,x1,y),fill='#30444f');d.text((55,y-15),str(nf*i//5),font=font(22),fill='white')
    pts=[(x0,y1)]
    for i,tm in enumerate(t['output_ms']):pts.extend([(xx(tm),y1-(y1-y0)*i/nf),(xx(tm),y1-(y1-y0)*(i+1)/nf)])
    d.line(pts,fill='#64d9a2',width=4)
    for i in range(7):
        value=limit*i/6;label=f'{value:.1f}';width=d.textlength(label,font=font(22))
        d.text((min(x1-width,max(x0,xx(value)-width/2)),595),label,font=font(22),fill='white')
    d.text((780,633),'时间 / ms',font=font(22),fill='white')
    for i,gap in enumerate(t['gaps_ms']):
        d.text((35+(i%4)*405,685+(i//4)*65),f"{t['output_order'][i]}→{t['output_order'][i+1]}：{gap:.3f}ms",font=font(24),fill='#64d9a2')
    d.text((35,755 if nf==5 else 930),f"{nf-1}个间隔平均 {t['mean_gap_ms']:.3f}ms；{nf}图为有限批次，未证明无限稳态吞吐。",font=font(24),fill='white')
    im.save(out/'output_cadence.png')
    gap_labels=['—']+[f'{gap:.5f}' for gap in t['gaps_ms']]
    table='\n'.join(f"|{i+1}|{image}|{tm:.5f}|{gap_labels[i]}|" for i,(image,tm) in enumerate(zip(t['output_order'],t['output_ms'])))
    unit_table='\n'.join(f"|{names[u['unit']]}|{u['tasks']}|{100*u['active_cycles']/b['cycles']:.2f}%|{u['arbitration_wait_cycles']:,}|" for u in b['units'])
    gate_table='\n'.join(f"|{mode}|{entry['metrics']['cycles']:,}|PASS|" for mode,entry in g['scenarios'].items())
    text=f'''# {nf}张图片完整MobileFaceNet仿真

完整RTL PASS。K1由12套减到6套，Post由4套减到3套；K3保持4套，DW7/Add/Pad各1套，共16个算子。算术RTL、C++检查器、权重、诊断量化、调度和存储接口源码与上次23算子版本一致，只有实例数量、{nf}图上下文与对应容量参数改变。

{expected['commands']:,}个任务、{expected['macs']:,}次MAC、{expected['checked_bytes']:,}个中间输出字节逐值核对，{nf}份128字节输出共{nf*128}字节。结果与独立整数参考及上次15图的前{nf}张逐字节相同。

|时间口径|本次实测|
|---|---:|
|整批硬件周期|{b['cycles']:,}拍|
|整批时间（假设100MHz）|{t['batch_ms']:.5f}ms|
|首张结果读完|{t['first_ms']:.5f}ms|
|{nf-1}个相邻结果间隔平均|{t['mean_gap_ms']:.5f}ms|
|相邻间隔最小 / 最大|{t['min_gap_ms']:.5f} / {t['max_gap_ms']:.5f}ms|
|整批时间 / {nf}|{t['batch_ms_per_image']:.5f}ms/张|
|电脑模拟器主体|{b['simulation_seconds']:.3f}秒|
|电脑全网运行（含初始化收尾）|{r['wall_seconds']:.3f}秒|
|全网重新编译|{r['compile_seconds']:.3f}秒|
|小规模检查编译，另计|{g['compile_seconds']:.3f}秒|
|四项小规模检查，另计|{g['wall_seconds']:.3f}秒|

100MHz仅作周期换算，未经整机布局布线。{nf}图与上次15图批次和上下文数量不同，没有同{nf}图23算子基线，不能据两批整批时间计算削减算子的加速比或性能损失。

## {nf}张结果

|返回序号|图片|读完时间/ms|距上一结果/ms|
|---|---|---:|---:|
{table}

[输出时间与输入提交后延迟](output_timing.csv)、[输出节奏图](output_cadence.png)。结果完成即读取，未人为攒结果；有限批次间隔不等于无限连续吞吐。

## 查看算子协作

- [{nf}图交互任务图](task_timeline/index.html)，默认显示完整网络，可移动游标查看每图当前层和实例。
- [全部{expected['commands']}个任务](task_timeline/full_network.png)、[跨算子放大窗口](task_timeline/cross_operator.png)。
- [真实MAC推进](mac_detail.png)、[跨类推进](pipeline_detail.png)及相应VCD/GTKWave会话。

跨图实际work重叠{b['multi_frame_work_cycles']:,}拍，跨算子类别work重叠{b['cross_operator_work_cycles']:,}拍。任务条包含访存等待；K3每拍最多4MAC、K1最多8MAC，Post/Add/Pad的work代表接受写请求。波形为局部256拍窗口，16位算子总线映射见下表。

|实例（按总线低位到高位）|任务数|忙碌占整批|仲裁等待拍数|
|---|---:|---:|---:|
{unit_table}

每张图片最多一个已发射任务，因此同时在途任务数受{nf}个上下文限制；有限批次利用率不代表无限持续输入。忙碌与访存等待可以和内部work重叠，不能简单相加或相减当作纯计算时间。

## 小规模检查

每项{8*nf}任务、{102400*nf:,}MAC、{17964*nf:,}检查字节、{1024*nf:,}最终字节；四项输出相同，与独立参考一致。

|场景|周期|结果|
|---|---:|---|
{gate_table}

全网与小规模检查使用同一源码、参数和可执行程序。检查了任务展开、依赖、实例归属、存储请求/响应、逐任务写出字节及MAC计数、缓冲分配释放和最终读回。

## 配置与范围

沿用原十图数据的前{nf}张不同112×112 RGB合成输入，模型预训练权重与诊断量化保持不变。真实SRAM端口整图写完后提交；{nf}独立上下文、{nf*4}工作槽、{r['max_tasks']}任务容量、32MiB实验SRAM，初始化{m['init_bytes']:,}字节。四bank接口和输入pace80不变；FRAME_PRIORITY、PW8、K3_PAR4、DW_CACHE和POST_GROUP16启用。

本次仅运行CNN子系统，没有新资源综合；CPU/UART、同图条带输入、准确率和板级存储/时序适配不在此验证范围。

原始run：{run}。输出SHA256：{sha(out/'outputs.bin')}。
'''
    text+=comparison_text
    if nf==10:
        verdict='完整仿真在第一个15分钟检查点前结束，未触发中途记录。' if checkpoint['finished_before_first_checkpoint'] else f"已保存{len(checkpoint['records'])}份15分钟进度检查记录。"
        text+='\n## 15分钟进度检查\n\n'+verdict+'[检查记录汇总](checkpoint_summary.json)。检查点只记录任务进展和状态，不暂停仿真，也不支持从中途恢复。\n'
    (out/'README.md').write_text(text,encoding='utf-8')
    save(out/'provenance.json',dict(run=str(run),gate=r['gate'],source_signature=r['source_signature'],
        manifest_sha256=r['manifest_sha256'],exe_sha256=r['exe_sha256'],reference_manifest_sha256=sha(source/'manifest.json'),
        previous_output_prefix_check=str(PRIOR/'overlap/outputs.bin'),task_rows=len(rows),
        files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}))
    print(out,flush=True)

if __name__=='__main__':main()
