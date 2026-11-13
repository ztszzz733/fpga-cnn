# -*- coding: utf-8 -*-
"""Editable draw.io schematic plus a matching layout preview; no RTL edits."""
from pathlib import Path
import html
import math
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parents[1]/'docs'/'figures'
OUT.mkdir(parents=True,exist_ok=True)
W,H=2230,1340
nodes=[];edges=[];labels=[];lookup={}


def box(id,x,y,w,h,text,parent='1',size=21,dashed=False,group=False):
    n=dict(id=id,x=x,y=y,w=w,h=h,text=text,parent=parent,size=size,dashed=dashed,group=group)
    nodes.append(n);lookup[id]=n
    return id


def label(id,x,y,w,h,text,size=16,white=True):
    labels.append(dict(id=id,x=x,y=y,w=w,h=h,text=text,size=size,white=white))


def edge(id,source,target,points):
    assert all(a[0]==b[0] or a[1]==b[1] for a,b in zip(points,points[1:])),id
    edges.append(dict(id=id,source=source,target=target,points=points))


box('engine',330,45,1595,1235,'计算引擎内部结构  /  systolic_conv_controller',size=24,dashed=True,group=True)
box('queue',40,300,220,340,'队列控制器\ntask_queue_controller',size=21)
box('mmio',40,780,220,130,'MMIO 寄存器组\n软件复位输出',size=21)
box('clock',40,1030,220,110,'系统时钟 / 复位\nclk / rst_n',size=21)
box('ram',1990,130,205,410,'RAM 访问接口\naccelerator_mem_if\n\n（计算引擎外部）',size=20)

box('control',410,370,280,320,'配置锁存与调度控制\n\nia / oa / wa / ba\nfs / ch / lp / op\n\n任务表范围检查\nmb / nb / kb 及索引\n加载 → 计算 → 写回',parent='engine',size=20)
box('address',830,150,370,170,'卷积窗口与地址生成\nconv_window_address\n└ address_generator',parent='engine',size=21)
box('memory',1480,150,330,170,'RAM 请求选择 / 响应转接\n读请求与结果写回共用端口\n组合选择逻辑',parent='engine',size=20)
box('cache',880,470,330,140,'双路整字读缓存\nsystolic_read_cache\n输入 32 位  /  权重·偏置 32 位',parent='engine',size=20)
box('padding',950,680,230,65,'输入字节 / 填充零选择',parent='engine',size=18)

box('tile',810,790,490,380,'分块计算模块  systolic_tile',parent='engine',size=22,group=True)
box('buffers',840,850,430,65,'分块缓冲：A 权重 / B 输入 / Bias 偏置',parent='tile',size=18)
box('feed',840,985,175,135,'馈数与计算时序\n按行列错拍送数\nDW 直接馈数',parent='tile',size=18)
box('array',1070,985,200,135,'8×8 脉动阵列\nsystolic_array8\n64 个 PE\n各自 32 位累加',parent='tile',size=18)

box('output',1460,790,350,380,'输出处理',parent='engine',size=22,group=True)
box('select',1500,850,270,70,'结果选择\nsums → 一个 raw',parent='output',size=19)
box('quant',1500,990,120,90,'量化\nquantizer',parent='output',size=17)
box('store',1660,990,120,90,'输出暂存\noutput_buffer',parent='output',size=16)
label('outnote',1485,1100,300,45,'shift 控制右移；we 控制保存',16,False)

# External ports: one-way bundles with explicit directions.
edge('config','queue','control',[(260,405),(410,405)])
label('config_label',262,315,145,83,'ia / oa / wa / ba\nfs / ch / lp\n7×32 + op(4)',14)
edge('start','queue','control',[(260,495),(410,495)])
label('start_label',263,427,142,65,'start / queue_active\nqueue_base(32)\nqueue_end(64)',14)
edge('status','control','queue',[(410,610),(260,610)])
label('status_label',264,555,143,45,'busy / done / error\n各 1 位',15)
edge('reset','mmio','control',[(260,845),(360,845),(360,665),(410,665)])
label('reset_label',274,742,110,30,'clear (1)',16)
edge('system','clock','engine',[(260,1085),(330,1085)])
label('clk_note',365,1115,385,80,'公共连接：clk、rst_n 接各时序模块\nclear / 新任务检查 → 缓存、tile、输出暂存\n图中不逐根展开公共时钟与清理线',15,False)

