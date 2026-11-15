"""Editable reference-style diagrams of the current six-peer NEureka SoC."""
from pathlib import Path
import xml.etree.ElementTree as E
import json
import draw_soc_top as d

ROOT=Path(__file__).resolve().parents[1]
d.OUT=ROOT/'deliverables/neureka_interfaces'
d.OUT.mkdir(parents=True,exist_ok=True)
B,Y,P,R,W,G=d.BLUE,d.YELLOW,d.PINK,d.RED,d.WHITE,d.GRAY
signals=[]

def block(p,name,impl,x,y,w,h,notes,state):
    p.rect(x,y,w,h,fill='#101216',stroke=W,kind=name)
    p.text(x+12,y+h/2-70,w-24,44,name,W,29)
    p.text(x+10,y+h/2-20,w-20,30,impl,G,17)
    p.text(x+15,y+h/2+25,w-30,75,notes,G,20)
    p.text(x+12,y+h-65,w-24,36,state+' /2',P,20)

def wire(p,pts,label,color,xy,wh,src=None,dst=None,rotate=0):
    p.edge(pts,color,src,dst)
    p.text(*xy,*wh,label,W,23,rotate=rotate)

def entry(names,widths,src,dst,note):
    for n,w in zip(names,widths):signals.append(dict(signal=n,width=w,source=src,destination=dst,function=note))

p=d.Page('01 六大模块与数据接口',3120,2200)
p.rect(25,25,3070,2150,fill='#101216',stroke='#b4b4b4')
p.text(80,42,2960,55,'NEureka SoC · 六大模块与输入输出信号',W,35)
p.text(80,105,2960,35,'face_soc_neureka_top  |  信号名 / 位宽  |  蓝：地址   黄：数据   粉：控制   红：外部接口',G,22)
block(p,'CPU_CORE','cpu_core_autoload',160,290,540,630,'执行指令 / 提交任务\nMMIO 轮询完成','cpu_state')
block(p,'IMEM','imem_rom',1210,290,350,290,'指令存储','imem_state')
block(p,'CNN','mobilefacenet_neureka_top',160,1330,540,640,'NEureka 4×4 PE\n格式转换 / 原 ReLU / 原池化','cnn_state')
block(p,'DATASRAM','datasram_banked',1280,770,350,1200,'4-bank SRAM\n内部仲裁\nCPU / CNN / IO 共享','sram_state')
block(p,'IMAGE_BRIDGE','image_bridge_autoload',2210,770,420,680,'UART 接收 / CRC\n加载资料到 SRAM','bridge_state')
block(p,'CLOCK','clock_unit',2230,1690,400,280,'时钟直通 / 复位释放','clock_state')
for y,name,w,color,rev in [(335,'imem_addr',32,B,0),(410,'imem_rdata',32,Y,1),(485,'imem_re',1,P,0)]:
    src,dst=('IMEM','CPU_CORE') if rev else ('CPU_CORE','IMEM')
    wire(p,[(1210,y),(700,y)] if rev else [(700,y),(1210,y)],f'{name} /{w}',color,(720,y-39),(470,32),src,dst)
    entry([name],[w],src,dst,'取指地址 / 指令数据 / 读使能')
wire(p,[(2490,770),(2490,205),(490,205),(490,290)],'load_complete /1   +   load_error /1',P,(1050,164),(1100,35),'IMAGE_BRIDGE','CPU_CORE')
wire(p,[(700,655),(2090,655),(2090,805),(2210,805)],'load_req /1',P,(1210,612),(550,34),'CPU_CORE','IMAGE_BRIDGE')
entry(['load_req'],[1],'CPU_CORE','IMAGE_BRIDGE','请求启动固定批次加载')
entry(['load_complete','load_error'],[1,1],'IMAGE_BRIDGE','CPU_CORE','加载完成握手及加载错误')
for y,label,color,rev,names,widths in [
    (785,'dmem_addr /32',B,0,['dmem_addr'],[32]),
    (825,'dmem_wdata /32',Y,0,['dmem_wdata'],[32]),
    (865,'dmem_re /1 + dmem_we /1 + dmem_wstrb /4',P,0,['dmem_re','dmem_we','dmem_wstrb'],[1,1,4]),
    (905,'dmem_rdata /32',Y,1,['dmem_rdata'],[32])]:
    src,dst=('DATASRAM','CPU_CORE') if rev else ('CPU_CORE','DATASRAM')
    wire(p,[(1280,y),(700,y)] if rev else [(700,y),(1280,y)],label,color,(714,y-32),(552,28),src,dst)
    entry(names,widths,src,dst,'CPU 数据读写；wstrb 按字节使能，读返回固定时序')
