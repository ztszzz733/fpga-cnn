"""Render triple-slot control evidence from the actual successful RTL run."""
import argparse,csv,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments,Signal
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
    result=json.loads((run/'result.json').read_text());assert result['status']=='PASS'
    for group in ['hashes','include_hashes']:
        for name,h in result['build_inputs'][group].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    out=ROOT/'deliverables/mobilefacenet_residual';out.mkdir(exist_ok=True)
    for name in ['control.vcd','events.csv','workload.json','sim.log']:shutil.copyfile(run/'residual'/name,out/name)
    for case in ['recycle_stall','restart']:shutil.copyfile(run/case/'events.csv',out/(case+'_events.csv'))
    shutil.copyfile(run/'result.json',out/'result.json')
    workload=json.loads((out/'workload.json').read_text())
    with (out/'task_map.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['node','frame','operator','row_start','rows','channels','dependencies','consumers','output_address','output_bytes','keep'])
        for n in workload['nodes']:
            consumers=[c['id'] for c in workload['nodes'] if n['id'] in c['dependency_nodes']]
            writer.writerow([n['id'],n['frame'],['Conv_5','Conv_6+ReLU6','Conv_7(DW)+ReLU6','Conv_8','Add'][n['layer']],
                             n['y'],n['rows'],n['channels'],str(n['dependency_nodes']),str(consumers),
                             hex(n['destination']),n['count'],n['keep']])
    # Preserve original evidence; named bit decodes improve readability only.
    shutil.copyfile(out/'control.vcd',out/'control_raw.vcd')
    v=read_vcd(out/'control.vcd');sig={n.removeprefix('pipeline.'):s for n,s in v.signals.items()}
    import bisect
    raw_times={n:[t for t,b in s.events] for n,s in sig.items()}
    def raw_value(n,t):
        idx=bisect.bisect_right(raw_times[n],t)-1
        return int(sig[n].events[idx][1],2) if idx>=0 else 0
    first_add_write=next(t for t,b in sig['post_write_fire'].events if b=='1' and raw_value('post_add',t))
    first_add_node=raw_value('post_node',first_add_write)
    first_add_start=next(t for t,b in sig['post_start'].events if b=='1' and raw_value('post_add',t) and raw_value('post_node',t)==first_add_node)
    skip_node,main_node=workload['nodes'][first_add_node]['dependency_nodes']
    decoded={'join_skip_ready':('completed_mask',skip_node), 'join_main_ready':('completed_mask',main_node),
             'skip0_released':('released_mask',0),'skip0_release':('release_pulse',0),'skip0_live':('live_mask',0)}
    for i,(name,(source,bit)) in enumerate(decoded.items()):
        ev=[]
        for t,b in sig[source].events:
            val=str((int(b,2)>>bit)&1)
            if not ev or ev[-1][1]!=val:ev.append((t,val))
        sig[name]=Signal('pipeline.'+name,1,'d'+str(i),ev)
    changes={}
    for s in sig.values():
        for t,b in s.events:changes.setdefault(int(t),[]).append('b'+b+' '+s.code)
    header=['$timescale 1ns $end','$scope module pipeline $end']
    header += [f'$var wire {s.width} {s.code} {n} $end' for n,s in sig.items()]
    header += ['$upscope $end','$enddefinitions $end']
    body=[]
    for t in sorted(changes):body += ['#'+str(t),*changes[t]]
    body += ['#'+str(int(v.end_ns))]
    (out/'control.vcd').write_text('\n'.join(header+body)+'\n')
    assert len(sig)==len({s.code for s in sig.values()})
    first=lambda n:next(t for t,b in sig[n].events if b=='1')
    assert any(b=='1' for _,b in sig['done'].events)
    assert not any(b=='1' for n in ['error','memory_fault'] for _,b in sig[n].events)
    def value(n,t):
        import bisect
        ev=sig[n].events;idx=bisect.bisect_right([v[0] for v in ev],t)-1
        return int(ev[idx][1],2) if idx>=0 else 0
    add_write=next(t for t,b in sig['post_write_fire'].events if b=='1' and value('post_add',t))
    add_done=next(t for t,b in sig['post_done'].events if b=='1' and t>add_write and value('post_add',t))
    release=next(t for t,b in sig['release_pulse'].events if int(b,2)&1)
    overview=['conv_node0','compute_active0','conv_node1','compute_active1','post_node','post_add','post_busy','post_write_fire',
              'completed_mask','released_mask','live_mask','done','error']
    detail=['conv_node0','compute_active0','conv_node1','compute_active1','join_skip_ready','join_main_ready',
            'post_node','post_add','post_start','post_busy','post_read_fire','post_write_fire','post_done']
    lifetime=['post_node','post_add','post_write_fire','post_done','skip0_live','skip0_release','skip0_released']
    views=[('01_overview','残差任务图：卷积与双输入相加的执行全程',0,v.end_ns,overview),
           ('02_add','第一次残差相加：两路就绪后启动，读取并写回',max(0,first_add_start-300),add_done+200,detail),
           ('03_release','旁路数据：最后一个消费者完成后才允许回收',max(0,release-1000),release+300,lifetime)]
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
                    value=f'{int(bits,2):X}' if n in ('post_address','completed_mask','released_mask','release_pulse','live_mask') else str(int(bits,2))
                    if xb-xa>max(25,len(value)*10):d.text((xa+3,y+2),value,font=font(15),fill=c)
        im.save(out/(stem+'.png'))
        gtk=['[*] Real RTL dependency pipeline','[dumpfile] "'+str(out/'control.vcd').replace('\\','/')+'"','[timestart] 0']
        for n in names:
            s=sig[n];gtk+=['@28' if s.width==1 else ('@22' if n in ('post_address','completed_mask','released_mask','release_pulse','live_mask') else '@24'),f'[color] {color(n)[1]}',s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
        (out/(stem+'.gtkw')).write_text('\n'.join(gtk)+'\n')
        tcl=['gtkwave::/Edit/Set_Trace_Max_Hier 1','gtkwave::/View/Scale_To_Time_Dimension/us',f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}','gtkwave::setMarker -1']
        (out/(stem+'.tcl')).write_text('\n'.join(tcl)+'\n')
        (out/('verify_'+stem+'.tcl')).write_text('\n'.join(tcl+[
            'set out [file dirname [file normalize [info script]]]','set shown [gtkwave::getDisplayedSignals]',
            f'if {{[llength $shown] != {len(names)}}} {{error "signal count mismatch"}}',
            'set f [open [file join $out gtkwave_validation.log] a]',f'puts $f "PASS {stem} COUNT=[llength $shown]"','close $f','gtkwave::/File/Quit'])+'\n')
        (out/('open_'+stem+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0'+stem+'.gtkw" -S "%~dp0'+stem+'.tcl"\n')
    m=result['cases']['residual'];tim=result['timing_seconds']
    events=list(csv.DictReader((out/'events.csv').open(newline='')))
    def event_cycle(kind,node):return next(int(e['cycle']) for e in events if e['event']==kind and int(e['node'])==node)
    held_after_main=event_cycle('release',0)-event_cycle('post_done',6)
    assert held_after_main>0 and event_cycle('release',0)>event_cycle('post_done',20)
    for n in workload['nodes']:
        if n['keep']:continue
        rc=event_cycle('release',n['id'])
        for c in workload['nodes']:
            if n['id'] in c['dependency_nodes']:assert rc>event_cycle('post_done',c['id'])
    rows='\n'.join(f"| {name} | {r['cycles']:,} | {r['cycles']/100:.2f} µs | {tim[key]:.2f} 秒 | {r['checked_bytes']:,} |" for key,name in [('residual','正常'),('recycle_stall','限速＋回收覆盖'),('restart','Add中止后复位重启')] for r in [result['cases'][key]])
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),derived_signals=decoded,first_add_node=first_add_node,first_add_write_ns=add_write,first_add_done_ns=add_done,first_bypass_release_ns=release,views={v[0]:v[4] for v in views}),indent=2))
    guide=f"""# 真实残差块调度验证

三项 **PASS**。两套真实NEureka、一套量化/激活/相加后处理，保留三槽流水，新增双输入汇合与中间特征释放通知。

## 本次跑了什么

两张人脸的局部特征，各跑 `Conv_5 → Conv_6+ReLU6 → Conv_7(DW)+ReLU6 → Conv_8 → Add`，Conv_5结果同时作为旁路。64/128通道与权重来自固定MobileFaceNet模型，20个卷积条带、8个Add行任务，共28节点。前面的网络由软件执行；RTL入口是6×6×128特征，不是直接输入RGB。本块输出每图4×4×64。

完整模型的对应浮点ROI已比对。RTL逐条带INT32、逐后处理UINT8与独立整数参考逐字节核对；当前量化尺度仅用于诊断，不能据此宣称识别准确率通过。没有UART、主CPU驱动或完整网络RTL。

| 用例 | 周期 | 100MHz硬件时间 | 电脑仿真耗时 | 核对字节数 |
|---|---:|---:|---:|---:|
{rows}

本次编译 **{tim['compile']:.2f} 秒**，三项仿真合计 **{sum(tim[k] for k in ['residual','recycle_stall','restart']):.2f} 秒**；总流程 **{tim['total']:.2f} 秒**。这些是电脑耗时，与微秒级硬件时间不同。重启用例的电脑耗时包含中止前预热，表内周期从复位后正式重跑计数。缓存可哈希校验复用。

## 证明了什么

- 每项8次Add，只在两路生产者均完成最后写响应后启动。
- 正常用例Add忙且另一路NEureka处于计算阶段：**{m['add_compute_overlap_cycles']:,}周期**。这是阶段重叠，不表示每个PE每拍都有效。
- 每项发出20次中间特征释放通知，8个最终Add结果保留。测试独立反查消费者并断言未提前释放、未重复释放。
- 压力用例在释放后立即把旧特征覆盖成0xD7，并限速实例0；最终输出仍一致，检查后层没有使用已释放的有效数据。
- 具体例子：节点0的旁路，在主分支消费者节点6完成后仍保留 **{held_after_main:,}周期**，等到Add节点20也完成，才释放。事件日志独立核对了全部20次释放的消费者顺序。
- Add写回中clear，复位并重装数据/图后再次通过。不是断点续算。
- `skip_hold_cycles`、`join_wait_cycles`按节点累计等待，多个节点同拍会累计多次，不能当成总执行周期或性能损失。

## 波形怎么读

- [全程](01_overview.png)：看两个 `compute_active`、`post_add` 和 `post_write_fire`，相加可以与另一任务的卷积重叠。
- [首次Add](02_add.png)：`post_add=1`、`post_start`发起；后处理先读参数，再交替读旁路/主分支，计算并逐元素写回。最后写响应之后 `post_done` 拉高。
- [旁路释放](03_release.png)：节点0属于帧0的Conv_5首两行。只有主分支相关消费者和使用旁路的Add行都完成，`release_pulse`的bit0才置1，随后`released_mask`记录该位。
- 双击对应 `open_01_overview.cmd` / `open_02_add.cmd` / `open_03_release.cmd` 用GTKWave查看原始VCD。

| 信号 | 方向与功能 |
|---|---|
| conv_node0/1 | 调度器→卷积实例，当前节点编号；空闲时数值不代表正在执行 |
| compute_active0/1 | NEureka→观察端，忙且处于MATRIXVEC计算阶段 |
| post_node / post_add | 调度器→后处理器，节点编号与模式；add=1双输入相加，0卷积重定量/激活 |
| post_start / post_busy / post_done | 调度器发起，后处理返回忙/完成；done表示最后写响应已收到 |
| post_read_fire / post_write_fire | 后处理↔SRAM，请求已被接受；写握手不等于写响应已完成 |
| completed_mask | 每位对应一个节点，其结果已提交；依赖满足才允许后层发射 |
| release_pulse | 调度器→未来存储分配端，每位对应可回收的生产者节点，本次在TB中驱动覆盖压力测试 |
| released_mask / live_mask | 累计已释放、已完成但仍保留的结果集合，均为十六进制 |
| done / error | 本批图完成 / 故障；外部消费最终结果的协议尚未接入 |

图中的 `join_skip_ready/main_ready` 是首次Add节点 **{first_add_node}** 的两个依赖（旁路节点{skip_node}、主分支节点{main_node}）的完成位解码，`skip0_live/release/released` 是节点0的生命周期位解码；由真实掩码导出，不是新增RTL端口。原始未解码VCD保留为 `control_raw.vcd`。

节点编号、依赖、消费者和地址可直接看 [任务对照表](task_map.csv)，机器描述见 [workload.json](workload.json)，精确提交/完成/释放顺序见 [events.csv](events.csv)。每个视图信号只出现一次；图由本次真实VCD绘制。`post_slot=3`只表示Add不用INT32槽。

## 与同学对接时的边界

本实验SRAM模型 **512 KiB、4 banks、21客户端**，用于保留两个帧的中间数据和对照地址；没有修改生产SoC的256 KiB存储基线。临时槽在0x70000/0x72000/0x74000，各8 KiB。

已经有安全释放通知，尚无通用动态地址分配器或循环行缓存。下一步存储端可按通知回收，但必须保留地址/长度映射、宽读取安全范围和输入背压。最终结果keep=1不自动释放；当前批次clear/reset重建。

详细接口和生命周期约束见 [设计说明](../../docs/mobilefacenet_residual_design.md)。
"""
    (out/'README.md').write_text(guide,encoding='utf-8')
    (out/'SHA256.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file() and f.name not in ['SHA256.json','gtkwave_validation.log']},indent=2))
    print(str(out))
if __name__=='__main__':main()
