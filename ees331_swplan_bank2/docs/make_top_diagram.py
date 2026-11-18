"""Generate an editable diagrams.net diagram and previews from one geometry model."""
from pathlib import Path
import xml.etree.ElementTree as ET
import json, hashlib, math, html
from PIL import Image, ImageDraw, ImageFont

BASE=Path(__file__).resolve().parent.parent
OUT=BASE/'docs/diagrams'
OUT.mkdir(parents=True,exist_ok=True)
BG='#101216'; PANEL='#14181e'; FG='#e5e7eb'; MUTED='#aab4c0'
BLUE='#58a6ff'; RED='#ff777d'; RAM='#efdf69'; PURPLE='#d987ed'; GREEN='#5bd6ab'; CLOCK='#f3a54d'; IMEM='#8aa8ff'
FONT='Microsoft YaHei'
pages=[]

class Page:
 def __init__(self,name,w,h):
  self.name,self.w,self.h=name,w,h;self.items=[];self.nodes={};self.edges=[];self.seq=0;pages.append(self)
 def ident(self):self.seq+=1;return f'p{len(pages)}_{self.seq}'
 def box(self,id,x,y,w,h,title='',subtitle='',body='',color=BLUE,size=22,footer=None,fill=PANEL):
  item=dict(kind='box',id=id,x=x,y=y,w=w,h=h,color=color,fill=fill)
  self.items.append(item);self.nodes[id]=item
  if title:self.text(x+12,y+15,w-24,42,title,29,color)
  if subtitle:self.text(x+12,y+61,w-24,51,subtitle,18,MUTED)
  if body:self.text(x+20,y+112,w-40,h-145-(30 if footer else 0),body,size)
  if footer:self.text(x+10,y+h-42,w-20,30,footer,18,MUTED)
  return id
 def text(self,x,y,w,h,value,size=21,color=FG,align='center',fill=None):
  self.items.append(dict(kind='text',id=self.ident(),x=x,y=y,w=w,h=h,value=value,size=size,color=color,align=align,fill=fill))
 def edge(self,id,source,target,points,color=BLUE,label=None,lpos=None,size=21,dashed=False):
  item=dict(kind='edge',id=id,source=source,target=target,points=points,color=color,dashed=dashed)
  self.edges.append(item);self.items.append(item)
  if label:
   self.text(*lpos,label,size,color,fill=BG)
   self.items[-1]['edge_label_for']=id
 def title(self,title,subtitle):
  self.text(40,25,self.w-80,60,title,36)
  self.text(50,95,self.w-100,42,subtitle,21,MUTED)
 def note(self,x,y,w,h,value,color=MUTED,size=21):self.text(x,y,w,h,value,size,color,'left',BG)

p=Page('01 顶层六模块与PS连线',3000,2140)
p.title('EES331 · 两 bank / 软件规划访存 · 顶层连线图',
        'face_soc_ees331_mover_top  |  K3×2 + PW8×4 + Post×2 + Add + Pad  |  10 路 CNN 访存  |  392 KiB')
p.box('pl',40,170,2290,1740,fill=BG,color='#526172')
p.note(70,1860,2210,35,'PL 区域：六个平级功能实例；u_ps 封装图中 PS7。构建参数 K1_UNITS=4，图示不采用顶层默认的 6。',size=20)
p.box('cpu',150,360,470,350,'CPU CORE','u_cpu_core : cpu_core','RV32I 控制固件\n取指 / 本地数据访问\n执行 ARM 邮箱请求\n唯一的 CNN / Cache CSR 写入方',BLUE,22,'G：clk / rst_n')
p.box('imem',1050,300,380,240,'IMEM · 8 KiB','u_imem : imem_rom','RISC-V 指令 ROM\nprogram.mem 初始化',IMEM,21,'G：clk / rst_n')
p.box('data',1050,850,460,630,'DATASRAM + MOVER','u_datasram\ndatasram_mover_subsystem',
      'CPU Data SRAM：16 KiB\nCPU 固定一拍读写\n\nCNN 共享缓存：392 KiB\nBank 0：196 KiB\nBank 1：196 KiB\n392 个 1 KiB 页\n\n分页 / 两 bank 仲裁 / DMA\n内部 data_mover 为 HP0 主设备',RAM,22,'G：clk / rst_n')
