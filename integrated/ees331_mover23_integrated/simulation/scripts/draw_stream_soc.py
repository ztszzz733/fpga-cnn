"""Editable six-block diagram matching the stream signal catalog."""
import json,re,xml.etree.ElementTree as E
from pathlib import Path
import draw_soc_top as d
ROOT=Path(__file__).absolute().parents[1];OUT=ROOT/'deliverables/stream_six_images'
d.OUT=OUT;d.mx=E.Element('mxfile',host='app.diagrams.net',version='24.7.17',type='device')
sig=json.loads((OUT/'signal_catalog.json').read_text(encoding='utf-8'))
p=d.Page('01 六模块图片流式处理',2800,2200)
p.text(80,20,2640,60,'六张 524×524 图片流式特征提取',d.WHITE,34)
p.module('CPU CORE','cpu_core_autoload',140,280,500,490,'启动固定流程\n查询完成 · 读取校验和','cpu_state [1:0]')
p.module('IMEM','imem_rom',1100,280,360,300,'固定 RV32I 程序','imem_state [1:0]')
p.module('CNN','cnn_stream_features',140,1210,500,550,'两路固定 3×3 Sobel 卷积\n幅值 /4 → 2×2 最大池化\n行缓冲 · 流式写回','cnn_state [1:0]')
p.module('DATASRAM','datasram_banked',1180,1050,410,710,'1 MiB · 4 个存储体\n六帧结果全部保留\n每帧 136242 字节','sram_state [1:0]')
p.module('IMAGE_BRIDGE','image_bridge_stream',2110,280,440,650,'25 Mbps UART\n双 1024 字节包缓冲\n按包 CRC · 接收和消费解耦','bridge_state [1:0]')
p.module('CLOCK','clock_unit',2130,1410,400,300,'100 MHz · 复位同步释放','clock_state [1:0]')
covered=[]
def link(points,ns,color,src=None,dst=None,box=None):
    p.edge(points,color,src,dst)
    label='\n'.join(' / '.join(f'{n}[{sig[n]["width"]}]' for n in ns[i:i+2]) for i in range(0,len(ns),2))
    if box:p.text(*box,label,color,18)
    covered.extend(ns)
link([(640,350),(1100,350)],['imem_addr','imem_re'],d.BLUE,'CPU CORE','IMEM',(650,288,440,55))
link([(1100,470),(640,470)],['imem_rdata'],d.YELLOW,'IMEM','CPU CORE',(670,426,400,30))
link([(640,620),(1010,620),(1010,1100),(1180,1100)],['dmem_addr','dmem_wdata','dmem_re','dmem_we','dmem_wstrb'],d.BLUE,'CPU CORE','DATASRAM',(650,642,510,100))
link([(1180,1150),(940,1150),(940,740),(640,740)],['dmem_rdata'],d.YELLOW,'DATASRAM','CPU CORE',(655,755,485,30))
link([(260,770),(260,1210)],['cnn_mmio_addr','cnn_mmio_wdata','cnn_mmio_re','cnn_mmio_we'],d.BLUE,'CPU CORE','CNN',(20,845,710,85))
link([(530,1210),(530,770)],['cnn_mmio_rdata','cnn_mmio_ready'],d.YELLOW,'CNN','CPU CORE',(20,1030,710,45))
link([(500,280),(500,155),(2300,155),(2300,280)],['load_req'],d.PINK,'CPU CORE','IMAGE_BRIDGE',(1100,110,700,30))
link([(2450,280),(2450,220),(600,220),(600,280)],['load_complete','load_error'],d.PINK,'IMAGE_BRIDGE','CPU CORE',(1100,175,700,30))
link([(2110,815),(1790,815),(1790,985),(640,985),(640,1240)],['pixel_valid','pixel_data','pixel_sof','pixel_eof','pixel_frame','bridge_error'],d.PINK,'IMAGE_BRIDGE','CNN',(1130,822,940,125))
link([(600,1210),(600,1015),(1750,1015),(1750,920),(2110,920)],['pixel_ready'],d.PINK,'CNN','IMAGE_BRIDGE',(1780,935,300,30))
link([(640,1400),(1180,1400)],['cnn_valid','cnn_write','cnn_byte','cnn_addr','cnn_wdata','cnn_cancel'],d.BLUE,'CNN','DATASRAM',(650,1240,520,135))
link([(1180,1580),(640,1580)],['cnn_ready','cnn_response','cnn_rdata'],d.YELLOW,'DATASRAM','CNN',(650,1455,520,95))
remaining=[n for n in sig if n not in covered and not n.endswith('_state')]
# Include packed state separately because it also ends in _state.
if 'soc_module_state' not in remaining:remaining.append('soc_module_state')
label='顶层引脚与观察信号（不是额外硬件模块）\n'+'\n'.join('   '.join(f'{n}[{sig[n]["width"]}]' for n in remaining[i:i+4]) for i in range(0,len(remaining),4))
p.text(60,1820,2680,310,label,d.GRAY,19)
p.text(1700,1100,1030,220,'CLOCK 的 clk / rst_n 接入其余五个模块\n外部 sys_clk / rst_n_in → CLOCK\nuart_rx 外部 → IMAGE_BRIDGE；uart_tx 反向\n彩色线为总线组，括号内是各信号位宽',d.WHITE,20)
p.save_svg('soc_architecture.svg')
q=d.Page('02 六模块观察状态',2000,1600)
q.text(60,30,1880,70,'六路并行观察状态机',d.WHITE,34)
for i,(name,state) in enumerate(zip(['CPU CORE','CNN','DATASRAM','IMEM','IMAGE_BRIDGE','CLOCK'],['cpu_state','cnn_state','sram_state','imem_state','bridge_state','clock_state'])):
    x=60+(i%2)*970;y=150+(i//2)*450
    q.rect(x,y,910,400,stroke=d.COLORS[name]);q.text(x+20,y+12,870,40,name+' · '+state,d.COLORS[name],25)
    for j,s in enumerate(['RESET = 0','IDLE = 1','WORK = 2','FAULT = 3']):q.rect(x+30+j*215,y+100,195,65,s,stroke=d.COLORS[name],size=20)
    desc={'CPU CORE':'取指或访问接口时 WORK；FAULT 保留。','CNN':'整批处理期间 WORK，包括等像素；流/内存错误进入 FAULT。','DATASRAM':'请求或响应活动时 WORK；内存故障进入 FAULT。','IMEM':'取指使能有效时 WORK；FAULT 保留。','IMAGE_BRIDGE':'收发/缓冲处理时 WORK；协议、CRC、超时错误进入 FAULT。','CLOCK':'外部复位为 RESET；等待释放为 IDLE；释放后 WORK。'}[name]
    q.text(x+35,y+200,840,130,desc+'\n状态在上升沿采样后更新；硬复位回到 RESET。',d.WHITE,21)
q.save_svg('module_states.svg')
E.ElementTree(d.mx).write(OUT/'soc_architecture.drawio',encoding='utf-8',xml_declaration=True)
mapping={n:[] for n in sig}
for c in d.mx.findall('./diagram[1]/mxGraphModel/root/mxCell'):
    for n in sig:
        if re.search(r'(?<![\w])'+re.escape(n)+r'(?![\w])',c.get('value','')):mapping[n].append(c.get('id'))
assert all(mapping.values()),[n for n,v in mapping.items() if not v]
(OUT/'diagram_signal_map.json').write_text(json.dumps(mapping,indent=2))
print('PASS diagram: six hardware blocks, 64 signal names, two pages')
