"""Generate unique waveform groups, actual output PNGs and interface reference."""
import argparse,csv,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from soc_top_signals import SIGNALS as OLD,STATES,UNITS,COLORS

ROOT=Path(__file__).absolute().parents[1]
OUT=ROOT/'deliverables/stream_six_images'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('run');args=parser.parse_args();run=Path(args.run).absolute()
    report=json.loads((run/'result.json').read_text());assert report['status']=='PASS' and not report['config']['fault']
    OUT.mkdir(parents=True,exist_ok=True)
    for f in ['result.json','manifest.json','events.csv','actual.bin']:shutil.copyfile(run/f,OUT/f)
    sig={n:dict(s) for n,s in OLD.items() if not n.startswith('io_mem_')}
    updates={
        'cnn_mmio_wdata':'CONTROL bit0 启动，bit1 取消；OUTPUT_BASE 指定结果起址。',
        'cnn_mmio_rdata':'STATUS busy/done/error，已完成帧数、消费像素数及固定尺寸。',
        'cnn_status_busy':'固定六帧处理正在进行；包括等待 UART 像素。',
        'cnn_status_done':'全部帧处理完成脉冲；STATUS done 同时保持为 1。',
        'cnn_status_error':'流错误、内存错误或像素边界错误，结果无效。',
        'led_busy':'bridge_busy OR cnn_status_busy。',
        'led_error':'bridge_error OR cnn_mem_fault OR cnn_status_error。',
        'cnn_valid':'位 0/1 分别是水平/垂直梯度特征写回；其余通道未使用。',
        'cnn_cancel':'CONTROL bit1 取消或 bridge_error 错误中止，不回滚已写入的结果。',
        'load_complete':'六张图的像素全部交给 CNN，或发生接收错误；计算收尾看 CNN done。',
        'load_error':'本批像素流失败，支持包格式、包 CRC、UART 帧和超时检测。'}
    for n,desc in updates.items():sig[n]['description']=desc
    additions=[
        ('pixel_valid',1,'IMAGE_BRIDGE','CNN','已校验像素有效；与 ready 同拍为 1 才传递。'),
        ('pixel_ready',1,'CNN','IMAGE_BRIDGE','CNN 可接收下一像素；写回未排空时反压。'),
        ('pixel_data',8,'IMAGE_BRIDGE','CNN','无符号灰度像素 0～255，逐行排列。'),
        ('pixel_sof',1,'IMAGE_BRIDGE','CNN','帧首像素标记，随像素握手。'),
        ('pixel_eof',1,'IMAGE_BRIDGE','CNN','帧尾像素标记，随像素握手。'),
        ('pixel_frame',32,'IMAGE_BRIDGE','CNN','帧编号 0～5，随像素握手。'),
        ('rx_receiving',1,'IMAGE_BRIDGE','顶层','UART 回复接收阶段，包括协议头、像素和 CRC。'),
        ('packets_checked',32,'IMAGE_BRIDGE','顶层','校验成功且发布给 CNN 的包数。'),
        ('compute_fire',1,'CNN','顶层','上一上升沿完成一个位置的两路 3×3 卷积。'),
        ('frame_done',1,'CNN','顶层','一帧全部结果写回响应排空后的脉冲。'),
        ('frames_done',32,'CNN','顶层','完成帧数，最终为 6。'),
        ('pixels_consumed',32,'CNN','顶层','已消费的累计像素数，最终为 1647456。')]
    for n,w,src,dst,desc in additions:sig[n]=dict(width=w,source=src,target=dst,description=desc,valid='像素字段按 valid && ready 采样')
    groups=[('TOP STATES',0,STATES+['soc_module_state','soc_active','soc_fault']),('EXTERNAL INPUTS',0,['sys_clk','rst_n_in','uart_rx'])]
    for unit,color in zip(UNITS,COLORS):groups.append((unit,color,[n for n,s in sig.items() if s['source']==unit]))
    groups.append(('TOP OUTPUTS',0,['led_ready','led_busy','led_error']))
    names=[n for _,_,g in groups for n in g];assert len(names)==len(set(names))==len(sig)
    (OUT/'state_names.txt').write_text('0 RESET\n1 IDLE\n2 WORK\n3 FAULT\n')
    events=list(csv.DictReader((run/'events.csv').open()))
    first=int(next(e['cycle'] for e in events if e['event']=='first_compute'))*10000
    end=report['metrics']['total_cycles']*10000;wave=run/'wave.fst'
    def trace(n):return 'stream_top.'+n+(f'[{sig[n]["width"]-1}:0]' if sig[n]['width']>1 else '')
    overview=[('FRAME PROGRESS AND STATES',0,STATES+['soc_module_state','soc_active','soc_fault','frame_done','frames_done','pixel_frame'])]
    for name,selected,t0,t1 in [('all_modules',groups,first-500000,first+35000000),('all_frames',overview,0,end),('power_on',groups,0,1500000)]:
        lines=[f'[dumpfile] "{OUT/(name+".fst")}"',f'[timestart] {t0}','[size] 1800 1050','[signals_width] 340','[sst_width] 160','*-25 -1 '+' '.join(['-1']*26)]
        count=0
        for title,color,ns in selected:
            lines+=['@200','-'+title]
            for n in ns:
                tint=COLORS[STATES.index(n)] if n in STATES else color
                lines+=['@2022' if n in STATES else '@28' if sig[n]['width']==1 else '@22',f'[color] {tint}']
                if n in STATES:lines+=['^1 state_names.txt']
                lines.append(trace(n));count+=1
        (OUT/f'{name}.gtkw').write_text('\n'.join(lines)+'\n')
        rel=Path(name+'.fst')
        (OUT/f'open_{name}.cmd').write_text(f'@echo off\nsetlocal\ncd /d "%~dp0"\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0{rel}" -a "%~dp0{name}.gtkw"\n')
        state_list=' '.join('{'+trace(n)+'}' for n in STATES)
        script=f'''set out [file dirname [file normalize [info script]]]
set log [open [file join $out validation_{name}.log] w]
set filter [gtkwave::setCurrentTranslateFile [file join $out state_names.txt]]
set states [list {state_list}]
gtkwave::highlightSignalsFromList $states
gtkwave::installFileFilter $filter
gtkwave::unhighlightSignalsFromList $states
gtkwave::setZoomRangeTimes {t0} {t1}
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out {name}.gtkw]
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {{[llength $shown]!={count} || [llength [lsort -unique $shown]]!={count}}} {{puts $log "FAIL signal count"}}
gtkwave::setMarker {1000000 if name=='power_on' else first+100000}
set value [gtkwave::getTraceValueAtMarkerFromName {{{trace('cnn_state')}}}]
puts $log "CNN_STATE=$value"
if {{![string match "*WORK*" $value]}} {{puts $log "FAIL state translation"}}
puts $log "PASS GTKWave stream session"
close $log
gtkwave::/File/Quit
'''
        (OUT/f'verify_{name}.tcl').write_text(script)
    (OUT/'signal_catalog.json').write_text(json.dumps(sig,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'provenance.json').write_text(json.dumps(dict(run=str(run),wave=str(wave),signal_count=len(names),wave_sha256=hashlib.sha256(wave.read_bytes()).hexdigest(),signal_names=names),indent=2))
    actual=(run/'actual.bin').read_bytes();manifest=report['manifest'];w=manifest['output_width'];h=manifest['output_height'];n=w*h
    tiles=[]
    for f in range(manifest['frames']):
        inp=Image.open(run/f'input_{f+1:02}.pgm');inp.save(OUT/f'input_{f+1:02}.png')
        frame=actual[f*n*2:(f+1)*n*2];imgs=[inp]
        for ci,axis in enumerate(['x','y']):
            img=Image.frombytes('L',(w,h),frame[ci::2]);img.save(OUT/f'feature_{f+1:02}_{axis}.png');imgs.append(img)
        tiles.append(imgs)
    contact=Image.new('RGB',(900,manifest['frames']*320+70),'#f4f6f8');pen=ImageDraw.Draw(contact)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
    for c,title in enumerate(['UART input 524 x 524','Sobel X + maxpool','Sobel Y + maxpool']):pen.text((c*300+15,20),title,font=font,fill='#172233')
    for f,imgs in enumerate(tiles):
        for ci,img in enumerate(imgs):contact.paste(img.resize((270,270)),(ci*300+15,70+f*320))
        pen.text((15,345+f*320),f'Frame {f+1}: '+manifest['input_names'][f],font=font,fill='#172233')
    contact.save(OUT/'results_overview.png')
    gallery='<html lang="zh-CN"><meta charset="utf-8"><title>六帧图片与实际特征结果</title><style>body{font:17px Microsoft YaHei;background:#f4f6f8;padding:30px}table{border-collapse:collapse}td,th{padding:12px;border:1px solid #ddd;background:white}img{width:261px;height:261px}</style><h1>六帧图片与实际 SRAM 特征结果</h1><p>输入 524×524 灰度图；输出两张 261×261 特征图。输出 PNG 来自实际 SRAM 数据，逐字节比对通过。</p><table><tr><th>帧</th><th>UART 输入</th><th>水平方向梯度</th><th>垂直方向梯度</th></tr>'
    for f in range(manifest['frames']):
        files=[f'input_{f+1:02}.png',f'feature_{f+1:02}_x.png',f'feature_{f+1:02}_y.png']
        gallery+=f'<tr><td>{f+1}</td>'+''.join(f'<td><a href="{x}"><img src="{x}"></a></td>' for x in files)+'</tr>'
    (OUT/'results.html').write_text(gallery+'</table></html>',encoding='utf-8')
    rows=['| 信号 | 位宽 | 来源 → 去向 | 功能 |','|---|---:|---|---|']
    rows += [f'| {n} | {sig[n]["width"]} | {sig[n]["source"]} → {sig[n]["target"]} | {sig[n]["description"]} |' for n in names]
    (OUT/'信号说明.md').write_text('# 图片流式版波形信号说明\n\n完整视图 '+str(len(names))+' 根信号，每个名称只出现一次，按输出端模块分组。\n\n'+'\n'.join(rows)+'\n',encoding='utf-8')
    print(f'Prepared {OUT}; {len(names)} unique waveform signals')
if __name__=='__main__':main()