edge('addr_cfg','control','address',[(550,370),(550,240),(830,240)])
label('addr_cfg_label',550,160,270,70,'已锁存配置：7×32 + op(4)\nmb / nb / kb：3×32\nrow / col / kidx：3×3',16)
edge('addr_return','address','control',[(830,285),(750,285),(750,445),(690,445)])
label('addr_ret_label',695,290,125,110,'input / weight /\nbias_address\n各32位\nvalid / padding\n规模参数 3×32',14)
edge('write_address','address','memory',[(1200,240),(1480,240)])
label('write_address_label',1210,205,260,28,'output_address (32)',18)
edge('write_control','control','memory',[(665,370),(665,105),(1420,105),(1420,185),(1480,185)])
label('write_ctl_label',870,87,420,32,'写回请求 / 写通路选择（来自控制状态）',16)
edge('memory_status','memory','control',[(1480,285),(1400,285),(1400,350),(780,350),(780,420),(690,420)])
label('mem_status_label',850,330,450,28,'cmd_ready / 写回完成 rsp_valid',16)

edge('read_req','control','cache',[(690,510),(880,510)])
label('read_req_label',696,458,178,48,'read_address(32)\nreq_valid / byte / bank',14)
edge('read_feedback','cache','control',[(880,580),(690,580)])
label('read_feedback_label',698,583,175,48,'req_ready\nresponse_valid',15)
edge('cache_cmd','cache','memory',[(1100,470),(1100,380),(1550,380),(1550,320)])
label('cache_cmd_label',1150,361,340,30,'cmd_addr(32) + cmd_valid',16)
edge('cache_rsp','memory','cache',[(1740,320),(1740,425),(1170,425),(1170,470)])
label('cache_rsp_label',1240,405,445,30,'rsp_data(32) + rsp_valid + cmd_ready',16)

edge('ram_cmd','memory','ram',[(1810,190),(1990,190)])
label('ram_cmd_label',1817,85,165,98,'cmd_addr / cmd_wdata\n各32位\ncmd_valid / cmd_write\ncmd_byte：各1位',14)
edge('ram_rsp','ram','memory',[(1990,270),(1810,270)])
label('ram_rsp_label',1817,205,165,62,'rsp_data(32)\ncmd_ready\nrsp_valid',15)

