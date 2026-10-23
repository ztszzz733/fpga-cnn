"""Prepare actual small-RTL control traces; capacity result kept separate."""
import argparse,csv,hashlib,json,shutil,struct
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plot_waveforms import read_vcd,segments,Signal
ROOT=Path(__file__).resolve().parents[1]
def local(p):return Path('D:/'+p[7:]) if p.startswith('/mnt/d/') else Path(p)
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
 r=json.loads((run/'result.json').read_text());assert r['status']=='PASS'
 for path,h in r['build_inputs'].items():assert hashlib.sha256(local(path).read_bytes()).hexdigest()==h,path
 cap=ROOT/'build/network_parallel_data/full_plan';cr=json.loads((cap/'dispatch_result.json').read_text());assert cr['status']=='PASS'
 for path,h in cr['hashes'].items():assert hashlib.sha256(local(path).read_bytes()).hexdigest()==h,path
 out=ROOT/'deliverables/network_parallel';out.mkdir(exist_ok=True)
 for f in ['dispatch_result.json','dispatch.log']:shutil.copyfile(cap/f,out/f)
 shutil.copyfile(run/'result.json',out/'result.json')
 for case in ['dual','skew_stall']:
  src=run/case
  for n,h in r['data_hashes'].items():assert hashlib.sha256((src/n).read_bytes()).hexdigest()==h
  for f in ['control.vcd','events.csv','launches.csv','metrics.json','sim.log']:shutil.copyfile(src/f,out/(case+'_'+f))
  raw=read_vcd(src/'control.vcd');jobs=list(struct.iter_unpack('<16I',(src/'jobs.bin').read_bytes()))
  entries=[]
  def add(name,source,width,color,transform=lambda v:v):
   original=raw.signals['network.'+source];events=[(t,format(transform(int(v,2)),f'0{width}b')) for t,v in original.events]
   entries.append((Signal(name,width,'s'+str(len(entries)),events),color))
  for u,name,color in [(0,'conv0','#287bd0'),(1,'conv1','#27864d'),(2,'post','#c08016'),(3,'dw7','#9861bc'),(4,'pad','#168c8e')]:
   add(name+'_busy','operator_busy',1,color,lambda v,u=u:(v>>u)&1)
   if u<3:
    add(name+'_node',name+'_node',10,color)
    add(name+'_frame',name+'_node',1,color,lambda v:jobs[v][13])
  add('completion_pulse','completion_pulse',5,'#51647d');add('completed_count','completed_count',11,'#51647d')
  add('done','done',1,'#51647d');add('error','error',1,'#b53c39')
  text=['$timescale 1ns $end','$scope module network $end'];changes={}
  for s,c in entries:
   text.append(f'$var wire {s.width} {s.code} {s.path} $end')
   for t,v in s.events:changes.setdefault(int(t),[]).append(f'b{v} {s.code}')
  text+=['$upscope $end','$enddefinitions $end']
  for t in sorted(changes):text+=['#'+str(t),*changes[t]]
  (out/(case+'.vcd')).write_text('\n'.join(text)+'\n')
  left=10;right=raw.end_ns;im=Image.new('RGB',(1800,1100),'#f7f9fc');d=ImageDraw.Draw(im)
  font=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
  d.text((24,18),'两图小数据真实RTL：'+('正常双核' if case=='dual' else '卷积核0限速与存储反压'),font=font(26),fill='#243a52')
  d.text((24,60),'busy包含访存等待；节点/帧号仅在对应busy期间有效。DW7与补边为独立算子探针，非ROI链的后续网络层。',font=font(18),fill='#51647d')
  x=lambda t:300+(t-left)/(right-left)*1450
  for i in range(9):
   t=left+(right-left)*i/8;xx=x(t);d.line((xx,130,xx,1020),fill='#dce4ed');d.text((min(xx-20,1640),103),f'{t/1000:.1f} us',font=font(15),fill='#51647d')
  for i,(s,color) in enumerate(entries):
   y=143+i*55;d.text((24,y),s.path,font=font(19),fill=color);prev=None
   for l,rr,b in segments(s,left,right):
    aa,bb=x(l),x(rr);v=int(b,2)
    if s.width==1:
     yy=y+3 if v else y+29
     if prev is not None:d.line((aa,prev,aa,yy),fill=color,width=2)
     d.line((aa,yy,bb,yy),fill=color,width=2);prev=yy
    else:
     d.rectangle((aa,y+3,bb,y+29),outline=color)
     if bb-aa>len(str(v))*10+8:d.text((aa+3,y+2),str(v),font=font(16),fill=color)
   if s.path=='done':d.line((1750,y+29,1750,y+3),fill=color,width=2);d.text((1510,y),'done=1，采样结束',font=font(16),fill=color)
  im.save(out/(case+'.png'))
  gtk=['[dumpfile] "'+str(out/(case+'.vcd')).replace('\\','/')+'"']
  for i,(s,c) in enumerate(entries):gtk+=['@24' if s.width>1 else '@28','[color] '+str([4,2,3,6,5][min(i//3,4)]),'network.'+s.path+(f'[{s.width-1}:0]' if s.width>1 else '')]
  (out/(case+'.gtkw')).write_text('\n'.join(gtk)+'\n')
  tcl=f'gtkwave::setZoomRangeTimes {left} {int(right)}\n'
  (out/(case+'.tcl')).write_text(tcl)
  (out/('verify_'+case+'.tcl')).write_text(tcl+f'if {{[llength [gtkwave::getDisplayedSignals]] != {len(entries)}}} {{error "signal count"}}\nset f [open [file join [file dirname [info script]] validation.log] a]\nputs $f "PASS {case} signals={len(entries)}"\nclose $f\ngtkwave::/File/Quit\n')
  (out/('open_'+case+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0'+case+'.vcd" -a "%~dp0'+case+'.gtkw" -S "%~dp0'+case+'.tcl"\n')
 (out/'provenance.json').write_text(json.dumps(dict(run=str(run),capacity=str(cap),numeric_full_network=False),indent=2))
 print(out)
if __name__=='__main__':main()
