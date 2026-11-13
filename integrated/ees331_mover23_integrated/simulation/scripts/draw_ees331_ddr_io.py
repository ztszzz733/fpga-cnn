"""Generate editable draw.io, SVG, PNG and a typed IO manifest from one model.

Architecture proposal only. No RTL or existing verification evidence is changed.
"""
from pathlib import Path
import csv, hashlib, html, json, math, re, textwrap
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'deliverables/ees331_ddr_io'
FONT = Path('C:/Windows/Fonts/msyh.ttc')
BOLD = Path('C:/Windows/Fonts/msyhbd.ttc')
BG, INK, MUTED = '#f8fafc', '#182a40', '#536479'
COLORS = {'address':'#2563b8', 'data':'#b96500', 'control':'#16805b'}
LABELS = {'address':'地址线', 'data':'数据线', 'control':'控制/信号线'}
MX = ET.Element('mxfile', host='app.diagrams.net', type='device', version='24.7.17')
PAGES, TEXT_ERRORS = [], []

def sig(name, width, direction='fwd'):
    return {'name':name, 'width':width, 'direction':direction}

def fields(names, direction='fwd'):
    result=[]
    for word in names.split():
        name, width = word.rsplit('/',1)
        result.append(sig(name,int(width),direction))
    return result

def link(id, source, target, title, addr='', wf='', rb='', cf='', cr='', state='拟新增/改造'):
    return {'id':id,'source':source,'target':target,'title':title,'state':state,
            'address':fields(addr),'data':fields(wf)+fields(rb,'rev'),
            'control':fields(cf)+fields(cr,'rev')}

LINKS = [
 link('I','cpu','imem','CPU取指',addr='imem_addr/32',rb='imem_rdata/32',cf='imem_re/1',state='保留接口；64→8 KiB为拟定容量'),
 link('D','cpu','ram','CPU本地数据口',addr='dmem_addr/32',wf='dmem_wdata/32',rb='dmem_rdata/32',cf='dmem_re/1 dmem_we/1 dmem_wstrb/4',state='保留端口；只访问本地RAM，固定一拍'),
 link('M0','cpu','bridge','CPU控制/邮箱口',addr='mmio_addr/32',wf='mmio_wdata/32',rb='mmio_rdata/32',cf='mmio_re/1 mmio_we/1',cr='mmio_ready/1',state='改接image_control_bridge；ready保持零等待'),
 link('M1','bridge','cnn','CNN寄存器封装',addr='cnn_mmio_addr/32',wf='cnn_mmio_wdata/32',rb='cnn_mmio_rdata/32',cf='cnn_mmio_re/1 cnn_mmio_we/1',cr='cnn_mmio_ready/1',state='拟新增新CNN的零等待寄存器封装'),
 link('C','cnn','ram','10路新CNN访存',addr='cnn_addr/320',wf='cnn_wdata/320',rb='cnn_rdata/320',cf='cnn_valid/10 cnn_write/10 cnn_byte/10 cnn_cancel/1',cr='cnn_ready/10 cnn_response/10 cnn_mem_fault/1',state='由新CNN真实10客户端端口引出；存储改接cache'),
 link('F','bridge','ram','cache维护寄存器',addr='cache_csr_addr/32',wf='cache_csr_wdata/32',rb='cache_csr_rdata/32',cf='cache_csr_re/1 cache_csr_we/1',cr='cache_csr_ready/1',state='拟新增；发clean/invalidate/fence，轮询busy/error'),
]

def axi(id, source, target, prefix, data_width, id_width, title):
    p=lambda text:' '.join(prefix+x for x in text.split())
    cf=p(f'AWID/{id_width} ARID/{id_width} WID/{id_width} AWLEN/4 ARLEN/4 AWSIZE/3 ARSIZE/3 AWBURST/2 ARBURST/2 AWLOCK/2 ARLOCK/2 AWCACHE/4 ARCACHE/4 AWPROT/3 ARPROT/3 AWQOS/4 ARQOS/4 WSTRB/{data_width//8} AWVALID/1 WVALID/1 WLAST/1 BREADY/1 ARVALID/1 RREADY/1')
    cr=p(f'BID/{id_width} RID/{id_width} BRESP/2 RRESP/2 AWREADY/1 WREADY/1 BVALID/1 ARREADY/1 RVALID/1 RLAST/1')
    return link(id,source,target,title,addr=p('AWADDR/32 ARADDR/32'),wf=p(f'WDATA/{data_width}'),rb=p(f'RDATA/{data_width}'),cf=cf,cr=cr)