edge('cache_data','cache','padding',[(1065,610),(1065,680)])
label('cache_data_label',1076,624,270,42,'response_data (32)\n低8位为输入/权重；32位为偏置',14)
edge('padding_ctl','control','padding',[(690,650),(900,650),(900,712),(950,712)])
label('padding_label',706,626,185,28,'padding 选择条件 (1)',15)
edge('load_data','padding','buffers',[(1065,745),(1065,765),(1330,765),(1330,882),(1270,882)])
label('load_data_label',1090,744,225,28,'wr_value(8) / wr_bias(32)',15)
edge('buffer_control','control','tile',[(485,690),(485,885),(810,885)])
label('buffer_ctl_label',500,810,295,64,'a_we / b_we / bias_we：3×1\nwr_row / wr_col / wr_k：3×3',16)
edge('tile_control','control','tile',[(570,690),(570,1000),(810,1000)])
label('tile_ctl_label',580,930,222,60,'start / accumulate / dw：3×1\nrows / cols / depth：3×4\n对应 nr / nc / nk',14)
edge('tile_feedback','tile','control',[(810,1090),(670,1090),(670,690)])
label('tile_feedback_label',687,1030,120,45,'tile_busy\ntile_done',16)
edge('buffers_feed','buffers','feed',[(927,915),(927,985)])
label('buffer_feed_label',840,939,80,26,'取数',16)
edge('feed_array','feed','array',[(1015,1050),(1070,1050)])
label('feed_label',999,940,205,28,'数据 / 控制（见右上注）',14)
label('array_port_note',1360,480,440,240,'阵列馈入信号（馈数逻辑 → 8×8 阵列）\na_edge / b_edge：各64位\na_valid / b_valid：各8位\ndw_inputs：512位；dw_weights：64位\ndw_valid：64位\ninitial_sums：2048位（偏置展开）\nce / load / dw：各1位',16,False)
edge('sums','array','select',[(1270,1050),(1380,1050),(1380,885),(1500,885)])
label('sums_label',1303,951,150,50,'sums\n2048 位',19)
edge('raw','select','quant',[(1560,920),(1560,990)])
label('raw_label',1476,944,125,28,'raw (32)',17)
edge('quantized','quant','store',[(1620,1035),(1660,1035)])
label('quant_label',1625,1003,29,26,'8',17)
edge('output_value','store','memory',[(1780,1035),(1870,1035),(1870,300),(1810,300)])
label('out_value_label',1822,684,95,110,'out_value(8)\n高24位补0\n↓\ncmd_wdata\n(32)',15)
edge('output_control','control','output',[(430,690),(430,1220),(1620,1220),(1620,1170)])
label('output_ctl_label',830,1196,680,36,'row / col：2×3  +  shift=clp[19:12]：8  +  we：1',18)

label('legend',380,1290,1490,48,'实线箭头表示信号方向；多位信号按组标注；交叉无圆点表示不连接。\n虚线框为计算引擎边界；内部按功能展开，不改变 RTL 实例层级。',16,False)


def make_drawio():
    mx=ET.Element('mxfile',host='app.diagrams.net',version='24.7.17',type='device')
    page=ET.SubElement(mx,'diagram',id='compute-engine',name='计算引擎内部结构')
    model=ET.SubElement(page,'mxGraphModel',dx=str(W),dy=str(H),grid='1',gridSize='10',guides='1',
                        tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth=str(W),pageHeight=str(H),math='0',shadow='0')
    root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
    for n in nodes:
        style=f'rounded=0;whiteSpace=wrap;html=1;fillColor={"none" if n["group"] else "#FFFFFF"};strokeColor=#000000;strokeWidth=2;fontColor=#000000;fontFamily=Microsoft YaHei;fontSize={n["size"]};'
        style+='verticalAlign=top;spacingTop=12;' if n['group'] else 'align=center;verticalAlign=middle;'
        if n['dashed']:style+='dashed=1;dashPattern=2 5;strokeWidth=3;'
        cell=ET.SubElement(root,'mxCell',id=n['id'],value=html.escape(n['text']).replace('\n','<br>'),style=style,vertex='1',parent=n['parent'])
        px=lookup[n['parent']]['x'] if n['parent']!='1' else 0;py=lookup[n['parent']]['y'] if n['parent']!='1' else 0
        ET.SubElement(cell,'mxGeometry',x=str(n['x']-px),y=str(n['y']-py),width=str(n['w']),height=str(n['h']),attrib={'as':'geometry'})
    for e in edges:
        src=lookup[e['source']];dst=lookup[e['target']];p=e['points'][0];q=e['points'][-1]
        ex,ey=(p[0]-src['x'])/src['w'],(p[1]-src['y'])/src['h'];ix,iy=(q[0]-dst['x'])/dst['w'],(q[1]-dst['y'])/dst['h']
        assert 0<=ex<=1 and 0<=ey<=1 and 0<=ix<=1 and 0<=iy<=1,e['id']
        style=f'edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=0;html=1;strokeColor=#000000;strokeWidth=2;endArrow=block;endFill=1;exitX={ex};exitY={ey};exitDx=0;exitDy=0;entryX={ix};entryY={iy};entryDx=0;entryDy=0;exitPerimeter=0;entryPerimeter=0;'
        cell=ET.SubElement(root,'mxCell',id=e['id'],style=style,edge='1',parent='1',source=e['source'],target=e['target'])
        geo=ET.SubElement(cell,'mxGeometry',relative='1',attrib={'as':'geometry'})
        if len(e['points'])>2:
            array=ET.SubElement(geo,'Array',attrib={'as':'points'})
            for x,y in e['points'][1:-1]:ET.SubElement(array,'mxPoint',x=str(x),y=str(y))
    for l in labels:
        style=f'text;html=1;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;strokeColor=none;fillColor={"#FFFFFF" if l["white"] else "none"};fontColor=#000000;fontFamily=Microsoft YaHei;fontSize={l["size"]};'
        cell=ET.SubElement(root,'mxCell',id=l['id'],value=html.escape(l['text']).replace('\n','<br>'),style=style,vertex='1',parent='1')
        ET.SubElement(cell,'mxGeometry',x=str(l['x']),y=str(l['y']),width=str(l['w']),height=str(l['h']),attrib={'as':'geometry'})
    ET.indent(mx);ET.ElementTree(mx).write(OUT/'compute_engine.drawio',encoding='utf-8',xml_declaration=True)


