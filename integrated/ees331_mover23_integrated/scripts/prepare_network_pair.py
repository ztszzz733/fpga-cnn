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
 out=ROOT/('deliverables/network_pair_full' if r['full_image'] else 'deliverables/network_pair_small');out.mkdir(exist_ok=True)
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
 case_name='fast_reader' if r['full_image'] else 'slow_reader';src=run/case_name;v=read_vcd(src/'control.vcd');entries=[]
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
 for name,left,right,title in [('overview',10,v.end_ns,'两图实际计算与结果交接：全程控制波形'),('first_ack',first_ack-60,first_ack+180,'首个结果交接：读完确认 → 解除保留 → 释放槽位')]:
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
 table='\n'.join(f"| {n} | {m['cycles']:,} | {m['cycles']/100000:.5f} ms | {m['allocations']}/{m['releases']} | {r['timing_seconds'][n]:.2f} 秒 |" for n,m in r['cases'].items())
 spec=json.loads((src/'workload.json').read_text());t=r['timing_seconds']
 scope='完整两张112×112人脸，各128维特征；746条命令' if r['full_image'] else '两张人脸ROI前三层及独立Add、DW7、补边探针；26条命令。探针不是完整网络链路，最终外部取走的是两个90字节补边结果'
 text=f'''# 两图通用数值入口验证

**真实RTL数值检查PASS。** 本轮范围：{scope}。

使用实际NEureka/DW7/后处理/补边，测试台仅实现存储、仲裁、结果读取和比对。中间缓存初始为0xA5，释放后立即覆写0xD7，不向RTL注入参考中间结果。每条有检查负载的命令完成时与独立整数参考比对；最终结果按描述地址读取后确认，帧号、地址和字节数从results.bin获取，不再写死。

| 场景 | 周期 | 100MHz对应硬件时间 | 分配/释放 | 电脑仿真耗时 |
|---|---:|---:|---:|---:|
{table}

本次编译{t['compile']:.2f}秒；数值运行总计{t['total']:.2f}秒。已复用真实NEureka编译库。小数据慢读取包含人为等待，不能作为网络吞吐基准。完整运行若存在，只有fast_reader场景，不重复长仿真。

## 波形

[全程](overview.png) · [首个读取确认附近](first_ack.png)。用open_overview.cmd或open_first_ack.cmd打开GTKWave，共16条分组控制信号。前三条busy包括访存等待，不等于每拍乘加。result_valid表示最终写响应已经排空；外部按result_addr/result_bytes读取，读完才拉result_ready；result_accept是交接后的单拍确认。external_hold清除后才允许buffer_release。compute_done为计算结束，done还要求外部取走全部结果及槽回收。

采样在上升沿后，所以握手后valid可能已下降；识别已发生的握手看result_accept。帧号/地址只在valid为1时有效。全程图密集短脉冲须放大看，不应理解为连续等待；末端done是记录终点，不扩展虚构时间。原始VCD、事件、分配/释放、外部读取日志都保留。

## 边界

SRAM预加载，不包括CPU/UART或分块图像输入；外部读取是测试台直接读SRAM，没有验证生产输出总线带宽。量化尺度是诊断用途，不能宣称识别准确率。中间池{spec['pool_bytes']:,}字节，不包含只读输入/参数和控制表。两图各组缓存隔离，每图内部顺序，跨图并行；不是同一张图跨层条带流水。

[接口说明](../../docs/network_output_handoff.md) · [完整两图计划](../../docs/mobilefacenet_pair_plan.md)
'''
 (out/'README.md').write_text(text,encoding='utf-8')
 (out/'provenance.json').write_text(json.dumps({'run':str(run),'protocols':protocols},indent=2));print(out)
if __name__=='__main__':main()
