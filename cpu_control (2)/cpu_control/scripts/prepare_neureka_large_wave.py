"""Package a completed large-image RTL run and its directly sampled control VCD."""
from pathlib import Path
import argparse, json, csv, shutil, struct, hashlib, bisect, html
from PIL import Image, ImageDraw, ImageFont
from plot_waveforms import read_vcd, segments

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
run=a.run.resolve();src=run/'neureka'
record=json.loads((run/'result.json').read_text())
assert record['status']=='PASS' and record['control_waves']
for name,digest in record['source_hashes'].items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest, name
out=ROOT/'deliverables/neureka_large_wave';out.mkdir(exist_ok=True)
for name in ['controls.vcd','events.csv','control_markers.csv','workload.json','sim.log','program.asm']:
    shutil.copyfile(src/name,out/name)
shutil.copyfile(run/'result.json',out/'result.json')
meta=json.loads((ROOT/'scripts/neureka_control_signals.json').read_text(encoding='utf-8'))
v=read_vcd(out/'controls.vcd')
signals={m['name']:v.signals['control.'+m['name']] for m in meta}
assert len({s.code for s in signals.values()})==len(meta)
assert all('1' not in value for _,value in signals['status_error'].events)
assert all('1' not in value for _,value in signals['mem_fault'].events)
assert any(value=='1' for _,value in signals['status_done'].events)
for name in ['hci_req','hci_gnt','hci_rvalid','cnn_req','cnn_gnt','cnn_response']:
    assert any('1' in value for _,value in signals[name].events),name
assert any(value=='000100' for _,value in signals['core_state'].events)
assert any('x' in value for _,value in signals['hci_req'].events)
work=json.loads((src/'workload.json').read_text());desc=work['descriptors']
markers=list(csv.DictReader((src/'control_markers.csv').open()))
events=list(csv.DictReader((src/'events.csv').open()))
def mark(event,task=None):
    return int(next(m['time_ns'] for m in markers if m['event']==event and (task is None or int(m['task'])==task)))
dispatch={i:mark('dispatch',i) for i in range(5)}
conv_write=mark('first_sram_write',1);pool_write=mark('first_sram_write',4)
all_done=mark('all_done');cpu_done=mark('cpu_completion')
start_cycle=int(next(e['cycle'] for e in events if e['event']=='start'))
offset=dispatch[0]-int(next(e['cycle'] for e in events if e['event']=='dispatch'))*10
start_ns=start_cycle*10+offset
stages=[]
labels=['输入 CHW→HWC','NEureka 卷积 / 量化','输出 HWC→CHW','ReLU','2×2 MaxPool']
for i in range(5):
    end=int(next(e['cycle'] for e in events if e['event']=='complete' and int(e['task'])==i))*10+offset
    stages.append((labels[i],dispatch[i],end))
common=['detail_valid','clk','task_index','task_opcode','queue_state']
memory=['cnn_req','cnn_gnt','cnn_write','cnn_byte','cnn_response']
views={
 '01_overview':('全程：五个任务如何依次完成',0,v.end_ns,
   ['rst_n','queue_state','task_index','task_opcode','task_launch','status_busy','status_done','status_error','wrapper_state','core_busy','core_state','dma_busy','scalar_busy','detail_valid']),
 '02_input':('输入：CPU 启动后，DMA 从 SRAM 读图并转换格式',max(0,start_ns-30),dispatch[0]+850,
   common+['mmio_we','mmio_ready','mmio_addr','mmio_wdata','dma_busy']+memory+['dma_cfg_addr','dma_cfg_wdata','mem_fault']),
 '03_conv_setup':('卷积启动：配置读取、NEureka 开始取数',dispatch[1]-40,dispatch[1]+3000,
   common+['wrapper_state','core_busy','core_state','cfg_req','hci_req','hci_gnt','hci_wen','hci_rvalid','hci_rready','hci_addr']+memory+['lane0_addr','bridge_pending']),
 '04_conv_write':('第一次卷积写回：先完成 SRAM 写，再向 NEureka 回复',max(mark('first_hci_store')-5,conv_write-80),conv_write+500,
   common+['core_busy','core_state','hci_req','hci_gnt','hci_wen','hci_rvalid','hci_rready','hci_addr','hci_be']+memory+['lane0_addr','lane0_wdata','bridge_pending','memory_idle']),
 '05_pool_write':('池化输出：客户端10写入最终结果区',pool_write-65,pool_write+35,
   common+['scalar_busy']+memory+['post_addr','post_wdata','mem_fault']),
 '06_complete':('整批完成：CNN 完成脉冲与 CPU 成功邮箱',all_done-20,cpu_done+2,
   common+['status_busy','status_done','status_error','core_busy','dma_busy','scalar_busy','mmio_re','mmio_ready','mmio_addr','cpu_store','cpu_store_addr','cpu_store_data'])}