for x,label,color,rev,names,widths in [
    (215,'cnn_mmio_addr /32',B,0,['cnn_mmio_addr'],[32]),
    (320,'cnn_mmio_wdata /32',Y,0,['cnn_mmio_wdata'],[32]),
    (425,'cnn_mmio_re /1 + we /1',P,0,['cnn_mmio_re','cnn_mmio_we'],[1,1]),
    (530,'cnn_mmio_rdata /32',Y,1,['cnn_mmio_rdata'],[32]),
    (635,'cnn_mmio_ready /1',P,1,['cnn_mmio_ready'],[1])]:
    src,dst=('CNN','CPU_CORE') if rev else ('CPU_CORE','CNN')
    wire(p,[(x,1330),(x,920)] if rev else [(x,920),(x,1330)],label,color,(x-203,1110),(360,30),src,dst,rotate=-90)
    entry(names,widths,src,dst,'CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手')
for y,label,color,rev,names,widths in [
    (1410,'cnn_addr /352 (11 × 32)',B,0,['cnn_addr'],[352]),
    (1480,'cnn_wdata /352 (11 × 32)',Y,0,['cnn_wdata'],[352]),
    (1550,'cnn_valid /11',P,0,['cnn_valid'],[11]),
    (1620,'cnn_write /11  +  cnn_byte /11',P,0,['cnn_write','cnn_byte'],[11,11]),
    (1690,'cnn_ready /11',P,1,['cnn_ready'],[11]),
    (1760,'cnn_response /11',P,1,['cnn_response'],[11]),
    (1830,'cnn_rdata /352 (11 × 32)',Y,1,['cnn_rdata'],[352]),
    (1900,'cnn_cancel /1',P,0,['cnn_cancel'],[1])]:
    src,dst=('DATASRAM','CNN') if rev else ('CNN','DATASRAM')
    wire(p,[(1280,y),(700,y)] if rev else [(700,y),(1280,y)],label,color,(725,y-38),(530,31),src,dst)
    entry(names,widths,src,dst,'11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务')
for y,label,color,rev,names,widths in [
    (900,'io_mem_addr /32',B,0,['io_mem_addr'],[32]),
    (980,'io_mem_wdata /32',Y,0,['io_mem_wdata'],[32]),
    (1060,'io_mem_req /1 + we /1 + be /4',P,0,['io_mem_req','io_mem_we','io_mem_be'],[1,1,4]),
    (1190,'io_mem_rdata /32',Y,1,['io_mem_rdata'],[32]),
    (1270,'io_mem_gnt /1 + rvalid /1 + error /1',P,1,['io_mem_gnt','io_mem_rvalid','io_mem_error'],[1,1,1])]:
    src,dst=('DATASRAM','IMAGE_BRIDGE') if rev else ('IMAGE_BRIDGE','DATASRAM')
    wire(p,[(1630,y),(2210,y)] if rev else [(2210,y),(1630,y)],label,color,(1640,y-38),(560,31),src,dst)
    entry(names,widths,src,dst,'加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求')
for y,label,rev in [(920,'uart_rx /1',0),(1370,'uart_tx /1',1)]:
    wire(p,[(2630,y),(3045,y)] if rev else [(3045,y),(2630,y)],label,R,(2645,y-39),(385,32),'IMAGE_BRIDGE' if rev else None,None if rev else 'IMAGE_BRIDGE')
    entry([label.split()[0]],[1],'IMAGE_BRIDGE' if rev else '外部','外部' if rev else 'IMAGE_BRIDGE','外部 UART 串行数据')
