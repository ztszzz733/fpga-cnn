"""Package real small-run control VCDs, GTKWave sessions and overview plots."""
from pathlib import Path
import argparse,hashlib,json,shutil
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]

def parse(path):
    names={};data={};t=0
    for line in path.open():
        a=line.split()
        if not a:continue
        if a[0]=='$var':names[a[3]]=a[4];data[a[4]]=[]
        elif line.startswith('#'):t=int(line[1:])
        elif line.startswith('b') and len(a)==2:
            data[names[a[1]]].append((t,int(a[0][1:],2)))
    return data

def plot(data,path,start,end,title):
    rows=[('phase',None,'#ffffff'),('mmio_we',None,'#f781bf'),('mmio_re',None,'#f781bf'),
          ('mmio_ready',None,'#e6cf5a'),('config_state',None,'#c699ff'),
          ('cnn_valid',0,'#65b8ff'),('cnn_response',0,'#65b8ff'),
          ('cnn_valid',1,'#f0d45c'),('cnn_response',1,'#f0d45c'),
          ('read_state',None,'#65b8ff'),('write_state',None,'#f0d45c'),
          ('read_beats',None,'#65b8ff'),('write_beats',None,'#f0d45c'),('irq',None,'#71da94'),('fault',None,'#f77575')]
    image=Image.new('RGB',(1900,920),'#111820');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19)
    small=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
    draw.text((30,18),title,fill='white',font=font)
    x0,x1=260,1860
    def x(t):return x0+(t-start)*(x1-x0)/(end-start)
    for j in range(11):
        t=start+(end-start)*j/10;xx=x(t)
        draw.line((xx,70,xx,850),fill='#2b3641')
        label=f'{t/1000:.2f}'
        tx=min(xx-22,1880-draw.textlength(label,font=small))
        draw.text((tx,858),label,font=small,fill='#bfccd9')
    draw.text((730,894),'Hardware time (us), 100 MHz; control sampled from RTL',font=small,fill='white')
    for row,(name,bit,color) in enumerate(rows):
        series=data[name];selected=[(t,v) for t,v in series if start<=t<=end]
        before=[v for t,v in series if t<start]
        if before:selected.insert(0,(start,before[-1]))
        if not selected:selected=[(start,0)]
        selected.append((end,selected[-1][1]))
        y=82+row*50
        draw.text((18,y),name+(f'[{bit}]' if bit is not None else ''),fill=color,font=font)
        digital=bit is not None or name in ['mmio_we','mmio_re','mmio_ready','irq','fault']
        for (t,v),(tn,vn) in zip(selected,selected[1:]):
            left,right=x(t),x(tn)
            if digital:
                v=(v>>bit)&1 if bit is not None else v;vn=(vn>>bit)&1 if bit is not None else vn
                yy=y+25-v*22;draw.line((left,yy,right,yy),fill=color,width=2)
                if v!=vn:draw.line((right,yy,right,y+25-vn*22),fill=color,width=2)
            else:
                draw.line((left,y+3,right,y+3),fill=color);draw.line((left,y+28,right,y+28),fill=color)
                draw.line((left,y+3,left,y+28),fill=color)
                label=str(v)
                if right-left>len(label)*10+8:draw.text((left+4,y+5),label,fill=color,font=small)
    image.save(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);args=ap.parse_args()
    result=json.loads((args.run/'result.json').read_text())
    assert result['status']=='PASS','only package a completed passing run'
    for name,digest in result['source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest, name
    dest=ROOT/'deliverables/nvdla_small';dest.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(args.run/'result.json',dest/'result.json')
    for test in result['tests']:
        name=test['name'];src=args.run/name;out=dest/name;out.mkdir(exist_ok=True)
        for file in ['control.vcd','sim.log','metrics.json','commands.txt','memory_map.json','output.bin']:
            shutil.copyfile(src/file,out/file)
        data=parse(out/'control.vcd');end=test['hardware_ns_at_100MHz']
        assert all(v==0 for t,v in data['fault']) and any(v==1 for t,v in data['irq'])
        assert data['phase'][-1][1]==5 and test['read_beats']>0 and test['write_beats']>0
        plot(data,out/'overview.png',0,end,name+' | real NVDLA RTL + banked SRAM')
        first_write=next(t for t,v in data['write_beats'] if v>0)
        plot(data,out/'first_write.png',max(0,first_write-700),min(end,first_write+900),name+' | first completed 64-bit SRAM write')
        signals=['clk','rst_n','phase','mmio_addr','mmio_wdata','mmio_rdata','mmio_we','mmio_re','mmio_ready','config_state',
                 'cnn_valid','cnn_ready','cnn_response','cnn_write','read_state','write_state','read_beats','write_beats','irq','fault','host_addr','host_we','host_re']
        session='[*] NVDLA small test control signals, sampled from RTL\n[dumpfile] "'+str(out/'control.vcd').replace('\\','/')+'"\n[size] 1800 1000\n[signals_width] 280\n[timestart] 0\n'
        widths={'phase':3,'mmio_addr':32,'mmio_wdata':32,'mmio_rdata':32,'config_state':2,
                'cnn_valid':11,'cnn_ready':11,'cnn_response':11,'cnn_write':11,'read_state':3,'write_state':3,
                'read_beats':32,'write_beats':32,'host_addr':32}
        for i,s in enumerate(signals):
            # GTKWave appends a bus range even when the sampled VCD omits it.
            suffix=f'[{widths[s]-1}:0]' if s in widths else ''
            session+=('@22' if s in widths else '@28')+'\n[color] '+str(2+(i//4)%6)+'\nnvdla_small.'+s+suffix+'\n'
        (out/'control.gtkw').write_text(session)
        (out/'verify.tcl').write_text('set out [file dirname [file normalize [info script]]]\n'
            'set shown [gtkwave::getDisplayedSignals]\n'
            'set log [open [file join $out gtkwave_validation.log] w]\n'
            'if {[llength $shown] == 23} {puts $log "PASS COUNT=[llength $shown]"} else {puts $log "FAIL COUNT=[llength $shown]"}\n'
            'puts $log $shown\nclose $log\n'
            'gtkwave::/File/Quit\n')
        gtkw=ROOT/'tools/gtkwave/portable/gtkwave64/bin/gtkwave.exe'
        (out/'view.tcl').write_text(f'gtkwave::setZoomRangeTimes 0 {end}\n')
        (out/'open_wave.cmd').write_text('@echo off\r\nstart "" "'+str(gtkw)+'" -f "%~dp0control.vcd" -a "%~dp0control.gtkw" -S "%~dp0view.tcl"\r\n')
    table='\n'.join('| '+t['name']+' | '+f"{t['simulation_seconds']:.3f} s | {t['hardware_ns_at_100MHz']/1000:.2f} us | PASS |" for t in result['tests'])
    links='\n'.join('- ['+t['name']+' 全程]('+t['name']+'/overview.png) · [首次写回]('+t['name']+'/first_write.png) · [GTKWave 会话]('+t['name']+'/control.gtkw)' for t in result['tests'])
    readme=f'''# NVDLA 小图适配结果

来源运行：`{args.run.resolve()}`。已核对适配源码 SHA256、PASS 标记、无故障状态和读写活动。

本次使用真实 NVDLA nv_small 与本工程 banked SRAM。测试端驱动 CPU 风格的 MMIO/A 口；不包含 UART 输入或 CPU 执行指令，不是完整人脸识别网络。

本次运行的编译耗时：**{result['compile_seconds']:.3f} 秒**。这是该次编译记录，不包含此前环境准备和失败排查。每个用例独立复位，硬件时间包含装载、配置、运算、读回校验，按 100 MHz 计算。

| 小测试 | 电脑执行仿真时间 | 硬件时间（全程） | 结果 |
|---|---:|---:|---|
{table}

{links}

打开各子目录 `open_wave.cmd` 可用工程自带 GTKWave 观察。蓝色为读请求/响应，黄色为写回请求/响应，绿色为完成中断。`phase`：1 装载、2 配置、3 等完成、4 读回校验、5 结束。

详细接线、信号方向、状态编码、构建步骤和未覆盖范围见 [适配说明](../../docs/nvdla_small_integration.md)。每项的原始日志、输出字节、地址映射与寄存器命令也已保留。
'''
    (dest/'README.md').write_text(readme,encoding='utf-8')
    print(dest)

if __name__=='__main__':main()
