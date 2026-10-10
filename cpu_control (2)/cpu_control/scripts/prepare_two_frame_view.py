"""Readable activity overview and exact edge-level write views from real FST data."""
import csv,json,html
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).absolute().parents[1];OUT=ROOT/'deliverables/stream_six_images'
FONT='C:/Windows/Fonts/msyh.ttc'
F=lambda n:ImageFont.truetype(FONT,n)
BG='#101a29';INK='#e6edf7';MUTED='#b4c3d6';GRID='#2a394d'
CYAN='#5fe0d4';RED='#ff929a';GOLD='#ffcf73';BLUE='#a2c8ff'
rows=lambda name:list(csv.DictReader((OUT/name).open()))
activity=[{k:int(v) for k,v in r.items()} for r in rows('two_frame_activity.csv')]
writes=[{k:int(v) for k,v in r.items()} for r in rows('two_frame_writes.csv')]
events=[{k:(v if k=='event' else int(v)) for k,v in r.items()} for r in rows('two_frame_events.csv')]
actual=(OUT/'actual.bin').read_bytes()
assert len(writes)==272484
for i,r in enumerate(writes):
    assert r['address']==0x1000+i,(i,r)
    assert r['data']==actual[i],(i,r)
for frame in range(2):
    assert sum(r['frame']==frame for r in writes)==136242
assert sum(r['compute_cycles'] for r in activity)==544968

def overview():
    im=Image.new('RGB',(1900,1230),BG);d=ImageDraw.Draw(im);L,R=285,1840
    X=lambda ms:L+ms/226.7771*(R-L)
    d.text((35,25),'前两张图片：接收、实际计算、写回发生在同一时间段',font=F(31),fill=INK)
    d.text((35,78),'全程 0～226.7771 ms；每根细柱汇总 0.25 ms 内的真实活动，不代表该时间格内每拍都工作。',font=F(21),fill=MUTED)
    for start,end,label in [(0,113.390465,'第 1 张 · frame 0'),(113.390465,226.777045,'第 2 张 · frame 1')]:
        d.rectangle((X(start),130,X(end)-2,176),fill='#243751')
        d.text(((X(start)+X(end))/2-120,136),label,font=F(22),fill=INK)
    panels=[(220,'UART 正在接收','rx_receiving / 时间占比','rx_ps',CYAN),(410,'CNN 实际卷积','compute_fire / 周期数','compute_cycles',RED),(600,'CNN → SRAM 写回','握手成功 / 字节数','write_bytes',GOLD)]
    for top,title,sub,key,col in panels:
        d.text((28,top+25),title,font=F(23),fill=col);d.text((28,top+65),sub,font=F(16),fill=MUTED)
        vals=[r[key]/(r['end_ps']-r['start_ps'])*100 if key=='rx_ps' else r[key] for r in activity]
        mx=100 if key=='rx_ps' else max(vals)
        for tick in [0,50,100,150,200,226.7771]:
            x=X(tick);d.line((x,top,x,top+120),fill=GRID)
        for row,v in zip(activity,vals):
            x1=X(row['start_ps']/1e9);x2=X(row['end_ps']/1e9)
            if v:d.rectangle((x1,top+120-v/mx*115,max(x1+1,x2),top+120),fill=col)
        d.text((L,top+130),f'最大值：{mx:g}'+(' %' if key=='rx_ps' else ' / 时间格'),font=F(16),fill=col)
    for t in [0,50,100,113.390465,150,200,226.777045]:
        label=f'{t:.3f}' if t not in [0,50,100,150,200] else str(t)
        d.text((X(t)-24,774),label,font=F(17),fill=MUTED)
    d.text((1780,809),'时间 / ms',font=F(18),fill=INK)
    eof=[r for r in events if r['event']=='pixel_eof_handshake']
    assert [r['frame'] for r in eof]==[0,1]
    d.text((28,850),'pixel_eof',font=F(23),fill=CYAN)
    d.line((L,894,R,894),fill=CYAN,width=2)
    for r in eof:
        x=X(r['time_ps']/1e9);d.line((x,864,x,894),fill=CYAN,width=3)
    d.text((L,906),'窄标记按最少一像素显示；两次 valid && ready && eof 握手分别表示两张图片交给 CNN 完成。',font=F(17),fill=MUTED)
    first=[r for r in events if r['event']=='first_write'];done=[r for r in events if r['event']=='frame_done']
    for i,(a,b) in enumerate(zip(first,done)):
        y=975+i*65
        d.text((35,y),f'第 {i+1} 张：首次写回 {a["time_ps"]/1e9:.6f} ms → 写回完成 {b["time_ps"]/1e9:.6f} ms；136242 字节',font=F(23),fill=GOLD)
    d.text((35,1140),'判断方法：三个活动条在同一横坐标出现活动；精确到哪一拍、写哪个地址，请看后面的 100 ns 放大图。',font=F(20),fill=MUTED)
    im.save(OUT/'first_two_overview.png')

