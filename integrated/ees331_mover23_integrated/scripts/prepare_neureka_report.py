"""Package measured (never estimated) benchmark data and an event waveform."""
from pathlib import Path
import argparse,json,csv,shutil,html,hashlib,re
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('neureka',type=Path);a=p.parse_args()
out=ROOT/'deliverables/neureka_benchmark';out.mkdir(parents=True,exist_ok=True)
results=[]
for name,run in [('baseline',a.baseline),('neureka',a.neureka)]:
    record=json.loads((run/'result.json').read_text());assert record['status']=='PASS'
    workload=json.loads((run/name/'workload.json').read_text())
    results.append((record['tests'][name],workload))
    dest=out/name;dest.mkdir(exist_ok=True)
    for f in ['sim.log','events.csv','workload.json','program.asm','bench_config.hex']:
        shutil.copyfile(run/name/f,dest/f)
    shutil.copyfile(run/'result.json',dest/'result.json')
    compiled=run
    if 'reused_binary_from' in record:
        compiled=ROOT/'build/runs'/Path(record['reused_binary_from']).name
    shutil.copyfile(compiled/name/'compile.log',dest/'compile.log')
    hashes={f:hashlib.sha256((run/name/f).read_bytes()).hexdigest()
            for f in ['memory.bin','golden.hex','program.hex','bench_config.hex','simulator']}
    (dest/'fixture_hashes.json').write_text(json.dumps(hashes,indent=2))
b,bw=results[0];n,nw=results[1]
assert [bw[k] for k in ('size','ci','co','seed','shift','sram_bytes')]==[nw[k] for k in ('size','ci','co','seed','shift','sram_bytes')]
assert (a.baseline/'baseline/golden.hex').read_text()==(a.neureka/'neureka/golden.hex').read_text()
speed=b['cnn_cycles']/n['cnn_cycles'];conv_speed=b['stages']['original_conv']/n['stages']['NEureka_conv']
memory=(a.baseline/'baseline/memory.bin').read_bytes()
descriptor=bw['descriptors'][0];input_address=descriptor[1];weight_address=descriptor[3]
size=bw['size'];ci=bw['ci'];co=bw['co'];oh=size-2
signed=lambda v:v if v<128 else v-256
contributions=[]
for channel in range(ci):
    contributions.append(sum(memory[input_address+(channel*size+y)*size+x]*
        signed(memory[weight_address+channel*9+y*3+x]) for y in range(3) for x in range(3)))
golden=[signed(int(line,16)) for line in (a.baseline/'baseline/golden.hex').read_text().splitlines()]
acc=sum(contributions);quantized=max(-128,min(127,acc>>bw['shift']))
assert quantized==golden[0]
first_four=[golden[i] for i in [0,1,oh,oh+1]]
first_pool=max(0,*first_four)
assert first_pool==golden[oh*oh*co*2]
summary=dict(baseline=b,neureka=n,total_speedup=speed,convolution_speedup=conv_speed,
             baseline_run=str(a.baseline),neureka_run=str(a.neureka))
(out/'comparison.json').write_text(json.dumps(summary,indent=2))
rows=[('卷积',b['stages']['original_conv'],n['stages']['NEureka_conv']),
      ('输入/输出排布转换',0,n['stages']['CHW_to_HWC']+n['stages']['HWC_to_CHW']),
      ('ReLU',b['stages']['ReLU'],n['stages']['ReLU']),('2×2 最大池化',b['stages']['MaxPool2x2'],n['stages']['MaxPool2x2']),
      ('总计（含队列控制）',b['cnn_cycles'],n['cnn_cycles'])]
