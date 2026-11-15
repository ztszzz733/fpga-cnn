"""Draw the current SoC as CPU/MEM -> internal links -> I/O -> board devices."""
from pathlib import Path
from html import escape
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/figures"
W, H = 2400, 1700
im = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<rect width="100%" height="100%" fill="white"/>']
FONT = "C:/Windows/Fonts/msyh.ttc"
INK, GRAY = "#202b36", "#617080"
BLUE, GREEN, RED = "#2169ab", "#21805a", "#c64646"


def text(x, y, value, size=25, color=INK, center=False):
    font = ImageFont.truetype(FONT, size)
    for i, s in enumerate(value.split("\n")):
        yy = y + i * (size + 10)
        width = draw.textlength(s, font=font)
        xx = x - width / 2 if center else x
        assert 0 <= xx and xx + width <= W, (s, xx, width)
        draw.text((xx, yy), s, font=font, fill=color)
        svg.append(f'<text x="{xx}" y="{yy + size}" font-family="Microsoft YaHei, sans-serif" font-size="{size}" fill="{color}">{escape(s)}</text>')


def line(points, color=INK, width=3, dashed=False, start=False, end=False):
    if dashed:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            length = math.hypot(x2-x1, y2-y1)
            for t in range(0, int(length), 18):
                a, b = t/length, min(t+10, length)/length
                draw.line((x1+(x2-x1)*a, y1+(y2-y1)*a,
                           x1+(x2-x1)*b, y1+(y2-y1)*b), fill=color, width=width)
    else:
        draw.line(points, fill=color, width=width)
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"{dash}/>')
    for active, tip, prev in [(start, points[0], points[1]), (end, points[-1], points[-2])]:
        if active:
            a = math.atan2(tip[1]-prev[1], tip[0]-prev[0])
            pts = [tip, (tip[0]-14*math.cos(a)+7*math.sin(a), tip[1]-14*math.sin(a)-7*math.cos(a)),
                   (tip[0]-14*math.cos(a)-7*math.sin(a), tip[1]-14*math.sin(a)+7*math.cos(a))]
            draw.polygon(pts, fill=color)
            svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{color}"/>')


def box(x, y, w, h, fill="#ffffff", color=INK, dashed=False):
    draw.rectangle((x,y,x+w,y+h), fill=fill)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
    line([(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)], color, 3, dashed)



text(60, 25, "SoC 六模块连接图：CPU + 存储器 → 内部连线 → I/O", 40)
text(60, 85, "当前板级顶层 face_soc_top  |  六个实线模块均有 RTL  |  双向箭头代表两组单向请求 / 返回线", 24, GRAY)
box(40,150,1770,1080,"#fbfcfe","#95a6b5")
text(60,160,"SoC / FPGA 芯片内部",25,GRAY)
line([(1850,150),(1850,1220)],RED,4,True)
text(1870,160,"封装外部",27,RED)

box(100,225,420,110,"#f2f4f6",GRAY)
text(310,240,"clock_unit",30,center=True)
text(310,285,"时钟直通；复位同步释放",24,GRAY,True)
line([(2020,265),(520,265)],GRAY,3,end=True)
text(950,225,"sys_clk / rst_n_in：外部 → 时钟模块，各 1 位",23,GRAY)
text(2020,230,"晶振 + 复位按钮",26)
text(650,300,"clk / rst_n：clock_unit → 其余五模块，各 1 位（公共线不重复展开）",24,GRAY)

text(100,370,"CPU + MEM",29,BLUE)
text(1270,370,"I/O + CNN",29,GREEN)
box(100,425,420,170,"#fcebed",RED)
text(310,443,"cpu_core",32,center=True)
text(310,491,"内部：cpu_control",25,center=True)
text(310,531,"+ cpu_datapath",25,center=True)
box(100,705,420,115,"#e8f1fa",BLUE)
text(310,718,"IEM（imem_rom）",30,center=True)
text(310,763,"只保存 CPU 程序",24,BLUE,True)
box(100,965,420,200,"#e8f1fa",BLUE)
text(310,980,"datasram",32,center=True)
text(310,1029,"共享数据 RAM",25,center=True)
text(310,1069,"A：CPU   B：CNN / 图像桥",23,BLUE,True)
text(310,1110,"仲裁 + 完成时序逻辑均在内部",23,BLUE,True)