LINKS += [axi('G','ps','bridge','M_AXI_GP0_',32,12,'PS→PL控制：AXI3 GP0'),
          axi('H','ram','ps','S_AXI_HP0_',64,6,'PL→PS存储：AXI3 HP0')]
LINKS += [
 link('B','ps','ddr','PS专用DDR3引脚',addr='DDR_Addr/15 DDR_BankAddr/3',wf='DDR_DM/4',cf='DDR_Clk/1 DDR_Clk_n/1 DDR_CKE/1 DDR_CS_n/1 DDR_RAS_n/1 DDR_CAS_n/1 DDR_WEB/1 DDR_ODT/1 DDR_DRSTB/1',state='板上已有物理布线；PS专用DDR IO，不经过PL'),
 link('U','ps','pc','J3串口逻辑端',wf='UART1_TX/1',rb='UART1_RX/1',state='PS MIO串口经J3板载桥接到PC；不新增PL UART端口'),
 link('K','ps','clock','PS提供PL时钟/复位',cf='FCLK_CLK0_to_sys_clk/1 FCLK_RESET0_N_to_rst_n_in/1',state='拟选用同一FCLK；不与M19外部时钟并驱'),
]
LINKS[-3]['data'] += [sig('DDR_DQ',32,'bidir'),sig('DDR_DQS',4,'bidir'),sig('DDR_DQS_n',4,'bidir')]
OLD = [
 link('I','cpu','imem','CPU取指',addr='imem_addr/32',rb='imem_rdata/32',cf='imem_re/1',state='当前生产RTL'),
 link('D','cpu','ram','CPU数据A口',addr='dmem_addr/32',wf='dmem_wdata/32',rb='dmem_rdata/32',cf='dmem_re/1 dmem_we/1 dmem_wstrb/4',state='当前生产RTL'),
 link('M','cpu','cnn','旧CNN MMIO',addr='cnn_mmio_addr/32',wf='cnn_mmio_wdata/32',rb='cnn_mmio_rdata/32',cf='cnn_mmio_re/1 cnn_mmio_we/1',cr='cnn_mmio_ready/1',state='当前生产RTL'),
 link('C','cnn','ram','旧CNN存储B口',addr='mem_addr/32',wf='mem_wdata/32',rb='mem_rdata/32',cf='mem_read/1 mem_write/1',cr='mem_ready/1',state='当前生产RTL；cnn_mem_fault另接顶层LED，不接旧CNN端口'),
 link('J','bridge','ram','旧图像桥B口',addr='io_mem_addr/32',wf='io_mem_wdata/32',rb='io_mem_rdata/32',cf='io_mem_req/1 io_mem_we/1 io_mem_be/4',cr='io_mem_gnt/1 io_mem_rvalid/1 io_mem_error/1',state='当前生产RTL'),
]
NAMES={'cpu':'① CPU_CORE','cnn':'② CNN','ram':'③ DATASRAM','imem':'④ IMEM / IEM','bridge':'⑤ IMAGE_BRIDGE','clock':'⑥ CLOCK_UNIT','ps':'新增 PS7 / ARM + DDR控制器','ddr':'板外 DDR3 / 1GB','pc':'电脑 / J3'}

def spelling(s):
    n,w=s['name'],s['width']
    a={'fwd':'→','rev':'←','bidir':'<->'}[s['direction']]
    return f'{a} {n}' + (f'[{w-1}:0]' if w>1 else '') + f' / {w} bit'

def totals(items):
    return '  '.join(f'{arrow}{sum(s["width"] for s in items if s["direction"]==d)} bit' for d,arrow in [('fwd','→'),('rev','←'),('bidir','<->')] if any(s['direction']==d for s in items))