p.box('cnn',150,1100,470,470,'CNN','u_cnn : cnn_ees331',
      '任务模板 / 帧上下文 / 调度\nK3 × 2：软件规划读段\nPW8 × 4\nPost × 2 / Add / Pad\n\n10 个逻辑访存客户端\nDW7 沿用关闭配置',RED,22,'G：clk / rst_n')
p.box('bridge',1830,650,430,460,'IMAGE CONTROL BRIDGE','u_image_bridge\nimage_control_bridge',
      'GP0：AXI3 邮箱从设备\nARM 发布请求 / 读取 ACK\n\nM0：CPU 邮箱 / 索引窗口\nM1：CPU → CNN CSR\nF：CPU → Cache CSR\n\n不直接收发 J3 串口',PURPLE,21,'G：clk / rst_n')
p.box('clock',1830,1350,430,250,'CLOCK / RESET','u_clock_unit : clock_unit','FCLK0 时钟通路\n复位同步释放',CLOCK,22)
p.box('ps',2450,500,480,1020,'PS7 · Cortex-A9','u_ps : ees331_ps_wrapper',
      'ARM FreeRTOS\n软件计划校验 / 调度 / 文件 I/O\n\nUART1 双向连接 J3 USB-UART\nSD0 双向连接 microSD\nDDR 控制器连接板载 DDR3\n\nM_AXI_GP0：32-bit 控制\nS_AXI_HP0：64-bit 数据\n\nFCLK_CLK0 / FCLK_RESET0_N\nGP0_ACLK / HP0_ACLK',GREEN,23)
p.box('j3',2410,220,250,145,'J3 USB-UART',body='',color=GREEN)
p.text(2420,279,230,65,'板载 USB-UART 桥\nUART1 · MIO48/49',19)
p.box('sd',2700,220,250,145,'microSD',body='',color=GREEN)
p.text(2710,279,230,65,'SD0 · MIO40…45\n卡检测 · MIO0',19)
p.box('ddr',2450,1740,480,170,'板载 DDR3','PS DDR 控制器 / DQ[31:0]',color=GREEN)
p.text(2470,1850,440,40,'模型 / 图片 / 中间结果 / ARM 程序',20)
p.box('g',1830,1770,430,90,color=CLOCK,fill=BG)
p.text(1840,1782,410,66,'G：clk / rst_n → 全部 PL 功能模块\n同一 clk → GP0_ACLK / HP0_ACLK',19,CLOCK)

p.edge('I_req','cpu','imem',[(620,410),(830,410),(830,355),(1050,355)],IMEM,'I 请求：imem_addr[31:0] + imem_re', (650,315,375,65),19)
p.edge('I_ret','imem','cpu',[(1050,460),(880,460),(880,535),(620,535)],IMEM,'I 返回：imem_rdata[31:0]',(650,480,375,38),19)
p.edge('D_req','cpu','data',[(620,625),(760,625),(760,945),(1050,945)],RAM,'D 请求 / 70 bit\naddr32 / wdata32\nre / we / wstrb4',(835,840,205,90),17)
p.edge('D_ret','data','cpu',[(1050,1020),(820,1020),(820,685),(620,685)],RAM,'D 返回 / 32 bit\ndmem_rdata',(835,950,200,60),19)
p.edge('M0_req','cpu','bridge',[(410,360),(410,220),(1980,220),(1980,650)],PURPLE,'M0 请求 / 66 bit：mmio_addr、wdata、re/we',(730,180,970,34),21)
p.edge('M0_ret','bridge','cpu',[(2140,650),(2140,280),(550,280),(550,360)],PURPLE,'M0 返回 / 33 bit：mmio_rdata、mmio_ready',(730,243,970,32),21)
p.edge('M1_req','bridge','cnn',[(1830,900),(1680,900),(1680,740),(100,740),(100,1210),(150,1210)],RED,
       'M1 请求 / 66 bit：cnn_mmio_addr、wdata、re/we',(920,705,650,30),20)
p.edge('M1_ret','cnn','bridge',[(150,1320),(70,1320),(70,790),(1580,790),(1580,580),(1900,580),(1900,650)],RED,
       'M1 返回 / 33 bit：cnn_mmio_rdata、ready',(920,753,650,30),20)