box(1270,425,460,180,"#e9f6ef",GREEN)
text(1500,440,"cnn",32,center=True)
text(1500,486,"mobilefacenet_accelerator_top",21,center=True)
text(1500,525,"CPU 口：accelerator_regs",23,center=True)
text(1500,565,"存储口：accelerator_mem_if",23,center=True)
box(1270,965,460,200,"#e9f6ef",GREEN)
text(1500,980,"image_bridge",32,center=True)
text(1500,1029,"UART RX / TX + CRC32",25,center=True)
text(1500,1070,"收完整包并校验，再写入 RAM",23,center=True)
text(1500,1110,"支持 SRAM 读回和错误回包",23,center=True)

line([(310,595),(310,705)],BLUE,3,start=True,end=True)
text(345,610,"① 取指",24,BLUE)
text(345,650,"33 / 32 位",22,BLUE)
text(125,858,"② CPU 数据口：70 / 32 位",23,BLUE)
line([(520,560),(575,560),(575,990),(520,990)],BLUE,3,start=True,end=True)

line([(520,470),(1270,470)],GREEN,4,start=True,end=True)
text(875,424,"③ CPU 与 CNN：MMIO 66 / 33 位",24,GREEN,True)
line([(1270,570),(1090,570),(1090,1000),(520,1000)],GREEN,4,start=True,end=True)
text(705,664,"④ CNN 与 datasram",26,GREEN)
text(705,711,"原生 mem_*：66 / 33 位",24,GREEN)
text(705,760,"不经过 CPU；无独立适配器",24,GREEN)
line([(520,1090),(1270,1090)],BLUE,4,start=True,end=True)
text(895,1039,"⑤ 图像桥与 datasram：70 / 35 位",23,BLUE,True)

line([(1730,1015),(2010,1015)],GREEN,3,start=True,end=True)
text(1885,938,"uart_rx / uart_tx",21,GREEN,True)
text(1885,972,"各 1 位",21,GREEN,True)
text(2020,1000,"电脑 / USB-UART",25)
line([(1730,1138),(2010,1138)],GRAY,3,end=True)
text(1885,1170,"状态输出共 3 位",21,GRAY,True)
text(2020,1110,"板载 LED",25)
text(2020,1155,"ready / busy / error",22,GRAY)
text(720,1185,"cnn_mem_fault：datasram → 顶层错误灯组合逻辑，1 位",23,RED)

text(60,1270,"每条编号接口都分成地址线、数据线、信号线；不是一根双向总线，也不另加总线模块。",27)
text(60,1325,"① 地址 imem_addr[31:0]；数据 imem_rdata[31:0]；信号 imem_re（1）",24)
text(60,1370,"② 地址 dmem_addr[31:0]；数据 wdata / rdata 各 32；信号 re / we 各 1、wstrb[3:0]",24)
text(60,1415,"③ 地址 mmio_addr[31:0]；数据 wdata / rdata 各 32；信号 re / we / ready 各 1",24)
text(60,1460,"④ 地址 mem_addr[31:0]；数据 wdata / rdata 各 32；信号 read / write / ready 各 1",24)
text(60,1505,"⑤ 地址 io_mem_addr[31:0]；数据 wdata / rdata 各 32；信号 req / we / gnt / rvalid / error 各 1、be[3:0]",24)
text(60,1570,"封装顶层共 7 根数字 I/O（不含电源 / 地 / 下载专用脚）。LED busy 表示 UART 传输忙，不是 CNN busy。",24,GRAY)
text(60,1620,"精确方向、时序、软件所有权和验证边界：见顶层《SoC顶层连线与总体IO说明_小白版.md》。",24,GRAY)
OUT.mkdir(parents=True,exist_ok=True)
im.save(OUT / "soc_cpu_mem_io.png")
svg.append("</svg>")
(OUT / "soc_cpu_mem_io.svg").write_text("\n".join(svg),encoding="utf-8")
print(OUT / "soc_cpu_mem_io.png")