def detail(frame,start):
    end=start+100000;names=['clk','uart_rx','rx_receiving','pixel_valid','pixel_eof','pixel_ready','compute_fire','cnn_valid','cnn_ready','cnn_response','cnn_addr','cnn_wdata']
    values={n:[] for n in names}
    for row in rows('two_frame_detail.csv'):
        t=int(row['time_ps']);n=row['signal'];v=int(row['value'])
        if n in values and start<=t<=end:
            a=values[n]
            if a and a[-1][0]==t:a[-1]=(t,v)
            elif not a or a[-1][1]!=v:a.append((t,v))
    assert all(a and a[0][0]==start for a in values.values())
    selected=[r for r in writes if start<=r['time_ps']<=end]
    assert selected and values['rx_receiving'][0][1]==1
    W,L,R,T,ROW=1900,355,1830,160,49
    im=Image.new('RGB',(W,1130),BG);d=ImageDraw.Draw(im);X=lambda t:L+(t-start)/100000*(R-L)
    d.text((30,20),f'第 {frame+1} 张：UART 接收期间，CNN 实际计算并写入 SRAM',font=F(30),fill=INK)
    d.text((30,70),f'绝对时间 {start/1e6:.3f}～{end/1e6:.3f} μs（仅 100 ns）；虚线标出真正写入 SRAM 的时钟上升沿。',font=F(20),fill=MUTED)
    for t in range(start,end+1,10000):
        x=X(t);d.line((x,T-8,x,T+ROW*len(names)),fill=GRID)
        d.text((x-30,122),f'+{(t-start)//1000}',font=F(17),fill=MUTED)
    d.text((R-8,100),'ns',font=F(16),fill=MUTED)
    for r in selected:
        x=X(r['time_ps'])
        for y in range(T,T+ROW*len(names),9):d.line((x,y,x,y+4),fill='#856538')
    for i,n in enumerate(names):
        y=T+i*ROW
        color=CYAN if n in ['pixel_valid','pixel_eof','rx_receiving'] else GOLD if n in ['cnn_ready','cnn_response'] else RED if n not in ['clk','uart_rx'] else BLUE
        label=n+('  X / Y' if n in ['cnn_addr','cnn_wdata'] else '')
        d.text((25,y+7),label,font=F(20),fill=color)
        a=values[n]
        for j,(t,v) in enumerate(a):
            stop=a[j+1][0] if j+1<len(a) else end
            if stop<=t:continue
            x1,x2=X(t),X(stop)
            if n in ['clk','uart_rx','rx_receiving','pixel_valid','pixel_eof','pixel_ready','compute_fire']:
                yy=y+9 if v else y+36
                if j and a[j-1][1]!=v:d.line((x1,y+9,x1,y+36),fill=color,width=2)
                d.line((x1,yy,x2,yy),fill=color,width=2)
                if x2-x1>150:d.text(((x1+x2)/2-7,y+12),str(v),font=F(16),fill=color)
            else:
                d.line([(x1,y+23),(x1+4,y+8),(x2-4,y+8),(x2,y+23),(x2-4,y+38),(x1+4,y+38),(x1,y+23)],fill=color,width=2)
                if n in ['cnn_addr','cnn_wdata']:s=f'0x{v&0xffffffff:X} / 0x{v>>32:X}'
                else:s=f'0x{v:X}'
                tw=d.textlength(s,font=F(16))
                if tw+8<x2-x1:d.text(((x1+x2-tw)/2,y+11),s,font=F(16),fill=color)
    y=785;d.text((30,y),'实际写入记录（按上升沿之前的 valid / ready / address / data 采样）',font=F(22),fill=GOLD)
    for i,r in enumerate(selected):
        text=f'{r["time_ps"]/1e6:.3f} μs   通道 {r["channel"]} ({"X" if r["channel"]==0 else "Y"})   地址 0x{r["address"]:05X}   写入 0x{r["data"]:02X}'
        d.text((45,y+38+i*31),text,font=F(21),fill=INK)
    d.text((30,1050),'注意：上升沿后 valid 可能清零、ready 切到另一通道；判断本拍写入，要看虚线左侧的请求值。',font=F(20),fill=MUTED)
    im.save(OUT/f'frame_{frame+1}_write_detail.png')
    return selected