colors={0:'#687b91',1:'#bb6c24',2:'#2674c8',3:'#8658c4',4:'#239878',5:'#b44989'}
gtkcolors={0:0,1:6,2:4,3:3,4:2,5:1}
byname={m['name']:m for m in meta}
marker_list=[('A',start_ns,'CPU_START'),('B',dispatch[1],'CONV_DISPATCH'),('C',conv_write,'FIRST_CONV_WRITE'),('D',dispatch[2],'OUTPUT_LAYOUT'),('E',dispatch[3],'RELU'),('F',dispatch[4],'POOL'),('G',pool_write,'FIRST_POOL_WRITE'),('H',all_done,'ALL_DONE')]
exports=['set out [file dirname [file normalize [info script]]]','set log [open [file join $out gtkwave_validation.log] a]',
 'gtkwave::/Edit/Set_Trace_Max_Hier 1','gtkwave::/View/Scale_To_Time_Dimension/us']
for key,(title,left,right,names) in views.items():
    assert len(names)==len(set(names))
    g=['[*] Directly sampled genuine RTL control nets; detail_valid=0 means unavailable',f'[dumpfile] "{(out/"controls.vcd").as_posix()}"',
       '[size] 1850 1050','[pos] 0 0','*-18 -1 '+' '.join(['-1']*26),'[signals_width] 300','[sst_expanded] 0']
    for name in names:
        m=byname[name];width=m['width']
        g+=['@28' if width==1 else '@22',f'[color] {gtkcolors[m["group"]]}','control.'+name+(f'[{width-1}:0]' if width>1 else '')]
    (out/(key+'.gtkw')).write_text('\n'.join(g)+'\n')
    tcl=['gtkwave::/Edit/Set_Trace_Max_Hier 1','gtkwave::/View/Scale_To_Time_Dimension/us',f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}','gtkwave::setMarker -1']
    tcl += [f'gtkwave::setNamedMarker {letter} {t} {label}' for letter,t,label in marker_list]
    (out/(key+'.tcl')).write_text('\n'.join(tcl)+'\n')
    launcher='@echo off\nsetlocal\nset "GTK=%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe"\nstart "" "%GTK%" -f "%~dp0controls.vcd" -a "%~dp0'+key+'.gtkw" -S "%~dp0'+key+'.tcl"\n'
    (out/('open_'+key+'.cmd')).write_text(launcher,encoding='ascii')
    verify=tcl+['set out [file dirname [file normalize [info script]]]','set log [open [file join $out gtkwave_validation.log] a]',
        'set shown [gtkwave::getDisplayedSignals]',f'if {{[llength $shown] != {len(names)}}} {{error "wrong signal count"}}',
        f'puts $log "PASS {key} COUNT=[llength $shown]"','close $log','gtkwave::/File/Quit']
    (out/('export_'+key+'.tcl')).write_text('\n'.join(verify)+'\n')