for y,name in [(1755,'sys_clk'),(1860,'rst_n_in')]:
    wire(p,[(3045,y),(2630,y)],name+' /1',R,(2650,y-38),(370,32),None,'CLOCK')
    entry([name],[1],'外部','CLOCK','外部时钟 / 低有效复位')
wire(p,[(2230,1800),(1910,1800)],'clk /1',P,(1930,1759),(280,32),'CLOCK')
wire(p,[(2230,1910),(1910,1910)],'rst_n /1',P,(1930,1869),(280,32),'CLOCK')
p.text(1770,1978,980,40,'同名全局网分发至其余五模块；完整连接见第 2 页',G,21)
p.text(140,2010,1570,38,'CNN 客户端：0～8 卷积桥；9 描述符 / 配置 / DMA；10 后处理。',G,23)
p.text(140,2060,2800,35,'本图为当前完整 SoC 接线；已完成的大图仿真只覆盖 CPU / IMEM / CNN / SRAM，图片预加载，不含 UART 闭环。',G,22)
p.text(140,2110,2800,30,'各模块底部为顶层观察状态：0 RESET · 1 IDLE · 2 WORK · 3 FAULT；状态逻辑不增加第七个大模块。',G,21)
p.save_svg('01_soc_interfaces.svg')

q=d.Page('02 时钟复位与状态输出',2560,1710)
q.rect(25,25,2510,1660,fill='#101216',stroke='#b4b4b4')
q.text(60,45,2440,60,'全局时钟、复位及顶层状态信号',W,34)
q.text(60,108,2440,38,'同一设计的辅助接线页 · 下面公式为顶层组合逻辑，不代表新增硬件大模块',G,22)
q.rect(110,245,420,380,'CLOCK\nclock_unit\n\n输入 sys_clk /1、rst_n_in /1\n输出 clk /1、rst_n /1',stroke=W,fill='#101216',size=23,kind='CLOCK')
for i,(name,impl) in enumerate([('CPU_CORE','cpu_core_autoload'),('IMEM','imem_rom'),('CNN','mobilefacenet_neureka_top'),('DATASRAM','datasram_banked'),('IMAGE_BRIDGE','image_bridge_autoload')]):
    yy=205+i*112
    q.rect(1180,yy,560,86,name+'  ·  '+impl,stroke=W,fill='#101216',size=21,kind=name)
    wire(q,[(530,280+i*60),(650+i*70,280+i*60),(650+i*70,yy+43),(1180,yy+43)],'clk /1  +  rst_n /1',P,(925,yy+7),(235,28),'CLOCK',name)
q.text(1830,290,590,220,'clk：sys_clk 直通\n\nrst_n：异步拉低，\n经 3 个时钟沿同步释放\n\n不包含 PLL',G,25)
entry(['clk','rst_n'],[1,1],'CLOCK','CPU_CORE / IMEM / CNN / DATASRAM / IMAGE_BRIDGE','同名全局网，时钟直通及复位同步释放')
q.text(100,825,2350,42,'状态来源与外部 LED',W,29)
rows=[('CNN','cnn_status_busy /1 + cnn_status_done /1 + cnn_status_error /1','顶层观察逻辑',
       'busy/error 用于 cnn_state；done 是完成脉冲，不是板级输出'),
      ('DATASRAM','cnn_mem_fault /1','顶层观察 / LED 组合逻辑','参与 CNN/SRAM 故障状态以及 led_ready / led_error'),
      ('IMAGE_BRIDGE','bridge_ready /1 + bridge_busy /1 + bridge_error /1','顶层观察 / LED 组合逻辑','桥就绪、忙、错误；led_busy 仅表示桥忙')]
for i,(src,label,dst,note) in enumerate(rows):
    yy=920+i*140
    q.text(80,yy-22,360,36,src,W,25)
    wire(q,[(440,yy),(1580,yy)],label,P,(440,yy-41),(1135,32))
    q.text(1605,yy-24,850,38,dst,W,24)
    q.text(440,yy+20,1880,34,note,G,21,align='left')
