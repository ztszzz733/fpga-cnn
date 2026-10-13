"""Package only a verified real-SoC run, with unique control signals and VCD plots."""
from pathlib import Path
import argparse,bisect,hashlib,json,shutil,xml.etree.ElementTree as ET
from plot_waveforms import read_vcd,segments
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]

def render(vcd_path,config_path,out,*,group,start_ns,end_ns,name,title):
    v=read_vcd(vcd_path);entries=json.loads(config_path.read_text())['groups'][group]
    width=1920;height=180+len(entries)*58
    image=Image.new('RGB',(width,height),'#101821');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',20)
    small=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
    draw.text((25,18),title,fill='white',font=font)
    left,right=280,width-45
    def x(t):return left+(t-start_ns)*(right-left)/(end_ns-start_ns)
    for i in range(9):
        t=start_ns+(end_ns-start_ns)*i/8;xx=x(t)
        draw.line((xx,68,xx,height-83),fill='#273a4d')
        label=f'{t/1000:.3f}';draw.text((min(xx-20,width-100),height-68),label,font=small,fill='#cedcea')
    for i,e in enumerate(entries):
        sig=v.signals[e['path']];y=80+i*58
        color='#6ac5fa' if e['label'].startswith(('cnn','read','nv')) else '#7ae3b1' if e['label'].startswith('vec') else '#ebc86c'
        draw.text((20,y+3),e['label'],font=font,fill=color)
        pieces=list(segments(sig,start_ns,end_ns))
        for j,(a,b,bits) in enumerate(pieces):
            xx,yy=x(a),x(b);val=int(bits,2)
            if sig.width==1:
                h=y+30-val*24;draw.line((xx,h,yy,h),fill=color,width=2)
                if j:draw.line((xx,y+6,xx,y+30),fill=color,width=2)
            else:
                draw.line((xx,y+4,yy,y+4),fill=color,width=1);draw.line((xx,y+31,yy,y+31),fill=color,width=1)
                draw.line((xx,y+4,xx,y+31),fill=color)
                label=f'{val:X}' if e['label'] in ('status','vec_addr','vec_wdata','cnn_valid','cnn_ready','cnn_response','cnn_write') else str(val)
                if yy-xx>draw.textlength(label,font=small)+10:draw.text((xx+4,y+6),label,font=small,fill=color)
    draw.text((left,height-33),'Time (us) at 100 MHz | real RTL VCD | CNN masks: bit0 NV read, bit1 NV write, bit2 Vicuna',font=small,fill='#cedcea')
    image.save(out/(name+'.png'))