fontpath=Path('C:/Windows/Fonts/msyh.ttc')
def font(n):return ImageFont.truetype(str(fontpath),n)
def draw_view(key,title,left,right,names):
    width=1800;row=37;top=150;height=top+row*len(names)+88
    im=Image.new('RGB',(width,height),'#f7f9fc');d=ImageDraw.Draw(im);x0=340;x1=1760
    def x(t):return x0+(t-left)/(right-left)*(x1-x0)
    d.text((25,20),title,font=font(28),fill='#1d304a')
    d.text((25,62),'直接采样 RTL 控制信号 · 100 MHz · 时间为上电起点的绝对时间 · X = 此窗口未记录',font=font(19),fill='#52637b')
    for j in range(9):
        xx=x0+(x1-x0)*j/8;t=left+(right-left)*j/8
        d.line((xx,top-25,xx,height-62),fill='#dce4ed')
        label=f'{t/1000:.3f}us' if right-left<10000 else f'{t/1e6:.2f}ms'
        tw=d.textlength(label,font=font(15))
        d.text((max(8,min(xx-tw/2,width-tw-12)),top-50),label,font=font(15),fill='#52637b')
    for i,name in enumerate(names):
        y=top+i*row;c=colors[byname[name]['group']];signal=signals[name]
        d.text((25,y-3),name,font=font(19),fill=c);last=None
        for a,b,value in segments(signal,left,right):
            xa,xb=x(a),x(b)
            if 'x' in value:
                d.line((xa,y+13,xb,y+13),fill='#bbbbbb')
                if xb-xa>35:d.text((xa+4,y-2),'X',font=font(15),fill='#999999')
            elif signal.width==1:
                yy=y+3 if value=='1' else y+24
                if last is not None:d.line((xa,last,xa,yy),fill=c,width=2)
                d.line((xa,yy,xb,yy),fill=c,width=2);last=yy
            else:
                d.line((xa,y+3,xb,y+3),fill=c);d.line((xa,y+25,xb,y+25),fill=c)
                if xb-xa>4:d.line((xa,y+3,xa+2,y+25),fill=c)
                valueint=int(value,2);label=str(valueint) if name in ['queue_state','task_index','wrapper_state','core_state'] else f'{valueint:x}'
                if xb-xa>len(label)*10+5:d.text((xa+4,y+3),label,font=font(15),fill=c)
        d.line((x0,y+31,x1,y+31),fill='#e7ecf2')
    drawn_markers=[]
    for letter,t,label in marker_list:
        if left<=t<=right:
            xx=x(t)
            if drawn_markers and xx-drawn_markers[-1][0]<22:
                drawn_markers[-1][1]+='/'+letter
            else:drawn_markers.append([xx,letter])
    for xx,label in drawn_markers:
        d.line((xx,top-20,xx,height-60),fill='#df4b44',width=1)
        d.text((xx+2,top-23),label,font=font(15),fill='#df4b44')
    d.text((25,height-40),'握手在时钟上升沿发生；取样在每个边沿后 1 ns。状态号和位图含义见《波形阅读说明》。',font=font(18),fill='#52637b')
    im.save(out/(key+'.png'))
for key,args in views.items():draw_view(key,*args)

