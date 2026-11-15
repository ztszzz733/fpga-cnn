"""Deliver only a fully passed wide-read/post-pipeline six-frame run."""
from pathlib import Path
import json,hashlib,shutil,sys,subprocess
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/runs/20261023_215237_self_six'
SMALL=ROOT/'build/runs/20261024_003435_837468_self_six'
PREVIOUS=ROOT/'build/runs/20261023_235119_795821_self_six'
EVIDENCE={
 'k3_unit':('20261024_002915_167020_wide_unit_k3','rtl/cnn_self/self_conv_wide_engine.sv'),
 'post_unit':('20261024_003247_912639_post_pipe_unit','rtl/cnn_quant/quant_post_pipe_engine.sv'),
 'k3_synth':('20261024_003208_449556_self_cnn_synth','rtl/cnn_self/self_conv_wide_engine.sv'),
 'post_synth':('20261024_003338_786521_self_cnn_synth','rtl/cnn_quant/quant_post_pipe_engine.sv')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def seal(out):
 # The generic report is extended above; update its hashes to the final files.
 base=read(out/'provenance.json')
 base['files']={p.name:sha(p) for p in out.iterdir() if p.is_file() and not p.name.endswith('provenance.json')}
 base['extended_reporter_sha256']=sha(Path(__file__))
 save(out/'provenance.json',base)
 save(out/'optimization_provenance.json',dict(reporter_sha256=sha(Path(__file__)),result_sha256=sha(out/'result.json'),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='optimization_provenance.json'}))
