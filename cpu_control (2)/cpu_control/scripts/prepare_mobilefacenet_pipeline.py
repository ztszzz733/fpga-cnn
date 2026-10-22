"""Fresh PASS waveform views for two-frame dependency scheduling."""
import argparse,csv,hashlib,json,shutil,bisect
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
    result=json.loads((run/'result.json').read_text());assert result['status']=='PASS'
    for name,h in result['build_inputs']['hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    out=ROOT/'deliverables/mobilefacenet_pipeline';out.mkdir(exist_ok=True)
    for name in ['control.vcd','events.csv','workload.json','sim.log']:shutil.copyfile(run/'parallel'/name,out/name)
    shutil.copyfile(run/'result.json',out/'result.json')
    v=read_vcd(out/'control.vcd');sig={n.removeprefix('pipeline.'):s for n,s in v.signals.items()}
    assert len(sig)==len({s.code for s in sig.values()})
    first=lambda n:next(t for t,b in sig[n].events if b=='1')
    assert any(b=='1' for _,b in sig['done'].events)
    assert not any(b=='1' for n in ['error','memory_fault'] for _,b in sig[n].events)
    nodes=json.loads((out/'workload.json').read_text())['nodes']
    events=list(csv.DictReader((out/'events.csv').open()))
    complete=set();handoff=None
    for e in events:
        idx=int(e['node']);n=nodes[idx]
        if e['event']=='post_done':complete.add(idx)
        if e['event']=='conv_start' and n['layer']>0:
            previous={q['id'] for q in nodes if q['frame']==n['frame'] and q['layer']==n['layer']-1}
            if not previous<=complete:
                handoff=dict(event=e,previous_layer_pending=sorted(previous-complete));break
    assert handoff
    overlap=first('compute_post_overlap');handoff_ns=int(handoff['event']['cycle'])*10+55
    compute_events=sig['compute_active'].events
    compute_times=[t for t,_ in compute_events]
    write_overlap=next(t for t,b in sig['post_write_fire'].events
                       if b=='1' and compute_events[bisect.bisect_right(compute_times,t)-1][1]=='1')
    overview=['conv_frame','conv_layer','conv_stripe','core_busy','compute_active','post_frame','post_layer','post_stripe','post_busy','compute_post_overlap','slot_states','completed_mask','done','error']
    detail=['conv_node','conv_frame','conv_layer','conv_slot','compute_active','conv_read_fire','conv_write_fire','post_node','post_frame','post_layer','post_slot','post_read_fire','post_write_fire','post_address','compute_post_overlap']
    cross=['conv_start','conv_frame','conv_layer','conv_stripe','core_busy','post_frame','post_layer','post_stripe','post_busy','post_write_fire','post_done','completed_mask','slot_states']
    views=[('01_overview','两张真实人脸小区域：条带依赖调度与卷积/量化重叠',0,v.end_ns,overview),
           ('02_overlap','真实重叠：NEureka 计算阶段内，后处理仍在读写',max(0,write_overlap-200),write_overlap+1800,detail),
           ('03_layer_handoff','跨层条带交接：前层尚未全部写完，后层已经启动',max(0,handoff_ns-300),handoff_ns+3000,cross)]
    def color(n):
        return ('#8658bd',3) if n.startswith('conv') or n in ('core_busy','compute_active') else (('#138360',2) if n.startswith('post') else ('#946315',6))
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
    for stem,title,left,right,names in views:
        w=1800;top=145;h=top+len(names)*40+55;im=Image.new('RGB',(w,h),'#f7f9fc');d=ImageDraw.Draw(im);x0=310;x1=1760
        x=lambda t:x0+(t-left)/(right-left)*(x1-x0)
        d.text((24,20),title,font=font(26),fill='#243a52')
        d.text((24,65),'100 MHz · frame 0/1 · layer 0/1/2 · 真实 RTL · SRAM 输入预加载，不含 UART',font=font(19),fill='#52637b')
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
            s=sig[n];gtk+=['@28' if s.width==1 else '@22',f'[color] {color(n)[1]}',s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
        (out/(stem+'.gtkw')).write_text('\n'.join(gtk)+'\n')
        tcl=['gtkwave::/Edit/Set_Trace_Max_Hier 1','gtkwave::/View/Scale_To_Time_Dimension/us',f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}','gtkwave::setMarker -1']
        (out/(stem+'.tcl')).write_text('\n'.join(tcl)+'\n')
        (out/('verify_'+stem+'.tcl')).write_text('\n'.join(tcl+[
            'set out [file dirname [file normalize [info script]]]','set shown [gtkwave::getDisplayedSignals]',
            f'if {{[llength $shown] != {len(names)}}} {{error "signal count mismatch"}}',
            'set f [open [file join $out gtkwave_validation.log] a]',f'puts $f "PASS {stem} COUNT=[llength $shown]"','close $f','gtkwave::/File/Quit'])+'\n')
        (out/('open_'+stem+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0'+stem+'.gtkw" -S "%~dp0'+stem+'.tcl"\n')
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),first_overlap_ns=overlap,first_write_during_compute_ns=write_overlap,early_layer_handoff=handoff,views={v[0]:v[4] for v in views}),indent=2))
    m=result['cases']['parallel'];s=result['cases']['serial'];r=result['cases']['stalled_restart'];tim=result['timing_seconds']
    hn=nodes[int(handoff['event']['node'])]
    guide=f'''# 两张真实人脸小区域：跨层条带流水验证

本轮结果：**PASS**。来源 `{run}`。一套真实NEureka、一套量化后处理、两个INT32临时槽，自动按依赖表调度两张图片的三层局部网络。顶层六模块划分不变，尚未接生产CPU/UART。

## 验证了什么

- 输入为用户的 `person_1.jpg`、`person_2.jpg`，权重与上一轮固定MobileFaceNet相同；两图使用相同量化尺度。计算空间范围仍是首层6×6×64→DW4×4×64→PW4×4×64，全部64个通道参与。
- 每条带两行，14个任务，28次NEureka卷积发射与14次量化后处理。每个任务都携带frame/layer/stripe标签。
- 3×3 DW条带需要其上游4行，依赖相邻两个已写完的首层条带；1×1 PW只需要对应DW条带。依赖满足后才可发射。
- 两个32位临时槽复用：直到量化的最后写响应完成才释放。量化后的各层/各帧特征区仍单独保留，尚未实现循环行缓冲或全模型内存分配。
- 后层读取前层真实硬件输出，Python只提供初始输入/权重/参数和检查用金标准，没有给硬件注入中间结果。

并行、顺序、反压加中途清除复位三项都通过。每项核对 **{m['checked_bytes']:,} 字节**（包含全部条带INT32卷积和UINT8量化输出），所有最终输出文件哈希相同；检查不可写区域不变、任务不重不丢、标签正确、槽不被提前复用、halo依赖和clear后的重启。

## 并行证据

| 指标 | 实测 |
|---|---:|
| 卷积计算阶段与后处理busy重叠 | {m['compute_post_overlap_cycles']:,} 周期 |
| 卷积计算阶段内，后处理发生写握手 | {m['post_write_during_compute_cycles']:,} 周期 |
| 顺序对照的计算/后处理重叠 | {s['compute_post_overlap_cycles']} 周期 |
| 第二张图首次卷积启动 | 第 {m['first_frame1_conv']:,} 周期 |
| 第一张图最后条带写完 | 第 {m['last_frame0_post']:,} 周期 |

一次跨层交接发生在第 **{handoff['event']['cycle']} 周期**：frame {hn['frame']}、layer {hn['layer']}、stripe {hn['y']//2} 已启动，此时同帧上一层仍有任务 {handoff['previous_layer_pending']} 未全部写完。它所必需的条带已经提交，测试平台在发射时单独核验依赖。

只有一套NEureka，各层卷积仍轮流使用它；并行的是卷积与后处理。`core_state=4`表示计算阶段，不代表所有PE每拍都有效乘加；上表结合实际写握手和逐字节结果证明有用的重叠。

## 波形与信号

- [全程：两帧交错与条带状态](01_overview.png)
- [细节：计算阶段与量化读写重叠](02_overlap.png)
- [细节：前层未全部结束，后层已启动](03_layer_handoff.png)
- GTKWave打开入口：`open_01_overview.cmd`、`open_02_overlap.cmd`、`open_03_layer_handoff.cmd`。
- [周期事件表](events.csv)、[任务依赖/地址/量化尺度](workload.json)、[完整测试结果](result.json)。

每个视图内信号只出现一次，按模块分组着色；紫色卷积、绿色后处理、棕色调度/状态。PNG由本次真实VCD绘制，波形在每个时钟上升沿采样，不包含完整PE内部海量信号。

| 信号 | 从哪里到哪里 / 如何看 |
|---|---|
| conv_frame/layer/stripe，post_frame/layer/stripe | 调度表→相应执行单元的任务标签；frame0/1对应两张图片，layer0首层、1深度卷积、2点卷积。闲置期间保留/选择的标签不表示任务正在执行，须结合start/busy。 |
| conv_start | 调度器→NEureka封装，每条带两次（两个32通道组） |
| conv_node，post_node | 调度器→观察端，当前任务表编号 |
| conv_slot，post_slot | 调度器→执行端，正在使用的临时缓冲槽0或1；并发时必须不同 |
| core_busy，compute_active | NEureka→观察端，分别为核心忙、忙且处于MATRIXVEC计算阶段 |
| conv_read_fire / conv_write_fire | NEureka存储桥↔DATASRAM，有读取/写入请求得到接受；配置端口另行读取，不计在这两个信号里 |
| conv_tile_done | 卷积封装→调度器，两个通道组及待写事务完成，条带可开始后处理，但槽尚不能释放 |
| post_start / post_busy | 调度器→后处理、后处理→观察端，参数加载和重定量过程 |
| post_read_fire | 后处理→DATASRAM读握手，既包括参数，也包括32位卷积结果 |
| post_write_fire / post_address | 后处理→DATASRAM写握手和地址，每次提交一个UINT8结果 |
| post_done | 后处理→调度器，最后一次写响应完成；设置完成位并释放槽 |
| compute_post_overlap | 观察逻辑，compute_active与post_busy同时为1 |
| completed_mask | 调度器→观察端，十六进制显示；bit i为1表示任务i的量化结果已写完 |
| slot_states | 调度器→观察端，slot1为高3位、slot0为低3位；0空闲、1待卷积、2卷积中、3待后处理、4后处理中。显示的是打包数值，不是单个状态码。 |
| done / error / memory_fault | 整批结束、执行错误、SRAM访问错误；通过用例两种错误全程为0 |

没有UART输入波形，因为这次图像是SRAM预加载。看到卷积读取请求，表示从SRAM取数据，不等于串口正在接收图片。

## 时间与对照

| 模式 | 100MHz硬件周期 | 对应硬件时间 | 电脑实际仿真时间 |
|---|---:|---:|---:|
| 条带并行 | {m['cycles']:,} | {m['cycles']/100:.2f} µs | {tim['parallel']:.2f} 秒 |
| 同一任务图顺序执行 | {s['cycles']:,} | {s['cycles']/100:.2f} µs | {tim['serial']:.2f} 秒 |
| 反压+中途清除后重启 | {r['cycles']:,} | {r['cycles']/100:.2f} µs | {tim['stalled_restart']:.2f} 秒 |

本次首次编译 **{tim['compile']:.2f}秒**，整个运行脚本总耗时 **{tim['total']:.2f}秒**。复位重启用例的周期数统计重启后的完整任务，电脑耗时还包含被中断的预热段。100MHz是仿真设定，没有通过综合证明最高频率。

顺序/并行周期比为 **{result['serial_over_parallel_cycles']:.3f}**。它只比较同一小区域、同一条带任务图是否允许重叠，不是完整网络、人脸识别或UART端到端性能承诺，也不是与前一版整层任务划分的直接性能比较。

## 文件、复现与下一步

设计说明见 [调度与缓冲约定](../../docs/mobilefacenet_pipeline_design.md)，数值格式沿用 [整数约定](../../docs/mobilefacenet_quant_contract.md)。新模块在 `rtl/cnn_quant/quant_stripe_scheduler.sv`；原顺序小链条和上一轮小例保留。

Windows生成数据：`scripts/gen_mobilefacenet_pipeline.py build/mobilefacenet_pipeline_data`。WSL运行已有匹配程序：`python3 scripts/run_mobilefacenet_pipeline.py --reuse --data build/mobilefacenet_pipeline_data`。只在RTL/监视器改变时去掉`--reuse`重新编译；输入/参数变化仍要生成新的金标准。每次保存独立运行目录，缓存为 `.neureka_pipeline_build`。

下一步再接分批输入的行就绪通知和输入缓冲回收，然后扩展更长网络的残差依赖。CPU命令提交、UART流式输入、循环行缓冲、完整量化校准、GDConv7×7硬件、全网络推理和多NEureka仍未完成。内部预取沿用关闭配置；本次没有修复第三方预取问题，也未使用GPU。
'''
    (out/'README.md').write_text(guide,encoding='utf-8')
    print(out)
if __name__=='__main__':main()
