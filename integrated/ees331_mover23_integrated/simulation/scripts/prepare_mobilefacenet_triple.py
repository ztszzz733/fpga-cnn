"""Render triple-slot control evidence from the actual successful RTL run."""
import argparse,csv,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
    result=json.loads((run/'result.json').read_text());assert result['status']=='PASS'
    for group in ['hashes','include_hashes']:
        for name,h in result['build_inputs'][group].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    out=ROOT/'deliverables/mobilefacenet_triple';out.mkdir(exist_ok=True)
    for name in ['control.vcd','events.csv','workload.json','sim.log']:shutil.copyfile(run/'triple'/name,out/name)
    for case in ['two_slots','stress_restart']:shutil.copyfile(run/case/'events.csv',out/(case+'_events.csv'))
    shutil.copyfile(run/'result.json',out/'result.json')
    v=read_vcd(out/'control.vcd');sig={n.removeprefix('pipeline.'):s for n,s in v.signals.items()}
    assert len(sig)==len({s.code for s in sig.values()})
    first=lambda n:next(t for t,b in sig[n].events if b=='1')
    assert any(b=='1' for _,b in sig['done'].events)
    assert not any(b=='1' for n in ['error','memory_fault'] for _,b in sig[n].events)
    overlap=first('triple_write')
    overview=['conv_node0','compute_active0','conv_node1','compute_active1','post_node','post_busy','post_write_fire',
              'triple_active','slot0_state','slot1_state','slot2_state','completed_mask','done','error']
    detail=[]
    for e in range(2):detail += [n+str(e) for n in ['conv_node','conv_slot','compute_active','conv_read_fire','conv_write_fire']]
    detail += ['post_node','post_slot','post_busy','post_read_fire','post_write_fire','triple_active','triple_write']
    waits=['engine_busy0','engine_busy1','post_busy','slot0_state','slot1_state','slot2_state',
           'wait_slot','wait_dependency','wait_engine','wait_post','mem_wait0','mem_wait1','mem_wait_post','done']
    views=[('01_overview','三槽流水：两路卷积与后处理共享执行时间',0,v.end_ns,overview),
           ('02_triple_write','两路卷积均在计算阶段，后处理正在写回',max(0,overlap-200),overlap+1800,detail),
           ('03_waits','等待原因观察：缺槽、依赖、执行单元与存储接受',0,v.end_ns,waits)]
    def color(n):
        if n.startswith('slot'):return ('#946315',6)
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
    m=result['cases']['triple'];two=result['cases']['two_slots'];stress=result['cases']['stress_restart'];tim=result['timing_seconds']
    assert m['triple_write_cycles']>0 and two['triple_cycles']==0
    rows='\n'.join(f"| {name} | {result['cases'][key]['cycles']:,} | {result['cases'][key]['cycles']/100:.2f} µs | {tim[key]:.2f} 秒 |" for key,name in [('triple','三槽'),('two_slots','同程序限制两槽'),('stress_restart','三槽限速＋清除复位重启')])
    categories=[('wait_slot_cycles','就绪任务缺空槽'),('wait_dependency_cycles','未分配任务均在等依赖'),('wait_engine_cycles','槽内就绪条带等卷积实例'),('wait_post_cycles','已完成卷积的槽等后处理')]
    wait_rows='\n'.join(f"| {name} | {two[key]:,} | {m[key]:,} |" for key,name in categories)
    wait_rows+='\n'+'\n'.join(f"| {name}的存储请求等待 | {two['memory_wait_cycles'][i]:,} | {m['memory_wait_cycles'][i]:,} |" for i,name in enumerate(['卷积0','卷积1','后处理']))
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),first_triple_write_ns=overlap,views={v[0]:v[4] for v in views}),indent=2))
    guide=f'''# 三槽流水：两路卷积与一路后处理同时工作

本次 **PASS**。当前实验入口有两套真实NEureka和一套量化/激活后处理，将INT32临时槽从2个增加到3个。第三个槽让它们可以同时处理三个不同条带。**没有增加第三个卷积实例。** 生产CPU/UART与顶层六模块尚未接入本实验入口。

## 已验证的结果

- 输入、真实MobileFaceNet权重及量化尺度沿用上一阶段：两张人脸的局部前三层、全部64输出通道，14个条带、28次卷积子任务。
- 三槽、同程序两槽对照、三槽限速＋清除复位重启三项均通过；每项检查 **{m['checked_bytes']:,}字节**，包含INT32卷积结果和UINT8后处理结果。最终输出SHA256全部一致。
- 三槽的三个临时槽分别承接 **{m['slot_use']}** 个条带，第三槽实际被重复使用；两槽对照的分配次数为 **{two['slot_use']}**，第三槽区域保持原值。
- 两个核心同时处于计算阶段且后处理busy：**{m['triple_cycles']:,}周期**；其中后处理实际提交写请求：**{m['triple_write_cycles']:,}周期**。两槽对照没有三方重叠。
- 三槽两卷积实例分别完成 **{m['engine_nodes']}** 个条带。校验槽互斥、通道组绑定、依赖/标签、任务不重不丢、不可写区和最后写响应后才释放。

当前输入仍为SRAM预加载，后层读取真实硬件中间结果；未运行完整人脸网络，也不代表UART边收边算。第三槽地址0x3C000、容量8 KiB；总临时槽容量24 KiB，SRAM总容量仍为256 KiB。

## 波形怎么读

- [全程：三个执行单元与三槽状态](01_overview.png)
- [细节：两路卷积计算时，后处理实际写回](02_triple_write.png)
- [全程：不同等待原因](03_waits.png)
- GTKWave双击 `open_01_overview.cmd`、`open_02_triple_write.cmd`、`open_03_waits.cmd`。

细节从第一次真实三方写回前200ns开始。先看两条 `compute_active0/1`，同时为1表示两核都忙且处于MATRIXVEC阶段；再看 `post_write_fire` 的脉冲，表示后处理正在提交写入。`triple_write=1`是三者同时满足的直接标记，不表示所有PE每拍均有有效乘加。

紫色为卷积0，蓝色为卷积1，绿色为后处理，棕色为公共状态。每个视图每根信号只出现一次；PNG由本次真实VCD绘制，不是示意时序。空闲期间任务编号可能变化，需结合busy或compute_active判读。

| 信号 | 含义/连接方向 |
|---|---|
| conv_node0/1、conv_slot0/1 | 调度器→卷积执行端，当前任务编号和临时槽；三方并发时槽号应互不相同 |
| compute_active0/1 | NEureka→观察端，核心忙且处于计算阶段 |
| conv_read_fire0/1、conv_write_fire0/1 | 对应NEureka数据桥↔SRAM，至少一个数据客户端读/写请求被接受；不含配置读取 |
| engine_busy0/1 | 调度器→观察端，整个条带仍占用实例，包含配置及两通道组之间间隙 |
| post_node、post_slot | 调度器→后处理，当前条带和源INT32槽 |
| post_busy | 后处理→观察端，包含参数读取、重定量、激活和写完成等待 |
| post_read_fire、post_write_fire | 后处理↔SRAM，实际读取/写入请求握手 |
| triple_active、triple_write | 观察端组合条件，分别是两核计算＋后处理busy、再要求后处理写握手 |
| slot0_state/1_state/2_state | 调度器→观察端，0空闲、1待卷积、2卷积中、3待后处理、4后处理中 |
| completed_mask | 调度器已提交UINT8结果的任务位图，十六进制bit i对应任务i |
| wait_slot/dependency/engine/post | 调度器→观察端，各类等待条件，精确定义见下文及设计说明 |
| mem_wait0/1/post | 测试观察端，对应客户端有获准进入仲裁的请求，但SRAM未接受 |
| done / error | 调度器→调用方，全批次完成/失败；通过用例error全程为0 |

## 等待统计：先定位现象，再决定扩什么

| 条件成立的周期数 | 两槽 | 三槽 |
|---|---:|---:|
{wait_rows}

这些计数**不是互斥分类，不能相加成为总停顿，也不能直接当作增资源可节省的周期数**。例如有任务缺槽时两个卷积也可能全忙；增加槽也无法让第三个卷积同时运行。存储等待包含同实例九个32位客户端之间的bank冲突，不全是实例间争用。

`wait_dependency`只统计未分配任务均不满足依赖，不表示整个CNN空闲。`wait_post`表示有已卷积完成的槽排队，`wait_engine`表示有已分配槽的条带等待空闲卷积实例。上述条件支持后续定位，不能单凭某项计数最大就认定唯一瓶颈。

## 时间和对照

| 模式 | 硬件周期 | 100MHz硬件时间 | 电脑实际仿真时间 |
|---|---:|---:|---:|
{rows}

本次首次编译 **{tim['compile']:.2f}秒**，三项实际仿真合计 **{sum(tim[k] for k in ['triple','two_slots','stress_restart']):.2f}秒**，运行脚本总耗时 **{tim['total']:.2f}秒**。100MHz为仿真设定，未通过综合验证最高频率。压力重启周期数只统计重新初始化后的完整批次，电脑耗时包含预热段。

两槽/三槽周期比为 **{result['two_over_three_cycles']:.3f}**；比较的是同一14任务、同一4-bank SRAM和相同算子数量，不是完整网络或UART端到端加速比。电脑仿真耗时与硬件完成周期分别报告。

## 改动、复现和边界

原始记录 `{run}`。结果：[result.json](result.json)；事件：[三槽](events.csv)、[两槽](two_slots_events.csv)、[限速重启](stress_restart_events.csv)。[设计与等待定义](../../docs/mobilefacenet_triple_design.md)。

新增 `rtl/cnn_quant/quant_triple_scheduler.sv`，保留旧两槽模块。数据生成 `scripts/gen_mobilefacenet_triple.py build/mobilefacenet_triple_data`；WSL运行 `python3 scripts/run_mobilefacenet_triple.py --data build/mobilefacenet_triple_data --reuse`，源码/头文件或监视器改变则重新编译。独立缓存 `.neureka_triple_build`。

新测试平台的限速计数在预热期间也推进，因此本次可以组合限速与重启；旧双实例测试平台的组合选项问题没有被回写成通过。压力例在三方有效重叠时清除，再复位、重装初始内存与任务表，不是断点恢复。

本次只扩临时槽和生命周期调度，没有实现每类3～5个算子、第二套后处理、真实残差网络、输入行缓冲或完整模型。接下来可根据真实任务依赖和等待证据继续扩展；输入与存储同学的接口对接仍按各自要求文档进行。
'''
    (out/'README.md').write_text(guide,encoding='utf-8')
    print(out)
if __name__=='__main__':main()
