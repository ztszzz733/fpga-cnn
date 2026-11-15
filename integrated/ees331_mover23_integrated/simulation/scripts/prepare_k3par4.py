"""Verify and report a completed spatial-four 15-image run against the same previous full batch."""
from pathlib import Path
import argparse,csv,json,shutil
from PIL import Image,ImageDraw
from prepare_self_ten import ROOT,read,save,sha,local,font,wave_views
from prepare_self_fifteen import task_views
from prepare_self_thirty import timing
BASE=ROOT/'build/runs/20261025_150610_730169_self_fifteen'
def synth_path(value):
    p=local(value)/'result.json'
    if read(p)['status']=='TIMEOUT':
        q=p.with_name('completion_verified.json');assert read(q)['original_result_sha256']==sha(p);return q
    return p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run');ap.add_argument('--baseline-gate',required=True)
    ap.add_argument('--unit',required=True);ap.add_argument('--synth-old',required=True);ap.add_argument('--synth-new',required=True);a=ap.parse_args()
    run=local(a.run).resolve();r=read(run/'result.json');br=read(BASE/'result.json')
    for x in (r,br):
        assert x['status']=='PASS' and x['full_network'] and x['frames']==15
        assert x['dw_cache'] and x['post_group']==16 and x['frame_priority'] and x['pw8']
        assert x['pool']==dict(K3=2,K1=4,Post=1,Add=1,DW7=1,Pad=1)
    assert r['k3_par4'] and not br.get('k3_par4',False)
    assert r['manifest_sha256']==br['manifest_sha256'] and r['sram_capacity']==br['sram_capacity'] and r['input_pace']==br['input_pace']
    for name,h in r['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    allowed={'rtl/cnn_stream/self_stream_top.sv','rtl/cnn_stream/self_fixed_network_top.sv','tb/self_full_sim_top.sv'}
    for name,h in br['source_signature']['sources'].items():
        if name not in allowed:assert r['source_signature']['sources'][name]==h,name
    data=local(r['data']);m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,h in m['files_sha256'].items():assert sha(data/name)==h,name
    g=read(local(r['gate'])/'result.json');bg=read(local(a.baseline_gate)/'result.json')
    for x in (g,bg):
        assert x['status']=='PASS' and not x['full_network'] and x['frames']==15
        assert x['dw_cache'] and x['post_group']==16 and x['pw8'] and x['frame_priority']
        assert set(x['scenarios'])=={'overlap','serial','preloaded','stress'}
    assert g['k3_par4'] and not bg['k3_par4'] and g['manifest_sha256']==bg['manifest_sha256']
    assert g['source_signature']==r['source_signature'] and g['exe_sha256']==r['exe_sha256']
    assert g['source_signature']['sources']==bg['source_signature']['sources']
    assert [f for f in g['source_signature']['flags'] if not f.startswith('-GK3_PAR4=')]==[f for f in bg['source_signature']['flags'] if not f.startswith('-GK3_PAR4=')]
    previous_gate=read(ROOT/'build/runs/20261025_150333_123534_self_fifteen/result.json')
    for mode in g['scenarios']:
        assert bg['scenarios'][mode]['metrics']['cycles']==previous_gate['scenarios'][mode]['metrics']['cycles']
        assert bg['scenarios'][mode]['outputs_sha256']==g['scenarios'][mode]['outputs_sha256']==previous_gate['scenarios'][mode]['outputs_sha256']
    b=read(run/'overlap/metrics.json');assert b==r['scenarios']['overlap']['metrics']
    old=read(BASE/'overlap/metrics.json');assert old==br['scenarios']['overlap']['metrics']
    for k,v in dict(commands=1965,expanded_commands=1965,allocations=1965,releases=1965,results=15,macs=3507156480,checked_bytes=290059380).items():assert b[k]==old[k]==v,k
    raw=(run/'overlap/outputs.bin').read_bytes();assert len(raw)==1920 and raw==(BASE/'overlap/outputs.bin').read_bytes()
    assert sha(run/'overlap/outputs.bin')==m['final_expected_sha256']==br['scenarios']['overlap']['outputs_sha256']
    with (data/'expected.bin').open('rb') as f:
        for i,j in enumerate(j for j in m['jobs'] if j['result']):f.seek(j['expected_offset']);assert f.read(128)==raw[i*128:(i+1)*128]
    unit=read(local(a.unit)/'result.json');sn=read(synth_path(a.synth_new));so=read(synth_path(a.synth_old))
    assert unit['status']==sn['status']==so['status']=='PASS' and sn['synthesis_setup_met']
    for name,h in unit['sources'].items():assert sha(ROOT/name)==h,name
    assert sn['sources_sha256']['rtl/cnn_self/self_conv_spatial4_engine.sv']==sha(ROOT/'rtl/cnn_self/self_conv_spatial4_engine.sv')
    assert so['sources_sha256']['rtl/cnn_self/self_conv_wide_engine.sv']==sha(ROOT/'rtl/cnn_self/self_conv_wide_engine.sv')
    out=ROOT/'deliverables'/('self_cnn_k3par4_'+run.name);out.mkdir(exist_ok=True)
    for name in ('outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd'):shutil.copyfile(run/'overlap'/name,out/name)
    for name,path in [('result.json',run/'result.json'),('data_manifest.json',data/'manifest.json'),('small_gate.json',local(r['gate'])/'result.json'),('baseline_small_gate.json',local(a.baseline_gate)/'result.json'),('baseline_full.json',BASE/'result.json'),('unit_result.json',local(a.unit)/'result.json'),('unit_metrics.json',local(a.unit)/'metrics.json'),('synth_before.json',synth_path(a.synth_old)),('synth_after.json',synth_path(a.synth_new))]:shutil.copyfile(path,out/name)
    task_views(out,run,m,b);wave_views(out,k3_lanes=4);t=timing(b);bt=timing(old)
    comp={mode:dict(before=bg['scenarios'][mode]['metrics']['cycles'],after=g['scenarios'][mode]['metrics']['cycles']) for mode in g['scenarios']}
    for v in comp.values():v['cycle_reduction_percent']=(1-v['after']/v['before'])*100
    speed=old['cycles']/b['cycles'];reduction=(1-b['cycles']/old['cycles'])*100
    save(out/'summary.json',dict(status='PASS',frames=15,cycles=b['cycles'],timing=t,baseline_fifteen=bt,small_comparison=comp,same_fifteen_full_baseline=True,cycle_reduction_percent=reduction,same_frequency_speedup=speed,wall_seconds=r['wall_seconds'],simulation_seconds=b['simulation_seconds'],compile_seconds=r['compile_seconds'],output_sha256=sha(out/'outputs.bin')))
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
    resources='\n'.join(f"|{k}|{so['utilization'][k]['used']}|{sn['utilization'][k]['used']}|" for k in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'))
    text=f"""# 四位置3×3/DW3：同15图完整MobileFaceNet对比

完整RTL PASS：1965任务、3507156480 MAC，290059380字节逐值核验。15份128字节结果与独立整数参考、上一轮15图全部一致。

两套K3引擎各从一个位置乘加改为最多四个位置同时乘加，四个输入缓存银行按步长组织，一份输入字节只存一次，同一权重广播。保留整层DW权重缓存。K1仍四套PW8，DW7/Post/Add/Pad各一套，调度和存储接口不变。并行度边缘可为1/2/4；四条通路不等于全网四倍速度。

## 查看

- [逐图片交互图](task_timeline/index.html)、[完整15图](task_timeline/full_network.png)
- 大字分组：[1—5](task_timeline/images_1_5.png)、[6—10](task_timeline/images_6_10.png)、[11—15](task_timeline/images_11_15.png)
- [跨算子窗口](task_timeline/cross_operator.png)、[输出节奏](output_cadence.png)、[逐结果时间](output_timing.csv)
- [MAC波形](mac_detail.png)、[跨类波形](pipeline_detail.png)，同名VCD/GTKWave各10根唯一信号

## 同数据全网对比

|指标|上轮15图|本轮15图|
|---|---:|---:|
|整批周期|{old['cycles']:,}|{b['cycles']:,}|
|100MHz条件整批ms|{bt['batch_ms']:.3f}|{t['batch_ms']:.3f}|
|首张输出ms|{bt['first_ms']:.3f}|{t['first_ms']:.3f}|
|14个相邻间隔平均ms|{bt['mean_gap_ms']:.3f}|{t['mean_gap_ms']:.3f}|
|相邻间隔范围ms|{bt['min_gap_ms']:.3f}—{bt['max_gap_ms']:.3f}|{t['min_gap_ms']:.3f}—{t['max_gap_ms']:.3f}|

本轮整批周期减少{reduction:.2f}%，同频批次速度{speed:.3f}倍。相同输入/权重/诊断量化、算子数、15上下文、64MiB实验存储、提交节奏和调度策略。旧模式在当前集成代码上四项小回归逐周期复现上一轮，避免把集成变动当成新算术收益。有限批次相邻间隔不能称无限稳态吞吐。

电脑模拟器主体{b['simulation_seconds']:.3f}秒，含初始化收尾{r['wall_seconds']:.3f}秒。完整运行复用程序，编译{r['compile_seconds']:.3f}秒；小门槛编译{g['compile_seconds']:.3f}秒、四场景{g['wall_seconds']:.3f}秒另计，开发单元和综合耗时另计。

## 小数据及资源

|模式|旧周期|新周期|减少|
|---|---:|---:|---:|
{table}

单核Z7020/10ns独立综合：

|资源|原K3/DW缓存|新四位置K3|
|---|---:|---:|
{resources}

综合WNS旧{so['worst_setup_slack_ns']:+.3f}ns、新{sn['worst_setup_slack_ns']:+.3f}ns。未做整机布局布线，不证明整机上板100MHz或整体资源充足。新输入银行每块9×512字节，四块共18KiB有效分配范围，另有权重RAM；数据未复制四份，但银行填充增加存储资源。

任务条含访存等待。K3 work脉冲代表1/2/4次实际MAC；K1最多8次；Post/Add/Pad表示接受写入，不能直接比较脉冲数量当作运算量。实际跨图work重叠{b['multi_frame_work_cycles']:,}拍，跨类{b['cross_operator_work_cycles']:,}拍。VCD为真实局部256拍，整体时序看任务图。

输入仍原十张合成112×112RGB加前五张重复；每张独立完整计算。整图存储端口输入后提交，无CPU/UART/同图条带输入/识别准确率/512KiB适配结论。量化为诊断尺度。输出SHA256：{sha(out/'outputs.bin')}。

原始run：{run}。源/数据/程序/输出/依赖核验通过；交付QA见artifact_validation.json。
"""
    (out/'README.md').write_text(text,encoding='utf-8')
    save(out/'provenance.json',dict(run=str(run),result_sha256=sha(run/'result.json'),reporter_sha256=sha(Path(__file__)),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}))
    print(out);print(json.dumps(t))

if __name__=='__main__':main()