def main(run):
 run=Path(run).resolve();r=read(run/'result.json');old=read(BASE/'result.json');small=read(SMALL/'result.json');previous=read(PREVIOUS/'result.json')
 assert r['status']==old['status']==small['status']==previous['status']=='PASS'
 assert r['full_network'] and r['wide_pipe'] and r['conv_overlap'] and r['pw4']
 assert r['exe_sha256']==small['exe_sha256'] and r['source_signature']==small['source_signature']
 assert r['manifest_sha256']==old['manifest_sha256'] and r['pool']==old['pool'] and r['input_pace']==old['input_pace'] and r['sram_capacity']==old['sram_capacity']
 for name,digest in r['source_signature']['sources'].items():assert sha(ROOT/name)==digest,name
 data=ROOT/'build/self_six_full';m=read(data/'manifest.json');assert sha(data/'manifest.json')==r['manifest_sha256']
 for name,digest in m['files_sha256'].items():assert sha(data/name)==digest,name
 a=old['scenarios']['overlap']['metrics'];b=r['scenarios']['overlap']['metrics']
 assert read(run/'overlap/metrics.json')==b
 for name,val in [('commands',786),('results',6),('macs',1402862592),('checked_bytes',116023752),('allocations',786),('releases',786)]:assert a[name]==b[name]==val,name
 assert len((run/'overlap/outputs.bin').read_bytes())==768
 assert sha(run/'overlap/outputs.bin')==sha(BASE/'overlap/outputs.bin')==m['final_expected_sha256']
 subprocess.run([sys.executable,str(ROOT/'scripts/prepare_self_six.py'),str(run)],check=True)
 subprocess.run([sys.executable,str(ROOT/'scripts/prepare_self_six_tasks.py'),str(run)],check=True)
 out=ROOT/'deliverables'/('self_cnn_six_'+run.name);e=out/'optimization_evidence';e.mkdir(exist_ok=True)
 evidence={}
 for key,(name,source) in EVIDENCE.items():
  d=ROOT/'build/runs'/name;v=read(d/'result.json');assert v['status']=='PASS'
  h=v.get('sources',v.get('sources_sha256',{}));assert h[source]==sha(ROOT/source),source
  if key.endswith('synth'):assert v['synthesis_setup_met']
  dest=e/key;dest.mkdir(exist_ok=True)
  for f in ['result.json','metrics.json','simulation.log','utilization.rpt','timing_summary.rpt','primitive_counts.tsv']:
   if (d/f).exists():shutil.copyfile(d/f,dest/f)
  evidence[key]=dict(run=name,result_sha256=sha(d/'result.json'))
 for key,d in [('baseline_full',BASE),('gate',SMALL),('previous_small',PREVIOUS)]:shutil.copyfile(d/'result.json',e/(key+'.json'))
 small_cycles={k:dict(previous=previous['scenarios'][k]['metrics']['cycles'],new=v['metrics']['cycles']) for k,v in small['scenarios'].items()}
 comparison=dict(status='PASS',baseline_run=BASE.name,run=run.name,baseline_cycles=a['cycles'],new_cycles=b['cycles'],cycles_reduction_percent=100*(1-b['cycles']/a['cycles']),same_frequency_speedup=a['cycles']/b['cycles'],wall_seconds=r['wall_seconds'],simulation_seconds=b['simulation_seconds'],compile_seconds=r['compile_seconds'],gate_compile_seconds=small['compile_seconds'],small=small_cycles,evidence=evidence,output_sha256=sha(run/'overlap/outputs.bin'))
 save(out/'comparison.json',comparison)
 # Plot the complete six-image batch on a shared axis.
 im=Image.new('RGB',(1500,420),'#101820');draw=ImageDraw.Draw(im);font=lambda s:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',s)
 draw.text((30,20),'完整六图 MobileFaceNet：同样输入、相同输出、相同算子数量',font=font(27),fill='white')
 for i,(label,cycles,color) in enumerate([('原始六图版',a['cycles'],'#8095b6'),('三轮优化后',b['cycles'],'#64d9a2')]):
  y=100+i*120;draw.text((30,y),label,font=font(23),fill='white');end=260+1120*cycles/a['cycles'];draw.rectangle((260,y,end,y+45),fill=color)
  draw.text((260,y+50),f'{cycles:,} 拍 / {cycles/1e8:.6f} 秒 @ 假设100MHz',font=font(22),fill='white')
 draw.text((30,355),f"周期减少 {comparison['cycles_reduction_percent']:.2f}%；同频批次速度 {comparison['same_frequency_speedup']:.2f} 倍。未验证板级频率。",font=font(24),fill='white');im.save(out/'full_comparison.png')
 # Real captured work strobes, split by physical operator (not busy bars).
 labels=['K3 #0 MAC','K3 #1 MAC','K1 #0 MAC (4 lanes)','K1 #1 MAC (4 lanes)','K1 #2 MAC (4 lanes)','K1 #3 MAC (4 lanes)','DW7 MAC (8 lanes)','Post accepted write','Add accepted write','Pad accepted write']
 for name in ['mac_detail','pipeline_detail']:
  v=read_vcd(out/(name+'.vcd'));assert len(v.signals)==10
  s=v.signals['cnn_full.operator_work'];assert len(s.events)>1
  waveform=Image.new('RGB',(1900,1000),'#101820');wd=ImageDraw.Draw(waveform)
  wd.text((30,20),'真实MAC推进与输出写入窗口；Post/Add每次写入可含四个元素',font=font(25),fill='white')
  x0,x1,y0,dy=370,1840,110,76
  for cycle in range(0,257,32):
   x=x0+(x1-x0)*cycle/256
   wd.line((x,y0-20,x,y0+10*dy),fill='#354957')
   wd.text((x-15,y0-55),str(cycle),font=font(20),fill='#c6d5e1')
  ev=s.events+[(v.end_ns,s.events[-1][1])]
  for bit in range(10):
   y=y0+bit*dy;wd.text((25,y+12),labels[bit],font=font(22),fill='white')
   wd.text((333,y-5),'1',font=font(17),fill='#8294a3');wd.text((333,y+34),'0',font=font(17),fill='#8294a3')
   points=[]
   for (t,val),(end,nxt) in zip(ev,ev[1:]):
    level=(int(val,2)>>bit)&1;px=x0+(x1-x0)*t/v.end_ns;qx=x0+(x1-x0)*end/v.end_ns;py=y+40*(1-level)
    points.extend([(px,py),(qx,py)])
   wd.line(points,fill='#63bbef' if bit<7 else '#64d9a2',width=2)
  wd.text((30,925),'窗口相对周期（不是全网起点）；每张图片的全程任务请看 task_timeline。高=本拍推进，低=未推进。',font=font(23),fill='white')
  waveform.save(out/(name+'.png'))
  # Color by signal function while retaining ten unique physical signals.
  session=(out/(name+'.gtkw')).read_text();colors=[7,4,1,1,3,3,6,5,5,2];lines=session.splitlines();idx=0;colored=[]
  for line in lines:
   if line.startswith('cnn_full.'):
    colored.append('[color] '+str(colors[idx]));idx+=1
   colored.append(line)
  assert idx==10;(out/(name+'.gtkw')).write_text('\n'.join(colored)+'\n')
 validator=(ROOT/'scripts/prepare_self_full.py').read_text(encoding='utf-8').split("(out / 'validate_gtkwave.ps1').write_text(r'''",1)[1].split("''', encoding='utf-8')",1)[0]
 validator=validator.replace("('evidence/'+$view+'.vcd')","($view+'.vcd')").replace("$contents.Contains('PASS '+$view)","$contents.Contains('PASS')")
 (out/'validate_gtkwave.ps1').write_text(validator,encoding='utf-8')
 report=f'''# 六图完整网络：第三轮优化验证

完整RTL仿真PASS。六张112×112 RGB合成图片，同批交错执行完整MobileFaceNet，总共786任务、1,402,862,592 MAC；116,023,752个写出字节通过逐值检查，最终768字节与原版及整数参考完全一致。

## 加速结果

|范围|对照|优化后|
|---|---:|---:|
|完整六图硬件周期|{a['cycles']:,}|{b['cycles']:,}|
|假设100MHz，六图整批时间|{a['cycles']/1e8:.6f}秒|{b['cycles']/1e8:.6f}秒|
|六图小回归（仅本轮与上一轮比较）|263,887拍|239,519拍|

完整批次周期减少 **{comparison['cycles_reduction_percent']:.2f}%**，同频批次速度为 **{comparison['same_frequency_speedup']:.2f}倍**。完整对照是原始六图版本，包含四位置K1、K1搬运重叠、K3计算流水及本轮宽读取/后处理的累计收益；不是把全部收益归给本轮改动。小回归本轮再减少9.23%，不能单独外推成全网收益。

本次电脑执行总耗时 **{r['wall_seconds']:.3f}秒**，其中模拟器主体{b['simulation_seconds']:.3f}秒。本次复用小回归程序，重新编译0秒；小门槛首次编译{small['compile_seconds']:.3f}秒。不含此前开发、单测、综合和历史失败尝试，电脑耗时不是硬件时间。

## 看并行与数据流

- [六张图片逐任务交互图](task_timeline/index.html)：每张图一行，移动同一时间游标查看各图正在执行的层和算子。
- [跨算子交接放大图](task_timeline/cross_operator.png)、[卷积并行区间](task_timeline/early_tasks.png)、[全部786任务](task_timeline/full_network.png)。色块含访存等待。
- [完整六图前后比较](full_comparison.png)。
- [实际MAC脉冲](mac_detail.png)与[跨算子推进脉冲](pipeline_detail.png)：来自真实VCD，不是任务条模拟波形。
- GTKWave打开`mac_detail.gtkw`或`pipeline_detail.gtkw`，各10根唯一信号；实际载入验证结果见`gtkwave_validation.json`。

本次跨图实际work重叠{b['multi_frame_work_cycles']:,}拍，跨类work重叠{b['cross_operator_work_cycles']:,}拍。K3/K1/DW7的work为MAC推进，Post/Add/Pad为接受写请求；新Post/Add可一次写四个字节，不能将写脉冲数量下降误解为少算了元素。窗口只有相对起点256拍；全网起止看events.csv，不能将局部波形长度当全网时间。

## 结构与边界

仍为K3×2、K1×4，DW7/Post/Add/Pad各1；没有加倍算子。K3缓存复用不变，新增对齐四字节读取；Post/Add改为七级计算流水和四元素打包写，保留字节尾部及精确舍入。跨算子数据仍写入共享SRAM；尚未做卷积到后处理直接融合或同帧层内条带流水。

K3单模块OOC为2033 LUT、1528 FF、6 BRAM Tile、0 DSP，WNS+0.147ns；Post流水为1092 LUT、848 FF、2.5 BRAM Tile、8 DSP，WNS+2.674ns（Z7020/10ns）。这是独立综合，不是整机布局布线或已实现100MHz。详细证据在optimization_evidence。

输入由测试台经真实SRAM接口写入，整图提交后计算，可与后续图片输入重叠；没有UART或CPU固件参与。合成图片、诊断量化不能证明识别准确率。32MiB仿真SRAM尚未适配512KiB。输出SHA256：`{comparison['output_sha256']}`。

运行目录：`{run}`。设计和复现说明：[wide_pipe_design.md](../../docs/wide_pipe_design.md)。
'''
 (out/'README.md').write_text(report,encoding='utf-8')
 seal(out)
 print(out)
if __name__=='__main__':main(sys.argv[1])