p.edge('F_req','bridge','data',[(1830,995),(1770,995),(1770,930),(1510,930)],PURPLE,'F 请求 / 66 bit\ncache_csr_addr、wdata、re/we',(1518,950,275,64),18)
p.edge('F_ret','data','bridge',[(1510,1040),(1720,1040),(1720,1080),(1830,1080)],PURPLE,'F 返回 / 33 bit\ncache_csr_rdata、ready',(1525,1060,285,62),18)
p.edge('C_req','cnn','data',[(620,1200),(830,1200),(830,1130),(1050,1130)],RED,
       'C 请求：10 × 67 bit\naddr32 / wdata32 / valid / write / byte',(650,1080,380,70),18)
p.edge('C_ret','data','cnn',[(1050,1260),(880,1260),(880,1340),(620,1340)],RED,
       'C 返回：10 × 34 bit\nrdata32 / ready / response',(650,1270,380,65),19)
p.edge('C_fault','data','cnn',[(1050,1405),(955,1405),(955,1450),(620,1450)],RED,'cnn_mem_fault / 1',(650,1390,285,30),19)
p.edge('C_cancel','cnn','data',[(450,1570),(450,1710),(1150,1710),(1150,1480)],RED,
       'cnn_cancel / 1：协同取消与排空',(620,1660,470,38),21)
p.edge('GP_req','ps','bridge',[(2450,705),(2380,705),(2380,765),(2260,765)],GREEN,'GP0 请求\nAXI3 · A32 / D32',(2280,630,160,65),18)
p.edge('GP_ret','bridge','ps',[(2260,850),(2405,850),(2405,805),(2450,805)],GREEN,'GP0 回复\nRID / BID / RESP',(2280,865,160,60),18)
p.edge('HP_req','data','ps',[(1510,1270),(2370,1270),(2370,1170),(2450,1170)],GREEN,
       'HP0 请求：Mover → PS DDR（ADDR32 / WDATA64）',(1620,1205,690,50),21)
p.edge('HP_ret','ps','data',[(2930,1260),(2970,1260),(2970,1660),(1615,1660),(1615,1415),(1510,1415)],GREEN,
       'HP0 返回：RDATA64\nRRESP / BRESP',(1625,1605,400,65),19)
p.edge('fclk','ps','clock',[(2450,1380),(2260,1380)],CLOCK,'FCLK_CLK0 / 1',(2270,1335,170,36),18)
p.edge('frst','ps','clock',[(2450,1450),(2260,1450)],CLOCK,'FCLK_RESET0_N / 1',(2265,1460,180,48),17)
p.edge('clock_g','clock','g',[(2045,1600),(2045,1770)],CLOCK)
p.edge('uart_rx','j3','ps',[(2475,365),(2475,425),(2510,425),(2510,500)],GREEN,'UART1 RX / TX\n各 1 bit',(2400,430,170,50),17)
p.edge('uart_tx','ps','j3',[(2580,500),(2580,455),(2600,455),(2600,365)],GREEN)
p.edge('sd_req','ps','sd',[(2750,500),(2750,365)],GREEN,'SD0 / 卡检测',(2690,410,180,50),18)
p.edge('sd_ret','sd','ps',[(2890,365),(2890,500)],GREEN)
p.edge('ddr_req','ps','ddr',[(2600,1520),(2600,1740)],GREEN,'DDR_* / DQ32',(2455,1680,220,35),20)
p.edge('ddr_ret','ddr','ps',[(2800,1740),(2800,1520)],GREEN)
p.note(80,1950,2820,125,
 '读图约定：箭头标示信号来源 → 接收方；AXI 的请求/回复分别成组画出，完整信号见第 3 页。\nG 为同名全局时钟/复位网标签，不是新增 RTL 模块；交叉线无连接点时不相连。J3、SD 使用 PS MIO，不新增 PL 串口线。\n时钟配置目标 100 MHz；本版仅功能仿真通过，尚未综合、布局布线或上板验证。',size=22)

p=Page('02 两bank与软件规划读段',3000,1980)
p.title('软件规划与两 bank 数据通路展开','仅展开现有模块内部连接；共享 bank 数为 2，K3 内部四空间 MAC 的本地存储组织保持不变')
p.box('planner',70,200,520,230,'软件计划 / ARM FreeRTOS','prepare_plan.py / planned_schema.py',
      '主机预计算跨度 / 范围 / 读模式\nARM FreeRTOS 校验、加载并下发\n17 个 K3 模板；每任务仍为 20 个字',GREEN,20)
