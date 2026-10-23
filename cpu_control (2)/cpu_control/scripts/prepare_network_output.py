"""Package verified real RTL control traces for the result-read handshake."""
import argparse,csv,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments,Signal
from prepare_network_parallel import local
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
 r=json.loads((run/'result.json').read_text());assert r['status']=='PASS'
 for n,h in r['build_inputs'].items():assert sha(local(n))==h,n
 out=ROOT/'deliverables/network_output';out.mkdir(exist_ok=True)
 shutil.copyfile(run/'result.json',out/'result.json')
 protocols={}
 for name in ['result_handoff_test','buffer_leases_test']:
  src=ROOT/'build'/name;pr=json.loads((src/'result.json').read_text());assert pr['status']=='PASS'
  for n,h in pr['hashes'].items():assert sha(local(n))==h,n
  protocols[name]=pr;shutil.copyfile(src/'result.json',out/(name+'.json'));shutil.copyfile(src/'sim.log',out/(name+'.log'))
 for case in r['cases']:
  src=run/case
  for n,h in r['data_hashes'].items():assert sha(src/n)==h,n
  assert sha(src/'outputs.bin')==r['cases'][case]['output_sha256']
  for n in ['control.vcd','handoffs.csv','lifetime.csv','events.csv','launches.csv','outputs.bin','metrics.json']:
   shutil.copyfile(src/n,out/(case+'_'+n))
 src=run/'slow_reader';v=read_vcd(src/'control.vcd');entries=[]
 for bit,name in enumerate(['conv0_busy','conv1_busy','post_busy']):
  s=v.signals['network.operator_busy'];entries.append(Signal(name,1,'o'+str(len(entries)),[(t,str((int(x,2)>>bit)&1)) for t,x in s.events]))
 for name,w in [('result_valid',1),('result_ready',1),('result_accept',1),('result_frame',32),('result_addr',32),('result_bytes',32),('external_hold',8),('buffer_release',8),('wait_buffer',1),('completed_count',11),('compute_done',1),('done',1),('error',1)]:
  s=v.signals['network.'+name];entries.append(Signal(name,w,'o'+str(len(entries)),[(t,format(int(x,2),f'0{w}b')) for t,x in s.events]))
 changes={};header=['$timescale 1ns $end','$scope module handoff $end']
 for s in entries:
  compact=[]
  for t,x in s.events:
   if not compact or compact[-1][1]!=x:compact.append((t,x))
  s.events=compact;header.append(f'$var wire {s.width} {s.code} {s.path} $end')
  for t,x in s.events:changes.setdefault(int(t),[]).append(f'b{x} {s.code}')
 header+=['$upscope $end','$enddefinitions $end']
 for t in sorted(changes):header+=['#'+str(t),*changes[t]]
 (out/'handoff.vcd').write_text('\n'.join(header)+'\n')
 rows=list(csv.DictReader((src/'handoffs.csv').open()));first_ack=next(int(e['cycle'])*10 for e in rows if e['event']=='read_complete')
 colors=['#287bd0']*3+['#23804b']*6+['#b57120']*3+['#8055ac']*4
 font=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
 for name,left,right,title in [('overview',10,v.end_ns,'慢读取全程：结果等待确认时，其他可运行任务继续计算'),('first_ack',first_ack-60,first_ack+180,'首个结果交接：读完确认 → 解除保留 → 释放槽位')]:
  im=Image.new('RGB',(1800,1120),'#f7f9fc');d=ImageDraw.Draw(im);x=lambda t:300+(t-left)/(right-left)*1450
  d.text((22,16),title,font=font(27),fill='#253a51')
  d.text((22,60),'蓝：算子忙闲（含访存等待）  绿：结果交接  橙：缓存保留/释放  紫：完成状态；数据来自实际RTL VCD。',font=font(18),fill='#51647d')
  for k in range(9):
   t=left+(right-left)*k/8;xx=x(t);d.line((xx,135,xx,1040),fill='#dce4ed')
   d.text((min(xx-26,1640),108),f'{t/1e6:.3f} ms' if name=='overview' else f'{t/1000:.2f} us',font=font(15),fill='#51647d')
  for i,s in enumerate(entries):
   y=151+i*55;color=colors[i];d.text((22,y),s.path,font=font(18),fill=color);prev=None
   for l,rr,b in segments(s,left,right):
    aa,bb=x(l),x(rr);val=int(b,2)
    if s.width==1:
     yy=y+2 if val else y+29
     if prev is not None:d.line((aa,prev,aa,yy),fill=color,width=2)
     d.line((aa,yy,bb,yy),fill=color,width=2);prev=yy
    else:
     label=hex(val) if s.path in ['result_addr','external_hold','buffer_release'] else str(val)
     d.rectangle((aa,y+2,bb,y+29),outline=color)
     if bb-aa>len(label)*10+8:d.text((aa+3,y+4),label,font=font(15),fill=color)
   if s.width==1:
    for t,b in s.events:
     if t==right and prev is not None:d.line((x(t),prev,x(t),y+2 if int(b,2) else y+29),fill=color,width=2)
  footer='描述仅在result_valid=1时有效；ready表示读响应已全部返回。每次确认后才能复用原地址。'
  d.text((22,1060),footer,font=font(18),fill='#51647d');im.save(out/(name+'.png'))
  gtk=['[dumpfile] "'+str(out/'handoff.vcd').replace('\\','/')+'"']
  for i,s in enumerate(entries):gtk+=['@28' if s.width==1 else '@22' if s.path in ['result_addr','external_hold','buffer_release'] else '@24','[color] '+str(4 if i<3 else 5 if i<9 else 3 if i<12 else 6),'handoff.'+s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
  (out/(name+'.gtkw')).write_text('\n'.join(gtk)+'\n')
  tcl=f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}\n';(out/(name+'.tcl')).write_text(tcl)
  (out/('verify_'+name+'.tcl')).write_text(tcl+'if {[llength [gtkwave::getDisplayedSignals]] != 16} {error "signal count"}\nset f [open [file join [file dirname [info script]] validation.log] a]\nputs $f "PASS '+name+' signals=16"\nclose $f\ngtkwave::/File/Quit\n')
  (out/('open_'+name+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0handoff.vcd" -a "%~dp0'+name+'.gtkw" -S "%~dp0'+name+'.tcl"\n')
 table='\n'.join(f"| {n} | {m['cycles']:,} | {m['cycles']/100000:.5f} ms | {m['accepted_results']} | {m['wait_buffer_cycles']:,} | {r['timing_seconds'][n]:.2f} 秒 |" for n,m in r['cases'].items())
 m=r['cases']['slow_reader'];t=r['timing_seconds']
 (out/'README.md').write_text(f'''# CNN 结果交接验证

两项真实 RTL 小数据仿真 PASS。六帧结果由外部读取模型按描述地址逐字节取回，正常读取与慢读取的最终结果均与参考及上一版一致。

本版增加“读完确认再释放”：CNN 提供帧号、地址、字节数；外部读完后用 result_ready 确认。未确认时保持描述和 SRAM 结果，缓存不足时正确反压。compute_done 只表示计算完成；done 还要求结果全部取走、槽位全部回收。

| 场景 | 总周期 | 100 MHz对应硬件时间 | 已确认结果 | 等待缓存条件周期 | 电脑仿真耗时 |
|---|---:|---:|---:|---:|---:|
{table}

每项60命令、136,704个数值检查字节、42次分配/42次释放，最终6帧共6,144字节。慢读取在每份描述出现后先等90,000周期，再每7周期读4字节；同时施加算子访存反压。等待外部读取期间有 {m['completions_while_reader_waiting']} 条其他命令完成，说明没有因单份结果等待而冻结全部计算。数据释放后立即覆写0xD7，未确认结果定期检查不变。

慢读取计算完成于第 {m['compute_finish_cycle']:,} 周期，全部交接完成于第 {m['cycles']:,} 周期，两个时间不能混为一谈。以上硬件时间包含人为设置的读取等待，不是网络吞吐率基准。复用已有NEureka库，本次新增包装/测试程序编译 {t['compile']:.2f} 秒，两项仿真共 {sum(t[n] for n in r['cases']):.2f} 秒，本次数值运行总计 {t['total']:.2f} 秒。独立协议测试及旧生命周期回归的耗时另见JSON。

## 波形怎么读

- [慢读取全程](overview.png)：看绿色result_valid长时间保持，以及期间蓝色算子busy和completed_count仍在变化。橙色external_hold保持结果槽占用。
- [首个确认附近](first_ack.png)：外部ready与valid在上升沿握手；随后result_accept脉冲、external_hold对应位清零，buffer_release通知释放。下一份描述可随后出现。
- `open_overview.cmd`、`open_first_ack.cmd` 用本机GTKWave打开相同16根不重复信号。短脉冲请用局部视图。wait_buffer为扫描受阻任务的脉冲，密集显示不代表每周期都停顿。

VCD是每周期上升沿后的采样，result_ready提前在周期前半拍驱动；握手后result_valid可能立即下降，所以观察已发生的握手用result_accept。帧号/地址在valid=0期间可能仍保留旧值，不能解读为新结果。busy包含访存等待，不等于每拍乘加。末端done升高是记录终点，没有额外延伸虚构波形。

## 对接与边界

[接口文档](../../docs/network_output_handoff.md)给同学对接：result_ready必须表示读完；不要收到地址就确认。外部读取必须在clear/cancel时同步取消，不能将旧确认带到新批次。

当前是6帧小ROI、真实前三层卷积/后处理＋人工残差压力Add、8个静态槽、38.5KiB中间池；不是完整MobileFaceNet或UART输入链路。外部读取用测试台直接访问SRAM，尚未验证生产总线/CPU输出带宽。没有改生产CPU、输入或DATASRAM。下一步是完整网络的生命周期规划，再验证多算子入口；没有启动大图仿真。
''',encoding='utf-8')
 (out/'provenance.json').write_text(json.dumps({'run':str(run),'protocols':protocols},indent=2))
 print(out)
if __name__=='__main__':main()
