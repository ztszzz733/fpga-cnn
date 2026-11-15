"""Draw the proposed independent program UART wiring; never overwrite v1."""
from pathlib import Path
from html import escape
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/figures"
W, H = 2600, 1830
im = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<rect width="100%" height="100%" fill="white"/>']
FONT = "C:/Windows/Fonts/msyh.ttc"
INK, GRAY = "#202b36", "#617080"
BLUE, GREEN, ORANGE, RED = "#2169ab", "#21805a", "#af6517", "#c64646"


def text(x, y, value, size=25, color=INK, center=False):
    font = ImageFont.truetype(FONT, size)
    for i, s in enumerate(value.split("\n")):
        yy = y + i * (size + 10)
        width = draw.textlength(s, font=font)
        xx = x - width / 2 if center else x
        assert 0 <= xx and xx + width <= W and yy + size + 10 <= H, s
        draw.text((xx, yy), s, font=font, fill=color)
        svg.append(f'<text x="{xx}" y="{yy + size}" font-family="Microsoft YaHei, sans-serif" font-size="{size}" fill="{color}">{escape(s)}</text>')


def line(points, color=INK, width=3, dashed=False, start=False, end=False):
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if dashed:
            length = math.hypot(x2-x1, y2-y1)
            for t in range(0, int(length), 18):
                a, b = t/length, min(t+10, length)/length
                draw.line((x1+(x2-x1)*a, y1+(y2-y1)*a, x1+(x2-x1)*b, y1+(y2-y1)*b), fill=color, width=width)
        else:
            draw.line((x1,y1,x2,y2), fill=color, width=width)
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"{dash}/>')
    for active, tip, prev in [(start, points[0], points[1]), (end, points[-1], points[-2])]:
        if active:
            a = math.atan2(tip[1]-prev[1], tip[0]-prev[0])
            pts = [tip, (tip[0]-14*math.cos(a)+7*math.sin(a), tip[1]-14*math.sin(a)-7*math.cos(a)),
                   (tip[0]-14*math.cos(a)-7*math.sin(a), tip[1]-14*math.sin(a)+7*math.cos(a))]
            draw.polygon(pts, fill=color)
            svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{color}"/>')


def box(x, y, w, h, fill="white", color=INK, dashed=False):
    draw.rectangle((x,y,x+w,y+h), fill=fill)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
    line([(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)], color, 3, dashed)


text(60, 25, "SoC 新版接线：独立程序下载口，工作与下载互斥", 42)
text(60, 89, "设计稿 · 未实现 RTL  |  旧版六模块与原图保留  |  新版七模块，共用一个 clk，外部 IO 由 7 根变为 9 根", 26, GRAY)
box(40, 155, 2170, 1330, "#fbfcfe", "#95a6b5")
text(65, 168, "SoC / FPGA 内部（橙色表示新增或改造；图中接口位数不含时钟、复位、状态控制）", 24, GRAY)
line([(2260,155),(2260,1485)], RED, 4, True)
text(2290,168,"芯片外部",29,RED)

box(100,225,470,115,"#fff3e4",ORANGE)
text(335,237,"clock_unit（复位控制扩展）",27,center=True)
text(335,285,"同一 clk；系统 / CPU 复位分开",23,ORANGE,True)
line([(2390,265),(570,265)], GRAY, 3, end=True)
text(1150,225,"sys_clk / rst_n_in，各 1 位",25,GRAY,True)
text(2290,295,"晶振 / 复位",25)
text(670,307,"clk → 全部模块；rst_n → 其余模块；cpu_rst_n → 仅 CPU",25,GRAY)

box(100,425,470,180,"#fcebed",RED)
text(335,438,"cpu_core",33,center=True)
text(335,489,"Control C1 + Datapath 保留",24,center=True)
text(335,536,"封装补充可停机确认",24,ORANGE,True)
box(1050,425,480,180,"#e9f6ef",GREEN)
text(1290,438,"cnn",33,center=True)
text(1290,489,"原计算 / MMIO / 访存逻辑",24,center=True)
text(1290,536,"需新增正式 cnn_idle 状态出口",23,ORANGE,True)
line([(570,465),(1050,465)],GREEN,4,start=True,end=True)
text(810,410,"③ MMIO：66 / 33 位",24,GREEN,True)

