#!/usr/bin/env python3
"""读取真实 VCD，绘制数字阶梯/总线区间，同时输出 PNG/SVG。仅依赖 matplotlib。"""
from __future__ import annotations
import argparse, bisect, json, re, warnings
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Signal:
    path: str
    width: int
    code: str
    events: list[tuple[float,str]]

@dataclass
class VCD:
    signals: dict[str,Signal]
    end_ns: float
    timescale: str

def normalize(bits, width):
    bits=bits.lower()
    if not bits or any(c not in '01xz' for c in bits):
        raise ValueError('不支持的 VCD 数字值：'+bits)
    if len(bits)>width: raise ValueError('VCD 值超过声明位宽')
    return bits.rjust(width,bits[0] if bits[0] in 'xz' else '0')

def read_vcd(path: Path) -> VCD:
    content=Path(path).read_text(encoding='utf-8',errors='strict')
    header,sep,body=content.partition('$enddefinitions')
    if not sep: raise ValueError('缺少 VCD enddefinitions')
    scope=[];signals={};codes={};scale=None;timescale=''
    for match in re.finditer(r'\$(\w+)\s+(.*?)\s*\$end',header,re.S):
        directive,value=match.groups();parts=value.split()
        if directive=='timescale':
            m=re.fullmatch(r'(1|10|100)\s*(fs|ps|ns|us|ms|s)',value.strip())
            if not m: raise ValueError('无效 timescale：'+value)
            timescale=value.strip();scale=int(m[1])*{'fs':1e-6,'ps':1e-3,'ns':1,'us':1e3,'ms':1e6,'s':1e9}[m[2]]
        elif directive=='scope': scope.append(parts[1])
        elif directive=='upscope':
            if not scope: raise ValueError('VCD scope 不匹配')
            scope.pop()
        elif directive=='var':
            _,width,code,reference,*suffix=parts
            if parts[0] in ('real','realtime','string'): continue
            full='.'.join(scope+[reference.lstrip('\\')]);width=int(width)
            if full in signals: raise ValueError('重复层级名：'+full)
            if code in codes and codes[code][0]!=width: raise ValueError('别名位宽不一致')
            events=codes.setdefault(code,(width,[]))[1]
            signals[full]=Signal(full,width,code,events)
    if scale is None: raise ValueError('VCD 缺少 timescale，不能猜测时间单位')
    tokens=iter(body.split());now=0.0;end=0.0
    for token in tokens:
        if token.startswith('#'):
            timestamp=int(token[1:])*scale
            if timestamp<now: raise ValueError('VCD 时间戳倒退')
            now=timestamp;end=max(end,now);continue
        if token in ('$dumpvars','$dumpall','$dumpon','$dumpoff','$end'): continue
        if token.startswith('$'):
            for item in tokens:
                if item=='$end': break
            continue
        if token[0] in 'bB': bits=token[1:];code=next(tokens)
        elif token[0] in 'rRsS': next(tokens);continue
        elif token[0] in '01xXzZ': bits=token[0];code=token[1:]
        else: raise ValueError('未知 VCD token：'+token)
        if code not in codes: continue
        width,events=codes[code];value=normalize(bits,width)
        if events and events[-1][0]==now: events[-1]=(now,value)
        elif not events or events[-1][1]!=value: events.append((now,value))
    return VCD(signals,end,timescale)

def segments(signal: Signal, start: float, end: float):
    if end<=start: raise ValueError('结束时间必须大于开始时间')
    index=bisect.bisect_right([t for t,_ in signal.events],start)-1
    current=signal.events[index][1] if index>=0 else 'x'*signal.width
    cursor=start
    for t,value in signal.events[index+1:]:
        if t>=end: break
        if t>cursor: yield cursor,t,current
        cursor=t;current=value
    if end>cursor: yield cursor,end,current

def choose(vcd, config, group=None):
    groups=config['groups']
    if group and group not in groups: raise ValueError('未知信号组：'+group)
    selected=[];seen=set()
    for key in ([group] if group else groups):
        for entry in groups[key]:
            path=entry['path']
            if path not in vcd.signals:
                if entry.get('optional',False): warnings.warn('可选信号缺失：'+path);continue
                raise ValueError('必选信号不存在（请使用完整层级名）：'+path)
            if path not in seen: selected.append((vcd.signals[path],entry));seen.add(path)
    if not selected: raise ValueError('没有可绘制信号')
    return selected