class Page:
    def __init__(self, slug, title, w, h, subtitle):
        self.slug,self.w,self.h=slug,w,h;self.seq=0;self.boxes={};self.rows=[]
        d=ET.SubElement(MX,'diagram',id=slug,name=title)
        g=ET.SubElement(d,'mxGraphModel',dx=str(w),dy=str(h),grid='1',gridSize='10',guides='1',tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth=str(w),pageHeight=str(h),background=BG)
        self.root=ET.SubElement(g,'root');ET.SubElement(self.root,'mxCell',id='0');ET.SubElement(self.root,'mxCell',id='1',parent='0')
        self.image=Image.new('RGB',(w,h),BG);self.draw=ImageDraw.Draw(self.image)
        self.svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',f'<rect width="{w}" height="{h}" fill="{BG}"/>']
        self.text(50,26,w-100,65,title,42,bold=True)
        self.text(50,99,w-100,55,subtitle,23,color=MUTED)
        for i,(k,c) in enumerate(COLORS.items()):
            self.rect(55+i*420,167,30,18,'',fill=c,stroke=c)
            self.text(95+i*420,153,300,44,LABELS[k],23,color=c)
        PAGES.append(self)
    def id(self):self.seq+=1;return self.slug+'_'+str(self.seq)
    def rect(self,x,y,w,h,label='',fill='#ffffff',stroke='#7890a9',size=24,key=None,dashed=False):
        ident=self.id();style=f'rounded=0;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};strokeWidth=2;fontColor={INK};fontFamily=Microsoft YaHei;fontSize={size};'
        if dashed:style+='dashed=1;dashPattern=8 5;'
        c=ET.SubElement(self.root,'mxCell',id=ident,value=label,style=style,vertex='1',parent='1')
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
        self.draw.rectangle((x,y,x+w,y+h),fill=fill,outline=stroke,width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        if key:self.boxes[key]=(ident,x,y,w,h)
        if label:self.paint_text(x,y,w,h,label,size,INK)
        return ident
    def paint_text(self,x,y,w,h,label,size,color,bold=False,rotate=0,align='center'):
        font=ImageFont.truetype(str(BOLD if bold else FONT),size)
        lines=label.split('\n');maxwidth=max((self.draw.textlength(t,font=font) for t in lines),default=0)
        tw,th=(h,w) if rotate else (w,h)
        if maxwidth>tw-8 or len(lines)*size*1.4>th+4:TEXT_ERRORS.append({'page':self.slug,'label':label,'width':maxwidth,'limit':tw,'height':len(lines)*size*1.4,'height_limit':th})
        tile=Image.new('RGBA',(int(tw),int(th)),(0,0,0,0));d=ImageDraw.Draw(tile)
        yy=(th-len(lines)*size*1.4)/2
        for t in lines:
            xx=tw/2 if align=='center' else 5
            d.text((xx,yy),t,font=font,fill=color,anchor='mt' if align=='center' else 'lt');yy+=size*1.4
        if rotate:tile=tile.rotate(-rotate,expand=True)
        self.image.paste(tile,(int(x),int(y)),tile)
        cx=x+w/2;cy=y+h/2;anchor='middle' if align=='center' else 'start';xx=cx if align=='center' else x+5
        trans=f' transform="rotate({rotate} {cx} {cy})"' if rotate else ''
        self.svg.append(f'<text x="{xx}" y="{cy-(len(lines)-1)*size*.7}" text-anchor="{anchor}" dominant-baseline="central" font-family="Microsoft YaHei,sans-serif" font-size="{size}" fill="{color}"{trans}>')
        for i,t in enumerate(lines):self.svg.append(f'<tspan x="{xx}" dy="{0 if i==0 else size*1.4}">{html.escape(t)}</tspan>')
        self.svg.append('</text>')
    def text(self,x,y,w,h,label,size=24,color=INK,bold=False,rotate=0,align='center',back=None):
        style=f'text;whiteSpace=wrap;html=0;align={align};verticalAlign=middle;strokeColor=none;fillColor={back or "none"};fontColor={color};fontFamily=Microsoft YaHei;fontSize={size};rotation={rotate};'
        if bold:style+='fontStyle=1;'
        c=ET.SubElement(self.root,'mxCell',id=self.id(),value=label,style=style,vertex='1',parent='1')
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
        if back:
            self.draw.rectangle((x,y,x+w,y+h),fill=back)
            self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{back}"/>')
        self.paint_text(x,y,w,h,label,size,color,bold,rotate,align)
    def edge(self,points,color,source=None,target=None,reverse=False,bidir=False,dashed=False):
        if reverse:points=list(reversed(points));source,target=target,source
        a={'id':self.id(),'edge':'1','parent':'1','value':''}
        a['style']=f'edgeStyle=none;rounded=0;html=0;strokeColor={color};strokeWidth=3;endArrow=block;endFill=1;'
        if bidir:a['style']+='startArrow=block;startFill=1;'
        if dashed:a['style']+='dashed=1;dashPattern=8 5;'
        for side,key,pt in [('source',source,points[0]),('target',target,points[-1])]:
            if key in self.boxes:
                ident,x,y,w,h=self.boxes[key];a[side]=ident;pre='exit' if side=='source' else 'entry'
                a['style']+=f'{pre}X={(pt[0]-x)/w};{pre}Y={(pt[1]-y)/h};{pre}Perimeter=0;'
        c=ET.SubElement(self.root,'mxCell',**a);g=ET.SubElement(c,'mxGeometry',relative='1',**{'as':'geometry'})
        for name,pt in [('sourcePoint',points[0]),('targetPoint',points[-1])]:ET.SubElement(g,'mxPoint',x=str(pt[0]),y=str(pt[1]),**{'as':name})
        arr=ET.SubElement(g,'Array',**{'as':'points'})
        for x,y in points[1:-1]:ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
        self.draw.line(points,fill=color,width=3)
        self.svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="3"/>')
        ends=[(points[-2],points[-1])]+([(points[1],points[0])] if bidir else [])
        for prev,end in ends:
            dx,dy=end[0]-prev[0],end[1]-prev[1];l=math.hypot(dx,dy);ux,uy=dx/l,dy/l
            triangle=[end,(end[0]-16*ux+7*uy,end[1]-16*uy-7*ux),(end[0]-16*ux-7*uy,end[1]-16*uy+7*ux)]
            self.draw.polygon(triangle,fill=color)
            self.svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in triangle)}" fill="{color}"/>')
    def module(self,key,x,y,w,h,impl,detail,state='保留',fill='#ffffff'):
        self.rect(x,y,w,h,fill=fill,stroke='#45637e',key=key)
        self.text(x+12,y+16,w-24,48,NAMES[key],30,bold=True)
        self.text(x+15,y+76,w-30,50,impl,23,color=MUTED)
        self.text(x+20,y+140,w-40,h-210,detail,25)
        self.text(x+15,y+h-65,w-30,48,state+'  |  clk /1，rst_n /1' if key not in ['ps','ddr','pc'] else state,20,color=MUTED)
    def save(self):
        self.image.save(OUT/(self.slug+'.png'))
        (OUT/(self.slug+'.svg')).write_text('\n'.join(self.svg+['</svg>']),encoding='utf-8')
    def detail_row(self,y,h,l,group,items=None):
        items=l[group] if items is None else items;c=COLORS[group]
        self.rect(50,y,self.w-100,h,fill='#ffffff',stroke='#d5dfe8')
        self.rect(75,y+25,390,h-50,NAMES[l['source']],fill='#edf3f9',size=25)
        self.rect(self.w-465,y+25,390,h-50,NAMES[l['target']],fill='#edf3f9',size=25)
        self.text(500,y+8,self.w-1000,42,f"{l['id']} · {l['title']}   {totals(items)}",25,color=c,bold=True)
        # Actual connection line is separately editable; labels sit above it.
        directions={s['direction'] for s in items}
        both='bidir' in directions or {'fwd','rev'} <= directions
        self.edge([(465,y+h-27),(self.w-465,y+h-27)],c,bidir=both,reverse=directions=={'rev'})
        lines=[spelling(s) for s in items]
        self.text(500,y+54,self.w-1000,h-100,'\n'.join(lines) if lines else '本接口没有独立'+LABELS[group],23,color=c)