def diagram(out):
    mx=ET.Element('mxfile',host='app.diagrams.net')
    d=ET.SubElement(mx,'diagram',name='NVDLA + Vicuna SoC')
    m=ET.SubElement(d,'mxGraphModel',page='1',pageWidth='1700',pageHeight='1250',background='#111111')
    r=ET.SubElement(m,'root');ET.SubElement(r,'mxCell',id='0');ET.SubElement(r,'mxCell',id='1',parent='0')
    def box(i,title,x,y,w,h,parent='1',stroke='#dddddd'):
        c=ET.SubElement(r,'mxCell',id=i,value=title,vertex='1',parent=parent,
            style=f'whiteSpace=wrap;html=1;fillColor=#111111;strokeColor={stroke};fontColor=#ffffff;fontSize=18;')
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
    def edge(i,a,b,label,color,style=''):
        c=ET.SubElement(r,'mxCell',id=i,value=label,edge='1',parent='1',source=a,target=b,
            style=f'edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;strokeColor={color};fontColor=#ffffff;fontSize=16;labelBackgroundColor=#111111;{style}')
        ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
    box('cpu','CPU CORE<br>RV32I firmware',70,140,350,300)
    box('imem','IMEM<br>Main CPU ROM',650,140,210,200)
    box('cnn','CNN<br><br><br><br><br><br><br><br><br><br><br><br><br><br><br>',70,630,420,490)
    box('cmd','Command registers',25,60,370,55,'cnn','#ff6db4')
    box('nv','NVDLA<br>Conv / SDP / PDP',25,155,160,150,'cnn','#e8d86a')
    box('vec','CV32E40X<br>+ Vicuna 2<br>+ program RAM',210,155,185,150,'cnn','#57c5a8')
    box('mem','DATASRAM<br>4 banks<br>arbitration inside',780,460,230,660)
    box('io','IMAGE_BRIDGE<br>UART autoload',1280,490,270,230)
    box('clock','CLOCK<br>clock / reset',1280,940,270,140)
    edge('e1','cpu','imem','imem_addr /32, imem_re /1','#4b9bff','exitX=1;exitY=.15;entryX=0;entryY=.2;')
    edge('e2','imem','cpu','imem_rdata /32','#e8d86a','exitX=0;exitY=.7;entryX=1;entryY=.55;')
    edge('e3','cpu','cnn','mmio_addr /32, wdata /32, re/we /2','#ff6db4','exitX=.2;exitY=1;entryX=.2;entryY=0;')
    edge('e4','cnn','cpu','mmio_rdata /32, ready /1','#e8d86a','exitX=.8;exitY=0;entryX=.8;entryY=1;')
    edge('e5','cpu','mem','dmem_addr /32, wdata /32, re/we/wstrb /6','#4b9bff','exitX=1;exitY=.85;entryX=0;entryY=.1;')
    edge('e6','mem','cpu','dmem_rdata /32','#e8d86a','exitX=0;exitY=.25;entryX=1;entryY=1;')
    edge('e7','cnn','mem','cnn_valid/write/byte /11 each<br>cnn_addr/wdata /352 each<br>cnn_cancel /1','#57c5a8','exitX=1;exitY=.4;entryX=0;entryY=.5;')
    edge('e8','mem','cnn','cnn_ready/response /11 each<br>cnn_rdata /352, mem_fault /1','#e8d86a','exitX=0;exitY=.85;entryX=1;entryY=.85;')
    edge('e9','io','mem','io_mem_req/we/be /6<br>addr/wdata /32 each','#ff6db4','exitX=0;exitY=.2;entryX=1;entryY=.15;')
    edge('e10','mem','io','io_mem_gnt/rvalid/error /3<br>rdata /32','#e8d86a','exitX=1;exitY=.4;entryX=0;entryY=.8;')
    edge('e11','cpu','io','load_req /1','#ff6db4','exitX=.9;exitY=0;entryX=.2;entryY=0;')
    edge('e12','io','cpu','load_complete/error /2','#ff6db4','exitX=.8;exitY=0;entryX=.4;entryY=0;')
    box('notes','External: sys_clk, rst_n_in, uart_rx → SoC; uart_tx, led_ready/busy/error ← SoC.<br>CLOCK distributes clk/rst_n to all five blocks (shared nets omitted for clarity).<br>SRAM clients: 0=NVDLA read, 1=NVDLA write, 2=Vicuna data, 3..10 inactive.<br>This regression preloads SRAM; UART remains idle.',550,1140,1050,100,stroke='#555555')
    ET.indent(mx);ET.ElementTree(mx).write(out/'architecture.drawio',encoding='utf-8',xml_declaration=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);args=ap.parse_args()
    src=args.run.resolve();result=json.loads((src/'result.json').read_text());assert result['status']=='PASS'
    out=ROOT/'deliverables/hybrid_soc';out.mkdir(exist_ok=True)
    shutil.copyfile(src/'result.json',out/'result.json');evidence={};rows=[]
    for test in result['tests']:
        name=test['name'];a=src/name;b=out/name;b.mkdir(exist_ok=True)
        for f in a.iterdir():
            if f.is_file():shutil.copyfile(f,b/f.name)
        v=read_vcd(b/'control.vcd');signals=list(v.signals.values());assert len(signals)==39
        assert len({s.code for s in signals})==39
        groups={
            'overview':['phase','nv_irq','vec_busy','vec_done','vec_jobs','vec_stalls','fault','status'],
            'memory':['phase','nv_irq','vec_busy','cnn_valid','cnn_ready','cnn_response','cnn_write','vec_state','vec_addr','vec_wdata','vec_reads','vec_writes']}
        cfg={'groups':{g:[{'path':'hybrid_soc.'+s,'label':s} for s in ns] for g,ns in groups.items()}}
        (b/'plot_signals.json').write_text(json.dumps(cfg))
        render(b/'control.vcd',b/'plot_signals.json',b,group='overview',start_ns=0,end_ns=v.end_ns,name='overview',title=name+' | real CPU + NVDLA + Vicuna')
        def at(name,t):
            e=v.signals['hybrid_soc.'+name].events;i=bisect.bisect_right([x[0] for x in e],t)-1
            return int(e[i][1],2) if i>=0 else 0
        def find_write():
            for t,bits in v.signals['hybrid_soc.cnn_valid'].events:
                if int(bits,2)&4 and at('cnn_write',t)&4 and at('phase',t)==5:return t
            raise ValueError('missing vector chain write')
        t=find_write();left=max(0,t-80);right=min(v.end_ns,t+250)
        render(b/'control.vcd',b/'plot_signals.json',b,group='memory',start_ns=left,end_ns=right,name='first_vector_write',title=name+' | first chained vector write')
        render(b/'control.vcd',b/'plot_signals.json',b,group='overview',start_ns=max(0,v.end_ns-1800),end_ns=v.end_ns,name='completion',title=name+' | CPU completion and vector job count')
        if name=='pool_parallel':
            overlap=next(t for t,bits in v.signals['hybrid_soc.cnn_valid'].events if int(bits,2)&4 and int(bits,2)&3)
            render(b/'control.vcd',b/'plot_signals.json',b,group='memory',start_ns=max(0,overlap-80),end_ns=min(v.end_ns,overlap+400),name='concurrent_memory',title='NVDLA + Vicuna | overlapping shared SRAM requests')
        lines=['[*] Real integrated SoC RTL; unique control signals',f'[dumpfile] "{(b/"control.vcd").as_posix()}"','[size] 1700 1000','[signals_width] 280','*-18 -1 '+ ' '.join(['-1']*26)]
        for i,s in enumerate(signals):
            lines += ['@28' if s.width==1 else '@22',f'[color] {6 if i<11 else 3 if i<21 else 4}',s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
        (b/'control.gtkw').write_text('\n'.join(lines)+'\n')
        (b/'open_wave.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"..\\..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" "control.vcd" "control.gtkw"\r\n')
        evidence[name]={'vcd_sha256':hashlib.sha256((b/'control.vcd').read_bytes()).hexdigest(),'displayed_signals':39,'first_chained_vector_write_ns':t}
        rows.append(f"| {name} | PASS | {test['simulation_seconds']:.3f} | {test['hardware_ns_at_100MHz']/1000:.2f} | {test['vector_jobs']} |")
    diagram(out)
    (out/'wave_evidence.json').write_text(json.dumps(evidence,indent=2))
    original=json.loads((ROOT/'build/runs/20261013_210250_hybrid_soc/result.json').read_text())
    total=sum(t['simulation_seconds'] for t in result['tests'])
    text=f'''# NVDLA＋Vicuna 2 真实 SoC 小测试

**本轮 3/3 PASS。** 来源：`{src.relative_to(ROOT).as_posix()}`。
原 RV32I CPU 实际运行固件，配置 NVDLA、装入并启动 Vicuna 程序；两套真实 RTL 通过共享 DATASRAM 交换数据。
顶层仍为六大模块，CNN 内包含 NVDLA 和 CV32E40X＋Vicuna 2。

| 用例 | 结果 | 电脑仿真耗时/秒 | 100 MHz 假设下硬件时间/μs | Vicuna 任务数 |
|---|---|---:|---:|---:|
{chr(10).join(rows)}

本轮三个仿真进程合计 **{total:.3f} 秒**。本轮复用模型，编译为 {result['compile_seconds']:.2f} 秒。
首次联合模型编译 {original['compile_seconds']:.2f} 秒，另有展开检查；不包括固件编译、排错和文档生成。
硬件时间包含 CPU 程序装载、配置、轮询与计算，不能当作单算子耗时，也不代表上板频率已经验证。

## 做了什么

- `tiny_chain`：NVDLA 最小卷积 → SRAM → Vicuna INT8 PReLU，检查部分字节写入和再次启动。
- `conv_chain`：NVDLA 6×8、192 输入通道、32 输出通道的 3×3 卷积＋SDP → SRAM → Vicuna INT8 PReLU。
- `pool_parallel`：NVDLA 8×8×64 的 2×2 池化，与 Vicuna 的 256 元素 FP32 PReLU 并发；之后串联处理池化写回区并重复启动。

NVDLA 三项输出各自匹配官方 CRC32；Vicuna 输出逐字节比对，末尾保护字节保持不变。
并发场景统计见 `pool_parallel/metrics.json`：`both_request_cycles` 是双方同周期发存储请求的周期数，`vector_stall_cycles` 是 Vicuna 被仲裁暂缓的周期数。它们不是 PE 利用率或加速比。

**输入采用 SRAM 预加载，UART 本轮保持空闲；没有运行大图或完整人脸识别网络。**

## 需要明确的限制

集成配置下发现 FP32 PReLU 的“先比较、后乘法”指令顺序存在结果错误；本轮改为等价的“先乘法、后比较、再选择”并重新验证。根因尚未彻底定位，不能据此宣称任意向量程序都正确。
失败记录保留在 `build/runs/20261013_210250_hybrid_soc`，软件顺序诊断见 `build/runs/20261013_211032_hybrid_fp32_diagnostic`。
这与此前独立九项小测试的范围不同；新的共享存储时序暴露了额外限制。

## 看波形

双击各目录 `open_wave.cmd`。会话共 39 根不重复控制/数据观察信号，按 CPU、配置、NVDLA、Vicuna、共享内存排列并配色。
每项有 `overview.png` 全程图和 `first_vector_write.png` 首次串联写回放大图，均来自本轮真实 VCD。
`completion.png` 放大最终完成；`pool_parallel/concurrent_memory.png` 显示两套引擎同时请求 SRAM。
横轴为 ns，按 100 MHz 时钟实际推进模拟时间，同时保留官方 RAM 延迟。

| 信号 | 来源 → 去向 / 作用 |
|---|---|
| cpu_pc | 主 IMEM 取指地址，证明 CPU 在执行程序 |
| mmio_addr/wdata/re/we | 主 CPU → CNN 零等待命令寄存器 |
| mmio_rdata/ready | CNN → 主 CPU；ready 恒为 1，目标执行完成要看 cmd_done/软件 STATUS |
| cmd_busy/done/error | CNN 内部配置命令事务的状态；与算子任务完成不同 |
| config_state | NVDLA CSB 配置适配器状态 |
| nv_irq | NVDLA → CNN：未屏蔽任务完成标志，CPU 软件轮询原生完成状态 |
| read_state/write_state/read_beats/write_beats | NVDLA 存储桥状态及累计传输拍数 |
| vec_busy/done/jobs/code | Vicuna 任务活动、完成、累计任务数和结果码；busy 不等于每周期都运算 |
| vec_pending | 向量寄存器待写位图，不是 PE 忙闲位图 |
| vec_state | Vicuna 存储桥：0 空闲、1 请求 SRAM、2 等应答、3 返回内部核 |
| cnn_valid/ready/response/write | CNN ↔ SRAM，bit0=NVDLA 读，bit1=NVDLA 写，bit2=Vicuna |
| vec_addr/wdata/rdata | Vicuna 存储桥 ↔ DATASRAM：实际数据地址/写数据/返回数据 |
| vec_reads/writes/stalls | Vicuna 桥已完成 SRAM 读/写次数与等待仲裁周期数 |
| fault | CNN 故障状态，正常测试保持 0 |
| phase/status | CPU 写 SRAM 的测试观察字，非新增板级端口；phase=1 装程序、2 配置、3 等 NVDLA、4 等并发 Vicuna、5 串联、6 再次启动、7 结束 |
| uart_tx/load_req | UART 输出和 CPU 装载请求，本轮均无传输 |

当 `cnn_valid[2] && cnn_ready[2] && cnn_write[2]` 为 1 时，SRAM 接受 Vicuna 写回；随后 `cnn_response[2]` 为 1 表示完成。
串联输出从 0x18000 起，再次启动输出从 0x1A000 起；并发 FP32 输出在 0x31000。
软件任务选择及寄存器说明见 [接口文档](../../docs/hybrid_soc_integration.md)，结构图为 [可编辑 draw.io 文件](architecture.drawio)。
'''
    (out/'README.md').write_text(text,encoding='utf-8')
    print(out)
if __name__=='__main__':main()