p.box('mailbox',740,200,490,230,'GP0 邮箱','image_control_bridge','发布请求序号 / 参数\nCPU 返回 ACK / 结果状态',PURPLE,22)
p.box('rv',1370,200,440,230,'RISC-V 控制固件','cpu_core + program.mem','读取邮箱，执行配置命令\n间接访问 CNN / Cache CSR',BLUE,21)
p.box('sched',1970,200,900,230,'CNN 模板与调度','cnn_ees331 → fixed_schedule_compact',
      '保存任务、依赖和帧上下文；重定位输入/权重/输出地址\nunit_command[511:0] / unit_start / busy / done / error',RED,23)
p.edge('sw_gp','planner','mailbox',[(590,310),(740,310)],GREEN,'32-bit AXI3',(595,253,140,50),18)
p.edge('cpu_rpc','mailbox','rv',[(1230,310),(1370,310)],PURPLE,'M0 请求/ACK',(1235,253,130,50),18)
p.edge('cpu_cfg','rv','sched',[(1810,310),(1970,310)],RED,'M1：模板配置',(1815,253,150,50),18)
p.box('pool',70,550,700,1030,'CNN 执行单元池','10 个逻辑访存客户端',color=RED)
p.box('k3',105,690,630,360,'K3 × 2','self_conv_spatial4_engine',
      '输入/权重行段：base + beats + byte/word\n专用 planned_read_adapter（每实例）\n最多 4 个有序未完成读取\n无逐请求标签匹配 / 无自动扩宽\n数据与 response_valid 寄存后推进算子\n内部 4 个空间 MAC 与本地 banks 保留',RED,21)
p.box('other',105,1100,630,280,'PW8 × 4 / Post × 2 / Add / Pad','其余算子访存路径保留','各自发出 32-bit 地址与数据\n按原有握手访问共享缓存',RED,22)
p.text(110,1430,620,85,'客户端编号：K3[1:0] / PW8[5:2]\nPost[7:6] / Add[8] / Pad[9]',22,RED)
p.box('queues',950,600,560,220,'每客户端请求 FIFO','cnn_paged_mover / request_queue','10 × 4 项；保持客户端回复顺序\n队首负载与页命中分类寄存',RAM,22)
p.box('pages',1700,600,560,220,'分页元数据 / 查找','392 个 1 KiB 页槽','16-bit 页标签 / valid / dirty / hint\n查找分拍；未命中触发页搬运',RAM,22)
p.box('arb',2440,600,430,220,'两 bank 仲裁','每 bank 轮转选择','每 bank 每拍最多一个计算请求\n同 bank 冲突等待',RAM,20)
p.box('issue',2440,930,430,150,'两路 issue 寄存器','owner / slot / address / data',color=RAM)
p.box('b0',1770,930,490,160,'Bank 0 · 196 KiB','tile_local_ram_bank2 / bank[0]',color=RAM)
p.text(1790,1040,450,35,'物理页槽 0…195；本地 0x00000…0x30FFF',19)
p.box('b1',1770,1160,490,160,'Bank 1 · 196 KiB','tile_local_ram_bank2 / bank[1]',color=RAM)
p.text(1790,1270,450,35,'物理页槽 196…391；本地 0x31000…0x61FFF',18)
p.box('reply',1020,1070,490,230,'两路返回流水','bank_reply_* → response_q / rdata_q',
      '字节选择 / 符号扩展\n按 owner 返回给对应客户端',RAM,22)
p.box('maint',950,1500,560,220,'页替换 / 维护状态机','DRAIN / WB / FILL / SCAN',
      '仅锁定正在搬运的物理页槽\n其他页仍可进行计算访问',RAM,22)
p.box('mover',1770,1500,550,220,'DATA MOVER','data_mover · 唯一 HP0 主设备',
      '固定 1 KiB 页传输\n8 个 burst × 16 beat × 64 bit',GREEN,22)
p.box('hp',2510,1500,360,220,'PS S_AXI_HP0','返回第 1 页 PS7','64-bit AXI3\nPS DDR 控制器',GREEN,22)
p.edge('dispatch','sched','pool',[(2070,430),(2070,490),(450,490),(450,550)],RED,
       'unit_command[511:0] / unit_start → 执行单元',(970,451,850,34),21)
p.edge('unit_status','pool','sched',[(650,550),(650,520),(2230,520),(2230,430)],RED,
       'busy / done / error → 调度器',(1100,522,820,28),20)
