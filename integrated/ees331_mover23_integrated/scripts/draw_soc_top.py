"""Editable draw.io and SVG generated from identical geometry and labels."""
from pathlib import Path
import html,json,xml.etree.ElementTree as E

OUT=Path(__file__).resolve().parents[1]/'deliverables/soc_top_view'
BLUE='#58a6ff';YELLOW='#efdf69';PINK='#ef72b3';RED='#ff666c';WHITE='#e5e7eb';GRAY='#9ca3af'
COLORS={'CPU CORE':BLUE,'CNN':RED,'DATASRAM':YELLOW,'IMEM':'#8aa8ff','IMAGE_BRIDGE':'#d987ed','CLOCK':'#f3a54d'}
mx=E.Element('mxfile',host='app.diagrams.net',version='24.7.17',type='device')

class Page:
    def __init__(self,name,w,h):
        self.w,self.h=w,h;self.seq=0;self.blocks={}
        d=E.SubElement(mx,'diagram',id='page'+str(len(mx)),name=name)
        g=E.SubElement(d,'mxGraphModel',dx=str(w),dy=str(h),grid='1',gridSize='10',guides='1',
                       tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth=str(w),pageHeight=str(h),background='#101216')
        self.root=E.SubElement(g,'root');E.SubElement(self.root,'mxCell',id='0');E.SubElement(self.root,'mxCell',id='1',parent='0')
        self.svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
                  '<defs>'+''.join(f'<marker id="a{i}" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 L2,5 Z" fill="{c}"/></marker>' for i,c in enumerate([BLUE,YELLOW,PINK,RED,WHITE,GRAY]))+'</defs>',
                  f'<rect width="{w}" height="{h}" fill="#101216"/>']
    def ident(self):self.seq+=1;return 'p'+str(len(mx))+'_'+str(self.seq)
    def rect(self,x,y,w,h,label='',stroke=WHITE,fill='#14181e',size=22,kind=None):
        ident=self.ident()
        c=E.SubElement(self.root,'mxCell',id=ident,value=label,style=f'rounded=0;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};strokeWidth=2;fontColor={WHITE};fontFamily=Microsoft YaHei;fontSize={size};',vertex='1',parent='1')
        E.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
        if kind:c.set('module',kind);self.blocks[kind]=(ident,x,y,w,h)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        if label:self.svg_text(x,y,w,h,label,WHITE,size)
        return ident
    def svg_text(self,x,y,w,h,label,color,size,rotate=0,align='center'):
        lines=label.split('\n');cx=x+w/2;cy=y+h/2
        trans=f' transform="rotate({rotate} {cx} {cy})"' if rotate else ''
        anchor='middle' if align=='center' else 'start'
        xx=cx if align=='center' else x
        self.svg.append(f'<text x="{xx}" y="{cy-(len(lines)-1)*size*0.68}" text-anchor="{anchor}" dominant-baseline="central" font-family="Microsoft YaHei,Arial,sans-serif" font-size="{size}" fill="{color}"{trans}>')
        for i,s in enumerate(lines):self.svg.append(f'<tspan x="{xx}" dy="{0 if i==0 else size*1.36}">{html.escape(s)}</tspan>')
        self.svg.append('</text>')
    def text(self,x,y,w,h,label,color=WHITE,size=22,rotate=0,align='center'):
        c=E.SubElement(self.root,'mxCell',id=self.ident(),value=label,style=f'text;whiteSpace=wrap;html=0;align={align};verticalAlign=middle;strokeColor=none;fillColor=none;fontColor={color};fontFamily=Microsoft YaHei;fontSize={size};rotation={rotate};',vertex='1',parent='1')
        E.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
        self.svg_text(x,y,w,h,label,color,size,rotate,align)
    def edge(self,points,color=WHITE,source=None,target=None):
        style=f'edgeStyle=none;rounded=0;html=0;endArrow=block;endFill=1;strokeColor={color};strokeWidth=2.5;'
        attrs={'id':self.ident(),'value':'','style':style,'edge':'1','parent':'1'}
        for side,unit,pt in [('source',source,points[0]),('target',target,points[-1])]:
            if unit:
                ident,x,y,w,h=self.blocks[unit];attrs[side]=ident
                pre='exit' if side=='source' else 'entry'
                attrs['style']+=f'{pre}X={(pt[0]-x)/w};{pre}Y={(pt[1]-y)/h};{pre}Perimeter=0;'
        c=E.SubElement(self.root,'mxCell',**attrs)
        g=E.SubElement(c,'mxGeometry',relative='1',**{'as':'geometry'})
        for tag,p in [('sourcePoint',points[0]),('targetPoint',points[-1])]:
            E.SubElement(g,'mxPoint',x=str(p[0]),y=str(p[1]),**{'as':tag})
        if len(points)>2:
            a=E.SubElement(g,'Array',**{'as':'points'})
            for x,y in points[1:-1]:E.SubElement(a,'mxPoint',x=str(x),y=str(y))
        index=[BLUE,YELLOW,PINK,RED,WHITE,GRAY].index(color)
        self.svg.append(f'<polyline points="{" ".join(str(x)+","+str(y) for x,y in points)}" fill="none" stroke="{color}" stroke-width="2.5" marker-end="url(#a{index})"/>')
    def module(self,name,impl,x,y,w,h,description,state):
        self.rect(x,y,w,h,stroke=COLORS[name],kind=name)
        if h<=320:
            self.text(x+15,y+18,w-30,36,name,COLORS[name],26)
            self.text(x+15,y+63,w-30,25,impl,GRAY,16)
            self.text(x+15,y+99,w-30,48,description,WHITE,18)
            self.rect(x+25,y+h-100,w-50,55,state,stroke=COLORS[name],fill='#202630',size=18)
            self.text(x+10,y+h-31,w-20,24,'全局输入：clk / rst_n' if name!='CLOCK' else '全局输出：clk / rst_n',GRAY,15)
            return
        self.text(x+15,y+30,w-30,50,name,COLORS[name],30)
        self.text(x+15,y+95,w-30,45,impl,GRAY,17)
        self.text(x+25,y+h/2-40,w-50,100,description,WHITE,22)
        self.rect(x+28,y+h-105,w-56,55,state,stroke=COLORS[name],fill='#202630',size=19)
        self.text(x+15,y+h-39,w-30,27,'全局输入：clk / rst_n' if name!='CLOCK' else '输出同名全局网：clk / rst_n',GRAY,16)
    def save_svg(self,name):
        (OUT/name).write_text('\n'.join(self.svg+['</svg>']),encoding='utf-8')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    p=Page('01 六模块硬件架构',2600,2020)
    p.rect(25,25,2550,1970,fill='#101216',stroke='#66717e')
    p.text(80,35,2400,55,'SoC 六模块硬件架构 · 搬运 / 计算重叠版本',WHITE,34)
    p.text(80,92,2400,32,'face_soc_overlap_top  |  32-bit RV32I  |  共享 8×8 PE  |  4-bank SRAM  |  11 路 CNN 访存',GRAY,20)
    p.module('CPU CORE','cpu_core_autoload',160,250,520,610,'执行程序 · 提交任务队列\n轮询状态 · 读取结果','cpu_state [1:0]')
    p.module('CNN','mobilefacenet_overlap_top',160,1280,520,500,'加载 / 计算 / 写回重叠\n内部多执行单元共享阵列','cnn_state [1:0]')
    p.module('IMEM','imem_rom',1100,250,340,300,'只读指令存储','imem_state [1:0]')
    p.module('DATASRAM','datasram_banked',1180,720,340,1060,'共享数据存储\n\n4 个交错 bank\n内部多路仲裁\n字节写使能\n\nCPU 固定一拍接口','sram_state [1:0]')
    p.module('IMAGE_BRIDGE','image_bridge_autoload',1980,690,410,620,'主动 UART 资料加载\nCRC 校验 · 完成握手','bridge_state [1:0]')
    p.module('CLOCK','clock_unit',2000,1540,370,250,'时钟直通 / 复位释放','clock_state [1:0]')
    # Instruction interface.
    for y,label,color,reverse in [(300,'imem_addr /32',BLUE,False),(365,'imem_re /1',PINK,False),(430,'imem_rdata /32',YELLOW,True)]:
        p.edge([(1100,y),(680,y)] if reverse else [(680,y),(1100,y)],color,'IMEM' if reverse else 'CPU CORE','CPU CORE' if reverse else 'IMEM')
        p.text(710,y-33,350,28,label,color,22)
    # CPU data interface.
    for y,label,color,reverse in [(730,'dmem_addr /32',BLUE,False),(765,'dmem_wdata /32',YELLOW,False),(800,'dmem_re / we / wstrb /6',PINK,False),(835,'dmem_rdata /32',YELLOW,True)]:
        pts=[(1180,y),(680,y)] if reverse else [(680,y),(1180,y)]
        p.edge(pts,color,'DATASRAM' if reverse else 'CPU CORE','CPU CORE' if reverse else 'DATASRAM')
        p.text(700,y-29,355,26,label,color,20)
    # Direct handshake, routed above memory.
    p.edge([(680,590),(1890,590),(1890,720),(1980,720)],PINK,'CPU CORE','IMAGE_BRIDGE')
    p.text(950,555,700,30,'load_req /1   CPU → IMAGE_BRIDGE',PINK,22)
    p.edge([(2190,690),(2190,180),(470,180),(470,250)],PINK,'IMAGE_BRIDGE','CPU CORE')
    p.text(950,140,900,32,'load_complete /1 + load_error /1',PINK,22)
    # MMIO vertical lanes as in the reference image, with rotated labels.
    for x,label,color,reverse in [(225,'cnn_mmio_addr /32',BLUE,False),(325,'cnn_mmio_wdata /32',YELLOW,False),
                                  (425,'cnn_mmio_re / we /2',PINK,False),(525,'cnn_mmio_rdata /32',YELLOW,True),
                                  (625,'cnn_mmio_ready /1',PINK,True)]:
        p.edge([(x,1280),(x,860)] if reverse else [(x,860),(x,1280)],color,'CNN' if reverse else 'CPU CORE','CPU CORE' if reverse else 'CNN')
        p.text(x-170,1050,310,32,label,color,20,rotate=-90)
    # CNN channels: all 11 clients are flattened into these top wires.
    for y,label,color,reverse in [(1340,'cnn_addr /352 = 11×32',BLUE,False),(1405,'cnn_wdata /352',YELLOW,False),
                                 (1470,'cnn_valid / write / byte /33',PINK,False),(1535,'cnn_cancel /1',PINK,False),
                                 (1600,'cnn_ready / response /22',PINK,True),(1665,'cnn_rdata /352',YELLOW,True)]:
        p.edge([(1180,y),(680,y)] if reverse else [(680,y),(1180,y)],color,'DATASRAM' if reverse else 'CNN','CNN' if reverse else 'DATASRAM')
        p.text(705,y-39,445,30,label,color,20)
    p.text(695,1710,460,50,'通道 i：地址 / 数据 [32i+31:32i]\n有效 / 就绪 / 响应 bit i',GRAY,18)
    # Bridge memory request/return.
    for y,label,color,to_ram in [(815,'io_mem_addr /32',BLUE,True),(880,'io_mem_wdata /32',YELLOW,True),
                                (945,'io_mem_req / we / be /6',PINK,True),(1010,'io_mem_gnt / rvalid / error /3',PINK,False),
                                (1075,'io_mem_rdata /32',YELLOW,False)]:
        p.edge([(1980,y),(1520,y)] if to_ram else [(1520,y),(1980,y)],color,'IMAGE_BRIDGE' if to_ram else 'DATASRAM','DATASRAM' if to_ram else 'IMAGE_BRIDGE')
        p.text(1540,y-36,420,28,label,color,19)
    p.edge([(2570,910),(2390,910)],RED,None,'IMAGE_BRIDGE');p.text(2400,872,170,28,'uart_rx /1',RED,20)
    p.edge([(2390,1110),(2570,1110)],RED,'IMAGE_BRIDGE',None);p.text(2400,1072,170,28,'uart_tx /1',RED,20)
    p.text(1620,1160,320,105,'bridge_ready / busy / error /3\n→ 顶层 LED 与状态监测',COLORS['IMAGE_BRIDGE'],18)
    p.text(700,1120,445,95,'cnn_status_busy / done / error /3\n→ 顶层状态监测\n不经过 CPU 的专用控制端口',COLORS['CNN'],18)
    p.edge([(1520,1720),(1810,1720)],PINK,'DATASRAM',None)
    p.text(1530,1665,440,45,'cnn_mem_fault /1 → 顶层',PINK,19)
    # Clock and package-level pins.
    for y,label in [(1590,'sys_clk /1'),(1740,'rst_n_in /1')]:
        p.edge([(2570,y),(2370,y)],RED,None,'CLOCK');p.text(2390,y-40,180,30,label,RED,20)
    for y,label in [(1585,'clk /1'),(1640,'rst_n /1')]:
        p.edge([(2000,y),(1730,y)],WHITE,'CLOCK',None);p.text(1720,y-37,265,28,label,WHITE,20)
    p.text(1590,1445,390,95,'同名全局网连接到五个功能模块\nCPU / CNN / DATASRAM\nIMEM / IMAGE_BRIDGE',GRAY,18)
    p.text(2220,360,330,125,'顶层组合输出 → 外部\nled_ready /1\nled_busy /1\nled_error /1',RED,20)
    # Observer is annotated, not instantiated as a seventh module.
    p.text(120,1810,2350,62,'各模块方框内的 *_state 是顶层并行观测状态；六个状态可同时为 WORK。监测逻辑不参与数据控制，不增加第七个模块。',WHITE,21)
    p.text(130,1880,2330,38,'0 RESET  ·  1 IDLE  ·  2 WORK  ·  3 FAULT     |     soc_active /6   soc_fault /6   soc_module_state /12',GRAY,22)
    for x,c,label in [(200,BLUE,'地址'),(650,YELLOW,'数据'),(1100,PINK,'控制 / 握手'),(1650,RED,'外部引脚')]:
        p.edge([(x,1940),(x+90,1940)],c);p.text(x+105,1924,240,30,label,c,21)
    p.save_svg('soc_architecture.svg')
    # Page 2: six concurrent status machines, not a serial system sequencer.
    q=Page('02 第一层并行状态机',2200,1500)
    q.text(50,35,2100,65,'第一层状态机：六个大模块并行观察',WHITE,34)
    q.text(50,100,2100,65,'采样模块活动，不改变执行顺序；RESET 优先。下图 FAULT 仅在模块具备故障源时使用。',GRAY,22)
    rules=[
        ('CPU CORE','取指 / 数据访问 / MMIO / load_req','无故障输入，FAULT 为保留状态'),
        ('CNN','cnn_status_busy','queue error / memory fault；软复位清监测状态'),
        ('DATASRAM','CPU、CNN、桥的请求或响应','cnn_mem_fault；系统复位恢复'),
        ('IMEM','imem_re','无独立故障输入，FAULT 为保留状态'),
        ('IMAGE_BRIDGE','bridge_busy','bridge_error；系统复位恢复'),
        ('CLOCK','rst_n 已释放','IDLE=等待释放；无停钟或 PLL 失锁检测')]
    for i,(name,activity,faultnote) in enumerate(rules):
        x=50+(i%3)*720;y=210+(i//3)*620
        q.rect(x,y,660,555,stroke=COLORS[name])
        q.text(x+20,y+15,620,45,name,COLORS[name],28)
        q.rect(x+230,y+85,200,65,'RESET / 0',GRAY,'#252b34',21)
        q.rect(x+50,y+235,210,75,'IDLE / 1',GRAY,'#252b34',21)
        q.rect(x+400,y+235,210,75,'WORK / 2',COLORS[name],'#252b34',21)
        q.edge([(x+285,y+150),(x+285,y+190),(x+155,y+190),(x+155,y+235)],WHITE)
        q.edge([(x+380,y+150),(x+380,y+190),(x+505,y+190),(x+505,y+235)],WHITE)
        q.text(x+25,y+155,270,28,'释放复位 / 无活动',GRAY,17)
        q.text(x+365,y+155,270,28,'释放复位 / 有活动',GRAY,17)
        q.edge([(x+260,y+250),(x+400,y+250)],WHITE);q.text(x+267,y+210,130,28,'有活动',WHITE,17)
        q.edge([(x+400,y+296),(x+260,y+296)],WHITE);q.text(x+267,y+310,130,28,'无活动',WHITE,17)
        if name in ['CNN','DATASRAM','IMAGE_BRIDGE']:
            q.rect(x+230,y+365,200,60,'FAULT / 3',RED,'#252b34',21)
            q.edge([(x+510,y+310),(x+510,y+395),(x+430,y+395)],RED)
            q.edge([(x+155,y+310),(x+155,y+395),(x+230,y+395)],RED)
            q.text(x+445,y+338,150,28,'检测到故障',RED,16)
        else:q.text(x+120,y+369,420,50,'FAULT / 3：保留',GRAY,21)
        q.text(x+20,y+444,620,40,'活动依据：'+activity,WHITE,17)
        q.text(x+20,y+495,620,35,faultnote,GRAY,16)
    q.text(50,1430,2100,40,'所有状态遇硬复位回 RESET。CNN 软复位优先回 IDLE；若存储故障仍未清除，下个采样周期重新进入 FAULT。',GRAY,20)
    q.save_svg('module_state_machines.svg')
    E.indent(mx,space='  ')
    E.ElementTree(mx).write(OUT/'soc_architecture.drawio',encoding='utf-8',xml_declaration=True)
    parsed=E.parse(OUT/'soc_architecture.drawio')
    modules=parsed.findall("./diagram[1]/mxGraphModel/root/mxCell[@module]")
    assert len(modules)==6 and {n.attrib['module'] for n in modules}==set(COLORS)
    (OUT/'diagram_validation.json').write_text(json.dumps({'format':'uncompressed mxfile / mxGraphModel','pages':2,
        'first_level_modules':[n.attrib['module'] for n in modules],'port_widths':{'cnn_addr':352,'cnn_wdata':352,'cnn_rdata':352,'cnn_valid/write/byte':33,'cnn_ready/response':22}},indent=2)+'\n')
    print(OUT/'soc_architecture.drawio')

if __name__=='__main__':main()
