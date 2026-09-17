"""Render real VCD transitions as readable PNG timing diagrams (requires Pillow)."""
from pathlib import Path
import argparse
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--custom',action='store_true',help='render the editable 3x3 single-output experiment')
parser.add_argument('--queue-dir',type=Path,help='render the editable task queue experiment')
args=parser.parse_args()
if args.custom and args.queue_dir:parser.error('Choose one experiment')
OUTPUT_DIR=args.queue_dir.resolve() if args.queue_dir else ROOT/'build'/'custom_wave' if args.custom else ROOT/'build'
VCD=OUTPUT_DIR/('custom_queue.vcd' if args.queue_dir else 'custom.vcd' if args.custom else 'mobilefacenet.vcd')
PREFIX='tb_task_queue.dut.' if args.queue_dir else 'tb_custom_wave.dut.' if args.custom else 'tb_mobilefacenet.dut.'
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
    return events[signals[PREFIX + name]]


def decode(value, name=""):
    if "x" in value.lower() or "z" in value.lower():
        return "X"
    number = int(value, 2)
    signed_widths = {"av[7:0]":8, "wv[7:0]":8, "out_value[7:0]":8, "normal_result[31:0]":32}
    bits = signed_widths.get(name)
    if bits and number >= (1 << (bits-1)):
        number -= 1 << bits
    return str(number)


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
        if name=='regs.done_sticky':display_name='STATUS.DONE'
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
            known=decode(val,name)!="X"
            col=color if known else "#a3aab8"
            if is_bus:
                inset=min(4,(b-a)/3)
                draw.line([(a,(high+low)/2),(a+inset,high),(b-inset,high),(b,(high+low)/2),
                           (b-inset,low),(a+inset,low),(a,(high+low)/2)], fill=col,width=2)
                text=decode(val,name)
                if b-a > draw.textlength(text,font=font(17))+12:
                    draw.text(((a+b)/2,(high+low)/2),text,font=font(17),anchor="mm",fill=col)
            else:
                yy=high if val=="1" else low
                if last_y is not None and yy!=last_y:
                    draw.line((a,last_y,a,yy),fill=col,width=2)
                draw.line((a,yy,b,yy),fill=col,width=2)
                last_y=yy
        final=next(v for t,v in reversed(data) if t<=end)
        draw.text((1495,y+22),decode(final,name),font=font(20),anchor="mm",fill=color)
    draw.text((50,height-65),note,font=font(18),fill="#53637b")
    path=OUTPUT_DIR/filename
    im.save(path)
    print(path)


first_done = next(t for t,v in series("done") if v=="1")
first_sample = next(t for t,v in series("sv") if v=="1")
first_output = next(t for t,v in series("out_we") if v=="1")
if args.custom or args.queue_dir:
    case=json.loads((OUTPUT_DIR/'case_used.json').read_text(encoding='utf-8'))
    plot("wave_mac_detail.png", "自己改输入：第一层9次乘加与量化输出" if args.queue_dir else "自己改输入：9次乘加与最终输出",
         f"真实 VCD · 单通道3×3卷积 · Bias={case['bias']} · quant_shift={case['quant_shift']} · 总线显示有符号十进制",
         [("clk",False),("sv",False),("tap[5:0]",True),("av[7:0]",True),("wv[7:0]",True),
          ("normal_result[31:0]",True),("out_we",False),("out_value[7:0]",True)],
         max(0,first_sample-15),first_output+30,10,
         "对照 comparison.md：每个 sv 有效的时钟上升沿做一次乘加；该沿之后观察累加值；out_we 后观察输出。")
    if args.queue_dir:
        plot('wave_overview.png','自己改输入：一次START自动执行3条任务',
             '真实 VCD · 3×3 Conv → 1×1 Conv生成128维 → FINAL写回 · 表中任务编号从0开始',
             [('start',False),('core_busy',False),('queue_state[3:0]',True),
              ('queue_fetched[31:0]',True),('queue_completed[31:0]',True),('exec_start',False),
              ('out_value[7:0]',True),('regs.done_sticky',False)],
             0,END_NS,max(10,int(END_NS/8)//10*10),
             '每层具体输出时间见 comparison.md；全部任务完成后STATUS.DONE保持1，queue_completed=3。')
        raise SystemExit(0)
    plot("wave_overview.png", "自己改输入：一次完整的加速器任务",
         "MMIO配置 → START → 读取输入/权重/Bias → 9次乘加 → 量化 → RAM写回 → DONE",
         [("start",False),("core_busy",False),("mem_read",False),("mem_write",False),
          ("sv",False),("done",False),("mmio_rdata[31:0]",True),("out_value[7:0]",True)],
         0,END_NS,200,"此实验只启动一次，没有故意制造 ERROR；结束时 STATUS=2，RAM[0x401] 应等于预期 INT8 输出。")
    raise SystemExit(0)
plot("wave_overview.png", "MobileFaceNet 算子加速器：普通卷积测试",
     "真实 VCD · 输入宽5×高4×2通道 → 3×3卷积 → 输出60字节 · 此图截取第一次任务",
     [("start",False),("core_busy",False),("mem_read",False),("mem_write",False),
      ("sv",False),("done",False),("oc[15:0]",True),("out_value[7:0]",True)],
     0,first_done+40,10000,"sv 为卷积采样有效信号；密集跳变需放大查看。首任务故意重复 START，测试忙时保护。")
plot("wave_mac_detail.png", "放大观察：第一个输出点的累加与量化",
     "真实 VCD · av / wv / normal_result / out_value 按有符号十进制显示 · padding 输入为0",
     [("sv",False),("tap[5:0]",True),("av[7:0]",True),("wv[7:0]",True),
      ("normal_result[31:0]",True),("out_we",False),("out_value[7:0]",True)],
     max(0,first_sample-30),first_output+50,200,"sv=1 时接收样本；normal_result 累加；out_we 时锁存右移2位并饱和后的 INT8 输出。")