def compact(l,group):
    items=l[group]
    if not items:return LABELS[group]+'：无独立线'
    if len(items)>6:
        names=' / '.join(s['name'].split('_')[-1]+f'[{s["width"]}]' for s in items[:3])
        return LABELS[group]+'  '+totals(items)+'\n'+names+' …（详信号页）'
    return '\n'.join(spelling(s) for s in items)

def overview(old=False):
    p=Page('01_before' if old else '02_after','01 改前：当前六模块真实接线' if old else '02 改后：原六模块平级 + PS7 + 板外DDR3',4000,3200,
           '依据 face_soc_top.sv；当前仍接旧CNN，不混用新的10客户端接口。' if old else '待实施方案：保留六个功能位置；①CPU与④IMEM仍平级；PS为同一芯片硬核，DDR在板外。')
    p.rect(40,215,2600,2900,fill='#f0f5fa',stroke='#a8bed2',dashed=True)
    p.text(70,220,600,40,'PL / FPGA可编程逻辑',27,color=MUTED)
    p.module('cpu',160,650,650,850,'cpu_core','原Control + Datapath\n取指 / 本地数据 / MMIO\n\n数据口不增加等待\n保持固定一拍读')
    p.module('imem',1800,265,650,270,'imem_rom','64 KiB指令ROM' if old else '建议8 KiB指令ROM','接口保留；拟缩容量' if not old else '当前RTL')
    p.module('ram',1800,650,650,1150,'datasram' if old else 'datasram_ddr_subsystem（拟）',
             '256 KiB共享SRAM\nCPU A口固定一拍\nCNN / image_bridge共用B口\n仲裁在内部' if old else 'A：CPU本地RAM 16 KiB\n固定一拍，不经过cache\n\nB：CNN共享cache\n首版128 KiB / 目标256 KiB\n4 bank + tag / miss / 写回\n\n内部DDR突发主接口\n接PS的HP0；不放MIG',state='保留存储位置，内部大改' if not old else '当前RTL',fill='#fff8e7')
    p.module('bridge',160,1850,650,800,'image_bridge' if old else 'image_control_bridge（拟）',
             'PL UART接收 / CRC32\nIMIO分包\n直接读写共享SRAM' if old else '原PL串口收图移至PS\n本位置变为：\nPS / CPU双侧邮箱\nGP0 AXI3→AXI Lite转换\nCPU零等待MMIO译码/转接\ncache维护寄存器入口',state='职责调整；不是已存在RTL' if not old else '当前RTL',fill='#f2edff')
    p.module('cnn',1800,2250,650,400,'mobilefacenet_accelerator_top' if old else '新CNN子系统 + MMIO封装（拟）',
             '旧CNN，单路mem_*接口' if old else '2 K3 + 4 K1 + DW7/Post/Add/Pad\n紧凑固定调度，4图重叠计算','旧CNN接口' if old else '10客户端接口来自当前新CNN')
    p.module('clock',160,2790,650,270,'clock_unit' if old else 'clock_unit / reset同步（改）','时钟直通 / 复位同步' if old else 'PS FCLK作为统一PL时钟')
    chosen=OLD if old else LINKS
    get=lambda id:next(l for l in chosen if l['id']==id)
    # Instruction path, with three separate groups.
    l=get('I')
    for i,g in enumerate(COLORS):
        pts=[(500+i*90,650),(500+i*90,570+i*23),(1950+i*90,570+i*23),(1950+i*90,535)]
        p.edge(pts,COLORS[g],'cpu','imem',reverse=g=='data')
        p.text(850,490+i*42,850,42,compact(l,g),20,color=COLORS[g],back=BG)
    # CPU local data port.
    for i,g in enumerate(COLORS):
        y=800+i*290;p.edge([(810,y),(1800,y)],COLORS[g],'cpu','ram',bidir=g=='data')
        p.text(850,y-100,900,95,'D · '+compact(get('D'),g),23,color=COLORS[g],back=BG)
    if old:
        p.rect(2780,760,1100,1360,fill='#ffffff',stroke='#adbdca')
        p.text(2810,785,1040,1270,'当前板级IO（说明框，不是新增模块）\n\n输入：sys_clk /1 → clock_unit\n输入：rst_n_in /1 → clock_unit\n输入：uart_rx /1 → image_bridge\n输出：uart_tx /1 ← image_bridge\n\n输出：led_ready /1\n= bridge_ready & !cnn_mem_fault\n输出：led_busy /1 = bridge_busy\n输出：led_error /1\n= bridge_error | cnn_mem_fault\n\ncnn_mem_fault /1：DATASRAM → 顶层LED逻辑\n旧CNN没有这个fault输入端口。\n\nclk /1、rst_n /1为六模块同名公共网。\n新版DDR/J3的引脚分组见第07页。',27,color=MUTED)
        l=get('M')
        for i,g in enumerate(COLORS):
            x=930+i*220
            p.edge([(810,1450-i*55),(x,1450-i*55),(x,2340+i*130),(1800,2340+i*130)],COLORS[g],'cpu','cnn',bidir=g!='address')
            p.text(x-38,1520,80,600,compact(l,g),19,color=COLORS[g],rotate=-90,back=BG)
        l=get('J')
        for i,g in enumerate(COLORS):
            yy=1870+i*100;p.edge([(810,yy+80),(1450+i*70,yy+80),(1450+i*70,1500+i*110),(1800,1500+i*110)],COLORS[g],'bridge','ram',bidir=g!='address')
            caption='J · '+compact(l,g) if g!='control' else 'J · req /1、we /1、be /4 →\ngnt /1、rvalid /1、error /1 ←'
            p.text(830,yy+10,620,80,caption,19,color=COLORS[g],back=BG)
    else:
        l=get('M0')
        for i,g in enumerate(COLORS):
            x=260+i*225;p.edge([(x,1500),(x,1850)],COLORS[g],'cpu','bridge',bidir=g!='address')
            p.text(x-45,1515,90,320,'M0 · '+compact(l,g),18,color=COLORS[g],rotate=-90,back=BG)
        for i,g in enumerate(COLORS):
            y=2310+i*140;p.edge([(810,y),(1800,y)],COLORS[g],'bridge','cnn',bidir=g!='address')
            p.text(850,y-115,900,110,'M1 · '+compact(get('M1'),g),22,color=COLORS[g],back=BG)
        # Maintenance path from control bridge to cache, routed through gap.
        for i,g in enumerate(COLORS):
            x=1150+i*130;y=1510+i*110
            p.edge([(810,1900+i*95),(x,1900+i*95),(x,y),(1800,y)],COLORS[g],'bridge','ram',bidir=g!='address')
            p.text(1280,y-55,470,55,'F · '+LABELS[g]+' '+totals(get('F')[g]),19,color=COLORS[g],back=BG)
        p.module('ps',3100,650,650,1800,'ZYNQ7 Processing System','双核ARM + UART1\nPS收图程序 / CRC\n模型加载 / 数据可见性\n\nM_AXI_GP0：控制PL邮箱\nS_AXI_HP0：服务PL存储访问\n\n硬核DDR控制器 + PHY\nDDR初始化由PS执行\n\nPS内上传数据到DDR\n不经过PL UART/cache','新增使用PS硬核',fill='#e7f4f0')
        p.module('ddr',3100,240,650,280,'PS专用DDR物理引脚','完整模型 + 四图工作区','板载已有1GB；非PL BRAM',fill='#fff1e8')
        p.module('pc',3100,2780,650,270,'一根USB数据线 / J3','板载桥接 → PS UART1','USB供电能力按板卡验证')
        for i,g in enumerate(COLORS):
            y=815+i*340;p.edge([(2450,y),(3100,y)],COLORS[g],'ram','ps',bidir=g!='address')
            p.text(2485,y-110,575,105,'H · '+compact(get('H'),g),20,color=COLORS[g],back=BG)
        for i,g in enumerate(COLORS):
            yy=1940+i*100
            p.edge([(3100,yy),(810,yy)],COLORS[g],'ps','bridge',bidir=g!='address')
            p.text(2480,yy-63,590,60,'G · '+LABELS[g]+' '+totals(get('G')[g]),20,color=COLORS[g],back=BG)
        for i,g in enumerate(COLORS):
            x=3210+i*220;p.edge([(x,650),(x,520)],COLORS[g],'ps','ddr',bidir=g=='data')
            text={'address':'B · DDR_Addr /15\nDDR_BankAddr /3','data':'B · DQ /32 <->\nDQS/DQS_n 各4 <->\nDDR_DM /4 →','control':'B · DDR命令/时钟\n9根信号，各1 bit →\n逐根名称见第07页'}[g]
            p.text(x-100,530,205,103,text,16,color=COLORS[g],back=BG)
        p.edge([(3360,2450),(3360,2780)],COLORS['data'],'ps','pc',bidir=True)
        p.text(3390,2480,540,230,'U · PS UART1\nTX：MIO48 /1 → J3桥\nRX：MIO49 /1 ← J3桥\nJ3 USB端口不直接连PL',20,color=COLORS['data'],back=BG)
        p.edge([(3100,2350),(2860,2350),(2860,2740),(620,2740),(620,2790)],COLORS['control'],'ps','clock')
        p.text(1040,2690,1700,65,'K · FCLK_CLK0 /1 → sys_clk；FCLK_RESET0_N /1 → rst_n_in',22,color=COLORS['control'],back=BG)
    # Memory/CNN grouped ports.
    l=get('C')
    for i,g in enumerate(COLORS):
        x=1900+i*225;p.edge([(x,2250),(x,1800)],COLORS[g],'cnn','ram',bidir=g!='address')
        caption='C · '+(compact(l,g) if g!='control' else ('mem_read /1, mem_write /1 →\nmem_ready /1 ←' if old else 'valid/write/byte 各10 →\nready/response 各10 ←\ncancel /1 →，fault /1 ←'))
        p.text(x-42,1820,83,410,caption,17,color=COLORS[g],rotate=-90,back=BG)
    p.text(850,2860,2100,180,'全局同名网：clk /1、rst_n /1 → 各PL模块（各模块底部已标注）\n交叉无圆点 = 不连接；双向箭头表示两组相反方向的独立线，并非总线三态共驱。\n改后容量/新模块为设计方案，尚未实施；详图逐根列出接口，不省略控制位宽。',24,color=MUTED)
    p.save()

