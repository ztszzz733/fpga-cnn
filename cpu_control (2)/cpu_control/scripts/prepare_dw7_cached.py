"""Package actual cached-DW7 simulation results and compact control waveforms."""
import argparse,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);run=p.parse_args().run.resolve()
    r=json.loads((run/'result.json').read_text());assert r['status']=='PASS'
    for n,h in r['source_hashes'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    out=ROOT/'deliverables/dw7_cached';out.mkdir(exist_ok=True);shutil.copyfile(run/'result.json',out/'result.json')
    font=lambda s:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',s)
    views={}
    for case,title,names in [
        ('real512','真实512通道：第二张图复用缓存权重',['frame','start','cache_hit','weights_cached','weight_reads','input_reads','mac_fire','done','post_start','pbusy','pdone']),
        ('overlap16','重叠窗口：计算时使用内部数据，换输出行只补新行',['dut.block_c','dut.oy','dut.ox','dut.load_y','phase','input_reads','mac_fire','valid','ready','write','done'])]:
        v=read_vcd(run/case/'control.vcd');sig={n:v.signals['tb_dw7_cached.'+n] for n in names};assert len({s.code for s in sig.values()})==len(names)
        lastdone=max(t for t,b in v.signals['tb_dw7_cached.pdone'].events if b=='1')
        left=0;right=lastdone+20
        if case=='overlap16':
            left=next(t for t,b in v.signals['tb_dw7_cached.mac_fire'].events if b=='1')-100
            # Capture the first channel block's horizontal windows and row refill.
            right=left+4500
        views[case]=dict(names=names,left_ns=left,right_ns=right)
        changes={};header=['$timescale 1ns $end','$scope module dw7 $end']
        for i,(n,s) in enumerate(sig.items()):
            header.append(f'$var wire {s.width} s{i} {n.replace(".","_")} $end')
            for t,b in s.events:changes.setdefault(round(t),[]).append(f'b{b} s{i}')
        header+=['$upscope $end','$enddefinitions $end'];body=[]
        for t in sorted(changes):body+=['#'+str(t),*changes[t]]
        (out/(case+'.vcd')).write_text('\n'.join(header+body)+'\n')
        top=135;rh=42;w=1800;h=top+rh*len(names)+45;im=Image.new('RGB',(w,h),'#f7f9fc');d=ImageDraw.Draw(im)
        d.text((24,20),title,font=font(26),fill='#243a52');d.text((24,65),'真实RTL · 100MHz仿真时钟 · 原始结果→已有后处理 · 非完整CNN调度器',font=font(18),fill='#52637b')
        x=lambda t:310+(t-left)/(right-left)*1450
        for i in range(9):
            t=left+(right-left)*i/8;xx=x(t);d.line((xx,top-10,xx,h-25),fill='#dce4ed');d.text((min(xx-20,1640),top-35),f'{t/1000:.3f} µs',font=font(14),fill='#52637b')
        for i,n in enumerate(names):
            s=sig[n];y=top+i*rh;c='#8658bd' if n in ['mac_fire','dut.oy','dut.ox','dut.block_c'] else '#138360';d.text((24,y),n,font=font(18),fill=c);prev=None
            for l,rr,b in segments(s,left,right):
                if set(b)-set('01'):continue
                a,z=x(l),x(rr)
                if s.width==1:
                    yy=y+3 if int(b,2) else y+25
                    if prev is not None:d.line((a,prev,a,yy),fill=c,width=2)
                    d.line((a,yy,z,yy),fill=c,width=2);prev=yy
                else:
                    d.rectangle((a,y+3,z,y+25),outline=c);val=str(int(b,2))
                    if z-a>max(25,len(val)*10):d.text((a+3,y+2),val,font=font(15),fill=c)
        im.save(out/(case+'.png'))
        gtk=['[dumpfile] "'+str(out/(case+'.vcd')).replace('\\','/')+'"']
        for n,s in sig.items():gtk+=['@28' if s.width==1 else '@24','[color] 2','dw7.'+n.replace('.','_')+(f'[{s.width-1}:0]' if s.width>1 else '')]
        (out/(case+'.gtkw')).write_text('\n'.join(gtk)+'\n')
        tcl=['gtkwave::/View/Scale_To_Time_Dimension/us',f'gtkwave::setZoomRangeTimes {int(left)} {int(right)}']
        (out/(case+'.tcl')).write_text('\n'.join(tcl)+'\n')
        (out/('verify_'+case+'.tcl')).write_text('\n'.join(tcl+['set shown [gtkwave::getDisplayedSignals]',f'if {{[llength $shown] != {len(names)}}} {{error "signal count mismatch"}}','set f [open [file join [file dirname [info script]] gtkwave_validation.log] a]',f'puts $f "PASS {case} COUNT=[llength $shown]"','close $f','gtkwave::/File/Quit'])+'\n')
        (out/('open_'+case+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0'+case+'.vcd" -a "%~dp0'+case+'.gtkw" -S "%~dp0'+case+'.tcl"\n')
    for case in r['cases']:
        shutil.copyfile(run/case/'sim.log',out/(case+'_sim.log'));shutil.copyfile(run/case/'workload.json',out/(case+'_workload.json'))
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),views=views),indent=2))
    tim=r['timing_seconds'];rows='\n'.join(f"| {n} | {m['checked_bytes']} | {m['conv_cycles']} | {tim[n]:.3f}秒 |" for n,m in r['cases'].items())
    text=f'''# 7×7逐通道卷积：内部缓存与复用验证

五项小数据RTL仿真 **PASS**。新增独立 `dw7_cached_engine`，8路通道乘加、完整权重缓存、七行循环输入缓存。已串接原 `quant_post_engine`；尚未接到CNN多算子调度器，也未改CPU/UART/存储顶层。

## 真实配置与结果

MobileFaceNet `/Conv_49`：7×7×512→1×1×512，真实预训练权重；两张人脸的前缀网络由软件执行后提供本层输入。硬件原始INT32和后处理UINT8均逐字节核对。当前尺度为诊断尺度，不是准确率校准或全网RTL通过。

| 用例 | 核对字节数 | 两帧卷积周期 | 电脑运行耗时 |
|---|---:|---|---:|
{rows}

最终这次编译{tim['compile']:.2f}秒，五项运行合计{sum(tim[n] for n in r['cases']):.2f}秒，总流程{tim['total']:.2f}秒。未重编译NEureka。真实正常例两帧卷积分别423.70µs、235.54µs；连同后处理分别536.35µs、348.19µs，按100MHz换算，不是综合后的性能承诺。

## 复用证据

- 真实512通道例：每帧输入读取6,272个32位字＝25,088字节；权重首帧读取6,272字，第二帧0字。不能再宣称其输入窗口复用带来额外节省，因为7×7→1×1本来只有一个空间输出。
- 9×10×16→3×4×16重叠窗口例：逐输出重读的输入量为3×4×16×49＝9,408字节；实际每帧只读9×10×16＝1,440字节，降低约84.7%。这是与无缓存逐窗口读取的算术比较，不是与NEureka实测速度比较。
- 断言每个输入字地址只读取一次，乘加拍数为49×输出元素数/8；第二帧复用权重。限速/可变响应延迟、负权重极值、取消重启、非法配置、不可写区检查均通过。
- 首次运行 `20261022_171724_dw7_cached` 的错误参数测试晚一拍采样，误报错误脉冲丢失；修正TB后重跑通过，失败记录保留。没有把该失败当作PASS。

## 波形

- [两帧真实计算与权重复用](real512.png)：第二帧cache_hit=1，weight_reads保持0，input_reads继续增长；mac_fire高时8路执行乘加，done在最终INT32写响应后出现，随后post_start启动后处理。
- [相邻窗口复用细节](overlap16.png)：ox变化代表横向移动；MAC期间input_reads不变，换输出行时load_y推进，只加载新行。phase=3/4为输入读取，6为乘加，7/8为结果写入。
- GTKWave双击 `open_real512.cmd` 或 `open_overlap16.cmd`。每个视图11条不重复信号；VCD从实际仿真筛选，原始全信号记录保留在运行目录。图只截取正常计算区间，完整VCD尾部包含刻意触发的非法配置错误测试。

## 接入限制

输入必须提前在SRAM中准备好；本模块没有外部行就绪接口。内部缓存减少重复访问，但加载/计算/写出尚未重叠。INT32结果仍写回SRAM，再由原后处理读取。

支持stride1、无padding、8倍数通道、默认最大512通道；权重为tap-major二补码INT8，不能直接使用NEureka bit-plane权重文件。变更同地址权重时必须关闭复用或clear，否则会读到旧缓存。默认逻辑缓存约30.63KiB，未综合评估面积、BRAM推断、时序和功耗。

详细结构和接口见 [设计说明](../../docs/dw7_cached_design.md)。后续接入需要扩展调度任务类型、通道约束、客户端与缓冲分配，不能把本单元PASS写成完整CNN已经支持该层。
'''
    (out/'README.md').write_text(text,encoding='utf-8')
    (out/'SHA256.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file() and f.name not in ['SHA256.json','gtkwave_validation.log']},indent=2))
    print(out)
if __name__=='__main__':main()