def render():
    scale=1.5
    im=Image.new('RGB',(int(W*scale),int(H*scale)),'white');d=ImageDraw.Draw(im)
    fonts={}
    def font(size):
        if size not in fonts:fonts[size]=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',int(size*scale))
        return fonts[size]
    def line(points,width=2):d.line([(int(x*scale),int(y*scale)) for x,y in points],fill='black',width=int(width*scale))
    def texts(n,group=False):
        f=font(n['size']);texts=n['text'].split('\n');spacing=n['size']*1.35
        total=len(texts)*spacing;y=n['y']+12 if group else n['y']+(n['h']-total)/2
        for t in texts:
            length=d.textlength(t,font=f)
            d.text(((n['x']+n['w']/2)*scale-length/2,y*scale),t,font=f,fill='black')
            y+=spacing
    for n in nodes:
        x,y,w,h=[n[k] for k in ('x','y','w','h')]
        if n['dashed']:
            for start,end in [((x,y),(x+w,y)),((x+w,y),(x+w,y+h)),((x+w,y+h),(x,y+h)),((x,y+h),(x,y))]:
                length=abs(end[0]-start[0])+abs(end[1]-start[1])
                for t in range(0,int(length),11):
                    a=t/length;b=min(t+4,length)/length
                    line([(start[0]+a*(end[0]-start[0]),start[1]+a*(end[1]-start[1])),(start[0]+b*(end[0]-start[0]),start[1]+b*(end[1]-start[1]))],2)
        else:
            d.rectangle((x*scale,y*scale,(x+w)*scale,(y+h)*scale),outline='black',width=3,fill=None if n['group'] else 'white')
        texts(n,n['group'])
    for e in edges:
        line(e['points']);p,q=e['points'][-2:];angle=math.atan2(q[1]-p[1],q[0]-p[0]);length=12;width=5
        base=(q[0]-length*math.cos(angle),q[1]-length*math.sin(angle))
        triangle=[q,(base[0]-width*math.sin(angle),base[1]+width*math.cos(angle)),(base[0]+width*math.sin(angle),base[1]-width*math.cos(angle))]
        d.polygon([(x*scale,y*scale) for x,y in triangle],fill='black')
    for l in labels:
        if l['white']:d.rectangle((l['x']*scale,l['y']*scale,(l['x']+l['w'])*scale,(l['y']+l['h'])*scale),fill='white')
        texts(l)
    im.save(OUT/'compute_engine.png')


if __name__=='__main__':
    make_drawio();render()
    tree=ET.parse(OUT/'compute_engine.drawio');cells=tree.findall('.//mxCell')
    assert len({c.attrib['id'] for c in cells})==len(cells)
    print(f'Created editable draw.io: {len(nodes)} blocks, {len(edges)} connectors, {len(labels)} labels.')
    print(OUT/'compute_engine.drawio')