box(100,790,470,195,"#fff3e4",ORANGE)
text(335,805,"IMEM（新增可写版本）",29,center=True)
text(335,855,"CPU 读口 + 程序下载读写口",24,center=True)
text(335,902,"模式互斥；仍是一拍取指",24,ORANGE,True)
line([(335,605),(335,790)],BLUE,4,start=True,end=True)
text(380,659,"① 取指",25,BLUE)
text(380,703,"33 / 32 位",23,BLUE)

box(1050,790,480,195,"#e8f1fa",BLUE)
text(1290,805,"datasram",33,center=True)
text(1290,855,"A：CPU；B：CNN / 图像桥",24,center=True)
text(1290,902,"原内部仲裁保留；新增 idle 导出",22,ORANGE,True)
line([(570,565),(735,565),(735,835),(1050,835)],BLUE,3,start=True,end=True)
text(765,657,"② CPU A口",25,BLUE)
text(765,702,"70 / 32 位",23,BLUE)
line([(1290,605),(1290,790)],GREEN,4,start=True,end=True)
text(1330,659,"④ CNN B口",24,GREEN)
text(1330,702,"66 / 33 位",23,GREEN)

box(1670,790,480,195,"#e9f6ef",GREEN)
text(1910,805,"image_bridge",32,center=True)
text(1910,855,"原图像串口 + SRAM 传输",24,center=True)
text(1910,902,"新增业务锁定 / 已锁定确认",24,ORANGE,True)
line([(1530,865),(1670,865)],GREEN,4,start=True,end=True)
text(1600,1020,"⑤ 图像 B口：70 / 35 位（含 error）",23,GREEN,True)
line([(2390,855),(2150,855)],GREEN,4,start=True,end=True)
text(2290,727,"图像 USB-UART",24,GREEN)
text(2290,769,"原 uart_rx / uart_tx",22,GREEN)

box(1670,1220,480,215,"#fff3e4",ORANGE)
text(1910,1233,"program_bridge（新增）",28,center=True)
text(1910,1280,"独立 UART + 程序包 / 校验",24,center=True)
text(1910,1324,"忙状态检查 + 下载互锁",24,center=True)
text(1910,1368,"CPU 停止 / 启动控制",24,ORANGE,True)
line([(2390,1320),(2150,1320)],ORANGE,4,start=True,end=True)
text(2290,1190,"程序 USB-UART",24,ORANGE)
text(2290,1232,"新 prog_rx / prog_tx",22,ORANGE)
line([(1670,1330),(1480,1330),(1480,1115),(335,1115),(335,985)],ORANGE,4,start=True,end=True)
text(830,1072,"⑥ 新 IMEM 下载口：66 / 34 位（含 error）",25,ORANGE,True)

text(100,1210,"新增控制线（详细方向和条件见正文第 9、10 节）",26,ORANGE)
text(100,1260,"CPU可停机 / CNN空闲 / SRAM空闲 → 程序桥",25)
text(100,1305,"程序桥 <-> 图像桥：锁定请求 / 已锁定",25)
text(100,1350,"程序桥 <-> 复位控制：CPU保持 / 停止确认",25)
text(100,1395,"程序桥 → IMEM：download_enable",25)
text(2290,1400,"两组引脚独立",23,RED)

box(40,1520,2520,245,"#fff8ed",ORANGE)
text(70,1540,"下载准入：忙则拒绝，不改 IMEM；空闲确认后锁新业务、停 CPU，再开放下载",30,ORANGE)
text(70,1600,"运行 → 检查 / 锁定 → CPU 已停止 → 下载与读回校验 → 关闭写口 → CPU 从入口重新运行",27)
text(70,1650,"原图像 UART 不承载程序；下载期间拒绝新图像 SRAM 业务。不能用 led_busy 代替全系统状态。",25)
text(70,1696,"外部 IO：sys_clk、rst_n_in、uart_rx/tx、prog_rx/tx、原 3 个 LED；5 输入 + 4 输出 = 9 位。",25)
text(60,1780,"仅为接线设计稿；新增状态出口、维护握手、串口协议和引脚约束仍需实现与验证。",24,GRAY)

OUT.mkdir(parents=True,exist_ok=True)
im.save(OUT/'soc_prog_io_v2.png')
(OUT/'soc_prog_io_v2.svg').write_text('\n'.join(svg+['</svg>']),encoding='utf-8')
print('Wrote docs/figures/soc_prog_io_v2.png and .svg')