p.edge('q_req','pool','queues',[(770,730),(950,730)],RED,'10×67 bit',(775,674,170,40),20)
p.edge('q_page','queues','pages',[(1510,710),(1700,710)],RAM,'地址页 / hint',(1515,652,180,40),20)
p.edge('page_arb','pages','arb',[(2260,710),(2440,710)],RAM,'命中与槽号',(2265,652,170,40),20)
p.edge('arb_issue','arb','issue',[(2655,820),(2655,930)],RAM)
p.edge('comp0','issue','b0',[(2440,980),(2260,980)],RAM,'计算端 0',(2270,934,160,30),19)
p.edge('comp1','issue','b1',[(2550,1080),(2550,1210),(2260,1210)],RAM,'计算端 1',(2565,1120,280,45),19)
p.edge('r0','b0','reply',[(1770,990),(1600,990),(1600,1130),(1510,1130)],RAM,'rdata32 / error',(1520,1030,230,35),19)
p.edge('r1','b1','reply',[(1770,1230),(1510,1230)],RAM,'rdata32 / error',(1515,1240,245,34),19)
p.edge('responses','reply','pool',[(1020,1180),(900,1180),(900,1440),(770,1440)],RED,
       '10×34 bit\nrdata32 / ready / response',(920,1320,320,70),19)
p.edge('miss','pages','maint',[(1980,820),(1980,870),(870,870),(870,1600),(950,1600)],RAM,
       '未命中 / 刷新 / 失效\n等待已接收请求排空',(970,1395,490,75),20)
p.edge('dma_cmd','maint','mover',[(1510,1580),(1770,1580)],GREEN,'cmd_* / valid / ready',(1520,1530,240,36),19)
p.edge('dma_rsp','mover','maint',[(1770,1670),(1510,1670)],GREEN,'rsp_status / bytes / valid',(1515,1680,250,32),17)
p.box('dma_select',2390,1280,480,130,'DMA bank 选择 / 返回归属','tile_local_ram_bank2：单一 DMA 端口',color=GREEN)
p.edge('dma_command','mover','dma_select',[(2320,1530),(2400,1530),(2400,1450),(2660,1450),(2660,1410)],GREEN,
       'local_valid / write / addr32 / wdata32 / wstrb4',(2410,1415,530,28),17)
p.edge('dma_response','dma_select','mover',[(2390,1390),(2370,1390),(2370,1470),(2280,1470),(2280,1500)],GREEN)
p.edge('dma_b0','dma_select','b0',[(2390,1320),(2320,1320),(2320,1060),(2260,1060)],GREEN)
p.edge('dma_b1','dma_select','b1',[(2390,1370),(2350,1370),(2350,1280),(2260,1280)],GREEN)
p.edge('dma_r0','b0','dma_select',[(2260,1020),(2380,1020),(2380,1240),(2490,1240),(2490,1280)],GREEN)
p.edge('dma_r1','b1','dma_select',[(2260,1240),(2300,1240),(2300,1260),(2580,1260),(2580,1280)],GREEN)
p.edge('hp_req','mover','hp',[(2320,1570),(2510,1570)],GREEN,'AW / W\nAR',(2420,1515,80,55),18)
p.edge('hp_resp','hp','mover',[(2510,1660),(2320,1660)],GREEN,'R/B 回复',(2325,1670,180,36),19)
p.note(70,1790,2800,130,
 '共享两 bank 与 K3 本地四 bank 是两种不同层级的存储，不能混淆。图中的存储连接均是逻辑接口，并非新增板级引脚。\n软件提供静态几何与读模式；硬件仍处理实际 ready/response、FIFO 信用、取消与错误。动态分页仍由 cnn_paged_mover 管理。\n两 bank 的实际数据端口、请求选择与返回通路均为两路；共享容量和原双图计算结果保持。',size=22)

p=Page('03 接口方向与位宽明细',3000,2320)
p.title('接口方向 / 信号名 / 位宽','所有位宽按本版本配置计算；时钟与复位不计入各业务线组合计；AXI 按独立通道列出')
def table(page,x,y,width,headers,rows,colwidths,rowh=95,size=20):
 cx=x
 for text,w in zip(headers,colwidths):
  page.box(page.ident(),cx,y,w,60,color='#526172',fill='#202630');page.text(cx+12,y+8,w-24,44,text,23);cx+=w
 for r,row in enumerate(rows):
  cx=x
  for text,w in zip(row,colwidths):
   page.box(page.ident(),cx,y+60+r*rowh,w,rowh,color='#394352',fill=PANEL if r%2==0 else '#181e26')
   page.text(cx+12,y+68+r*rowh,w-24,rowh-16,text,size,FG,'left');cx+=w