table='\n'.join(f'| {label} | {old:,} | {new:,} | {old/1e5:.3f} / {new/1e5:.3f} |' for label,old,new in rows)
text=f'''# NEureka 适配与大图实测

同一张 {bw['size']}×{bw['size']} RGB 测试图，3×3 valid 卷积（{bw['ci']}→{bw['co']} 通道）→右移量化→ReLU→2×2/stride2 最大池化。

**整体加速 {speed:.3f} 倍；卷积任务本身加速 {conv_speed:.3f} 倍。**

| 阶段 | 原 CNN 周期 | NEureka 版周期 | 原版 / 新版时间（ms） |
|---|---:|---:|---:|
{table}

时间按同一 100 MHz 仿真时钟换算。整体减少 {(1-n['cnn_cycles']/b['cnn_cycles'])*100:.2f}% 的周期。

两版都逐字节核对卷积、ReLU、池化输出，共 {b['checked_bytes']:,} 字节；全部通过。CPU 为项目原有 RV32I CPU，通过真实 MMIO 写入队列地址、任务数并轮询完成。两次格式转换均由硬件执行，其访存与等待时间已经包含在新版总耗时内。

测试图为固定随机种子 {bw['seed']} 的可复现 RGB 像素，统一归一化到 0～127；有正负值的权重仍按 8 bit 计算，累加后算术右移 {bw['shift']} 位并饱和到 [-128,127]。两版逻辑像素、权重、量化及参考结果相同。NEureka 权重在部署时预打包。四 bank SRAM 容量均为 {bw['sram_bytes']//1024//1024} MiB，每 bank 每周期一次访问，读写返回时序相同。

原版是 `mobilefacenet_overlap_top` 中的 8×8 阵列，并非此前的固定 Sobel 电路。新版是官方 NEureka 4×4 PE 配置，288 bit 访存拆到相同 SRAM；后处理继续用原算子。硬件规模不同，没有进行面积或功耗归一化。

## 一个实际数据点

输出通道 0、位置 (0,0) 的各输入通道分别贡献 {contributions}，累加为 {acc}；算术右移 {bw['shift']} 位并饱和后得到 {quantized}，ReLU 后为 {max(0,quantized)}。第一个 2×2 池化窗口的四个卷积结果为 {first_four}，先取 ReLU 再取最大值，最终输出 {first_pool}。两版均通过这些实际字节以及其余所有字节的检查。

`input_rgb.png` 是输入测试图；`pool_features.png` 展示全部输出通道。为了便于观察，图片显示时把非负数值乘以 2，计算和校验的数值保持原样。这是性能验证用的随机图像和随机权重，图中各通道没有“眼睛/鼻子”等训练语义。

## 结果适用范围

这是输入已驻留 SRAM 的算子性能。UART 传图时间、权重首次下载时间不在计时内；不能把这个倍数直接当作 UART 整图输入到人脸识别完成的倍数。没有运行完整人脸识别模型，没有工艺综合或真实频率证明。

新队列当前顺序执行，NEureka 内部预取与计算可以重叠。旧 op0/op1/op9 需要改成 NEureka 配置任务，不能直接把旧描述符送入新入口。详细接法和支持范围见项目 `docs/neureka_integration.md`。

## 怎么看交付文件

- `comparison.png`：实测各阶段耗时对比。
- `baseline/result.json`、`neureka/result.json`：周期、访存次数、实际编译源文件哈希。
- `*/sim.log`：逐项核对的 PASS 和真实周期。
- `*/events.csv`：各任务开始、结束周期。
- `stages.vcd`：由上述实测事件生成的任务阶段时间线，可用 GTKWave 打开；它不是每根数据总线的逐拍转储。
- `open_stages.cmd`：打开大图阶段时间线。两次独立仿真均对齐到 CPU 启动时刻，图中两版并列显示，不代表同时运行两个 CNN。
- `small_wave/open_all.cmd`、`small_wave/open_first_write.cmd`：最终 RTL 的小图逐拍接口波形；输入尺寸与大图不同，用于观察接口。
- `small_wave/波形阅读说明.md`：信号方向、握手、状态和首次卷积写回的实际时间。
- `neureka_architecture.drawio`：可编辑六模块总图与 CNN 内部图。
- `comparison.json`：便于继续分析的汇总数据。

原始运行目录：

- 原版：`{a.baseline}`
- 新版：`{a.neureka}`
'''
(out/'实测报告.md').write_text(text,encoding='utf-8')
fontpath=Path('C:/Windows/Fonts/msyh.ttc');font=lambda s:ImageFont.truetype(str(fontpath),s)
im=Image.new('RGB',(1600,780),'#f5f7fb');d=ImageDraw.Draw(im)
d.text((60,35),'NEureka：相同卷积 + ReLU + 池化任务',font=font(38),fill='#17283f')
d.text((60,95),f'{bw["size"]}×{bw["size"]} RGB · 100 MHz · 4 bank SRAM · 全部输出逐字节校验通过',font=font(23),fill='#526174')
colors=['#346fc4','#8d69c4','#32a58b','#e9ad43','#99a4b5']
limit=max(b['cnn_cycles'],n['cnn_cycles']);plotx=255;plotw=1260
for j,(label,m) in enumerate([('原 CNN',b),('NEureka',n)]):
    y=210+j*185;d.text((60,y+20),label,font=font(28),fill='#17283f');x=plotx
    vals=[m['stages'].get('original_conv',m['stages'].get('NEureka_conv',0)),
          m['stages'].get('CHW_to_HWC',0)+m['stages'].get('HWC_to_CHW',0),m['stages']['ReLU'],m['stages']['MaxPool2x2']]
    vals.append(m['cnn_cycles']-sum(vals))
    for v,c in zip(vals,colors):
        width=plotw*v/limit
        if v:d.rectangle((x,y,x+max(width,1),y+65),fill=c)
        if width>100:d.text((x+10,y+20),f'{v/1e5:.2f} ms',font=font(20),fill='white')
        x+=width
    d.text((plotx,y+80),f'总计 {m["cnn_cycles"]:,} 周期 / {m["cnn_cycles"]/1e5:.3f} ms',font=font(23),fill='#334155')
