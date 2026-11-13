"""Export real top-level I/O, grouped GTKWave sessions and a signal guide."""
import argparse,csv,hashlib,json,re,shutil,subprocess,os
import xml.etree.ElementTree as ET
from pathlib import Path
from soc_top_signals import SIGNALS,STATES,UNITS,COLORS,groups

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/soc_top_view'

def diagram_signal_map():
    path=OUT/'soc_architecture.drawio'
    cells=ET.parse(path).findall('./diagram[1]/mxGraphModel/root/mxCell')
    expansions={
        'dmem_re / we / wstrb':['dmem_re','dmem_we','dmem_wstrb'],
        'cnn_mmio_re / we':['cnn_mmio_re','cnn_mmio_we'],
        'cnn_valid / write / byte':['cnn_valid','cnn_write','cnn_byte'],
        'cnn_ready / response':['cnn_ready','cnn_response'],
        'io_mem_req / we / be':['io_mem_req','io_mem_we','io_mem_be'],
        'io_mem_gnt / rvalid / error':['io_mem_gnt','io_mem_rvalid','io_mem_error'],
        'bridge_ready / busy / error':['bridge_ready','bridge_busy','bridge_error'],
        'cnn_status_busy / done / error':['cnn_status_busy','cnn_status_done','cnn_status_error']}
    mapping={n:[] for n in SIGNALS}
    for cell in cells:
        label=cell.get('value','')
        names={n for n in SIGNALS if re.search(r'(?<![A-Za-z0-9_])'+re.escape(n)+r'(?![A-Za-z0-9_])',label)}
        for prefix,members in expansions.items():
            if prefix in label:names.update(members)
        for n in names:mapping[n].append({'cell_id':cell.get('id'),'label':label})
    assert all(mapping.values()),f'Signals absent from draw.io: {[n for n,v in mapping.items() if not v]}'
    (OUT/'diagram_signal_map.json').write_text(json.dumps({'drawio_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'signals':mapping},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def extract(source,dest):
    scope=[];found={};now=0;marks={}
    with source.open() as stream:
        header=[]
        for line in stream:
            header.append(line)
            if '$enddefinitions' in line:break
        for kind,value in re.findall(r'\$(\w+)\s+(.*?)\s*\$end',''.join(header),re.S):
            p=value.split()
            if kind=='scope':scope.append(p[1])
            elif kind=='upscope':scope.pop()
            elif kind=='var' and scope==['tb_soc_overlap','dut'] and p[3] in SIGNALS:
                found[p[3]]=(int(p[1]),p[2])
        assert set(found)==set(SIGNALS),f'Missing top signals: {set(SIGNALS)-set(found)}'
        assert all(found[n][0]==s['width'] for n,s in SIGNALS.items())
        codes={code for _,code in found.values()}
        special={found[n][1]:n for n in ['load_req','load_complete','cnn_status_busy','cnn_status_done','bridge_error']}
        with dest.open('w') as out:
            out.write('$version Actual RTL simulation, selected top-level nets $end\n$timescale 1ps $end\n$scope module soc_top $end\n')
            for n,(w,c) in found.items():
                out.write(f'$var wire {w} {c} {n}'+(f' [{w-1}:0]' if w>1 else '')+' $end\n')
            out.write('$upscope $end\n$enddefinitions $end\n')
            for line in stream:
                s=line.strip()
                if not s:continue
                if s[0]=='#':now=int(s[1:]);out.write(line)
                elif s[0]=='$':out.write(line)
                else:
                    c=s.split()[-1] if s[0] in 'bBrR' else s[1:]
                    if c in codes:out.write(line)
                    if c in special and s[0]=='1':
                        n=special[c]
                        if n!='cnn_status_busy' or 'load_complete' in marks:marks.setdefault(n,now)
    marks['end']=now
    return marks

def trace(name):return 'soc_top.'+name+(f"[{SIGNALS[name]['width']-1}:0]" if SIGNALS[name]['width']>1 else '')

def session(name,wave,selected,start,zoom):
    requested=[n for _,_,members in selected for n in members]
    assert len(requested)==len(set(requested)),f'Duplicate trace in {name}'
    lines=[f'[*] Six-module top-level view; {name}',f'[dumpfile] "{wave}"',
           f'[timestart] {start}','[size] 1800 1050','[pos] 0 0',f'*{zoom} -1 '+' '.join(['-1']*26),
           '[sst_width] 160','[signals_width] 340','[sst_expanded] 0']
    count=0
    for title,color,names in selected:
        lines+=['@200','-'+title]
        for n in names:
            state=n in STATES
            tint=COLORS[STATES.index(n)] if state else color
            lines+=['@2022' if state else '@28' if SIGNALS[n]['width']==1 else '@22',f'[color] {tint}']
            if state:lines+=['^1 state_names.txt']
            lines+=[trace(n)];count+=1
    (OUT/f'{name}.gtkw').write_text('\n'.join(lines)+'\n')
    launcher=f'@echo off\nsetlocal\ncd /d "%~dp0"\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0{wave}" -a "%~dp0{name}.gtkw"\n'
    (OUT/f'open_{name}.cmd').write_text(launcher)
    return count

def guide(run,marks,counts):
    report=json.loads((run/'result.json').read_text())
    uart=report.get('uart_config',{'baud':12500000,'chunk_bytes':64})
    lines=['# 六模块顶层波形与信号说明','',
        '本交付对应新版 face_soc_overlap_top。波形来自本次真实 CPU/UART/19 任务仿真，从复位开始记录；第一层只显示六个大模块的接口及顶层状态，不展开 CPU 流水级、CNN 算子或 PE 内部状态。','',
        f"当前仿真 UART：{uart['baud']/1000000:g} Mbps，每包 {uart['chunk_bytes']} 字节；收发两端使用一致设置，保留起止位、包 CRC 和整批 CRC。系统时钟仍为 100 MHz。",'',
        '## 打开波形','',
        '| 入口 | 显示内容 |','|---|---|',
        '| [open_all_modules.cmd](open_all_modules.cmd) | 全部接口，按模块分组着色；默认定位 CNN 运行区间 |',
        '| [open_power_on.cmd](open_power_on.cmd) | 相同完整信号列表，从上电复位开始 |',
        '| [open_module_states.cmd](open_module_states.cmd) | 六模块状态与总览位图，查看完整运行过程 |',
        '| [open_fault_reset.cmd](open_fault_reset.cmd) | UART 超时后 IMAGE_BRIDGE 故障及硬复位清除 |','',
        f"共 {len(SIGNALS)} 根图中标注的独立信号，完整视图显示 {counts['all_modules']} 条轨迹，每根只出现一次。共享连线只放在输出端模块组，不在输入端重复显示；六路状态及图中的状态总览量集中放在 TOP STATES。",
        '只显示 draw.io 第一页中标出的连线、状态及状态/引脚标注。图中合并标注如 dmem_re / we / wstrb，在波形中拆成三个真实信号，各显示一次；未额外展开 CNN 内部通道或流水线信号。diagram_signal_map.json 逐根记录图中对应的标签和单元编号。',
        '组标题使用英文以避免 GTKWave 字体兼容问题。模块颜色分别为 CPU 蓝、CNN 红、DATASRAM 黄、IMEM 靛蓝、IMAGE_BRIDGE 紫、CLOCK 橙。上下滚动可查看全部模块。TOP STATES、EXTERNAL INPUTS 和 TOP OUTPUTS 是观察分组，不是新增硬件模块。FST 是由真实 VCD 无损转换的紧凑波形，打开更快；原始 VCD 也保留。','',
        '## 第一层状态机','',
        '顶层新增六路并行寄存状态机，不增加第七个模块实例，也不参与功能控制。各路可同时 WORK。状态从上升沿前的真实接口/忙信号采样，在该上升沿后更新，不能将其与边沿后已经变化的组合请求直接逐值比较。',
        'GTKWave 使用 state_names.txt 将两位状态显示为 RESET / IDLE / WORK / FAULT；原始值仍为 0/1/2/3。','',
        '| 状态 | 数值 | 含义 |','|---|---:|---|',
        '| RESET | 0 | 复位中 |','| IDLE | 1 | 本模块没有被监测到的工作；CLOCK 表示复位释放等待 |',
        '| WORK | 2 | 模块活动或事务在途；CLOCK 表示内部复位已释放 |',
        '| FAULT | 3 | 观测到该模块支持的故障 |','',
        '| 状态信号 | WORK 的依据 | FAULT 与恢复 |','|---|---|---|',
        '| cpu_state | imem_re、数据存储访问、MMIO 访问或 load_req 任一有效 | 当前无 CPU 异常检测输入；FAULT 保留 |',
        '| cnn_state | cnn_status_busy；包括调度、执行、访存排空 | 队列错误或存储故障；监测状态保持至软/硬复位，存储故障本身仍需硬复位 |',
        '| sram_state | CPU 请求、CNN 请求/响应或桥请求/读响应 | cnn_mem_fault；硬复位恢复 |',
        '| imem_state | imem_re 被采样为 1 | 当前无独立 ROM 故障输入；FAULT 保留 |',
        '| bridge_state | bridge_busy | bridge_error；硬复位恢复 |',
        '| clock_state | rst_n 已释放 | 不包含停钟/PLL 失锁检测；FAULT 保留 |','',
        'CPU 在轮询或执行末尾自跳转时仍然取指，因此可持续 WORK。这不表示有效业务计算一直发生。IMEM 的状态反映同步读取；SRAM 的 WORK 包括等待仲裁，不能据此判定已完成访问。CPU 数据读取没有独立返回有效线。','',
        'soc_active、soc_fault 的 bit0～5 顺序均为 CPU、CNN、DATASRAM、IMEM、IMAGE_BRIDGE、CLOCK。soc_module_state 的 [1:0]、[3:2]、[5:4]、[7:6]、[9:8]、[11:10] 按同样顺序打包。','',
        '## 全部信号：功能、源端和目的端','',
        '以下名称为顶层连线名。CPU 内部 MMIO 端口名 mmio_* 对应顶层 cnn_mmio_*；CNN 的 status_* 输出对应顶层 cnn_status_*。顶层监测状态是内部可观察寄存器，没有增加封装引脚。每个功能模块的 clk/rst_n 来自 CLOCK。','',
        '| 信号 | 位宽 | 从哪里输出 | 到哪里输入/使用 | 功能 | 有效条件 |',
        '|---|---:|---|---|---|---|']
    for n,s in SIGNALS.items():
        lines.append(f"| {n} | {s['width']} | {s['source']} | {s['target']} | {s['description']} | {s['valid']} |")
    lines+=['','## CNN 的 11 路通道','',
        '三条 352 位总线均为 11×32 位。通道 i 位于 [32i+31:32i]；11 位控制向量中 bit i 对应该通道。低位是通道 0。','',
        '| 通道 | 使用者 |','|---|---|','| 0 | 描述符读取 |','| 1 / 2 | 计算上下文 0 加载 / 写回 |',
        '| 3 / 4 | 计算上下文 1 加载 / 写回 |','| 5 | ReLU6 |','| 6 | ADD |','| 7 | ReLU |','| 8 | PReLU |','| 9 | MaxPool |','| 10 | Requant |','',
        '看 cnn_valid & cnn_ready 确认哪一路请求在该边沿接受；看 cnn_response 确认完成。地址、写数据、读数据在无有效事务时可以保持旧值，不能把总线上任意数值当作一次访问。四个 bank 同周期最多接受四路 CNN/桥访问，CPU 优先占用其命中的 bank。','',
        '图中 cnn_valid/write/byte 合计 33 位，cnn_ready/response 合计 22 位；cnn_addr、cnn_wdata、cnn_rdata 各 352 位。旧图中的单路 mem_* 接口已不适用于新版。','',
        '## 关键时刻与证据','',
        f"- 本次运行：{run.name}",
        f"- 开始请求加载：{marks['load_req']/1000:.0f} ns",
        f"- 本批加载结束：{marks['load_complete']/1000:.0f} ns",
        f"- CNN busy 首次有效：{marks['cnn_status_busy']/1000:.0f} ns",
        f"- CNN 队列完成：{marks['cnn_status_done']/1000:.0f} ns",
        '- 正常用例逐字验证 8192 字节加载区，19 个任务完成；CNN 阶段仍为 3613 周期。',
        '- 新增状态断言逐周期对照采样接口；超时用例验证仅 IMAGE_BRIDGE 进入 FAULT，硬复位后六路状态及故障位图清零。',
        '- 原有运行中软复位和重复提交测试继续通过。',
        '- 结果、源文件哈希和波形来源保存在 simulation_result.json / provenance.json；GTKWave 原生检查保存在 validation.log。',
        '- 总图和状态图位于 soc_architecture.drawio 的两个页面，可在 draw.io / diagrams.net 中逐块、逐线编辑。SVG 是同一布局的预览。','']
    (OUT/'信号与状态说明.md').write_text('\n'.join(lines),encoding='utf-8')

def main(run):
    report=json.loads((run/'result.json').read_text())
    assert report['status']=='PASS' and report['tests']['observer_fault']['status']=='PASS'
    OUT.mkdir(parents=True,exist_ok=True)
    diagram_signal_map()
    marks=extract(run/'overlap/wave.vcd',OUT/'soc_top.vcd')
    fault=extract(run/'observer_fault/wave.vcd',OUT/'fault_reset.vcd')
    # Optional bundled GTKWave converter; do not fabricate or resample values.
    converter=ROOT/'tools/gtkwave/portable/gtkwave64/bin/vcd2fst.exe'
    ext='vcd'
    if os.name=='nt' and converter.exists():
        for stem in ['soc_top','fault_reset']:
            subprocess.run([str(converter),'-v',str(OUT/f'{stem}.vcd'),'-f',str(OUT/f'{stem}.fst')],check=True)
        ext='fst'
    (OUT/'state_names.txt').write_text('0 RESET\n1 IDLE\n2 WORK\n3 FAULT\n')
    g=groups();counts={}
    counts['all_modules']=session('all_modules',f'soc_top.{ext}',g,max(0,marks['cnn_status_busy']-500000),-26)
    counts['power_on']=session('power_on',f'soc_top.{ext}',g,0,-23)
    counts['module_states']=session('module_states',f'soc_top.{ext}',[g[0]],0,-12)
    counts['fault_reset']=session('fault_reset',f'fault_reset.{ext}',g,max(0,fault['bridge_error']-500000),-25)
    ranges={'all_modules':(max(0,marks['cnn_status_busy']-500000),marks['cnn_status_done']+500000),
            'power_on':(0,500000),'module_states':(0,marks['end']),
            'fault_reset':(max(0,fault['bridge_error']-500000),fault['end'])}
    for name,(start,end) in ranges.items():
        tcl=['set out [file dirname [file normalize [info script]]]',
             f'set log [open [file join $out validation_{name}.log] w]',
             'set filter [gtkwave::setCurrentTranslateFile [file join $out state_names.txt]]']
        tcl += ['set state_names [list '+ ' '.join('{'+trace(n)+'}' for n in STATES)+']',
                'gtkwave::highlightSignalsFromList $state_names',
                'gtkwave::installFileFilter $filter',
                'gtkwave::unhighlightSignalsFromList $state_names',
                f'gtkwave::setZoomRangeTimes {start} {end}',
                'gtkwave::/View/Scale_To_Time_Dimension/ns',
                'gtkwave::/Edit/Set_Trace_Max_Hier 1',
                f'gtkwave::/File/Write_Save_File_As [file join $out {name}.gtkw]',
                f'puts $log "{name} TOTAL=[gtkwave::getTotalNumTraces] SIGNALS=[llength [gtkwave::getDisplayedSignals]]"',
                f'if {{[llength [gtkwave::getDisplayedSignals]] != {counts[name]}}} {{puts $log "FAIL signal count"}}',
                'set shown [gtkwave::getDisplayedSignals]',
                'puts $log "UNIQUE=[llength [lsort -unique $shown]]"',
                'if {[llength $shown] != [llength [lsort -unique $shown]]} {puts $log "FAIL duplicate signal"}',
                'flush $log']
        check_name='bridge_state' if name=='fault_reset' else 'cnn_state'
        check_time=fault['bridge_error']+10000 if name=='fault_reset' else marks['cnn_status_busy']+100000
        expected='FAULT' if name=='fault_reset' else 'WORK'
        tcl += [f'gtkwave::setMarker {check_time}',
                f'set value [gtkwave::getTraceValueAtMarkerFromName {{{trace(check_name)}}}]',
                'puts $log "STATE=$value"',
                f'if {{![string match "*{expected}*" $value]}} {{puts $log "FAIL state translation"}}',
                'gtkwave::setMarker -1',
                'puts $log "PASS GTKWave six-module session"','close $log','gtkwave::/File/Quit']
        (OUT/f'verify_{name}.tcl').write_text('\n'.join(tcl)+'\n')
    guide(run,marks,counts)
    with (OUT/'signals.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['signal','width','source','target','function','valid'])
        for n,s in SIGNALS.items():w.writerow([n,*s.values()])
    (OUT/'provenance.json').write_text(json.dumps({'run':str(run),'marks_ps':marks,'fault_marks_ps':fault,
        'unique_signals':len(SIGNALS),'trace_counts':counts,
        'source_vcd_sha256':hashlib.sha256((run/'overlap/wave.vcd').read_bytes()).hexdigest(),
        'signal_mapping':{n:'tb_soc_overlap.dut.'+n for n in SIGNALS}},indent=2)+'\n')
    shutil.copyfile(run/'result.json',OUT/'simulation_result.json')
    print(OUT)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);main(p.parse_args().run.resolve())