entry(['cnn_status_busy','cnn_status_done','cnn_status_error'],[1,1,1],'CNN','顶层观察信号','CNN 忙 / 完成脉冲 / 错误；不是顶层外部端口')
entry(['cnn_mem_fault'],[1],'DATASRAM','顶层状态及 LED 逻辑','访存故障；并未直接接入 CNN 的故障输入端口')
entry(['bridge_ready','bridge_busy','bridge_error'],[1,1,1],'IMAGE_BRIDGE','顶层状态及 LED 逻辑','UART 加载桥的就绪 / 忙 / 错误')
q.text(100,1350,2360,100,'外部输出 / 每根 1 bit\nled_ready = bridge_ready && !cnn_mem_fault     ·     led_busy = bridge_busy     ·     led_error = bridge_error || cnn_mem_fault',R,23)
q.text(100,1490,2360,100,'观察状态：cpu_state / cnn_state / sram_state / imem_state / bridge_state / clock_state，各 2 bit\nsoc_module_state /12；soc_active /6；soc_fault /6。它们供仿真观察，不是外部引脚。',G,23)
for n in ['led_ready','led_busy','led_error']:entry([n],[1],'顶层组合逻辑','外部','由本页公式组合生成；led_busy 不是 CNN 忙信号')
for n in ['cpu_state','cnn_state','sram_state','imem_state','bridge_state','clock_state']:entry([n],[2],'顶层观察状态机','仿真观察','RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈')
entry(['soc_module_state','soc_active','soc_fault'],[12,6,6],'顶层观察逻辑','仿真观察','打包顺序高到低：CLOCK、IMAGE_BRIDGE、IMEM、DATASRAM、CNN、CPU_CORE')
q.save_svg('02_clock_status.svg')
target=d.OUT/'neureka_soc_interfaces.drawio'
E.indent(d.mx,space='  ')
E.ElementTree(d.mx).write(target,encoding='utf-8',xml_declaration=True)
parsed=E.parse(target)
assert len(parsed.findall('diagram'))==2
assert len({s['signal'] for s in signals})==len(signals)
for page in parsed.findall('diagram'):
    cells=page.findall('./mxGraphModel/root/mxCell');ids={c.get('id') for c in cells}
    for c in cells:
        for k in ['source','target']:
            assert not c.get(k) or c.get(k) in ids
(d.OUT/'signals.json').write_text(json.dumps(signals,ensure_ascii=False,indent=2),encoding='utf-8')
guide='''# NEureka 六模块接口图

用 draw.io / diagrams.net 打开 `neureka_soc_interfaces.drawio`，包含两页。所有模块、连线和文字均为可编辑对象，主模块端点已连接到对应方框。SVG/PNG 预览使用同一份布局。

第一页按参考图排列六大模块及数据接口；第二页展开时钟、复位、顶层状态和 LED 输出。蓝色为地址、黄色为数据、粉色为控制、红色为外部接口；标签 `/数字` 表示位宽。`we`、`be`、`rvalid` 等省略前缀的标签沿用同一条线上的 `io_mem_` 或 `cnn_mmio_` 前缀。

依据：`rtl/neureka/face_soc_neureka_top.sv` 及各实例的端口。本图描述当前实现，没有把讨论中的融合 ReLU 或流式池化画成已实现功能。CNN 内仍使用独立后处理任务；大图验证从 SRAM 预加载，未验证本顶层 UART 闭环。

CNN 与 SRAM 的 352 bit 地址/数据是 11 组 32 bit 客户端的展平总线，不是单次连续 352 bit 地址；valid、ready、write、byte、response 按客户端逐位对应。只有有效请求被接受时，write/byte/地址/写数据才有该笔事务的含义。

状态观察逻辑位于顶层，不增加第七个大模块。`cnn_mem_fault` 输出到顶层状态/LED 逻辑，不虚构其直接连入 CNN 的错误端口。`led_busy` 当前仅反映 IMAGE_BRIDGE 忙。

## 信号清单

| 信号 | 位宽 | 输出方 | 输入方 | 功能 |
|---|---:|---|---|---|
'''
guide+='\n'.join(f"| {s['signal']} | {s['width']} | {s['source']} | {s['destination']} | {s['function']} |" for s in signals)+'\n'
(d.OUT/'README.md').write_text(guide,encoding='utf-8')
print(target)
print(f'Validated: 2 pages, {len(signals)} unique signals')
