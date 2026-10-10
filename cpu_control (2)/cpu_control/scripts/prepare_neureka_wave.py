"""Select non-duplicated real RTL signals; derive markers from actual events."""
from pathlib import Path
import argparse,bisect,csv,json,shutil
from plot_waveforms import read_vcd

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
record=json.loads((a.run/'result.json').read_text())
assert record['status']=='PASS' and 'neureka' in record['tests']
src=a.run/'neureka';work=json.loads((src/'workload.json').read_text())
out=ROOT/'deliverables/neureka_benchmark/small_wave';out.mkdir(parents=True,exist_ok=True)
shutil.copyfile(src/'wave.vcd',out/'wave.vcd')
shutil.copyfile(a.run/'result.json',out/'result.json')
shutil.copyfile(src/'events.csv',out/'events.csv')
v=read_vcd(out/'wave.vcd');prefix='tb_neureka_benchmark.'
groups=[(0,['clk','rst_n']),
        (4,['status_busy','status_done','status_error','task_index','task_opcode','core_active','core_state']),
        (3,['mmio_addr','mmio_wdata','mmio_we','mmio_re','mmio_ready','mmio_rdata']),
        (1,['imem_addr','imem_re','imem_rdata']),
        (6,['dmem_addr','dmem_wdata','dmem_wstrb','dmem_we','dmem_re','dmem_rdata']),
        (2,['cnn_valid','cnn_ready','cnn_write','cnn_byte','cnn_addr','cnn_wdata','cnn_response','cnn_rdata','cnn_cancel','cnn_mem_fault'])]
names=[n for _,group in groups for n in group]
assert len(names)==len(set(names))
assert len({v.signals[prefix+n].code for n in names})==len(names),'aliased nets must appear only once'
events=list(csv.DictReader((src/'events.csv').open()))
offset=next(t for t,b in v.signals[prefix+'cycles'].events if int(b,2)==1)
event_ns=lambda event,task=None:next(int(e['cycle'])*10+offset for e in events if e['event']==event and (task is None or int(e['task'])==task))
conv_index=work['tasks'].index('NEureka_conv')
conv_start=event_ns('dispatch',conv_index);conv_end=event_ns('complete',conv_index)
def at(name,t):
    signal=v.signals[prefix+name];idx=bisect.bisect_right(signal.events,(t,'z'*max(signal.width,1)))-1
    return int(signal.events[idx][1],2)
writes=[]
for t,value in v.signals[prefix+'clk'].events:
    if value!='1' or not conv_start<=t<=conv_end:continue
    # Sample just before the accepting rising edge, not after NBA updates.
    q=t-0.001;mask=at('cnn_valid',q)&at('cnn_ready',q)&at('cnn_write',q)&0x1ff
    for lane in range(9):
        if mask>>lane&1:
            writes.append(dict(time_ns=t,lane=lane,address=f'0x{at("cnn_addr",q)>>(32*lane)&0xffffffff:08x}',
                               data=f'0x{at("cnn_wdata",q)>>(32*lane)&0xffffffff:08x}',byte_access=at('cnn_byte',q)>>lane&1))
    if len(writes)>=12:break
