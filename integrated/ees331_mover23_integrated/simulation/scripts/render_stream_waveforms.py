"""Plot actual exported VCD transitions; never synthesize illustrative waveforms."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).absolute().parents[1]
OUT = ROOT / 'deliverables/stream_six_images'
CAT = json.loads((OUT/'signal_catalog.json').read_text(encoding='utf-8'))

def read_vcd(path, wanted):
    codes, values, t = {}, {}, 0
    with path.open() as f:
        for line in f:
            if line.startswith('$var'):
                p=line.split()
                if p[4] in wanted:
                    codes.setdefault(p[3], []).append(p[4]); values[p[4]]=[]
            elif line.startswith('#'): t=int(line[1:])
            elif line[0:1] in '01xz' and line.strip():
                code=line[1:].strip()
                if code in codes: add(values,codes[code],t,line[0])
            elif line.startswith('b'):
                v,code=line[1:].split()
                if code in codes: add(values,codes[code],t,v)
    assert set(values)==set(wanted), set(wanted)-set(values)
    return values

def add(values,names,t,v):
    try: v=int(v,2)
    except ValueError: pass
    for n in names:
        a=values[n]
        if a and a[-1][0]==t: a[-1]=(t,v)
        elif not a or a[-1][1]!=v: a.append((t,v))

COLORS={'CPU CORE':'#76b6ff','CNN':'#ff959d','DATASRAM':'#ffc76b','IMEM':'#c6a0ff','IMAGE_BRIDGE':'#60ded1','CLOCK':'#8ed47d','外部':'#c7d2e0','顶层':'#e3eaf3'}
FONT='C:/Windows/Fonts/msyh.ttc'
def plot(file,title,subtitle,data,names,t0,t1,unit,ticks,notes):
    W,L,R,TOP,ROW=1900,370,1840,175,62
    H=TOP+ROW*len(names)+140
    im=Image.new('RGB',(W,H),'#0e1726'); d=ImageDraw.Draw(im)
    f=ImageFont.truetype(FONT,20); small=ImageFont.truetype(FONT,17); head=ImageFont.truetype(FONT,31)
    d.text((35,25),title,font=head,fill='#ffffff'); d.text((35,77),subtitle,font=f,fill='#b8c7d9')
    scale=1e9 if unit=='ms' else 1e6
    X=lambda t:L+(t-t0)/(t1-t0)*(R-L)
    for tick in ticks:
        x=X(tick*scale); d.line((x,TOP-15,x,TOP+ROW*len(names)),fill='#29374c')
        d.text((x-25,TOP-47),f'{tick:g}',font=small,fill='#cad6e5')
    d.text((R-30,TOP-78),unit,font=f,fill='#ffffff')
    for i,n in enumerate(names):
        y=TOP+i*ROW; source=CAT[n]['source']; color=COLORS.get(source,'#e3eaf3')
        d.text((24,y+9),n,font=f,fill=color)
        d.line((20,y+ROW-4,R,y+ROW-4),fill='#1b283b')
        a=data[n]; segments=[]
        for j,(t,v) in enumerate(a):
            end=a[j+1][0] if j+1<len(a) else t1
            if end<=t0 or t>=t1:continue
            segments.append((max(t,t0),min(end,t1),v))
        if CAT[n]['width']==1:
            last=None
            for st,en,v in segments:
                yy=y+12 if v==1 else y+43; x1,x2=X(st),X(en)
                if last is not None:d.line((x1,last,x1,yy),fill=color,width=2)
                d.line((x1,yy,max(x1+1,x2),yy),fill=color,width=2); last=yy
        else:
            for st,en,v in segments:
                x1,x2=X(st),X(en); length=x2-x1
                if length<3:d.line((x1,y+11,x1,y+43),fill=color);continue
                d.line([(x1,y+27),(x1+3,y+11),(x2-3,y+11),(x2,y+27),(x2-3,y+43),(x1+3,y+43),(x1,y+27)],fill=color,width=2)
                label={0:'RESET',1:'IDLE',2:'WORK',3:'FAULT'}.get(v,str(v)) if n.endswith('_state') else (f'0x{v:X}' if n in ['pixel_data','cnn_valid','cnn_ready','soc_fault'] and isinstance(v,int) else str(v))
                tw=d.textlength(label,font=small)
                if tw+10<length:d.text(((x1+x2-tw)/2,y+15),label,font=small,fill=color)
    for j,note in enumerate(notes): d.text((35,TOP+ROW*len(names)+20+j*29),note,font=small,fill='#c5d3e3')
    im.save(OUT/file)

def main():
    localnames=['uart_rx','rx_receiving','pixel_valid','pixel_data','pixel_ready','compute_fire','cnn_valid','cnn_ready','cnn_response','cnn_state','sram_state']
    local=read_vcd(OUT/'all_modules.vcd',localnames)
    print('LOCAL', {n:len(a) for n,a in local.items()},flush=True)
    print('COMPUTE',local['compute_fire'][:15],flush=True)
    print('RX',local['rx_receiving'][:10],flush=True)
    # A narrow view exposes individual cycles, bus handshakes and serial bits.
    plot('wave_overlap.png','UART 接收与 CNN 计算重叠 · 真实波形','第 1 帧局部放大；每行只出现一次，按信号来源模块着色。',local,localnames,858000000,859200000,'us',[858,858.2,858.4,858.6,858.8,859,859.2],[
        'pixel_valid 与 pixel_ready 在时钟上升沿同为 1 才传递像素；compute_fire 表示已执行一次双路卷积。',
        'cnn_valid / cnn_ready / cnn_response 是通道位图（十六进制）；位 0 / 1 为 X / Y 特征。'])
    fullnames=['cpu_state','cnn_state','bridge_state','clock_state','pixel_frame','frame_done','frames_done','soc_fault']
    full=read_vcd(OUT/'all_frames.vcd',fullnames)
    plot('wave_six_frames.png','六张 524×524 图片 · 全程进度','来自本次 RTL 仿真的 FST/VCD；时间为设计时间，100 MHz。',full,fullnames,0,717108930000,'ms',[0,100,200,300,400,500,600,700],[
        'pixel_frame：当前帧编号 0～5；frames_done：已完成帧数 0～6；frame_done：单帧完成脉冲。',
        '此比例下窄脉冲显示为竖线；WORK 包括等待，不等于每拍都在计算。完整六模块状态请打开 GTKWave。'])
    (OUT/'wave_image_provenance.json').write_text(json.dumps({'source':'wave_windows.json / provenance.json','images':{'wave_overlap.png':{'start_ps':858000000,'end_ps':859200000,'signals':localnames},'wave_six_frames.png':{'start_ps':0,'end_ps':717108930000,'signals':fullnames}},'rendering':'Actual VCD transitions; narrow pulses rendered at minimum one pixel; no invented transitions'},indent=2))
    print('Saved both waveform images',flush=True)

if __name__=='__main__':main()
