"""Package verified small-chain controls, without full PE-array waveforms."""
import argparse,hashlib,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
    result=json.loads((run/'result.json').read_text());assert result['status']=='PASS'
    for name,h in result['build_inputs']['hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    out=ROOT/'deliverables/mobilefacenet_chain';out.mkdir(exist_ok=True)
    for name in ['control.vcd','events.csv','workload.json','sim.log']:shutil.copyfile(run/'normal'/name,out/name)
    shutil.copyfile(run/'result.json',out/'result.json')
    v=read_vcd(out/'control.vcd');sig={n.removeprefix('chain.'):s for n,s in v.signals.items()}
    assert len({s.code for s in sig.values()})==len(sig)
    assert not any(b=='1' for _,b in sig['memory_fault'].events)
    t=next(t for t,b in sig['post_write_fire'].events if b=='1')
    names=['job','conv_start','core_busy','core_state','accum_done','prefetch_done','conv_read_fire','conv_write_fire','cdone',
           'post_start','mode_add','pbusy','post_read_fire','post_write_fire','pdone','memory_fault']
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
    for stem,title,left,right in [('01_overview','真实权重小区域：三层卷积、量化激活与残差单元检查',0,v.end_ns),
                                  ('02_quant_write','首次后处理：读 INT32 累加值，写 UINT8 激活',max(0,t-500),t+1200)]:
        im=Image.new('RGB',(1800,820),'#f7f9fc');d=ImageDraw.Draw(im);x0=310;x1=1760;top=145
        x=lambda ns:x0+(ns-left)/(right-left)*(x1-x0)
        d.text((24,20),title,font=font(27),fill='#243a52')
        d.text((24,66),'100 MHz · 真实 RTL 控制信号 · SRAM 预加载 · 顺序小链条，非完整网络/串口仿真',font=font(19),fill='#52637b')
        for j in range(9):
            xx=x0+(x1-x0)*j/8;tt=left+(right-left)*j/8
            d.line((xx,top-12,xx,780),fill='#dce4ed');d.text((min(xx-20,1655),top-40),f'{tt/1000:.3f} µs',font=font(14),fill='#52637b')
        for i,n in enumerate(names):
            y=top+i*39;c='#8b57b1' if n in names[1:9] else ('#167f64' if n in names[9:15] else '#2e5f91')
            d.text((24,y),n,font=font(19),fill=c);prev=None
            for l,r,bits in segments(sig[n],left,right):
                xa,xb=x(l),x(r)
                if set(bits)-set('01'):continue
                if sig[n].width==1:
                    yy=y+3 if int(bits,2) else y+25
                    if prev is not None:d.line((xa,prev,xa,yy),fill=c,width=2)
                    d.line((xa,yy,xb,yy),fill=c,width=2);prev=yy
                else:
                    d.rectangle((xa,y+3,xb,y+25),outline=c)
                    if xb-xa>30:d.text((xa+3,y+2),str(int(bits,2)),font=font(15),fill=c)
        im.save(out/(stem+'.png'))
    lines=['[*] Real RTL MobileFaceNet ROI controls','[dumpfile] "'+str(out/'control.vcd').replace('\\','/')+'"','[savefile] "'+str(out/'control.gtkw').replace('\\','/')+'"','[timestart] 0']
    for n in names:
        s=sig[n]
        lines+=['@28' if s.width==1 else '@22','[color] '+('3' if n in names[1:9] else '2' if n in names[9:15] else '4'),s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
    (out/'control.gtkw').write_text('\n'.join(lines)+'\n')
    (out/'open_gtkwave.cmd').write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0control.gtkw"\n')
    (out/'verify.tcl').write_text('set out [file dirname [file normalize [info script]]]\nset shown [gtkwave::getDisplayedSignals]\nif {[llength $shown] != 16} {error "signal count mismatch"}\nset f [open [file join $out gtkwave_validation.log] w]\nputs $f "PASS COUNT=[llength $shown]"\nclose $f\ngtkwave::/File/Quit\n')
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),signals=names,first_post_write_ns=t),indent=2))
    print(out)
if __name__=='__main__':main()
