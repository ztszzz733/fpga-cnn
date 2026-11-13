"""Report expanded operator pools only after a complete matched 15-image RTL PASS."""
from pathlib import Path
import argparse,csv,json,re,shutil
from PIL import Image,ImageDraw
from prepare_self_ten import ROOT,read,save,sha,local,font,wave_views
from prepare_self_fifteen import task_views
from prepare_self_thirty import timing
BASE=ROOT/'build/runs/20261025_161109_552493_k3par4_fifteen'
OLD_GATE=ROOT/'build/runs/20261025_160707_701204_self_fifteen'
def normalized(flags):
    return [re.sub(r'(-G(?:K3|K1|POST)_UNITS=|-DCNN_(?:K3|K1|POST)=)\d+',r'\1POOL',f) for f in flags]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('run');a=ap.parse_args()
    run=local(a.run).resolve();r=read(run/'result.json');br=read(BASE/'result.json')
    for x in (r,br):
        assert x['status']=='PASS' and x['full_network'] and x['frames']==15
        assert x['k3_par4'] and x['pw8'] and x['dw_cache'] and x['post_group']==16 and x['frame_priority']
        assert not x['dw_priority']
    assert r['pool']==dict(K3=4,K1=12,Post=4,Add=1,DW7=1,Pad=1)
    assert br['pool']==dict(K3=2,K1=4,Post=1,Add=1,DW7=1,Pad=1)
    assert r['manifest_sha256']==br['manifest_sha256'] and r['sram_capacity']==br['sram_capacity'] and r['input_pace']==br['input_pace']
    assert r['source_signature']['sources']==br['source_signature']['sources'],'RTL and C++ must be unchanged'
    assert normalized(r['source_signature']['flags'])==normalized(br['source_signature']['flags'])
    for name,h in r['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,h in m['files_sha256'].items():assert sha(data/name)==h,name
    g=read(local(r['gate'])/'result.json');bg=read(OLD_GATE/'result.json')
    for x in (g,bg):assert x['status']=='PASS' and not x['full_network'] and x['frames']==15 and set(x['scenarios'])=={'overlap','serial','preloaded','stress'}
    assert g['pool']==r['pool'] and bg['pool']==br['pool'] and g['manifest_sha256']==bg['manifest_sha256']
    assert g['source_signature']==r['source_signature'] and g['exe_sha256']==r['exe_sha256']
    assert bg['source_signature']==br['source_signature'] and bg['exe_sha256']==br['exe_sha256']
    b=read(run/'overlap/metrics.json');old=read(BASE/'overlap/metrics.json')
    assert b==r['scenarios']['overlap']['metrics'] and old==br['scenarios']['overlap']['metrics']
    for k,v in dict(commands=1965,expanded_commands=1965,allocations=1965,releases=1965,results=15,macs=3507156480,checked_bytes=290059380).items():assert b[k]==old[k]==v,k
    raw=(run/'overlap/outputs.bin').read_bytes();assert len(raw)==1920 and raw==(BASE/'overlap/outputs.bin').read_bytes()
    assert sha(run/'overlap/outputs.bin')==m['final_expected_sha256']==br['scenarios']['overlap']['outputs_sha256']
    with (data/'expected.bin').open('rb') as f:
        for i,j in enumerate(j for j in m['jobs'] if j['result']):f.seek(j['expected_offset']);assert f.read(128)==raw[i*128:(i+1)*128]
    for mode in g['scenarios']:
        x,y=g['scenarios'][mode],bg['scenarios'][mode]
        assert x['outputs_sha256']==y['outputs_sha256']
        for k in ('commands','macs','checked_bytes','results'):assert x['metrics'][k]==y['metrics'][k]
    assert g['scenarios']['serial']['metrics']['cycles']==bg['scenarios']['serial']['metrics']['cycles']
    out=ROOT/'deliverables'/('self_cnn_pool_scale_'+run.name);out.mkdir(exist_ok=True)
    for name in ('outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd'):shutil.copyfile(run/'overlap'/name,out/name)
    for name,path in [('result.json',run/'result.json'),('data_manifest.json',data/'manifest.json'),('small_gate.json',local(r['gate'])/'result.json'),('baseline_small_gate.json',OLD_GATE/'result.json'),('baseline_full.json',BASE/'result.json')]:shutil.copyfile(path,out/name)
    pool=r['pool'];names=[*[f'K3#{i}' for i in range(pool['K3'])],*[f'K1#{i}' for i in range(pool['K1'])],'DW7',*[f'Post#{i}' for i in range(pool['Post'])],'Add','Pad']
    assert len(names)==len(b['units'])==23 and b['pool']==pool
    task_views(out,run,m,b,unit_names=names);wave_views(out,k3_lanes=4,pool=pool);t=timing(b);bt=timing(old)
    comp={mode:dict(before=bg['scenarios'][mode]['metrics']['cycles'],after=g['scenarios'][mode]['metrics']['cycles']) for mode in g['scenarios']}
    for v in comp.values():v['cycle_reduction_percent']=(1-v['after']/v['before'])*100
    traffic=sum(u['read_bytes']+u['write_bytes'] for u in b['units']);old_traffic=sum(u['read_bytes']+u['write_bytes'] for u in old['units'])
    assert traffic==old_traffic,'Replication alone should not change layer traffic'
    bandwidth_bound_ms=traffic/(4*4*100000000)*1000/15
    reduction=(1-b['cycles']/old['cycles'])*100;speed=old['cycles']/b['cycles']
    target=dict(target_gap_ms=10,finite_mean_gap_under_10ms=t['mean_gap_ms']<10,all_gaps_under_10ms=t['max_gap_ms']<10,batch_ms_per_image_under_10=t['batch_ms_per_image']<10,sustained_10ms_proven=False,ideal_bandwidth_bound_ms_per_image=bandwidth_bound_ms)
    save(out/'summary.json',dict(status='PASS',pool=pool,frames=15,cycles=b['cycles'],timing=t,baseline=bt,small_comparison=comp,target=target,cycle_reduction_percent=reduction,same_frequency_speedup=speed,wall_seconds=r['wall_seconds'],simulation_seconds=b['simulation_seconds'],compile_seconds=r['compile_seconds'],output_sha256=sha(out/'outputs.bin'),traffic_bytes=traffic))
    with (out/'output_timing.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['output_index','image','read_complete_ms','gap_ms'])
        for i,(im,tm) in enumerate(zip(t['output_order'],t['output_ms'])):w.writerow([i+1,im,tm,None if i==0 else t['gaps_ms'][i-1]])
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
        x=30+(i%7)*263;y=680+(i//7)*75;d.text((x,y),f"{t['output_order'][i]}→{t['output_order'][i+1]}: {gap:.2f}ms",font=font(22),fill='#64d9a2')
    d.text((30,863),f"相邻间隔平均 {t['mean_gap_ms']:.3f}ms，范围 {t['min_gap_ms']:.3f}～{t['max_gap_ms']:.3f}ms；有限批次，非无限稳态。",font=font(24),fill='white')
    im.save(out/'output_cadence.png')
    table='\n'.join(f"|{mode}|{v['before']}|{v['after']}|{v['cycle_reduction_percent']:.2f}%|" for mode,v in comp.items())
    unit_rows='\n'.join(f"|{names[u['unit']]}|{u['tasks']}|{100*u['active_cycles']/b['cycles']:.2f}%|{u['arbitration_wait_cycles']}|" for u in b['units'])
    verdict='达到' if target['finite_mean_gap_under_10ms'] else '未达到'
    text=f"""# 多种算子扩容：15图完整MobileFaceNet

完整RTL PASS，1965任务、3507156480MAC、290059380检查字节；15份128字节结果与独立整数参考和上一版完全相同。

本轮只改变实例数量：K3（普通3×3/DW3共享）2→4套，每套4空间MAC；K1 4→12套，每套PW8；Post 1→4套；DW7/Add/Pad仍各1套。共有23个算子。RTL、算术C++检查器、权重、诊断量化、调度策略和存储接口源码与基线完全相同，编译参数仅改变池数量。没有新增资源综合或宣称这些实例可以完整上板。

## 10ms目标

有限15图平均相邻输出间隔{t['mean_gap_ms']:.3f}ms：**{verdict}小于10ms目标**。范围{t['min_gap_ms']:.3f}～{t['max_gap_ms']:.3f}ms；输出顺序{t['output_order']}。

整批平均每张{t['batch_ms_per_image']:.3f}ms包含首张等待，与相邻结果间隔不同。没有延迟读取或攒结果来压低输出间隔。即使有限批次平均间隔小于10ms，也不能证明无限连续100帧/秒。

本轮CNN读写合计{traffic:,}字节。原存储四bank每拍每bank至多32位，100MHz理想总带宽1.6GB/s；仅这些读写就给出{bandwidth_bound_ms:.3f}ms/张的持续吞吐下限，还没计仲裁、字节访问和输入/读结果争用。此为总交通量除理想带宽的下界，不是有限批次相邻输出间隔下界。仅复制算子无法让当前访存方式持续10ms/张；后续需减少中间结果搬运/提升复用或与存储同学协商带宽。

## 同15图对照（100MHz条件换算）

|指标|上轮2/4/1|本轮4/12/4|
|---|---:|---:|
|整批周期|{old['cycles']:,}|{b['cycles']:,}|
|整批ms|{bt['batch_ms']:.3f}|{t['batch_ms']:.3f}|
|首张ms|{bt['first_ms']:.3f}|{t['first_ms']:.3f}|
|平均相邻间隔ms|{bt['mean_gap_ms']:.3f}|{t['mean_gap_ms']:.3f}|
|最慢相邻间隔ms|{bt['max_gap_ms']:.3f}|{t['max_gap_ms']:.3f}|

整批周期减少{reduction:.2f}%，同频速度{speed:.3f}倍。100MHz为换算条件，未经完整布局布线，不是上板时钟承诺。

## 查看

- [逐图片交互并行图](task_timeline/index.html)、[全网PNG](task_timeline/full_network.png)
- [图片1—5](task_timeline/images_1_5.png)、[6—10](task_timeline/images_6_10.png)、[11—15](task_timeline/images_11_15.png)
- [跨类窗口](task_timeline/cross_operator.png)、[输出节奏](output_cadence.png)、[所有输出时间与14个间隔](output_timing.csv)
- [MAC推进](mac_detail.png)、[跨类推进](pipeline_detail.png)，对应VCD/GTKWave仍10根唯一信号，其中算子总线扩为23位，位标签与实际实例一致。

任务条包含访存等待；work中K3每拍最多4MAC、K1最多8MAC、Post/Add/Pad代表接受写请求。实际跨图work{b['multi_frame_work_cycles']:,}拍，跨类{b['cross_operator_work_cycles']:,}拍。

## 验证与耗时

|小数据模式|旧周期|新周期|减少|
|---|---:|---:|---:|
{table}

小数据四场景输出相同，serial逐周期一致；拥塞模式不保证改善。完整仿真电脑主体{b['simulation_seconds']:.3f}秒，runner含初始化收尾{r['wall_seconds']:.3f}秒，编译{r['compile_seconds']:.3f}秒。新小门槛编译{g['compile_seconds']:.3f}秒与四场景{g['wall_seconds']:.3f}秒另计。

|实例|任务数|忙碌占整批|仲裁等待拍数|
|---|---:|---:|---:|
{unit_rows}

仍15个有限上下文，原十张合成112×112RGB加前五张重复，每张完整计算；64MiB实验SRAM，整图输入写完提交，输入节奏80保持不变，无CPU/UART/同图条带输入/识别准确率/512KiB适配结论。

原始run：{run}。输出SHA：{sha(out/'outputs.bin')}。源/数据/程序/输出/逐任务依赖已核验，图片及GTKWave验证见artifact_validation.json。
"""
    (out/'README.md').write_text(text,encoding='utf-8')
    save(out/'provenance.json',dict(run=str(run),result_sha256=sha(run/'result.json'),reporter_sha256=sha(Path(__file__)),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}))
    print(out);print(json.dumps(t));print(json.dumps(target))

if __name__=='__main__':main()