mem=(src/'memory.bin').read_bytes();config=struct.unpack_from('<24I',mem,desc[1][1])
size=work['size'];co=work['co'];ci=work['ci'];ow=size-2
buffers=[('输入 CHW',desc[0][1],size*size*ci),('输入 HWC',desc[0][2],size*size*ci),('NEureka 打包权重',config[0],co*8*9*4),
         ('卷积输出 HWC',desc[2][1],ow*ow*co),('卷积输出 CHW',desc[2][2],ow*ow*co),('ReLU 输出',desc[3][2],ow*ow*co),('池化最终输出',desc[4][2],(ow//2)**2*co)]
times=record['timing_seconds'];metric=record['tests']['neureka']
def duration(s):return f'{s/60:.2f} 分钟（{s:.3f} 秒）'
guide=f'''# 大图仿真与控制波形阅读说明

本次真实 RTL 仿真已通过：{size}×{size}、{ci} 通道输入，3×3/stride1/valid 卷积得到 {ow}×{ow}×{co}，再做 ReLU 和 2×2/stride2 最大池化，最终得到 {ow//2}×{ow//2}×{co}。卷积、ReLU 和池化共 {metric['checked_bytes']:,} 字节均与独立整数参考计算一致；CPU 最后向 0x80 写入 0x600d。

这里是一张确定性生成的测试图，像素值 0～127、有正负值的 8 bit 权重。不是训练好的人脸识别网络，也不是六张 524×524 的 UART 测试。输入在复位前预置到 SRAM；下面的“输入”表示 SRAM→CNN。

## 实际花了多久

| 项目 | 本次实际记录 |
|---|---|
| 编译仿真程序 | {duration(times.get('neureka_compile',0))} |
| 电脑执行仿真（含波形写出和逐字节核对） | {duration(times['neureka_simulation'])} |
| 本次成功脚本总耗时（生成数据、编译、仿真等） | {duration(times['total'])} |
| 硬件任务时间（CPU 启动到 CNN 完成） | {metric['cnn_cycles']:,} 周期，即 {metric['cnn_cycles']/100000:.5f} ms @100 MHz |

本次复用了上次已保存的仿真程序，重新编译耗时为 0；该程序原始编译耗时为 {record.get('reused_build_compile_seconds', times.get('neureka_compile',0)):.3f} 秒。电脑死机中断的前次运行不是 PASS，其耗时也没有计入本次成功运行。

电脑运行耗时由 Python 单调时钟记录，见 result.json；硬件时间来自 RTL 周期计数。两者不能混用。此处不做前后加速倍数比较。成功脚本总耗时不包含本轮前期修改记录器和准备交付文件的时间。

## 先打开哪些文件

| 文件 | 观察内容 |
|---|---|
| open_01_overview.cmd | 全程五个任务及主要状态机 |
| open_02_input.cmd | CPU 启动及输入排布转换的 SRAM 读写 |
| open_03_conv_setup.cmd | 配置寄存器加载到 NEureka 开始取数 |
| open_04_conv_write.cmd | NEureka 第一次卷积结果写回 |
| open_05_pool_write.cmd | 池化结果写入最终输出区 |
| open_06_complete.cmd | CNN 全部完成与 CPU 写成功邮箱 |

每个视图同一信号只出现一次。颜色：CPU/队列橙色、NEureka 蓝色、DMA 紫色、后处理绿色、SRAM 接口粉色。PNG 是同一 VCD 的静态预览；GTKWave 可以移动、缩放和查看数值。

controls.vcd 是仿真期间直接从 RTL 取值生成，**不是任务事件重建波形**。记录器在每个时钟边沿后 1 ns 采样稳定值，不记录同一时刻的 delta-cycle 毛刺。主要状态全程记录；高频接口只记录各任务启动、首次卷积写回和最终完成附近的窗口。detail_valid=0 时这些接口明确标为 X，表示未记录，不能解释为硬件产生未知值或停止工作。

## 按数据流看控制

1. **CPU 发任务**：mmio_we 与 mmio_ready 配合，地址 0x40000000、写数据 0x3d 为启动。task_launch 表示派发一个任务。task_index 依次为 0～4；task_opcode 依次是 c、b、c、6、8（十六进制）。
2. **SRAM 输入搬运**：task_index=0、dma_busy=1。客户端9的 cnn_req、cnn_gnt 同时为1且 cnn_write=0 时，下一有效上升沿接受读请求；cnn_response[9] 表示读回。随后同一路 write=1，把转换后的字节写入 HWC 输入区。
3. **NEureka 配置与计算**：task_index=1。wrapper_state 先进行清理、配置、触发，再进入 RUN=9。core_state 反复经过 LOAD=2、WEIGHTOFFS=3、MATRIXVEC=4、量化和 STREAMOUT=8；MATRIXVEC 状态不等同于每一拍 MAC 都有效。
4. **卷积访存**：hci_req=1 发请求，hci_wen=1 是读、0 是写。hci_addr 对照下表识别输入、权重或输出。桥把请求拆给 SRAM 客户端0～8。先完成 SRAM 的接受/回复，再 hci_gnt=1，下一拍 hci_rvalid=1；该顺序是现有桥对 NEureka 响应时序的适配。
5. **结果写出**：task_index=1 时，客户端0～8某位 cnn_req & cnn_gnt & cnn_write 在上升沿成立，代表该笔卷积结果写入 SRAM。后续 task_index=2 由 DMA 转回 CHW；task_index=3 执行 ReLU；task_index=4 由客户端10写池化结果。首次写入不代表整张图处理完成。
6. **最终完成**：status_done 为一拍脉冲，status_busy 下降。随后 CPU 向 SRAM 0x80 写入 0x600d，表明固件读取到成功。最终结果保留在池化输出区。

## 关键标记

| 标记 | 绝对硬件时间（µs） | 含义 |
|---|---:|---|
'''
guide+='\n'.join(f'| {letter} | {t/1000:.3f} | {label} |' for letter,t,label in marker_list)
guide+='\n\n## SRAM 数据区\n\n| 内容 | 起始地址 | 字节数 |\n|---|---|---:|\n'
guide+='\n'.join(f'| {name} | 0x{addr:08x} | {length:,} |' for name,addr,length in buffers)
guide+='\n\n## 本次实际接受的首次写入\n\n下面不是预期地址，而是仿真中在上升沿观察到 req、gnt、write 同时成立的事务。32 位写数据按小端字节解释；byte=1 时仅低 8 位写入。\n\n| 任务 | 时间（µs） | SRAM 客户端 | 地址 | 写数据 |\n|---|---:|---:|---|---|\n'
for m in markers:
    if m['event']=='first_sram_write':
        guide+=f'| {labels[int(m["task"])]} | {int(m["time_ns"])/1000:.3f} | {m["lane"]} | 0x{m["address"]} | 0x{m["data"]} |\n'
guide+='\nPNG 中的状态号为十进制；GTKWave 默认将多位总线显示为十六进制，a/b/c/d 对应十进制 10/11/12/13。\n'
first_conv=next(m for m in markers if m['event']=='first_sram_write' and m['task']=='1')
if int(first_conv['address'],16)==desc[2][1] and co>=4:
    raw=int(first_conv['data'],16);values=[(raw>>(8*i)&255) for i in range(4)]
    values=[x if x<128 else x-256 for x in values]
    gold=[int(x,16) for x in (src/'golden.hex').read_text().splitlines()]
    assert all((values[i]&255)==gold[i*ow*ow] for i in range(4))
    guide+=f'\n例如首次卷积写回的数据字为 0x{raw:08x}，小端解释为第一个输出位置的前四个通道 {values}。后续 ReLU 将它们变成 {[max(0,x) for x in values]}；HWC→CHW 转换会改变存放地址，不改变这些数值。该数据字已与独立参考值核对。\n'
guide+='\n\n## 状态机与位图\n\nqueue_state：0 IDLE、1 FETCH_START、2 FETCH_WAIT、3 ISSUE、4 EXECUTE、5 ADVANCE。\n\nwrapper_state：0 IDLE、1 ACQUIRE、2 ACQUIRE_WAIT、3 FETCH、4 FETCH_WAIT、5 CONFIGURE、6 CONFIG_WAIT、7 TRIGGER、8 TRIGGER_WAIT、9 RUN、10 DRAIN、11 SOFT_CLEAR、12 CLEAR_WAIT、13 SETTLE。\n\ncore_state：0 IDLE、1 STREAMIN、2 LOAD、3 WEIGHTOFFS、4 MATRIXVEC、5 NORMQUANT、6 NORMQUANT_BIAS、7 NORMQUANT_SHIFT、8 STREAMOUT、9 STREAMOUT_DONE、10 UPDATEIDX、11 UPDATEIDX_WAIT、12 DONE。\n\n11 位 SRAM 位图按位表示客户端：bit0～8 为卷积桥、bit9 为配置/描述符/DMA、bit10 为后处理。十六进制 200 对应 bit9，400 对应 bit10；组合值表示多个客户端同时有效。scalar_busy 的 bit2 为 ReLU，bit4 为 MaxPool。\n\n## 所有已选信号\n\n| 信号 | 位宽 | 功能与方向 |\n|---|---:|---|\n'
guide+='\n'.join(f'| {m["name"]} | {m["width"]} | {m["description"]} |' for m in meta)
guide+=f'\n\n来源：`{run}`。result.json 保存当前 RTL/测试平台的源码 SHA-256、PASS 与耗时；sim.log 保存独立参考值核对结果；control_markers.csv 保存上升沿实际接受的首次 SRAM 写事务。first_sram_read 标记可能是描述符读取，不能把它一律当作像素读取。本次只增加测试平台记录器，没有改变 NEureka、SRAM 或 CPU RTL。\n'
(out/'波形阅读说明.md').write_text(guide,encoding='utf-8')
(out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>NEureka 大图仿真</title><style>body{max-width:1500px;margin:36px auto;padding:0 24px;background:#f7f9fc;color:#20334d;font:18px/1.7 system-ui}img{width:100%;border:1px solid #dce4ed;margin:20px 0}pre{white-space:pre-wrap;font:16px/1.8 system-ui}</style><h1>NEureka 大图控制波形</h1><p>256×256 RGB → 卷积 → ReLU → 池化。实际 RTL 结果核对通过。</p>'+''.join(f'<h2>{html.escape(args[0])}</h2><img src="{key}.png">' for key,args in views.items())+'<pre>'+html.escape(guide)+'</pre>',encoding='utf-8')
(out/'provenance.json').write_text(json.dumps(dict(run=str(run),signals=meta,markers=marker_list,views=views,stages=stages,signal_checks='PASS'),ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
