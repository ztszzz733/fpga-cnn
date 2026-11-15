"""Plot only documented SoC wires from the previously completed autoload VCD."""
from pathlib import Path
import argparse
import bisect
import csv
import hashlib
import json
import re

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.patches import Polygon
from plot_waveforms import read_vcd, segments

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT/'build/runs/20261008_230704_371733_autoload_integration'
GROUPS = {
    '外部IO': 'sys_clk rst_n_in uart_rx uart_tx led_ready led_busy led_error'.split(),
    '公共时钟复位': 'clk rst_n'.split(),
    'CPU与IMEM': 'imem_addr imem_re imem_rdata'.split(),
    'CPU与SRAM': 'dmem_addr dmem_wdata dmem_re dmem_we dmem_wstrb dmem_rdata'.split(),
    'CPU与CNN': 'cnn_mmio_addr cnn_mmio_wdata cnn_mmio_re cnn_mmio_we cnn_mmio_rdata cnn_mmio_ready'.split(),
    'CNN与SRAM': 'mem_addr mem_wdata mem_read mem_write mem_rdata mem_ready'.split(),
    '图像桥与SRAM': 'io_mem_addr io_mem_wdata io_mem_req io_mem_we io_mem_be io_mem_rdata io_mem_gnt io_mem_rvalid io_mem_error'.split(),
    '新增三线': 'load_req load_complete load_error'.split(),
    '原说明状态线': 'cnn_mem_fault bridge_ready bridge_busy bridge_error'.split(),
}
ALLOWED = {s for group in GROUPS.values() for s in group}
LABELS = {
    'clk':'公共时钟', 'rst_n_in':'外部复位', 'rst_n':'内部复位',
    'uart_tx':'桥 → 外部设备', 'uart_rx':'外部设备 → 桥',
    'load_req':'CPU → 桥：请求', 'load_complete':'桥 → CPU：结束', 'load_error':'桥 → CPU：错误',
    'io_mem_req':'桥：写入请求', 'io_mem_we':'桥：写方向', 'io_mem_gnt':'SRAM：接收确认',
    'io_mem_addr':'桥 → SRAM：对齐地址', 'io_mem_wdata':'桥 → SRAM：数据',
    'io_mem_be':'桥 → SRAM：字节选择', 'io_mem_error':'SRAM → 桥：错误',
    'imem_re':'CPU：取指使能', 'imem_addr':'CPU → IMEM：地址', 'imem_rdata':'IMEM → CPU：指令',
    'cnn_mmio_we':'CPU：写CNN寄存器', 'cnn_mmio_re':'CPU：读CNN寄存器',
    'cnn_mmio_ready':'CNN：访问完成', 'cnn_mmio_addr':'CPU → CNN：寄存器地址',
    'cnn_mmio_wdata':'CPU → CNN：写数据', 'cnn_mmio_rdata':'CNN → CPU：读数据',
    'mem_read':'CNN：读SRAM', 'mem_write':'CNN：写SRAM', 'mem_ready':'SRAM：访问完成',
    'mem_addr':'CNN → SRAM：对齐地址', 'mem_wdata':'CNN → SRAM：写数据',
    'mem_rdata':'SRAM → CNN：读数据', 'dmem_re':'CPU：读SRAM', 'dmem_we':'CPU：写SRAM',
    'dmem_addr':'CPU → SRAM：地址', 'dmem_wdata':'CPU → SRAM：写数据',
    'dmem_rdata':'SRAM → CPU：读数据', 'dmem_wstrb':'CPU：字节选择',
}