for i,(label,c) in enumerate(zip(['卷积','格式转换','ReLU','池化','队列控制'],colors)):
    x=60+i*290;d.rectangle((x,605,x+22,627),fill=c);d.text((x+34,600),label,font=font(22),fill='#334155')
d.text((60,690),f'整体加速 {speed:.3f}×；卷积加速 {conv_speed:.3f}×。不含 UART 传图。',font=font(29),fill='#17283f')
im.save(out/'comparison.png')
if ci==3:
    rgb=bytes(memory[input_address+c*size*size+p]*2 for p in range(size*size) for c in range(3))
    Image.frombytes('RGB',(size,size),rgb).save(out/'input_rgb.png')
pooled=golden[2*oh*oh*co:];side=oh//2;tile=256;columns=min(4,co);row_count=(co+columns-1)//columns
features=Image.new('RGB',(columns*(tile+24)+24,row_count*(tile+65)+24),'#f5f7fb');fd=ImageDraw.Draw(features)
for c in range(co):
    x=24+c%columns*(tile+24);y=24+c//columns*(tile+65)
    fd.text((x,y),f'Channel {c}',font=font(20),fill='#17283f')
    plane=Image.frombytes('L',(side,side),bytes(max(0,v)*2 for v in pooled[c*side*side:(c+1)*side*side]))
    features.paste(plane.resize((tile,tile),Image.Resampling.NEAREST),(x,y+32))