def grouped_page(group, slug, title, local_only=False):
    ls=[l for l in LINKS if l['id'] not in ['K','U'] and (not local_only or l['id'] not in ['G','H','B'])]
    heights=[max(150,100+len(l[group])*34) for l in ls]
    p=Page(slug,title,3300,270+sum(heights)+25*len(ls),
           '每行左右两框与总图同层级；→ 左框发往右框，← 右框返回左框，<-> 物理双向；/N 为该信号位宽。')
    y=225
    for l,h in zip(ls,heights):p.detail_row(y,h,l,group);y+=h+25
    p.save()

def axi_controls():
    p=Page('06_axi_control','06 AXI3控制信号：GP0与HP0逐根位宽',3700,2450,'地址/数据另见第03、04页；AXI ID、byte strobe、响应码归控制组；GP0转换在image_control_bridge内。')
    for col,id in enumerate(['G','H']):
        l=next(l for l in LINKS if l['id']==id);x=55+col*1820
        p.rect(x,230,1760,2050,fill='#ffffff',stroke='#b4c8bc')
        p.text(x+20,245,1720,110,l['title']+'\n'+NAMES[l['source']]+' → '+NAMES[l['target']],26,bold=True)
        for side in ['fwd','rev']:
            ss=[s for s in l['control'] if s['direction']==side];yy=390 if side=='fwd' else 1450
            p.text(x+30,yy,1700,45,('请求/属性 →' if side=='fwd' else '响应 ←')+'  '+totals(ss),25,color=COLORS['control'],bold=True)
            lines=[spelling(s) for s in ss]
            # Two vertical columns for the numerous AXI request attributes.
            half=(len(lines)+1)//2 if side=='fwd' else len(lines)
            if side=='fwd':
                p.text(x+45,yy+65,820,920,'\n'.join(lines[:half]),22,color=COLORS['control'],align='left')
                p.text(x+900,yy+65,820,920,'\n'.join(lines[half:]),22,color=COLORS['control'],align='left')
            else:p.text(x+45,yy+60,1670,620,'\n'.join(lines),22,color=COLORS['control'],align='left')
    p.text(70,2300,3550,115,'HP0设置64bit：WDATA/RDATA /64，WSTRB /8；GP0数据 /32，WSTRB /4。\nHP0可选FIFO计数/issue-cap端口非数据事务握手，见第07页；AXI3突发LEN /4，不能直接接AXI4的LEN /8。',24,color=MUTED)
    p.save()

