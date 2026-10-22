"""Package actual two-engine RTL controls, dispatch evidence and timing."""
import argparse,csv,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
    result=json.loads((run/'result.json').read_text());assert result['status']=='PASS'
    for name,h in result['build_inputs']['hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    out=ROOT/'deliverables/mobilefacenet_dual';out.mkdir(exist_ok=True)
    for name in ['control.vcd','events.csv','workload.json','sim.log']:shutil.copyfile(run/'dual'/name,out/name)
    for case in ['single','skew','restart']:shutil.copyfile(run/case/'events.csv',out/(case+'_events.csv'))
    shutil.copyfile(run/'result.json',out/'result.json')
    v=read_vcd(out/'control.vcd');sig={n.removeprefix('pipeline.'):s for n,s in v.signals.items()}
    assert len(sig)==len({s.code for s in sig.values()})
    first=lambda n:next(t for t,b in sig[n].events if b=='1')
    assert any(b=='1' for _,b in sig['done'].events)
    assert not any(b=='1' for n in ['error','memory_fault'] for _,b in sig[n].events)
    events=list(csv.DictReader((out/'events.csv').open()))
    assignments={}
    for e in events:
        if e['event']=='conv_start':assignments.setdefault(int(e['node']),e)
    active={};seen=set();dispatches=[]
    for e in events:
        worker=int(e['engine']);node=int(e['node'])
        if e['event']=='conv_start':
            if node not in seen:
                if node>=2 and (1-worker) in active:dispatches.append(e)
                seen.add(node)
            active[worker]=node
        elif e['event']=='conv_done':active.pop(worker,None)
    assert dispatches,'no new-task dispatch while the other engine is occupied'
    dispatch=dispatches[0]
    dispatch_ns=int(dispatch['cycle'])*10+55
    overlap=first('both_compute')
    overview=[]
    for e in range(2):overview += [n+str(e) for n in ['conv_node','conv_frame','conv_layer','engine_busy','compute_active']]
    overview += ['both_compute','post_node','post_busy','post_write_fire','slot_states','completed_mask','done','error']
    detail=[]
    for e in range(2):detail += [n+str(e) for n in ['conv_node','conv_frame','conv_slot','core_busy','compute_active','conv_read_fire','conv_write_fire']]
    detail += ['both_compute','post_busy','post_write_fire']
    dispatch_signals=[]
    for e in range(2):dispatch_signals += [n+str(e) for n in ['conv_start','conv_node','conv_frame','conv_layer','engine_busy','conv_tile_done']]
    dispatch_signals += ['post_node','post_done','slot_states','completed_mask']
    views=[('01_overview','双 NEureka：空闲实例自动派发与共享后处理',0,v.end_ns,overview),
           ('02_dual_compute','两套真实 NEureka 同时进入计算阶段',max(0,overlap-200),overlap+1800,detail),
           ('03_dispatch','一路仍被占用，空闲的另一路接收新条带',max(0,dispatch_ns-300),dispatch_ns+2500,dispatch_signals)]
    def color(n):
        return ('#8658bd',3) if n.endswith('0') else (('#2674b5',4) if n.endswith('1') else (('#138360',2) if n.startswith('post') else ('#946315',6)))
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
    for stem,title,left,right,names in views:
        w=1800;top=145;h=top+len(names)*40+55;im=Image.new('RGB',(w,h),'#f7f9fc');d=ImageDraw.Draw(im);x0=310;x1=1760
        x=lambda t:x0+(t-left)/(right-left)*(x1-x0)
        d.text((24,20),title,font=font(26),fill='#243a52')
        d.text((24,65),'100 MHz · 紫色实例0 / 蓝色实例1 / 绿色后处理 · 真实 RTL · SRAM 预加载，不含 UART',font=font(19),fill='#52637b')
        for j in range(9):
            xx=x0+(x1-x0)*j/8;tt=left+(right-left)*j/8
            d.line((xx,top-12,xx,h-35),fill='#dce4ed');d.text((min(xx-20,1655),top-40),f'{tt/1000:.3f} µs',font=font(14),fill='#52637b')
        for i,n in enumerate(names):
            y=top+i*40;c,_=color(n);d.text((24,y),n,font=font(18),fill=c);prev=None
            for l,r,bits in segments(sig[n],left,right):
                xa,xb=x(l),x(r)
                if set(bits)-set('01'):continue
                if sig[n].width==1:
                    yy=y+3 if int(bits,2) else y+25
                    if prev is not None:d.line((xa,prev,xa,yy),fill=c,width=2)
                    d.line((xa,yy,xb,yy),fill=c,width=2);prev=yy
                else:
                    d.rectangle((xa,y+3,xb,y+25),outline=c)
                    value=f'{int(bits,2):X}' if n in ('post_address','completed_mask') else str(int(bits,2))
                    if xb-xa>max(25,len(value)*10):d.text((xa+3,y+2),value,font=font(15),fill=c)
        im.save(out/(stem+'.png'))
        gtk=['[*] Real RTL dependency pipeline','[dumpfile] "'+str(out/'control.vcd').replace('\\','/')+'"','[timestart] 0']
        for n in names:
            s=sig[n];gtk+=['@28' if s.width==1 else ('@22' if n in ('post_address','completed_mask') else '@24'),f'[color] {color(n)[1]}',s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
        (out/(stem+'.gtkw')).write_text('\n'.join(gtk)+'\n')
        tcl=['gtkwave::/Edit/Set_Trace_Max_Hier 1','gtkwave::/View/Scale_To_Time_Dimension/us',f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}','gtkwave::setMarker -1']
        (out/(stem+'.tcl')).write_text('\n'.join(tcl)+'\n')
        (out/('verify_'+stem+'.tcl')).write_text('\n'.join(tcl+[
            'set out [file dirname [file normalize [info script]]]','set shown [gtkwave::getDisplayedSignals]',
            f'if {{[llength $shown] != {len(names)}}} {{error "signal count mismatch"}}',
            'set f [open [file join $out gtkwave_validation.log] a]',f'puts $f "PASS {stem} COUNT=[llength $shown]"','close $f','gtkwave::/File/Quit'])+'\n')
        (out/('open_'+stem+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0'+stem+'.gtkw" -S "%~dp0'+stem+'.tcl"\n')
    nodes=json.loads((out/'workload.json').read_text())['nodes']
    m=result['cases']['dual'];single=result['cases']['single'];skew=result['cases']['skew'];tim=result['timing_seconds']
    assignment_rows='\n'.join(f"| {i} | {nodes[i]['frame']} / {nodes[i]['layer']} / {nodes[i]['y']//2} | {e['engine']} | {e['cycle']} |" for i,e in sorted(assignments.items()))
    timing_rows='\n'.join(f"| {name} | {result['cases'][key]['cycles']:,} | {result['cases'][key]['cycles']/100:.2f} µs | {tim[key]:.2f} 秒 |" for key,name in [('dual','两实例'),('single','仅实例1'),('skew','仅实例0限速'),('restart','清除复位重启')])
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),first_dual_compute_ns=overlap,dispatch=dispatch,views={v[0]:v[4] for v in views}),indent=2))
    guide=f'''# 双 NEureka 自动派发：小区域 RTL 验证

本轮 **PASS**，原始记录 `{run}`。当前 CNN 实验入口包含 **两个真实 NEureka 卷积实例＋一个量化/激活后处理单元＋两个临时缓冲槽**。生产 CPU/UART 和六模块顶层还没有接入本入口。

## 这次解决了什么

任务表只指定图片、层、条带和依赖，不指定用哪一个卷积实例。硬件先检查上游结果是否写完，再挑空闲实例执行；两个都空闲时轮换选择，只有一个空闲时直接给它。每个条带的两个32通道组留在同一实例完成，不能中途迁移。

输入仍是 `person_1.jpg`、`person_2.jpg` 的局部计算范围，真实 MobileFaceNet 权重，首层6×6×64→DW4×4×64→PW4×4×64，共14个两行条带、28个卷积子任务。后层读取前层真实硬件输出。SRAM预加载，不含UART输入，也不是完整人脸识别。

| 证据 | 实测结果 |
|---|---:|
| 双实例分别处理的完整条带数 | {m['engine_nodes']} |
| 两个核心同时处于计算阶段 | {m['dual_compute_cycles']:,} 周期 |
| 两个实例同拍都有访存请求被接受（含配置读取） | {m['dual_memory_cycles']:,} 周期 |
| 卷积计算阶段内后处理提交写入 | {m['post_write_during_compute_cycles']:,} 周期 |
| 仅启用实例1，分别处理条带数 | {single['engine_nodes']} |
| 实例0被独立限速后，分别处理条带数 | {skew['engine_nodes']} |

第 {dispatch['cycle']} 周期，实例 {dispatch['engine']} 接到新任务 {dispatch['node']}，另一个实例仍占用未完成的条带。全程有 {len(dispatches)} 次这种后续派发。当前正常/限速用例都恰好各完成7条带，不据此宣称负载预测或智能负载均衡；仅启用实例1的用例证明任务没有绑定固定实例。

双实例、仅实例1、非对称停顿、清除复位重启四项全通过，每项检查 **{m['checked_bytes']:,}字节**，包括逐条带INT32卷积结果和UINT8后处理结果；四个最终输出SHA256一致。还检查依赖、任务不重不丢、两个通道组不能换实例、临时槽互斥、最后写响应后才释放、不可写区域保持不变。

非对称停顿测试仅允许实例0在每7拍中的3拍提交请求，实例1和后处理不被人工限速，返回响应不被阻塞。重启测试中断预热任务后执行clear、复位、重装初始内存与任务表，再核验完整批次，不是断点恢复。限速与重启分开运行：测试平台预热阶段尚未启动限速所用周期计数，同时启用这两个测试选项会停在预热；最初尝试记录保留，未把它算作通过。已通过的正常/单实例测试经源码、输入和输出哈希核对后复用，没有重新编译。

## 看波形

- [全程任务分配和忙闲](01_overview.png)
- [两套卷积同时计算](02_dual_compute.png)
- [槽释放后的自动派发](03_dispatch.png)
- GTKWave：双击 `open_01_overview.cmd`、`open_02_dual_compute.cmd` 或 `open_03_dispatch.cmd`。
- [双实例事件表](events.csv)、[仅实例1事件表](single_events.csv)、[限速事件表](skew_events.csv)、[重启事件表](restart_events.csv)。

颜色：紫色为实例0、蓝色为实例1、绿色为后处理、棕色为公共调度状态。同一视图内每个信号只出现一次。PNG由本次真实VCD绘制，按上升沿采样；细节波形用于看控制握手，不展开所有PE数据。

| 信号 | 含义与来源/去向 |
|---|---|
| conv_start0 / conv_start1 | 调度器→相应NEureka封装，发射一个32输出通道组；每个条带两次 |
| conv_node0/1、conv_frame0/1、conv_layer0/1 | 调度器→执行单元，任务编号、图片和层标签；闲置时标签可能改变，结合start/busy看 |
| conv_slot0 / conv_slot1 | 调度器→执行单元，使用的临时槽编号；并发时两个实例必须使用不同槽 |
| engine_busy0 / engine_busy1 | 调度器的实例占用，覆盖配置、两个通道组执行和写排空；不是单纯核心计算时间 |
| core_busy0/1、compute_active0/1 | NEureka→观察端，核心忙，以及核心忙且处于MATRIXVEC计算阶段 |
| both_compute | 两个compute_active同时为1；不等于每个PE每拍都发生有效乘加 |
| conv_read_fire0/1、conv_write_fire0/1 | 对应实例存储桥↔DATASRAM，九路数据客户端中至少一路读/写请求被接受；不含配置客户端 |
| conv_tile_done0/1 | 卷积封装→调度器，两个通道组和存储写排空，槽进入待后处理状态 |
| post_node / post_busy | 调度器→后处理的任务编号，以及后处理忙状态 |
| post_write_fire | 后处理→DATASRAM，一个UINT8结果写请求被接受 |
| post_done | 后处理→调度器，最后写响应已完成，才更新完成位并释放槽 |
| slot_states | 两槽打包状态，slot1高3位、slot0低3位，十进制显示：0空闲、1待卷积、2卷积中、3待后处理、4后处理中 |
| completed_mask | 已提交后处理结果的任务位图，十六进制；bit i 对应任务 i |
| done / error | 全批次完成/失败状态，传给调用方；不是单个卷积任务状态 |

## 实际分配记录

下面记录每条带第一次卷积发射；第二通道组继续使用同一实例。

| 任务 | 图片 / 层 / 条带 | 分配实例 | 首发周期 |
|---|---|---|---|
{assignment_rows}

## 时间

| 模式 | 硬件周期 | 100MHz对应时间 | 电脑实际仿真耗时 |
|---|---:|---:|---:|
{timing_rows}

本次重新编译 **{tim['compile']:.2f}秒**，原始首次编译 **{result.get('original_compile_seconds',tim['compile']):.2f}秒**。本次执行脚本 **{tim['total']:.2f}秒**（复用已完成测试的耗时不重复计入）；重启用例周期数仅统计重新初始化后的完整批次，电脑时间含预热。100MHz是仿真设定，没有经过综合时序验收。

仅实例1与双实例的周期比为 **{result['single_over_dual_cycles']:.3f}**，比较同一任务图、相同4-bank SRAM、相同后处理与两槽配置。两实例共享存储带宽，只有两个临时槽，所以不是两倍性能承诺；双卷积同时占满两槽时后处理不能再占第三槽。此比较也不是整个识别网络或UART端到端性能。

## 复现与下一步

[调度/接口设计](../../docs/mobilefacenet_dual_design.md)。WSL执行 `python3 scripts/run_mobilefacenet_dual.py --reuse --data build/mobilefacenet_pipeline_data`，缓存 `.neureka_dual_build`；RTL或监视器改变才重新编译。Windows制图 `scripts/prepare_mobilefacenet_dual.py <运行目录>`。旧单实例结果和源码保留。

目前完成的是 **两个同类卷积实例的自动派发验证**，尚未实现每种算子都有3～5个实例。下一步接输入行就绪与缓冲回收，或在明确带宽/缓冲预算后增加其他算子实例。完整网络、CPU命令接入、UART分批输入、循环行缓冲、7×7硬件与准确率校准仍待完成。
'''
    (out/'README.md').write_text(guide,encoding='utf-8')
    print(out)
if __name__=='__main__':main()