features.save(out/'pool_features.png')
# Actual task event timeline: one bit per task, no invented bus values.
v=['$timescale 1ns $end','$scope module measured_tasks $end'];changes=[];ids=[]
for ver,run in [('baseline',a.baseline),('neureka',a.neureka)]:
    names=json.loads((run/ver/'workload.json').read_text())['tasks']
    codes={i:f's{len(ids)+i}' for i in range(len(names))}
    for i,name in enumerate(names):v.append(f'$var wire 1 {codes[i]} {ver}_{name} $end')
    ids.extend(codes.values())
    events=list(csv.DictReader((run/ver/'events.csv').open()));start=int(next(e['cycle'] for e in events if e['event']=='start'))
    for e in events:
        if e['event'] in ('dispatch','complete'):changes.append(((int(e['cycle'])-start)*10,'1' if e['event']=='dispatch' else '0',codes[int(e['task'])]))
v+=['$upscope $end','$enddefinitions $end','#0']+[f'0{i}' for i in ids]
for t,value,code in sorted(changes):v += [f'#{t}',value+code]
(out/'stages.vcd').write_text('\n'.join(v)+'\n')
session=['[*] Measured event timeline, independent runs aligned to CPU START',
         f'[dumpfile] "{(out/"stages.vcd").as_posix()}"','[size] 1800 700','[pos] 0 0',
         '*-26 -1 '+' '.join(['-1']*26),'[signals_width] 420','[sst_expanded] 0']
for ver,work in [('baseline',bw),('neureka',nw)]:
    for name in work['tasks']:
        color=4 if 'conv' in name else 3 if 'HWC' in name else 2 if name=='ReLU' else 6
        session+=['@28',f'[color] {color}',f'measured_tasks.{ver}_{name}']
(out/'stages.gtkw').write_text('\n'.join(session)+'\n',encoding='ascii')
(out/'open_stages.cmd').write_text('@echo off\r\nsetlocal\r\nset "GTK=%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe"\r\nstart "" "%GTK%" -f "%~dp0stages.vcd" -a "%~dp0stages.gtkw"\r\n',encoding='ascii')
(out/'export_stages.tcl').write_text('set out [file dirname [file normalize [info script]]]\n'
    'gtkwave::/View/Scale_To_Time_Dimension/ms\n'
    f'gtkwave::setZoomRangeTimes 0 {max(b["cnn_cycles"],n["cnn_cycles"])*10}\n'
    'gtkwave::setMarker -1\nupdate\nafter 500\n'
    'gtkwave::/File/Write_Save_File_As [file join $out stages.gtkw]\n'
    'gtkwave::/File/Grab_To_File [file join $out stages.png]\n'
    'gtkwave::/File/Quit\n',encoding='ascii')
def inline(s):
    s=html.escape(s)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
body=[];in_table=False
for line in text.splitlines():
    if not line.strip():continue
    if line.startswith('|'):
        if re.fullmatch(r'[|:\- ]+',line):continue
        tag='td' if in_table else 'th'
        if not in_table:body.append('<table>');in_table=True
        body.append('<tr>'+''.join(f'<{tag}>{inline(c.strip())}</{tag}>' for c in line.strip('|').split('|'))+'</tr>')
        continue
    if in_table:body.append('</table>');in_table=False
    if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
    elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
    elif line.startswith('- '):body.append('<p class="item">• '+inline(line[2:])+'</p>')
    else:body.append('<p>'+inline(line)+'</p>')
if in_table:body.append('</table>')
(out/'实测报告.html').write_text('<!doctype html><meta charset="utf-8"><title>NEureka 实测</title>'
    '<style>body{font:17px/1.8 "Microsoft YaHei",sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#24364d}'
    'img{width:100%}table{border-collapse:collapse;width:100%;font-size:16px}td,th{padding:10px;border-bottom:1px solid #d7e1ed;text-align:right}'
    'td:first-child,th:first-child{text-align:left}th{background:#edf2fa}code{background:#edf2fa;padding:2px 5px;font-size:14px;overflow-wrap:anywhere}'
    'h1{font-size:30px}h2{margin-top:36px;font-size:23px}.item{margin:5px 0}</style><img src="comparison.png">'+''.join(body),encoding='utf-8')
print(out)