def filtered_vcd(source, target):
    text = source.read_text(encoding='utf-8')
    header, body = text.split('$enddefinitions $end', 1)
    assert re.search(r'\$timescale\s+1ps\s+\$end', header)
    scope = []; found = {}
    for directive, value in re.findall(r'\$(\w+)\s+(.*?)\s*\$end',header,re.S):
        words=value.split()
        if directive=='scope': scope.append(words[1])
        elif directive=='upscope': scope.pop()
        elif directive=='var' and scope==['tb_soc_autoload','dut'] and words[3] in ALLOWED:
            found[words[3]]=(int(words[1]),words[2])
    assert set(found)==ALLOWED, ALLOWED-set(found)
    assert all(width>0 for width,code in found.values())
    codes={code for width,code in found.values()}
    lines=['$comment Only documented SoC wires; original timestamps and values preserved. $end',
           '$timescale 1ps $end','$scope module soc_wires $end']
    for name,(width,code) in found.items():
        lines.append(f'$var wire {width} {code} {name}'+(f' [{width-1}:0]' if width>1 else '')+' $end')
    lines += ['$upscope $end','$enddefinitions $end']
    for raw in body.splitlines():
        line=raw.strip()
        if not line: continue
        if line.startswith('#') or line in ('$dumpvars','$dumpall','$dumpon','$dumpoff','$end'):
            lines.append(line)
        elif line[0] in '01xzXZ' and line[1:] in codes: lines.append(line)
        elif line[0] in 'bB' and line.split()[1] in codes: lines.append(line)
    target.write_text('\n'.join(lines)+'\n',encoding='ascii')
    return found


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-root',type=Path,default=DEFAULT_RUN)
    ap.add_argument('--out-dir',type=Path,default=ROOT/'docs/figures/soc_autoload_flow')
    args=ap.parse_args(); run=args.run_root.resolve(); out=args.out_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    result=json.loads((run/'result.json').read_text(encoding='utf-8'))
    assert result['tests']['power_on_success']=='PASS'
    source=run/'power_on_success.vcd'
    found=filtered_vcd(source,out/'soc_wires_only.vcd')
    vcd=read_vcd(out/'soc_wires_only.vcd')
    signals={n:vcd.signals['soc_wires.'+n] for n in found}
    times={n:[t for t,b in s.events] for n,s in signals.items()}

    def at(name,t,before=False):
        i=(bisect.bisect_left(times[name],t) if before else bisect.bisect_right(times[name],t))-1
        if i<0:return None
        bits=signals[name].events[i][1]
        return int(bits,2) if set(bits)<={'0','1'} else None

    edges=[t for t,b in signals['clk'].events if b=='1']
    transactions=[]
    for t in edges:
        pre=lambda n:at(n,t,True)
        if pre('rst_n')!=1:continue
        if pre('io_mem_req')==pre('io_mem_gnt')==1:
            transactions.append(dict(time_ns=t,interface='io_write',address=pre('io_mem_addr'),
                                     data=pre('io_mem_wdata'),be=pre('io_mem_be'),error=pre('io_mem_error')))
        if pre('cnn_mmio_ready')==1:
            for en,kind,data in [('cnn_mmio_we','mmio_write','cnn_mmio_wdata'),('cnn_mmio_re','mmio_read','cnn_mmio_rdata')]:
                if pre(en)==1:transactions.append(dict(time_ns=t,interface=kind,address=pre('cnn_mmio_addr'),data=pre(data)))
        if pre('mem_ready')==1:
            for en,kind,data in [('mem_read','cnn_read','mem_rdata'),('mem_write','cnn_write','mem_wdata')]:
                if pre(en)==1:transactions.append(dict(time_ns=t,interface=kind,address=pre('mem_addr'),data=pre(data)))
        if pre('dmem_we')==1:
            transactions.append(dict(time_ns=t,interface='cpu_write',address=pre('dmem_addr'),data=pre('dmem_wdata'),be=pre('dmem_wstrb')))
        if pre('dmem_re')==1:
            # A port returns the sampled address's data just after this edge.
            transactions.append(dict(time_ns=t,interface='cpu_read',address=pre('dmem_addr'),data=at('dmem_rdata',t)))

    kind=lambda k:[r for r in transactions if r['interface']==k]
    io=kind('io_write'); cw=kind('cnn_write'); cr=kind('cnn_read'); mw=kind('mmio_write')
    cpu_reads=kind('cpu_read'); finish=[r for r in kind('cpu_write') if r['address']==0x88 and r['data']==0x600d]
    assert len(io)==256 and len(cw)==4 and len(mw)==3 and len(finish)==1
    assert [r['data'] for r in cpu_reads if r['address'] in (0x140,0x144)]==[0x09ff05a5,0xa5a5a50b]
    assert [(r['address'],r['data']) for r in mw]==[(0x40000008,0x1e0),(0x40000018,1),(0x40000000,0x3d)]
    assert all(r['error']==0 for r in io)
    assert [r['address'] for r in cr[:8]]==list(range(0x1e0,0x200,4))
    rise=lambda n:next(t for t,b in signals[n].events if b=='1')
    after_fall=lambda n,t:next(s for s,b in signals[n].events if s>t and b=='0')
    load_start=rise('load_req'); complete=rise('load_complete')
    req_down=after_fall('load_req',complete); complete_down=after_fall('load_complete',complete)
    assert io[-1]['time_ns']<=complete<req_down<complete_down<mw[-1]['time_ns']
    milestones={'rst_n_in_rise_ns':rise('rst_n_in'),'rst_n_rise_ns':rise('rst_n'),
        'load_req_rise_ns':load_start,'first_uart_tx_start_ns':next(t for t,b in signals['uart_tx'].events if b=='0'),
        'first_uart_rx_start_ns':next(t for t,b in signals['uart_rx'].events if b=='0'),
        'first_sram_write_ns':io[0]['time_ns'],'last_sram_write_ns':io[-1]['time_ns'],
        'load_complete_rise_ns':complete,'load_req_fall_ns':req_down,'load_complete_fall_ns':complete_down,
        'cnn_start_sample_ns':mw[-1]['time_ns'],'first_cnn_read_ns':cr[0]['time_ns'],
        'first_cnn_write_ns':cw[0]['time_ns'],'last_cnn_write_ns':cw[-1]['time_ns'],
        'first_cpu_result_read_ns':cpu_reads[0]['time_ns'],'cpu_finish_write_ns':finish[0]['time_ns']}
    (out/'transactions.json').write_text(json.dumps(transactions,indent=2),encoding='utf-8')
    with (out/'transactions.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['time_ns','interface','address','data','be','error']);writer.writeheader()
        for r in transactions:
            writer.writerow({k:(f'0x{v:08X}' if k in ('address','data') and v is not None else v) for k,v in r.items()})

    font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'svg.fonttype':'none'})
    figures=[]

    def plot(name,title,names,start,end,notes,markers=(),unit='ns'):
        assert set(names)<=ALLOWED
        fig,axes=plt.subplots(len(names),1,figsize=(19,1.9+len(names)*.55),sharex=True,squeeze=False)
        fig.patch.set_facecolor('#f6f9fc'); axes=axes[:,0]; scale=1000 if unit=='us' else 1
        width=end-start
        for ax,n in zip(axes,names):
            signal=signals[n]; color='#007e87' if not n.startswith(('cnn_mmio','mem_')) else '#a4571b'
            ax.set_facecolor('#f6f9fc');ax.set_ylim(-.17,1.2);ax.set_yticks([])
            label=n+(' ['+str(signal.width-1)+':0]' if signal.width>1 else '')
            ax.text(-.018,.70,label,transform=ax.transAxes,ha='right',va='center',fontsize=10.5,fontfamily='DejaVu Sans Mono',color='#15364a')
            ax.text(-.018,.18,LABELS.get(n,''),transform=ax.transAxes,ha='right',va='center',fontsize=9,color='#5b7280')
            sections=list(segments(signal,start,end))
            if signal.width==1:
                xs=[];ys=[]
                for l,r,b in sections:
                    if b in ('0','1'):xs.extend([l/scale,r/scale]);ys.extend([int(b)]*2)
                    else:
                        xs.extend([l/scale,r/scale]);ys.extend([float('nan')]*2)
                        ax.axvspan(l/scale,r/scale,color='#f0d98b',alpha=.6)
                ax.plot(xs,ys,color=color,lw=1.25)
                ax.text(1.005,.04,'0',transform=ax.transAxes,fontsize=8,color='#82929a')
                ax.text(1.005,.77,'1',transform=ax.transAxes,fontsize=8,color='#82929a')
            else:
                for l,r,b in sections:
                    unknown=not set(b)<={'0','1'}; bevel=min(width*.002,(r-l)/5)
                    points=[(l,.5),(l+bevel,.12),(r-bevel,.12),(r,.5),(r-bevel,.88),(l+bevel,.88)]
                    ax.add_patch(Polygon([(x/scale,y) for x,y in points],facecolor='#f2dca4' if unknown else '#dbeaf0',edgecolor='#557485',lw=.65))
                    text='X' if unknown else f'{int(b,2):X}'
                    if (r-l)/width*1350>len(text)*6.2+6:
                        ax.text((l+r)/2/scale,.5,text,fontsize=9,ha='center',va='center',fontfamily='DejaVu Sans Mono',clip_on=True)
            for t,tag in markers:
                if start<=t<=end:ax.axvline(t/scale,lw=.75,color='#ca5660',ls='--',alpha=.8)
            ax.grid(axis='x',alpha=.17);ax.tick_params(axis='x',labelsize=9,length=0)
            for spine in ax.spines.values():spine.set_visible(False)
        for t,tag in markers:
            if start<=t<=end:axes[0].text(t/scale,1.43,tag,ha='center',va='bottom',fontsize=9,color='#a03643',clip_on=False)
        axes[-1].set_xlim(start/scale,end/scale)
        axes[-1].set_xlabel('仿真时间（微秒，μs）' if unit=='us' else '仿真时间（纳秒，ns）',fontsize=11)
        height=fig.get_figheight()
        fig.suptitle(title,x=.255,y=1-.20/height,ha='left',va='top',fontsize=17,fontweight='bold',color='#163c53')
        fig.text(.255,1-.63/height,'实际 XSim VCD · 仅接线与外部 IO · 总线为十六进制，省略前导零 · 黄色 X 表示未定义',fontsize=10,color='#5b7280',va='top')
        fig.text(.255,.021,notes,fontsize=10,color='#365365',linespacing=1.65)
        fig.subplots_adjust(left=.255,right=.977,top=1-1.16/height,bottom=1.05/height,hspace=.28)
        for ext in ('png','svg'):fig.savefig(out/(name+'.'+ext),dpi=160,facecolor=fig.get_facecolor())
        plt.close(fig)
        figures.append({'file':name+'.png','signals':names,'start_ns':start,'end_ns':end})

    plot('01_overview','① 全程总览：上电 → UART 加载 → CPU 启动 CNN → CPU 读回',
         ['rst_n','load_req','uart_tx','uart_rx','io_mem_req','load_complete','load_error','cnn_mmio_we','mem_read','mem_write','dmem_re','dmem_we'],
         0,315000,'UART 占据大部分时间；末尾约 312～314 μs 的计算与读回，请看后面的放大图。\n窄脉冲在全程图中接近竖线；这里没有增加任何“阶段状态”或测试台计数信号。',
         markers=[(io[0]['time_ns'],'首包写入'),(io[64]['time_ns'],'第2包写入'),(io[128]['time_ns'],'第3包写入'),(io[192]['time_ns'],'第4包写入')],unit='us')
    plot('02_boot','② 上电与取指：公共复位释放后，CPU 从 IMEM 读程序',
         ['clk','rst_n_in','rst_n','imem_re','imem_addr','imem_rdata','load_req'],0,280,
         f'外部复位 {rise("rst_n_in"):g} ns 释放；内部复位 {rise("rst_n"):g} ns 释放；load_req 在 {load_start:g} ns 置 1。\nIMEM 数据在采样请求的上升沿之后更新；地址/数据的变化不是软件人工驱动。',
         markers=[(rise('rst_n_in'),'外部释放'),(rise('rst_n'),'内部释放'),(load_start,'请求加载')])
    plot('03_uart','③ 串口交接：图像桥先发送读请求，外部设备随后回复',
         ['load_req','uart_tx','uart_rx','io_mem_req','load_complete','load_error'],
         0,io[0]['time_ns']+1000,
         'uart_tx：桥发 IMIO 读请求；uart_rx：外部设备发 IMOR 应答。双方空闲电平为 1。\n首包收齐且校验通过后才出现 io_mem_req；请求/应答的串行位是真实波形，没有画内部 RX 字节信号。',unit='us')
    first=io[0]['time_ns']
    plot('04_sram_input','④ 首四个图像字节落入 SRAM：看 req / gnt 和字节选择',
         ['clk','io_mem_req','io_mem_we','io_mem_gnt','io_mem_error','io_mem_addr','io_mem_be','io_mem_wdata','load_complete'],
         first-25,first+95,
         '在 req=1、gnt=1、error=0 的上升沿提交写入。前四拍 be=1、2、4、8，字地址均为 00000100。\n对应字节为 01、FE、03、04（有符号数 1、-2、3、4）；wdata 按字节位置移位。',
         markers=[(first,'01'),(first+10,'FE'),(first+20,'03'),(first+30,'04')])
    plot('05_handoff_start','⑤ 加载完成后，CPU 经原 MMIO 配置并启动 CNN',
         ['load_req','load_complete','load_error','io_mem_req','cnn_mmio_we','cnn_mmio_ready','cnn_mmio_addr','cnn_mmio_wdata'],
         complete-80,mw[-1]['time_ns']+45,
         '先完成 req↑ → complete↑ → req↓ → complete↓ 的握手，再出现 CNN 配置写。\nMMIO 有效写依次为：40000008 ← 000001E0；40000018 ← 00000001；40000000 ← 0000003D。',
         markers=[(complete,'完成'),(req_down,'CPU确认'),(mw[-1]['time_ns'],'启动采样')])
    plot('05b_mmio_detail','⑤-b MMIO 逐拍放大：三笔写分别交给 CNN 什么内容',
         ['clk','cnn_mmio_we','cnn_mmio_ready','cnn_mmio_addr','cnn_mmio_wdata','load_req','load_complete'],
         mw[0]['time_ns']-25,mw[-1]['time_ns']+25,
         '在 we=1 且 ready=1 的上升沿，读取沿前的地址与写数据；沿后线路可能已切换到下一条 CPU 指令。\n三笔依次是任务表地址 1E0、任务数 1、启动控制 3D；这些全部是原 CPU 与 CNN 之间的 MMIO 线。',
         markers=[(r['time_ns'],tag) for r,tag in zip(mw,['任务表地址','任务数量','开始执行'])])
    plot('06_cnn_descriptor','⑥ CNN 自己读任务表：CPU 给的是表地址，表内再给数据地址',
         ['clk','mem_read','mem_ready','mem_addr','mem_rdata','mem_write'],
         cr[0]['time_ns']-25,cr[7]['time_ns']+20,
         '只在 mem_read=1 且 mem_ready=1 的上升沿读取 mem_rdata；请求等待期间不要把旧值当返回值。\n前八次读地址 1E0～1FC；表中依次包含版本/算子、输入100、输出141、权重110、偏置120、尺寸、通道、层参数。')
    later=[r for r in cr if r['address']<0x1e0]
    plot('07_cnn_compute','⑦ CNN 读取操作数并写结果：使用 CNN 与 SRAM 原生连线',
         ['mem_read','mem_write','mem_ready','mem_addr','mem_rdata','mem_wdata','cnn_mmio_re','cnn_mmio_rdata'],
         later[0]['time_ns']-25,cw[-1]['time_ns']+45,
         'mem_read/ready：取偏置、权重、输入，也读取输出旧字做字节保护；mem_write/ready：提交整个结果字。\n四次有效写数据依次 A5A505A5、A5FF05A5、09FF05A5、A5A5A50B；算术内部信号不在接线图中，因此不绘制。')
    plot('07b_cnn_input_detail','⑦-b 操作数读取放大：偏置 3、权重 2、四个输入字节',
         ['clk','mem_read','mem_ready','mem_addr','mem_rdata','mem_write'],
         later[0]['time_ns']-25,later[2]['time_ns']+25,
         '三个有效读返回分别为：地址120 → 3；地址110 → 2；地址100 → 0403FE01。\n小端排列中 0403FE01 对应低地址到高地址的 01、FE、03、04，即输入 [1, -2, 3, 4]。',
         markers=[(r['time_ns'],tag) for r,tag in zip(later[:3],['偏置','权重','输入'])])
    done_reads=[r for r in kind('mmio_read') if r['address']==0x40000004 and r['data'] is not None and r['data']&2]
    assert done_reads
    plot('08_cpu_result','⑧ CPU 读到 DONE，再从 SRAM 取结果并留下成功标记',
         ['cnn_mmio_re','cnn_mmio_ready','cnn_mmio_addr','cnn_mmio_rdata','dmem_re','dmem_we','dmem_wstrb','dmem_addr','dmem_rdata','dmem_wdata'],
         done_reads[0]['time_ns']-35,finish[0]['time_ns']+30,
         'CNN STATUS 的 bit1=1 表示 DONE（不要要求整个寄存器一定等于 2）。随后 CPU 读 140、144。\nCPU 写回邮箱：80 ← 09FF05A5；84 ← A5A5A50B；88 ← 0000600D。成功标记是 dmem_wdata 上的数据，不是额外端口。')
    plot('08b_cpu_read_detail','⑧-b CPU 读回逐拍放大：两笔读请求、两笔结果保存',
         ['clk','dmem_re','dmem_we','dmem_wstrb','dmem_addr','dmem_rdata','dmem_wdata'],
         cpu_reads[0]['time_ns']-25,cpu_reads[-1]['time_ns']+45,
         'CPU SRAM 读：在上升沿采样沿前地址，沿后 dmem_rdata 给出该地址的数据；连续读时两者不能按同一时刻硬配。\nCPU SRAM 写：在 we=1 的上升沿采样沿前地址、wdata 和 wstrb；F 表示四个字节都写。',
         markers=[(cpu_reads[0]['time_ns'],'读140'),(cpu_reads[1]['time_ns'],'读144')])

    # Audit every plotted row against the immutable explicit connection allowlist.
    used=sorted({n for f in figures for n in f['signals']})
    assert set(used)<=ALLOWED
    audit={'status':'PASS','source_vcd':str(source),'source_vcd_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'historical_simulation':True,'source_result':str(run/'result.json'),
        'connection_documents':['SoC六模块增线说明_CPU与图像桥三线直连.md','SoC顶层连线与总体IO说明_小白版.md',
                                'SoC三线自动加载RTL与上电全流程仿真说明_小白版.md'],
        'allowlist':GROUPS,'plotted_signals':used,'figures':figures,'milestones':milestones,
        'notes':['Only dut top-level wire/port values; no testbench counters or private module state.',
                 'MMIO names cnn_mmio_* are the documented top-level aliases for mmio_*.',
                 'Transaction controls sampled before rising edge; CPU SRAM read data recorded after edge.',
                 'Existing demo loads weights/descriptors over UART; image-only mode has not been implemented.']}
    (out/'waveform_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(milestones,indent=2))
    print('CNN transactions:',json.dumps(cr+cw))
    print('CPU result:',json.dumps(cpu_reads+[r for r in kind('cpu_write') if r['time_ns']>complete]))
    print(f'PASS: {len(figures)} figures; {len(used)} plotted signals, all allowed; {len(found)} wires in filtered VCD')
    print(out)


if __name__=='__main__':main()