rows=[
 ('I 取指','CPU → IMEM','imem_addr[31:0]、imem_re','33','IMEM → CPU：imem_rdata[31:0] / 32'),
 ('D 本地数据','CPU → DATASRAM','dmem_addr[31:0]、dmem_wdata[31:0]\ndmem_re、dmem_we、dmem_wstrb[3:0]','70','DATASRAM → CPU：dmem_rdata[31:0] / 32'),
 ('M0 邮箱/索引','CPU → IMAGE_BRIDGE','mmio_addr[31:0]、mmio_wdata[31:0]\nmmio_re、mmio_we','66','Bridge → CPU：mmio_rdata[31:0]、mmio_ready / 33'),
 ('M1 CNN寄存器','IMAGE_BRIDGE → CNN','cnn_mmio_addr[31:0]、cnn_mmio_wdata[31:0]\ncnn_mmio_re、cnn_mmio_we','66','CNN → Bridge：cnn_mmio_rdata[31:0]、ready / 33'),
 ('F 缓存维护','IMAGE_BRIDGE → DATASRAM','cache_csr_addr[31:0]、cache_csr_wdata[31:0]\ncache_csr_re、cache_csr_we','66','DATASRAM → Bridge：cache_csr_rdata[31:0]、ready / 33'),
 ('C 计算访存','CNN → DATASRAM','10 × {cnn_addr[31:0]、cnn_wdata[31:0]\ncnn_valid、cnn_write、cnn_byte}','10 × 67','DATASRAM → CNN：10 × {rdata32、ready、response}\n10 × 34 bit；ready 与 response 含义不同'),
 ('取消 / 故障','CNN → DATASRAM / 反向','cnn_cancel / 1：CNN → DATASRAM','1 + 1','cnn_mem_fault / 1：DATASRAM → CNN'),
 ('内部 bank 计算口','Cache issue → 两 bank RAM','每 bank：comp_req、comp_we、comp_addr32\ncomp_wdata32、comp_wstrb4','2 × 70','每 bank：comp_rdata32、comp_error / 33\n固定流水延迟，未单独提供 ready'),
 ('内部 DMA 本地口','DATA MOVER → bank 选择','local_valid、local_write、local_addr32\nlocal_wdata32、local_wstrb4','70','RAM → Mover：local_ready、local_rsp_valid\nlocal_rdata32、local_error / 35'),
]
table(p,70,190,2860,('线组','请求来源 → 接收方','请求信号','请求位数','返回方向与信号'),rows,[260,440,850,210,1100],100,20)
axi=[
 ('M_AXI_GP0','PS → IMAGE_BRIDGE','AW / AR：ADDR32、ID12、LEN4、SIZE3、BURST2\nLOCK2、CACHE4、PROT3、QOS4、VALID；READY 反向\nW：DATA32、STRB4、ID12、LAST、VALID；READY 反向',
  'Bridge → PS\nB：ID12、RESP2、VALID；READY 反向\nR：DATA32、ID12、RESP2、LAST、VALID；READY 反向'),
 ('S_AXI_HP0','DATA MOVER → PS','AW / AR：ADDR32、ID6、LEN4、SIZE3、BURST2\nLOCK2、CACHE4、PROT3、QOS4、VALID；READY 反向\nW：DATA64、STRB8、ID6、LAST、VALID；READY 反向',
  'PS → Mover\nB：ID6、RESP2、VALID；READY 反向\nR：DATA64、ID6、RESP2、LAST、VALID；READY 反向'),
]
table(p,70,1230,2860,('AXI3 接口','主设备 → 从设备','请求通道字段（后缀按 AW / AR / W）','返回通道字段（B / R）'),axi,[300,500,1120,940],170,21)
p.note(80,1660,2800,300,
 'G 时钟与复位\nPS FCLK_CLK0 → clock_unit.sys_clk；PS FCLK_RESET0_N → clock_unit.rst_n_in。\nclock_unit.clk / rst_n → cpu_core、imem_rom、cnn_ees331、datasram_mover_subsystem、image_control_bridge。\nclk 同时回接 M_AXI_GP0_ACLK / S_AXI_HP0_ACLK；本图不新增独立 CPU 时钟或 PLL。\n\n地址与外设\nARM 经 GP0 访问邮箱窗口 0x40000000；RISC-V 通过索引窗口访问 CNN（index 0x1000…0x1FFF）和 Cache CSR（index 0x2000…0x20FF）。\n硬件 CNN 逻辑窗口为 64 MiB，DDR_BASE=0x10000000；当前 ARM 计划只使用其中前 16 MiB。\nIMEM：8 KiB；CPU Data SRAM：16 KiB；共享两 bank：392 KiB。J3 和 SD 走 PS MIO；板级顶层还导出 DDR_* 与 FIXED_IO_*。',size=22)