def board_page():
    p=Page('07_board_clock','07 板级DDR / J3 / 时钟复位 / 新旧接口变化',3500,2600,'DDR接PS专用引脚；既有板上布线保持。图中名称来自Vivado PS7 IP；方向按电路功能，HDL部分DDR端口为inout。')
    b=next(l for l in LINKS if l['id']=='B')
    y=230
    for g,h in [('address',230),('data',330),('control',500)]:p.detail_row(y,h,b,g);y+=h+25
    p.rect(50,y,3400,480,fill='#ffffff',stroke='#a9becf')
    p.text(80,y+15,3340,450,'时钟与复位（所有信号 /1）\nPS FCLK_CLK0 → clock_unit.sys_clk；PS FCLK_RESET0_N → clock_unit.rst_n_in\nclock_unit.clk → CPU / CNN / DATASRAM / IMEM / IMAGE_CONTROL_BRIDGE\n同一clk → PS S_AXI_HP0_ACLK、M_AXI_GP0_ACLK，以及桥内转换器/AXI逻辑\nclock_unit.rst_n → 上述PL模块与AXI复位逻辑；PS DDR初始化完成通过邮箱状态通知CPU。\n初版统一FCLK；外部M19 100MHz不再直接驱动同一根clk。PS_CLK F7仍是板上33.333333MHz输入。',26)
    y+=505
    p.rect(50,y,3400,390,fill='#ffffff',stroke='#a9becf')
    p.text(85,y+10,3330,370,'PC与专用PS引脚\nPC USB协议 <-> J3板载桥 <-> PS UART1_TX（MIO48）/1、UART1_RX（MIO49）/1；USB引脚不接PL。\nPS7 FIXED_IO_MIO[53:0] /54、PS_CLK /1、PS_PORB /1、PS_SRSTB /1由PS专用固定IO封装导出；不是新增PL总线。\nDDR_VRN /1、DDR_VRP /1接板上参考电阻，不接DDR芯片数据/地址口。DDR_DM[3:0]是写字节屏蔽，归数据组。\nHP0辅助口：RCOUNT /8、WCOUNT /8、RACOUNT /3、WACOUNT /6（PS→PL，监控）；\nRDISSUECAP1_EN /1、WRISSUECAP1_EN /1（PL→PS，默认按设计常量连接）。',24)
    y+=415
    p.text(65,y,3370,230,'改线要点：旧PL image_bridge的UART/CRC功能移到PS程序；旧io_mem_*→datasram收图路径在J3方案中删除。\nimage_bridge这个平级位置改为PS/CPU邮箱与寄存器转接；CPU MMIO由直连CNN改为经该桥译码，零等待合同保留。\nCNN从旧单路mem_*换成新10客户端cnn_*；DATASRAM中CPU本地RAM与CNN cache分开，新增HP0访存。\nDDR与PS为板上现有硬件，本方案新增其工程配置/初始化/连接；未新增一组PL DDR引脚或MIG。',25,color=MUTED)
    p.save()

