"""Package actual lease-control traces, preserving raw signals and provenance."""
import argparse,bisect,csv,json,hashlib,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments,Signal
from prepare_network_parallel import local
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
 r=json.loads((run/'result.json').read_text());assert r['status']=='PASS'
 for n,h in r['build_inputs'].items():assert hashlib.sha256(local(n).read_bytes()).hexdigest()==h,n
 protocol=ROOT/'build/buffer_leases_test';pr=json.loads((protocol/'result.json').read_text());assert pr['status']=='PASS'
 for n,h in pr['hashes'].items():assert hashlib.sha256(local(n).read_bytes()).hexdigest()==h,n
 out=ROOT/'deliverables/network_buffered';out.mkdir(exist_ok=True)
 shutil.copyfile(run/'result.json',out/'result.json');shutil.copyfile(protocol/'result.json',out/'protocol_result.json');shutil.copyfile(protocol/'sim.log',out/'protocol.log')
 spec=json.loads((run/'dual/workload.json').read_text());shutil.copyfile(run/'dual/workload.json',out/'workload.json')
 for case in ['dual','skew_stall']:
  src=run/case
  for n,h in r['data_hashes'].items():assert hashlib.sha256((src/n).read_bytes()).hexdigest()==h
  assert hashlib.sha256((src/'outputs.bin').read_bytes()).hexdigest()==r['cases'][case]['output_sha256']
  for n in ['control.vcd','lifetime.csv','events.csv','metrics.json','outputs.bin']:shutil.copyfile(src/n,out/(case+'_'+n))
  v=read_vcd(src/'control.vcd');entries=[]
  for slot in range(8):
   s=v.signals['network.buffer_live'];entries.append(Signal(f'slot{slot}_live',1,f'b{slot}',[(t,str((int(x,2)>>slot)&1)) for t,x in s.events]))
  for n,w in [('buffer_release',8),('buffer_allocate',8),('wait_buffer',1),('completed_count',11),('done',1),('error',1)]:
   s=v.signals['network.'+n];entries.append(Signal(n,w,'b'+str(len(entries)),[(t,format(int(x,2),f'0{w}b')) for t,x in s.events]))
  for s in entries:
   compact=[]
   for t,value in s.events:
    if not compact or compact[-1][1]!=value:compact.append((t,value))
   s.events=compact
  header=['$timescale 1ns $end','$scope module buffers $end'];changes={}
  for s in entries:
   header.append(f'$var wire {s.width} {s.code} {s.path} $end')
   for t,x in s.events:changes.setdefault(int(t),[]).append(f'b{x} {s.code}')
  header+=['$upscope $end','$enddefinitions $end']
  for t in sorted(changes):header+=['#'+str(t),*changes[t]]
  (out/(case+'.vcd')).write_text('\n'.join(header)+'\n')
  life=list(csv.DictReader((src/'lifetime.csv').open()));owners=[[(int(e['cycle'])*10,int(e['owner'])) for e in life if e['event']=='allocate' and int(e['slot'])==slot] for slot in range(8)]
  im=Image.new('RGB',(1800,1040),'#f7f9fc');d=ImageDraw.Draw(im);font=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
  d.text((24,18),'六帧中间缓冲复用：'+('正常双核' if case=='dual' else '限速与反压'),font=font(27),fill='#243a52')
  d.text((24,62),'高电平=槽位被占用；F为帧号、T为结果生产任务号。每次释放后测试台立即用0xD7覆写。',font=font(18),fill='#51647d')
  left=10;right=v.end_ns;x=lambda t:300+(t-left)/(right-left)*1450
  for k in range(9):
   t=left+(right-left)*k/8;xx=x(t);d.line((xx,130,xx,980),fill='#dce4ed');d.text((min(xx-20,1640),105),f'{t/1e6:.3f} ms',font=font(15),fill='#51647d')
  for i,s in enumerate(entries):
   y=146+i*57;color='#287bd0' if i<4 else '#27864d' if i<8 else '#8065ad';d.text((24,y),s.path,font=font(18),fill=color);prev=None
   for l,rr,b in segments(s,left,right):
    aa,bb=x(l),x(rr);val=int(b,2)
    if s.width==1:
     yy=y+2 if val else y+30
     if prev is not None:d.line((aa,prev,aa,yy),fill=color,width=2)
     d.line((aa,yy,bb,yy),fill=color,width=2);prev=yy
     if i<8 and val:
      k=bisect.bisect_right([t for t,o in owners[i]],l)-1
      if k>=0:
       node=owners[i][k][1];label=f'F{node//10}/T{node}'
       if bb-aa>len(label)*9+6:d.text((aa+3,y+4),label,font=font(15),fill=color)
    else:
     d.rectangle((aa,y+2,bb,y+30),outline=color)
     if bb-aa>len(str(val))*10+8:d.text((aa+3,y+4),str(val),font=font(16),fill=color)
   if s.width==1 and s.events[-1][0]==right and prev is not None:
    yy=y+2 if int(s.events[-1][1],2) else y+30;d.line((1750,prev,1750,yy),fill=color,width=2)
   if s.path=='done':d.text((1520,y+3),'done=1，记录结束',font=font(16),fill=color)
  assert int(v.signals['network.buffer_live'].events[-1][1],2)==0
  d.text((300,1000),'最后采样：completed_count=60，所有slot_live=0；右边界的释放沿请在GTKWave放大观察。',font=font(17),fill='#51647d')
  im.save(out/(case+'.png'))
  gtk=['[dumpfile] "'+str(out/(case+'.vcd')).replace('\\','/')+'"']
  for i,s in enumerate(entries):gtk+=['@28' if s.width==1 else '@24','[color] '+str(4 if i<4 else 5 if i<8 else 6),'buffers.'+s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
  (out/(case+'.gtkw')).write_text('\n'.join(gtk)+'\n');tcl=f'gtkwave::setZoomRangeTimes 10 {int(right)}\n';(out/(case+'.tcl')).write_text(tcl)
  (out/('verify_'+case+'.tcl')).write_text(tcl+'if {[llength [gtkwave::getDisplayedSignals]] != 14} {error "signal count"}\nset f [open [file join [file dirname [info script]] validation.log] a]\nputs $f "PASS '+case+' signals=14"\nclose $f\ngtkwave::/File/Quit\n')
  (out/('open_'+case+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0'+case+'.vcd" -a "%~dp0'+case+'.gtkw" -S "%~dp0'+case+'.tcl"\n')
 t=r['timing_seconds'];reused=r.get('reused_cases',{})
 table='\n'.join(f"| {n} | {m['cycles']:,} | {m['allocations']}/{m['releases']} | {m['wait_buffer_cycles']} | {reused.get(n,{}).get('original_seconds',t[n]):.2f}秒{'（复用先前PASS）' if n in reused else ''} |" for n,m in r['cases'].items())
 (out/'README.md').write_text(f'''# 六帧中间缓冲区复用：验证结果

**四项真实RTL回归PASS；独立生命周期协议测试PASS。**

6帧任务交替使用两张不同人脸的小区域输入，经前三层卷积/后处理，再做一次人为增加的残差Add压力测试。不是完整神经网络，不包括UART。新增8槽的占用、代号检查与消费者完成后释放；所有槽反复使用，每次释放立即覆写0xD7，后续计算仍全部匹配参考。

中间工作池{spec['intermediate_pool_bytes']:,}字节（38.5KiB，含每槽64字节保护区）；若这6帧的中间结果各自保留不复用，逻辑张量合计{spec['unreused_intermediate_bytes']:,}字节。该对比不包括输入、权重、命令/生命周期表、最终输出持久存储，也不是完整网络的SRAM容量结论。

| 场景 | 周期 | 分配/释放 | 等待缓冲条件周期 | 电脑仿真耗时 |
|---|---:|---:|---:|---:|
{table}

每项60命令，核对136,704字节，42次预约及42次释放；6帧最终输出均在回收前保存，四项最终哈希一致。本次编译{t['compile']:.2f}秒，新执行的仿真合计{sum(t[n] for n in r['cases']):.2f}秒，当前运行总计{t['total']:.2f}秒。表中复用项列的是原始PASS耗时，本次不重复执行。协议测试另外编译{pr['compile_seconds']:.2f}秒、仿真{pr['simulation_seconds']:.3f}秒。此前有编译列表遗漏、宽读取尾部越界和压力测试时间上限不足的失败运行，已保留，以上耗时不是整个调试过程总耗时。

## 看波形

- [正常双核的槽位占用](dual.png)，open_dual.cmd用GTKWave打开。
- [限速和反压下的复用](skew_stall.png)，open_skew_stall.cmd用GTKWave打开。

每个视图14条不重复信号。slot0～3属于一组工作区，slot4～7属于另一组；高电平表示不可覆盖。图内F0～F5为帧号，T为该结果的生产任务号，由实际预约日志解码。观察相同槽位反复从低到高、标签变成后续帧，说明地址被复用。slot3/7保留中间层旁路，等最终Add完成才释放。

buffer_allocate是预约通知，buffer_release为满足释放条件的通知，下一上升沿live清零；wait_buffer表示当前扫描任务因槽位条件等待。completed_count最终60，done在最后采样升高。短脉冲和末端计数可在GTKWave放大。原始控制VCD与逐次lifetime.csv另行保留。

## 当前边界与对接

静态地址规划＋硬件运行时预约，尚非任意地址动态分配器。两组工作区有帧进入依赖，避免多个帧各占一半资源导致死锁；尚非无限输入队列。生产DATASRAM未改。

最终结果由测试台在done通知时取走后立即允许回收；接生产CPU/UART时还需增加输出消费握手，消费者没读完就不能释放。完整网络生命周期、权重分批加载、条带输入还未接入。配置和端口详见[接口说明](../../docs/network_buffered_design.md)。
''',encoding='utf-8')
 (out/'provenance.json').write_text(json.dumps(dict(run=str(run),protocol=str(protocol)),indent=2));print(out)
if __name__=='__main__':main()