overview();samples=[detail(0,858000000),detail(1,114244650000)]

# GTKWave source nets appear once each, grouped by their driving module.
cat=json.loads((OUT/'signal_catalog.json').read_text(encoding='utf-8'))
groups=[('CLOCK',2,['clk']),('UART INPUT',0,['uart_rx']),('IMAGE_BRIDGE',6,['rx_receiving','pixel_valid','pixel_eof','pixel_data','pixel_frame']),('CNN',1,['pixel_ready','compute_fire','cnn_valid','cnn_write','cnn_byte','cnn_addr','cnn_wdata','frame_done','frames_done']),('DATASRAM',3,['cnn_ready','cnn_response'])]
eof_windows=[(f'frame_{r["frame"]+1}_end',r['time_ps']-100000,min(r['time_ps']+150000,226777100000)) for r in events if r['event']=='pixel_eof_handshake']
assert len(eof_windows)==2
for name,start,end in [('first_two',0,226777100000),('frame_1_write',858000000,858100000),('frame_2_write',114244650000,114244750000),*eof_windows]:
    lines=[f'[dumpfile] "{OUT/"first_two.fst"}"',f'[timestart] {start}','[size] 1800 1050','[signals_width] 340','[sst_width] 160','*-15 -1 '+' '.join(['-1']*26)]
    for title,col,ns in groups:
        lines+=['@200','-'+title]
        for n in ns:
            w=cat[n]['width'];lines+=['@28' if w==1 else '@22',f'[color] {col}','stream_top.'+n+(f'[{w-1}:0]' if w>1 else '')]
    (OUT/(name+'.gtkw')).write_text('\n'.join(lines)+'\n')
    (OUT/('open_'+name+'.cmd')).write_text(f'@echo off\ncd /d "%~dp0"\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0first_two.fst" -a "%~dp0{name}.gtkw" -S "%~dp0show_{name}.tcl"\n')
    commands=f'gtkwave::setZoomRangeTimes {start} {end}\ngtkwave::/View/Scale_To_Time_Dimension/{"ms" if name=="first_two" else "us"}\ngtkwave::/Edit/Set_Trace_Max_Hier 1\n'
    (OUT/('show_'+name+'.tcl')).write_text(commands)
    (OUT/('verify_'+name+'.tcl')).write_text(commands+f'set out [file dirname [file normalize [info script]]]\ngtkwave::/File/Write_Save_File_As [file join $out {name}.gtkw]\nset shown [gtkwave::getDisplayedSignals]\nset log [open [file join $out validation_{name}.log] w]\nputs $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\nclose $log\ngtkwave::/File/Quit\n')

summary={'status':'PASS','frames':2,'write_bytes':len(writes),'per_frame_bytes':136242,'compute_cycles':544968,'verified':'Every sampled write address is sequential from 0x1000 and every byte equals actual.bin; counts match reference output dimensions.','events':events,'detail_samples':samples,'overview_bin_ps':250000000,'end_ps':226777100000}
(OUT/'two_frame_validation.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
