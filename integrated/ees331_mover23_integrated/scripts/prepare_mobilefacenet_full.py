"""Package only a proven full-network RTL run; plots are from its actual VCD."""
import argparse,csv,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
 result=json.loads((run/'result.json').read_text());assert result['status']=='PASS'
 for n,h in result['build_inputs']['sources'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
 for n,h in result['build_inputs'].get('includes',{}).items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
 for n,h in result['data_hashes'].items():assert hashlib.sha256((run/n).read_bytes()).hexdigest()==h,n
 assert hashlib.sha256((run/'embedding.bin').read_bytes()).hexdigest()==result['output_sha256']
 spec=json.loads((run/'workload.json').read_text());actual=(run/'embedding.bin').read_bytes();assert len(actual)==128
 gold=(run/'golden.bin').read_bytes();assert actual==gold[spec['final_address']:spec['final_address']+128]
 events=list(csv.DictReader((run/'events.csv').open()));assert len(events)==spec['job_count']
 out=ROOT/'deliverables/mobilefacenet_full';out.mkdir(exist_ok=True)
 for n in ['result.json','workload.json','events.csv','embedding.bin','embedding_reference.csv','sim.log']:shutil.copyfile(run/n,out/n)
 shutil.copyfile(run/'control.vcd',out/'control_raw.vcd')
 with (out/'embedding_actual.csv').open('w',newline='',encoding='utf-8') as f:
  writer=csv.writer(f);writer.writerow(['index','rtl_uint8','dequantized'])
  for i,v in enumerate(actual):writer.writerow([i,v,(v-spec['final_zero'])*spec['final_scale']])
 vcd=read_vcd(out/'control_raw.vcd');names=['layer_index','command_kind','operator_start','conv_busy','post_busy','dw7_busy','pad_busy','command_done','done','error']
 sig={n:vcd.signals['network.'+n] for n in names};assert len({s.code for s in sig.values()})==len(names)
 # Restore native one-bit widths for control signals in the display copy;
 # the raw sampled values/timestamps are retained without changes.
 header=['$timescale 1ns $end','$scope module network $end'];changes={}
 for i,n in enumerate(names):
  s=sig[n];width=32 if n in ['layer_index','command_kind'] else 1
  header.append(f'$var wire {width} s{i} {n} $end')
  for t,b in s.events:
   assert int(b,2)<(1<<width)
   changes.setdefault(int(t),[]).append(f'b{int(b,2):0{width}b} s{i}')
 header+=['$upscope $end','$enddefinitions $end']
 for t in sorted(changes):header+=['#'+str(t),*changes[t]]
 (out/'control.vcd').write_text('\n'.join(header)+'\n')
 tail_start=max(int(e['cycle']) for e in events if int(e['layer'])==59)*10
 spans={'overview':(0,vcd.end_ns),'tail':(tail_start,vcd.end_ns),'completion':(vcd.end_ns-2000,vcd.end_ns)}
 font=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
 colors={'conv_busy':'#3383c8','post_busy':'#ba7d17','dw7_busy':'#9865ca','pad_busy':'#168574'}
 for view,(left,right) in spans.items():
  im=Image.new('RGB',(1800,660),'#f7f9fc');draw=ImageDraw.Draw(im);x=lambda t:300+(t-left)/(right-left)*1450
  draw.text((24,18),'完整单图网络：'+({'overview':'全程控制波形','tail':'末端投影、7×7逐通道卷积与最终输出','completion':'最终后处理与完成握手'}[view]),font=font(26),fill='#243a52')
  draw.text((24,61),'真实RTL · 顺序执行 · 100MHz · kind: 0卷积 / 1后处理 / 2Add / 3DW7 / 4补边',font=font(18),fill='#52637b')
  ticks=4 if view=='completion' else 8
  for i in range(ticks+1):
   t=left+(right-left)*i/ticks;xx=x(t);draw.line((xx,130,xx,620),fill='#dce4ed');draw.text((min(xx-20,1620),102),f'{t/1e6:.6f} ms' if view=='completion' else f'{t/1e6:.3f} ms',font=font(14),fill='#52637b')
  for i,n in enumerate(names):
   y=143+i*46;c=colors.get(n,'#51647d');draw.text((24,y),n,font=font(18),fill=c);prev=None
   for l,r,b in segments(sig[n],left,right):
    aa,bb=x(l),x(r)
    if any(v in b for v in 'xz'):
     draw.rectangle((aa,y+3,bb,y+27),outline='#b47a19');prev=None
     if bb-aa>14:draw.text((aa+2,y+2),'X',font=font(16),fill='#b47a19')
     continue
    value=int(b,2)
    if n not in ['layer_index','command_kind']:
     yy=y+3 if value else y+27
     if prev is not None:draw.line((aa,prev,aa,yy),fill=c,width=2)
     draw.line((aa,yy,bb,yy),fill=c,width=2);prev=yy
    else:
     draw.rectangle((aa,y+3,bb,y+27),outline=c)
     if bb-aa>len(str(value))*11+10:draw.text((aa+4,y+2),str(value),font=font(16),fill=c)
   if n=='done' and sig[n].events[-1][0]==right and int(sig[n].events[-1][1],2)==1:
    draw.line((x(right),y+27,x(right),y+3),fill=c,width=2)
    draw.text((x(right)-235,y-3),'done=1（采样在此结束）',font=font(16),fill=c)
  im.save(out/(view+'.png'))
  gtk=['[dumpfile] "'+str(out/'control.vcd').replace('\\','/')+'"']
  for n in names:
   bus=n in ['layer_index','command_kind']
   gtk+=['@24' if bus else '@28','[color] '+str({'conv_busy':4,'post_busy':3,'dw7_busy':6,'pad_busy':2}.get(n,7)),'network.'+n+('[31:0]' if bus else '')]
  (out/(view+'.gtkw')).write_text('\n'.join(gtk)+'\n')
  commands=['gtkwave::/View/Scale_To_Time_Dimension/ms',f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}']
  (out/(view+'.tcl')).write_text('\n'.join(commands)+'\n')
  (out/('verify_'+view+'.tcl')).write_text('\n'.join(commands+['set shown [gtkwave::getDisplayedSignals]','if {[llength $shown] != 10} {error "signal count"}','set f [open [file join [file dirname [info script]] gtkwave_validation.log] a]',f'puts $f "PASS {view} COUNT=[llength $shown]"','close $f','gtkwave::/File/Quit'])+'\n')
  (out/('open_'+view+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0'+view+'.gtkw" -S "%~dp0'+view+'.tcl"\n')
 tim=result['timing_seconds'];m=result['metrics']
 history=[]
 for old in sorted(run.parent.glob('*_mobilefacenet_full')):
  if old.name>run.name or not (old/'result.json').exists():continue
  rr=json.loads((old/'result.json').read_text(encoding='utf-8-sig'));tt=rr.get('timing_seconds',{})
  seconds=lambda key:f"{tt[key]:.2f}秒" if key in tt else '未完整记录'
  history.append(f"| {old.name} | {rr['status']} | {seconds('compile')} | {seconds('simulation')} |")
 history_table='\n'.join(history)
 (out/'README.md').write_text(f'''# 完整单图 MobileFaceNet：顺序RTL验证

**PASS：112×112×3图片 → 51层卷积＋12处残差相加（激活融合后处理）→ 128维量化特征。**

本次运行目录：`{run.name}`。NEureka、末端7×7逐通道算子、量化/激活/Add和补边均执行真实RTL。输入预处理在软件完成并预加载SRAM，中间张量由RTL产生；没有软件替算中间层或注入金标准。

## 结果和耗时

- {m['commands']}条命令全部完成，共逐字节核对{m['checked_bytes']:,}字节；包括各层INT32卷积、UINT8后处理、Add和补边结果。保护区检查通过。
- 本次编译{tim['compile']:.2f}秒；电脑执行仿真{tim['simulation']:.2f}秒；运行流程总计{tim['total']:.2f}秒。不包含此前的数据生成和其他失败/诊断运行。
- 硬件模拟时间：{m['cycles']:,}周期，即{m['cycles']/1e5:.3f}毫秒（100MHz）。这是当前顺序实验配置，不是并行CNN性能或综合时序承诺。
- 最终向量：[实际128维结果](embedding_actual.csv)，量化原始字节[embedding.bin](embedding.bin)。解释方式为`(字节值−{spec['final_zero']})×{spec['final_scale']:.10g}`。
- 本图诊断量化向量与浮点参考的余弦值{spec['diagnostic_float_cosine']:.6f}。尺度取自本图，不能据此声称识别准确率。

本任务此前还有编译中断及因运行慢而主动停止的尝试，不能把最终一次耗时当作整个开发调试耗时：

| 运行 | 状态 | 编译 | 仿真 |
|---|---|---|---|
{history_table}

## 波形怎么看

[全程](overview.png)观察网络节点`layer_index`从0推进到62；这是51个卷积节点和12个Add节点的统一编号，不是原ONNX卷积编号。[末端细节](tail.png)观察`dw7_busy`，随后后处理、最终1×1投影和`done`。

`command_kind`：0 NEureka卷积、1偏置/量化/激活、2残差Add、3独立DW7、4补边。`operator_start`表示发射；对应`*_busy`表示任务尚在执行，包含计算和存储等待，不能理解为每拍都在乘加。`command_done`在该命令最后写响应结束后出现；`done`是整条网络完成。没有UART输入信号，因为本次不包含UART。

双击`open_overview.cmd`或`open_tail.cmd`用GTKWave打开；每个视图10个不重复信号。记录为实际控制状态变化，未记录全部内部乘加阵列。显示副本将0/1控制值恢复为原端口的一位宽度，原始采样另存`control_raw.vcd`；值与时间没有更改。

[最终完成握手放大](completion.png)对应`open_completion.cmd`，观察最后一个`command_done`和全网`done`。0到10ns尚未首次采样，因此显示未知，不能理解为计算错误。全程图中的短脉冲需在GTKWave放大观察。
仿真在`done`升高的最后一个采样点结束，因此图中以右边界上升沿和文字标明，不人为延长高电平。

## 仍未完成的部分

本入口按命令顺序执行，不是把完整网络接入现有双NEureka并行调度器；还没有多图同时运行、UART边收边算或层间直接流转。

实验保留所有中间数据，存储空间{spec['memory_bytes']:,}字节（{spec['memory_bytes']/1048576:.2f}MiB），由四bank C++ SRAM模型响应。生产SRAM容量及RTL没有改变，实际对接需要分块/复用/分批加载权重。输入已预处理，未接CPU/IMAGE_BRIDGE。未做综合、时序、功耗、独立数据集的量化校准或识别准确率评估。

接口和设计见[顺序入口说明](../../docs/mobilefacenet_full_design.md)。后续优先把这一份已核对的任务和参数映射回多算子调度，并落实容量限制；不要直接把本次20MiB地址图交给生产存储使用。
''',encoding='utf-8')
 (out/'provenance.json').write_text(json.dumps(dict(run=str(run),views=spans),indent=2))
 (out/'SHA256.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file() and f.name not in ['SHA256.json','gtkwave_validation.log']},indent=2))
 print(out)
if __name__=='__main__':main()