def render(vcd_path, signals_path, out_dir, *, group=None, start_ns=None, end_ns=None,
           dpi=180, name='waveforms', title=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Polygon
    available={f.name for f in font_manager.fontManager.ttflist}
    matplotlib.rcParams['font.family']=['DejaVu Sans']+[n for n in ('Microsoft YaHei','SimHei','Noto Sans CJK SC') if n in available]
    if dpi<150: raise ValueError('dpi 至少 150')
    vcd=read_vcd(Path(vcd_path));config=json.loads(Path(signals_path).read_text(encoding='utf-8'))
    selected=choose(vcd,config,group)
    start=0.0 if start_ns is None else start_ns
    end=min(vcd.end_ns,start+200) if end_ns is None else end_ns
    if start<0 or end<=start or start>=vcd.end_ns or end>vcd.end_ns+1e-6:
        raise ValueError(f'空或越界时间窗口 [{start},{end}]；VCD 范围 [0,{vcd.end_ns}] ns')
    fig,axes=plt.subplots(len(selected),1,figsize=(14,max(4,0.5*len(selected)+1.5)),sharex=True,squeeze=False)
    fig.patch.set_facecolor('#f7fafc')
    span=end-start
    for axrow,(signal,entry) in zip(axes,selected):
        ax=axrow[0];ax.set_facecolor('#f7fafc');ax.set_ylim(-0.2,1.2);ax.set_yticks([])
        ax.text(-0.015,0.5,entry.get('label',signal.path),transform=ax.transAxes,ha='right',va='center',fontsize=9,family='DejaVu Sans Mono')
        for left,right,bits in segments(signal,start,end):
            unknown=any(c in bits for c in 'xz')
            if signal.width==1 and not unknown:
                y=int(bits);ax.plot([left,right],[y,y],color='#007e87',linewidth=1.5)
                if left>start: ax.plot([left,left],[0,1],color='#007e87',linewidth=1)
            else:
                color=('#efb63f' if 'x' in bits else '#d788c7') if unknown else '#cbe9ef'
                bevel=min(span*0.002,(right-left)/5)
                poly=Polygon([(left,.5),(left+bevel,.12),(right-bevel,.12),(right,.5),(right-bevel,.88),(left+bevel,.88)],closed=True,facecolor=color,edgecolor='#496779',linewidth=.7,hatch='//' if unknown else None)
                ax.add_patch(poly)
                if unknown: label=bits.upper() if len(bits)<=8 else ('X/Z' if 'x' in bits and 'z' in bits else ('X' if 'x' in bits else 'Z'))
                else:
                    value=int(bits,2);label=entry.get('enum',{}).get(str(value))
                    if label is None: label=str(value) if entry.get('radix')=='dec' else f'{value:0{(signal.width+3)//4}X}'
                available=(right-left)/span*1100
                if available>=len(label)*5+3: ax.text((left+right)/2,.5,label,ha='center',va='center',fontsize=8,family='DejaVu Sans Mono',clip_on=True)
        ax.grid(axis='x',alpha=.22)
        for spine in ax.spines.values(): spine.set_visible(False)
        ax.tick_params(axis='x',length=0,labelsize=9)
    axes[-1][0].set_xlim(start,end);axes[-1][0].set_xlabel('Time (ns)')
    fig.suptitle(title or f'{name} | seed=unspecified',fontsize=14,fontweight='bold',x=.57)
    fig.text(.02,.012,f'Source: {Path(vcd_path).resolve()}\nVCD timescale: {vcd.timescale} | interval [{start:g}, {end:g}] ns | X: amber / Z: purple',fontsize=7,color='#405060')
    fig.subplots_adjust(left=.24,right=.985,top=.91,bottom=.13,hspace=.12)
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    for extension in ('png','svg'): fig.savefig(out/f'{name}.{extension}',dpi=dpi,facecolor=fig.get_facecolor())
    plt.close(fig)
    return out/f'{name}.png'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vcd',required=True,type=Path);p.add_argument('--signals',required=True,type=Path)
    p.add_argument('--out-dir',required=True,type=Path);p.add_argument('--group')
    p.add_argument('--start-ns',type=float);p.add_argument('--end-ns',type=float)
    p.add_argument('--dpi',type=int,default=180);p.add_argument('--name',default='waveforms')
    p.add_argument('--test-name',default='manual');p.add_argument('--seed',default='unspecified')
    a=p.parse_args()
    try:
        image=render(a.vcd,a.signals,a.out_dir,group=a.group,start_ns=a.start_ns,end_ns=a.end_ns,dpi=a.dpi,name=a.name,title=f'{a.test_name} | seed={a.seed} | {a.name}')
    except (ValueError,OSError,KeyError,StopIteration) as exc: p.exit(1,'绘图失败：'+str(exc)+'\n')
    print(image)
if __name__=='__main__': main()
