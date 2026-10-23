"""Evidence-backed small-network comparison; never claims a new full run."""
from pathlib import Path
import json,csv,hashlib,shutil
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
RUNS={'baseline':'20261024_012743_310534_self_six','priority':'20261024_011944_108428_self_six','pw8':'20261024_012424_704291_self_six','both':'20261024_012601_237444_self_six'}
OTHER={'pw8_unit':'20261024_012638_214658_pw8_unit_k1','dispatch_unit':'20261024_012510_658248_dispatch_priority','pw8_synth':'20261024_012253_161051_self_cnn_synth'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=ROOT/'deliverables/pw8_priority';out.mkdir(exist_ok=True);ev=out/'evidence';ev.mkdir(exist_ok=True)
 summary={};events={};manifest=read(ROOT/'build/self_six_small/manifest.json')
 for key,name in RUNS.items():
  p=ROOT/'build/runs'/name;r=read(p/'result.json');assert r['status']=='PASS' and not r['full_network']
  assert sha(ROOT/'build/self_six_small/manifest.json')==r['manifest_sha256']
  for path,digest in r['source_signature']['sources'].items():
   # Unselected candidate code may have evolved during independent experiments.
   if path.endswith('self_pw8_engine.sv') and not r['pw8']:continue
   assert sha(ROOT/path)==digest,path
  for mode,v in r['scenarios'].items():
   m=v['metrics'];assert m['status']=='PASS' and m['commands']==48 and m['macs']==614400 and m['checked_bytes']==107784
   assert sha(p/mode/'outputs.bin')==manifest['final_expected_sha256']==v['outputs_sha256']
  dest=ev/key;dest.mkdir(exist_ok=True);shutil.copyfile(p/'result.json',dest/'result.json')
  shutil.copyfile(p/'overlap/events.csv',dest/'events.csv')
  e=list(csv.DictReader((p/'overlap/events.csv').open()));events[key]=e
  dw_start=next(int(x['cycle']) for x in e if x['event']=='launch' and x['node']=='24')
  pad_end=next(int(x['cycle']) for x in e if x['event']=='done' and x['node']=='18')
  m=r['scenarios']['overlap']['metrics']
  summary[key]=dict(run=name,cycles=m['cycles'],first_result=m['frames'][0]['read_complete'],first_dw_start=dw_start,first_dw_wait=dw_start-pad_end,scenario_cycles={k:v['metrics']['cycles'] for k,v in r['scenarios'].items()},compile_seconds=r['compile_seconds'],wall_seconds=r['wall_seconds'])
 for key,name in OTHER.items():
  p=ROOT/'build/runs'/name;r=read(p/'result.json');assert r['status']=='PASS'
  selected=['rtl/cnn_stream/stream_dispatch.sv','tb/integration/dispatch_priority_main.cpp'] if key=='dispatch_unit' else ['rtl/cnn_self/self_pw8_engine.sv']
  hashes=r.get('sources',r.get('sources_sha256',{}))
  for source in selected:assert hashes[source]==sha(ROOT/source),source
  if key=='pw8_synth':assert r['synthesis_setup_met']
  dest=ev/key;dest.mkdir(exist_ok=True)
  for f in ['result.json','metrics.json','simulation.log','utilization.rpt','timing_summary.rpt','primitive_counts.tsv']:
   if (p/f).exists():shutil.copyfile(p/f,dest/f)
 (out/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
 jobs={j['node']:j for j in manifest['jobs']};layers={l['index']:l for l in manifest['layers']}
 colors={'3×3':'#51b8fa','DW3':'#ac9aff','1×1':'#ffbc69','后处理':'#64d9a2','补边':'#e2dc83'}
 im=Image.new('RGB',(1800,1060),'#101820');d=ImageDraw.Draw(im);font=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
 d.text((30,20),'六图小回归：DW3优先缩短前图等待，但可能延长整批（不是全网）',font=font(29),fill='white')
 for i,(k,col) in enumerate(colors.items()):
  x=30+i*280;d.rectangle((x,80,x+23,101),fill=col);d.text((x+32,73),k,font=font(23),fill='white')
 end=max(summary['baseline']['cycles'],summary['both']['cycles'])
 for panel,key in enumerate(['baseline','both']):
  y0=190+panel*390;x0=170;x1=1740
  title='上一轮基线：四位置1×1 / 原调度' if key=='baseline' else '本轮组合：八位置1×1 / DW3有限优先'
  d.text((30,y0-65),title,font=font(25),fill='white')
  for c in range(0,250001,50000):
   x=x0+(x1-x0)*c/end;d.line((x,y0-15,x,y0+6*40),fill='#354957');d.text((x-15,y0-35),str(c//1000)+'k',font=font(18),fill='#c6d5e1')
  pending={}
  for e in events[key]:
   if e['event']=='launch':pending[int(e['node'])]=(int(e['cycle']),int(e['frame']))
   if e['event']=='done':
    n=int(e['node']);a,f=pending.pop(n);b=int(e['cycle']);j=jobs[n];l=layers[j['layer']]
    kind={0:'DW3' if l.get('depthwise') else '3×3',5:'1×1',1:'后处理',4:'补边'}[j['opcode']]
    ax=x0+(x1-x0)*a/end;bx=x0+(x1-x0)*b/end;y=y0+(f-100)*40
    d.rectangle((ax,y,bx,y+25),fill=colors[kind])
    if bx-ax>80:d.text((ax+5,y+1),kind,font=font(18),fill='#101820')
  for f in range(6):d.text((30,y0+f*40),f'图片 {f+1}',font=font(20),fill='white')
  m=summary[key]
  d.text((30,y0+265),f"图1的DW3排队：{m['first_dw_wait']:,}拍；图1结果：{m['first_result']:,}拍；整批：{m['cycles']:,}拍",font=font(23),fill='white')
 d.text((30,970),'横轴为真实硬件周期；色块含访存等待。每项仅8×8 ROI首三层 / 48任务，不能据此宣称完整网络加速。',font=font(23),fill='white')
 im.save(out/'small_task_comparison.png')
 labels={'baseline':'基线','priority':'只改DW3调度','pw8':'只改八位置1×1','both':'两者同时启用'}
 table='\n'.join(f"|{labels[k]}|{v['first_dw_wait']:,}|{v['first_result']:,}|{v['cycles']:,}|" for k,v in summary.items())
 report=f'''# DW3调度与1×1继续优化：小回归结果

已完成代码、独立单元验证和四配置真实六图小回归；**本轮未重跑完整MobileFaceNet**。上一轮完整网络153487331拍仍是历史配置的结果，不能当本轮结果。

## 1×1采用八空间位置并行

每套引擎把输出块从2×2改为4×2，最多八个位置同步使用同一权重，每拍最多8次MAC。仍四套1×1，没有增加实例数量。输入缓存独立分银行，权重双缓冲和八字写队列沿用原方案；尾部位置屏蔽，stride1/2、非对齐和字节尾部保留。

|独立1×1样例|四位置周期|八位置周期|读取字节前→后|
|---|---:|---:|---:|
|4×4，Ci=Co=64|22,993|14,350|17,408→9,216|
|7×7，Ci=Co=128|311,359|171,717|268,416→137,344|
|1×1，Ci=512/Co=128|70,744|70,744|66,048→66,048|

最后一行只有一个空间位置，不能利用额外空间通道，速度不变。最初尝试四位置×双输入通道，4×4样例反而22993→23350，主要受权重供给限制，未选用；记录留在build/runs/20261024_011751_934434_pw8_unit_k1，不能将该结果与最终八位置版本混淆。

单核Z7020/10ns OOC：LUT2247→2700、FF1354→1553、BRAM Tile3→5、DSP仍0，新WNS+0.579ns。四套合计增加1812 LUT、796 FF、8个36Kb BRAM等效块。实际输入缓存增加共8KiB，RAM银行映射导致BRAM分配增加约36KiB。没有整机P&R或板级频率证明，512KiB整体存储问题仍未解决。

## DW3有限优先是延迟与吞吐的选择

两套K3仍共享普通3×3/DW3。启用DW_PRIORITY后，空闲时先搜索就绪的DW3，连续发射最多两项后给普通3×3一次优先机会；整轮没有可运行的优先类别就回退。依赖、输入提交、缓冲预约及clear/fault取消仍必须满足。已执行任务不抢占，其他算子池独立发射。

|配置|图1补边后等待DW3|图1结果读完时刻|六图整批周期|
|---|---:|---:|---:|
{table}

本次组合让图1更早出结果、DW3排队明显缩短，但整批比基线慢约4.2%；因此保留可选开关，不称为无条件吞吐优化。**当前小回归吞吐更好的选择是八位置1×1 + 原调度**：239519→229583拍，减少约4.15%。单层改善不能直接外推成全网改善；全网需同数据对照后决定调度策略。

四配置均通过overlap、serial、preloaded、stress，各48任务/614400MAC/107784检查字节，6144字节输出SHA相同。压力场景组合400488→338547拍，说明最优策略依赖输入/输出等待条件。

## 查看与复现

- [小回归逐图片前后图](small_task_comparison.png)；[原始数值与配置](comparison.json)；evidence保留四配置、单测和综合来源。
- PW8独立72数值配置、3次clear、锁存、13非法、2同拍响应PASS；包括7×7尾块、奇数通道、最终1×1×512层。
- 调度器七组控制测试覆盖有限优先、防饥饿机会、单类别回退、缓冲反压、依赖与输入门控、clear、fault。该单测使用延迟模型，只证明控制；六图小回归使用真实算术RTL。

```text
python3 scripts/run_pw8_unit_wsl.py
python3 scripts/run_dispatch_priority_wsl.py
python3 scripts/run_self_six_wsl.py --data build/self_six_small --pw8
python3 scripts/run_self_six_wsl.py --data build/self_six_small --pw8 --dw-priority
```

两个开关为RTL例化/编译参数，默认0，尚未做CPU运行时策略寄存器。--pw8同时打开前三轮优化，--dw-priority单独选择调度。旧交付、旧波形与默认配置不被覆盖。更详细设计见[设计说明](../../docs/pw8_priority_design.md)。
'''
 (out/'README.md').write_text(report,encoding='utf-8')
 (out/'provenance.json').write_text(json.dumps(dict(reporter_sha256=sha(Path(__file__)),runs=RUNS,other=OTHER,files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}),indent=2)+'\n')
 print(out)
if __name__=='__main__':main()