p.note(80,2040,2800,160,
 '软件读计划仅对 K3 重新解释命令字 4、5、12、15 及字 11 的指定标志；字 13/14 保留给帧重定位，模板宽度不变。\n本图依据 source/rtl/soc/ees331/face_soc_ees331_mover_top.sv 及实际实例连接生成，未照搬旧图中当前不存在的状态灯、PL UART 或 IMEM 下载口。\n全部图形、标签与连线均可在 draw.io 中逐项编辑；页面 1 / 2 为分组接口图，页面 3 是精确信号索引。',size=21)

def font(size):return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',int(size))
def lines(text,width,size):
 f=font(size);result=[]
 for para in text.split('\n'):
  if not para:result.append('');continue
  row=''
  for char in para:
   if row and f.getlength(row+char)>width:
    result.append(row);row=char
   else:row+=char
  result.append(row)
 return result

mxfile=ET.Element('mxfile',host='app.diagrams.net',pages=str(len(pages)),type='device')
overflow=[]
for n,page in enumerate(pages,1):
 diagram=ET.SubElement(mxfile,'diagram',id=f'ees331_page_{n}',name=page.name)
 model=ET.SubElement(diagram,'mxGraphModel',dx='1800',dy='1200',grid='1',gridSize='10',guides='1',
   tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth=str(page.w),pageHeight=str(page.h),background=BG,math='0',shadow='0')
 root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
 image=Image.new('RGB',(page.w,page.h),BG);draw=ImageDraw.Draw(image)
 svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.w}" height="{page.h}" viewBox="0 0 {page.w} {page.h}"><rect width="100%" height="100%" fill="{BG}"/>']
 for item in page.items:
  kind=item['kind'];id=item['id']
  if kind=='edge':
   source=page.nodes[item['source']];target=page.nodes[item['target']];points=item['points'];sx,sy=points[0];tx,ty=points[-1]
   ex=(sx-source['x'])/source['w'];ey=(sy-source['y'])/source['h'];ix=(tx-target['x'])/target['w'];iy=(ty-target['y'])/target['h']
   for a in (ex,ey,ix,iy):assert -.001<=a<=1.001,(page.name,id,'anchor outside node',a)
   style=f'edgeStyle=none;rounded=0;html=0;endArrow=block;endFill=1;strokeColor={item["color"]};strokeWidth=2.5;jumpStyle=arc;jumpSize=10;exitX={ex};exitY={ey};exitPerimeter=0;entryX={ix};entryY={iy};entryPerimeter=0;'
   cell=ET.SubElement(root,'mxCell',id=id,parent='1',edge='1',source=item['source'],target=item['target'],style=style,value='')
   g=ET.SubElement(cell,'mxGeometry',relative='1',**{'as':'geometry'})
   ET.SubElement(g,'mxPoint',x=str(sx),y=str(sy),**{'as':'sourcePoint'});ET.SubElement(g,'mxPoint',x=str(tx),y=str(ty),**{'as':'targetPoint'})
   if len(points)>2:
    arr=ET.SubElement(g,'Array',**{'as':'points'})
    for x,y in points[1:-1]:ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
   draw.line(points,fill=item['color'],width=3)
   x0,y0=points[-2];dx,dy=tx-x0,ty-y0;length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
   triangle=[(tx,ty),(tx-15*ux+6*uy,ty-15*uy-6*ux),(tx-15*ux-6*uy,ty-15*uy+6*ux)]
   draw.polygon(triangle,fill=item['color'])
   svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{item["color"]}" stroke-width="3"/><polygon points="{" ".join(f"{x},{y}" for x,y in triangle)}" fill="{item["color"]}"/>')
  else:
   x,y,w,h=[item[k] for k in ('x','y','w','h')]
   assert x>=0 and y>=0 and x+w<=page.w and y+h<=page.h,(page.name,id,'outside page')
   if kind=='box':
    style=f'rounded=0;whiteSpace=wrap;html=0;fillColor={item["fill"]};strokeColor={item["color"]};strokeWidth=2;fontFamily={FONT};'
    value='';draw.rectangle((x,y,x+w,y+h),fill=item['fill'],outline=item['color'],width=2)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{item["fill"]}" stroke="{item["color"]}" stroke-width="2"/>')
   else:
    value=item['value'];size=item['size'];fill=item['fill'] or 'none'
    style=f'text;whiteSpace=wrap;html=0;align={item["align"]};verticalAlign=middle;strokeColor=none;fillColor={fill};fontColor={item["color"]};fontFamily={FONT};fontSize={size};spacing=0;'
    rows=lines(value,w,size);lineh=size*1.4;used=len(rows)*lineh
    if used>h+3:overflow.append((page.name,id,value[:75],round(used),h))
    if item['fill']:
     draw.rectangle((x,y,x+w,y+h),fill=fill);svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
    top=y+(h-used)/2
    for i,line in enumerate(rows):
     lx=x+(w-font(size).getlength(line))/2 if item['align']=='center' else x
     ly=top+i*lineh
     draw.text((lx,ly),line,font=font(size),fill=item['color'],anchor='lt')
     svg.append(f'<text x="{lx}" y="{ly+size}" font-family="{FONT}" font-size="{size}" fill="{item["color"]}">{html.escape(line)}</text>')
   cell=ET.SubElement(root,'mxCell',id=id,parent='1',vertex='1',style=style,value=value)
   ET.SubElement(cell,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
 svg.append('</svg>')
 name=f'EES331_bank2_page{n}'
 image.save(OUT/(name+'.png'))
 (OUT/(name+'.svg')).write_text(''.join(svg),encoding='utf-8')
path=OUT/'EES331_两bank_软件规划访存_顶层连线图.drawio'
ET.indent(mxfile,space='  ');ET.ElementTree(mxfile).write(path,encoding='utf-8',xml_declaration=True)
if overflow:
 print('TEXT_OVERFLOW',json.dumps(overflow,ensure_ascii=False,indent=2));raise RuntimeError('Fix text boxes before delivery')
tree=ET.parse(path)
for diagram in tree.getroot().findall('diagram'):
 cells=diagram.findall('.//mxCell');ids=[c.get('id') for c in cells]
 assert len(ids)==len(set(ids)),diagram.get('name')
 for c in cells:
  for k in ('parent','source','target'):
   if c.get(k):assert c.get(k) in ids,(c.get('id'),k,c.get(k))
collisions=[]
for page in pages:
 for edge in page.edges:
  for node in page.nodes.values():
   if node['id'] in (edge['source'],edge['target'],'pl','pool'):continue
   l,r=node['x'],node['x']+node['w'];t,b=node['y'],node['y']+node['h']
   for (x1,y1),(x2,y2) in zip(edge['points'],edge['points'][1:]):
    hit=(x1==x2 and l<x1<r and max(min(y1,y2),t)<min(max(y1,y2),b)) or (y1==y2 and t<y1<b and max(min(x1,x2),l)<min(max(x1,x2),r))
    if hit:collisions.append((page.name,edge['id'],node['id']))
assert not collisions,collisions
label_collisions=[]
for page in pages:
 for label in page.items:
  if not label.get('edge_label_for'):continue
  l,r=label['x'],label['x']+label['w'];t,b=label['y'],label['y']+label['h']
  for edge in page.edges:
   if edge['id']==label['edge_label_for']:continue
   for (x1,y1),(x2,y2) in zip(edge['points'],edge['points'][1:]):
    hit=(x1==x2 and l<x1<r and max(min(y1,y2),t)<min(max(y1,y2),b)) or (y1==y2 and t<y1<b and max(min(x1,x2),l)<min(max(x1,x2),r))
    if hit:label_collisions.append((page.name,label['edge_label_for'],edge['id']))
assert not label_collisions,label_collisions
record=dict(file=str(path),pages=[p.name for p in pages],source_top_sha256=hashlib.sha256((BASE/'source/rtl/soc/ees331/face_soc_ees331_mover_top.sv').read_bytes()).hexdigest(),
 k1_units=int((BASE/'k1_units.txt').read_text()),cache_bytes=401408,bank_count=2,
 node_count=sum(len(p.nodes) for p in pages),edge_count=sum(len(p.edges) for p in pages),text_overflow=0,unrelated_box_crossings=0,label_edge_collisions=0)
(OUT/'diagram_validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
