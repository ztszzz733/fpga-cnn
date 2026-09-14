"""Render real VCD transitions as readable PNG timing diagrams (requires Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VCD = ROOT / "build" / "top_smoke.vcd"
scope, signals, events = [], {}, {}
time_ps = 0
for line in VCD.read_text(encoding="ascii").splitlines():
    parts = line.split()
    if not parts:
        continue
    if parts[0] == "$scope":
        scope.append(parts[2])
    elif parts[0] == "$upscope":
        scope.pop()
    elif parts[0] == "$var":
        signals[".".join(scope + [parts[4]]) + "".join(parts[5:-1])] = parts[3]
    elif line.startswith("#"):
        time_ps = int(line[1:])
    elif line[0] in "01xz":
        events.setdefault(line[1:], []).append((time_ps / 1000, line[0]))
    elif line[0] == "b":
        events.setdefault(parts[1], []).append((time_ps / 1000, parts[0][1:]))
END_NS = time_ps / 1000


def series(name):
    return events[signals["tb_top_smoke.dut." + name]]


def decode(value):
    return "X" if "x" in value.lower() or "z" in value.lower() else str(int(value, 2))


font_path = Path("C:/Windows/Fonts/msyh.ttc")
if not font_path.is_file():
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def font(size):
    return ImageFont.truetype(str(font_path), size)


def plot(filename, title, subtitle, traces, start, end, tick, note, highlights=()):
    width, left, right, top, row = 1600, 235, 1450, 178, 70
    height = top + row * len(traces) + 100
    im = Image.new("RGB", (width, height), "#f5f7fb")
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((22, 20, width-22, height-20), 20, fill="white")
    draw.text((50, 40), title, font=font(31), fill="#15243b")
    draw.text((50, 91), subtitle, font=font(19), fill="#53637b")
    draw.text((1470, 142), "结束值", font=font(17), fill="#53637b")
    x = lambda t: left + (t-start) * (right-left) / (end-start)
    bottom = top + row * len(traces)
    for lo, hi in highlights:
        draw.rectangle((x(max(lo,start)),top-16,x(min(hi,end)),bottom), fill="#fdf5df")
    tick_start = int(start // tick) * tick
    for t in range(tick_start, int(end)+1, tick):
        if t < start:
            continue
        xx=x(t)
        draw.line((xx,top-12,xx,bottom), fill="#e1e7f0", width=1)
        draw.text((xx,top-34), str(t), font=font(15), anchor="mm", fill="#53637b")
    draw.text((right-12,bottom+20), "时间 / ns", font=font(16), anchor="ra", fill="#53637b")
    for idx,(name,is_bus) in enumerate(traces):
        y=top+idx*row
        high,low=y+6,y+40
        data=series(name)
        display_name=name.split("[")[0]
        color="#087f77" if not is_bus else "#2459b9"
        draw.text((50,y+20),display_name,font=font(18),anchor="lm",fill="#20344d")
        draw.line((left,y+55,right,y+55),fill="#eef1f6",width=1)
        current = next((v for t,v in reversed(data) if t <= start), "x")
        clipped=[(start,current)] + [(t,v) for t,v in data if start<t<end]
        last_y=None
        for j,(t,val) in enumerate(clipped):
            until=clipped[j+1][0] if j+1<len(clipped) else end
            if until<=t:
                continue
            a,b=x(t),x(until)
            known=decode(val)!="X"
            col=color if known else "#a3aab8"
            if is_bus:
                inset=min(4,(b-a)/3)
                draw.line([(a,(high+low)/2),(a+inset,high),(b-inset,high),(b,(high+low)/2),
                           (b-inset,low),(a+inset,low),(a,(high+low)/2)], fill=col,width=2)
                text=decode(val)
                if b-a > draw.textlength(text,font=font(17))+12:
                    draw.text(((a+b)/2,(high+low)/2),text,font=font(17),anchor="mm",fill=col)
            else:
                yy=high if val=="1" else low
                if last_y is not None and yy!=last_y:
                    draw.line((a,last_y,a,yy),fill=col,width=2)
                draw.line((a,yy,b,yy),fill=col,width=2)
                last_y=yy
        final=next(v for t,v in reversed(data) if t<=end)
        draw.text((1495,y+22),decode(final),font=font(20),anchor="mm",fill=color)
    draw.text((50,height-65),note,font=font(18),fill="#53637b")
    path=ROOT/"build"/filename
    im.save(path)
    print(path)


assert decode(series("output_value[7:0]")[-1][1]) == "45"
assert decode(series("mmio_rdata[31:0]")[-1][1]) == "2"
assert [int(v,2) for t,v in series("acc_value[31:0]") if 785<=t<=865] == [1,3,6,10,15,21,28,36,45]
plot("wave_overview.png", "CNN 加速器：真实仿真波形", "3×3 输入 1…9 · 权重全 1 · Bias = 0 · 总线数值以十进制显示",
     [("start",False),("core_busy",False),("mem_read",False),("mem_write",False),
      ("mac_enable",False),("done",False),("mmio_rdata[31:0]",True),("output_value[7:0]",True)],
     0,END_NS,100,"175 ns 启动 → 读取与计算 → 895 ns 输出 45 → 945 ns STATUS = 2（完成）")
plot("wave_mac_detail.png", "放大观察：MAC 累加到 45", "770–951 ns · 淡黄色区域为 MAC 使能阶段 · 数据直接提取自 top_smoke.vcd",
     [("clk",False),("mac_enable",False),("input_value[7:0]",True),("acc_value[31:0]",True),
      ("output_value[7:0]",True),("mem_write",False),("done",False),("mmio_rdata[31:0]",True)],
     770,END_NS,20,"acc_value：1 → 3 → 6 → 10 → 15 → 21 → 28 → 36 → 45；写回后 DONE 脉冲到来。",[(775,865)])