def validation():
    for l in LINKS+OLD:
        for g in COLORS:
            for s in l[g]:assert s['width']>0 and s['direction'] in ['fwd','rev','bidir']
    refs=[]
    for d in MX:
        root=d.find('mxGraphModel/root');ids={c.get('id') for c in root}
        for c in root:
            for k in ['source','target']:
                if c.get(k):assert c.get(k) in ids
        refs.append({'page':d.get('name'),'cells':len(root),'edges':sum(c.get('edge')=='1' for c in root)})
    assert not TEXT_ERRORS,json.dumps(TEXT_ERRORS,ensure_ascii=False,indent=2)
    return refs

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    overview(True);overview(False)
    grouped_page('address','03_address','03 改后逐接口接线：地址线（蓝色）')
    grouped_page('data','04_data','04 改后逐接口接线：数据线（橙色）')
    grouped_page('control','05_local_control','05 改后逐接口接线：本地控制/信号线（绿色）',True)
    axi_controls();board_page()
    # Save the editable document even if visual text validation needs repair.
    ET.indent(MX);ET.ElementTree(MX).write(OUT/'ees331_soc_ddr_io.drawio',encoding='utf-8',xml_declaration=True)
    (OUT/'io_manifest.json').write_text(json.dumps({'status':'ARCHITECTURE_PROPOSAL_NOT_IMPLEMENTED','local_cnn_clients':10,'groups':COLORS,'before':OLD,'after':LINKS},ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'io_connections.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['interface','source','target','group','signal','width_bits','direction','status'])
        for l in LINKS:
            for g in COLORS:
                for s in l[g]:writer.writerow([l['id'],l['source'],l['target'],g,s['name'],s['width'],s['direction'],l['state']])
    result={'pages':validation(),'checks':['XML references valid','positive widths and defined directions','no text overflow at generated geometry'],'drawio_sha256':hashlib.sha256((OUT/'ees331_soc_ddr_io.drawio').read_bytes()).hexdigest()}
    (OUT/'diagram_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'pages':len(PAGES),'status':'PASS'},ensure_ascii=False))

if __name__=='__main__':main()