assert writes,'no accepted convolution output writes'
with (out/'first_convolution_writes.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(writes[0]));writer.writeheader();writer.writerows(writes)
markers={'CPU_START':event_ns('start'),'CONV_DISPATCH':conv_start,'FIRST_CONV_WRITE':writes[0]['time_ns'],'CONV_COMPLETE':conv_end}
lines=['[*] Genuine final NEureka RTL, small tensor validation; no UART stimulus',
       f'[dumpfile] "{(out/"wave.vcd").as_posix()}"',f'[savefile] "{(out/"signals.gtkw").as_posix()}"',
       '[timestart] 0','[size] 1800 1400','[pos] 0 0','*-17 -1 '+' '.join(['-1']*26),
       '[sst_width] 120','[signals_width] 370','[sst_expanded] 0']
for color,group in groups:
    for name in group:
        s=v.signals[prefix+name]
        lines += ['@28' if s.width==1 else '@22',f'[color] {color}',s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
(out/'signals.gtkw').write_text('\n'.join(lines)+'\n',encoding='ascii')
(out/'view.rc').write_text('fontname_signals Monospace 9\nfontname_waves Monospace 9\nsst_expanded 0\nsplash_disable 1\n',encoding='ascii')
tcl=['set out [file dirname [file normalize [info script]]]','set log [open [file join $out validation.log] w]',
     'set shown [gtkwave::getDisplayedSignals]',f'if {{[llength $shown] != {len(names)}}} {{error "wrong signal count"}}',
     'puts $log "COUNT=[llength $shown]"','foreach name $shown {puts $log "SIGNAL=$name"}',
     'gtkwave::/Edit/Set_Trace_Max_Hier 1','gtkwave::/View/Scale_To_Time_Dimension/us']
for letter,(name,t) in zip('ABCD',markers.items()):tcl.append(f'gtkwave::setNamedMarker {letter} {round(t*1000)} {name}')
for view,start,end in [('all',0,v.end_ns),('first_write',max(0,writes[0]['time_ns']-150),writes[0]['time_ns']+450)]:
    tcl += [f'gtkwave::setZoomRangeTimes {round(start*1000)} {round(end*1000)}','gtkwave::setMarker -1',
            'gtkwave::setTraceScrollbarRowValue 0','update','after 500',
            f'gtkwave::/File/Write_Save_File_As [file join $out {view}.gtkw]',
            f'gtkwave::/File/Grab_To_File [file join $out {view}.png]']
tcl += ['puts $log "PASS unique RTL signals loaded"','close $log','gtkwave::/File/Quit']
(out/'export.tcl').write_text('\n'.join(tcl)+'\n',encoding='ascii')
for view in ['all','first_write']:
    (out/f'open_{view}.cmd').write_text('@echo off\r\nsetlocal\r\nset "GTK=%~dp0..\\..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe"\r\nstart "" "%GTK%" -f "%~dp0wave.vcd" -a "%~dp0'+view+'.gtkw" -r "%~dp0view.rc"\r\n',encoding='ascii')
(out/'provenance.json').write_text(json.dumps(dict(run=str(a.run),workload=work,markers_ns=markers,signals=names),indent=2))
guide=f'''# NEureka 小图逐拍波形怎么读

这是本次适配 RTL 对 {work['size']}×{work['size']}、{work['ci']}→{work['co']} 通道的验证波形，用来观察接口。大图性能数字请看上一级实测报告，不能把本文件的微秒长度当成大图耗时。本用例没有 UART 输入，数据由仿真预置在 SRAM。

打开 `open_all.cmd` 看全过程，`open_first_write.cmd` 看第一批卷积写回。共 {len(names)} 根信号，同一根网只展示一次，按时钟、状态、MMIO、IMEM、CPU 数据口、CNN 存储口分组并着色。GTKWave 可以手动展开 352 bit 总线。

| 标记 | 真实时间（µs） | 意义 |
|---|---:|---|
| A | {markers['CPU_START']/1000:.3f} | CPU 写启动寄存器 |
| B | {conv_start/1000:.3f} | 队列派发 op11，随后配置 NEureka |
| C | {writes[0]['time_ns']/1000:.3f} | SRAM 接受第一笔卷积结果写入 |
| D | {conv_end/1000:.3f} | 卷积任务完成，后面仍有排布转换和后处理 |

任务依次为：0 输入 CHW→HWC，1 卷积，2 输出 HWC→CHW，3 ReLU，4 MaxPool。`task_index` 是已完成任务数，在当前执行阶段也对应任务序号；阶段交界还包含取描述符的时间。`task_opcode` 为 12、11、12、6、8，GTKWave 十六进制分别显示 c、b、c、6、8。

| 信号 | 从哪里到哪里 / 功能 |
|---|---|
| clk / rst_n | 仿真时钟、低有效复位；100 MHz，每周期 10 ns |
| status_busy / done / error | CNN 到 CPU MMIO 状态寄存器；busy 包含搬运和后处理，done/error 是完成或异常事件 |
| core_active | NEureka 核心到内部控制器的 busy；包括取数、计算、量化、写回，不等于每拍 MAC 都有效 |
| core_state | NEureka 内部控制状态观察值；0 IDLE、2 LOAD、3 WEIGHTOFFS、4 MATRIXVEC、5～7 量化、8 STREAMOUT、12 DONE；计算阶段也可能有等待 |
| mmio_addr / wdata / re / we | CPU → CNN，寄存器地址、写数据、读写请求 |
| mmio_ready / rdata | CNN → CPU，寄存器访问可完成、读回数据；与请求在上升沿相遇表示一次访问 |
| imem_addr / re | CPU → IMEM，指令地址和读取请求 |
| imem_rdata | IMEM → CPU，32 位指令 |
| dmem_addr / wdata / wstrb / re / we | CPU → DATASRAM，地址、写数据、四字节使能、读写请求；结束时 CPU 向 0x80 写 0x600d |
| dmem_rdata | DATASRAM → CPU，读取结果 |
| cnn_valid[i] / ready[i] | CNN 请求 / SRAM 接受；上升沿两者为 1 才发生一次访问 |
| cnn_write[i] / byte[i] | CNN → SRAM，1 表示写 / 单字节访问；write=0 为读，byte=0 为 32 位访问 |
| cnn_addr / wdata | CNN → SRAM，每个客户端对应一个 32 位字段，从低位到高位排列 0～10 |
| cnn_response[i] / rdata | SRAM → CNN，该客户端事务完成，读数据位于同编号的 32 位字段；写事务也有完成回复 |
| cnn_cancel | CNN → SRAM，复位或取消未完成请求 |
| cnn_mem_fault | SRAM → SoC 故障观察，越界/非法访问锁存；本用例应始终为 0 |

观察卷积写回时，选 `task_opcode=b`，再看客户端 0～8：某位 `valid & ready & write` 在时钟上升沿为 1，就代表该路卷积输出被 SRAM 接受。客户端 9 的写是排布转换，客户端 10 的写是后处理，不能把所有写都当成卷积写回。首次实际写入为客户端 {writes[0]['lane']}、地址 {writes[0]['address']}、数据 {writes[0]['data']}；其他并行写见 `first_convolution_writes.csv`。

NEureka 此时写的是临时 HWC 输出区。它随后转成原后处理使用的 CHW 区，再经过 ReLU 和池化写入最终结果区，因此第一次卷积写入不代表整张图的全部处理结束。波形中的 `status_done` 为一拍完成事件；CPU 读到的 MMIO STATUS 的 DONE 位会保持，直到新启动或清除。

来源：`{a.run}`。`result.json` 保存 PASS、周期和实际编译源码哈希；`wave.vcd` 为仿真器原始逐拍转储。
'''
(out/'波形阅读说明.md').write_text(guide,encoding='utf-8')
print(out)
