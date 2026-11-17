from pathlib import Path
import json,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
B=Path(__file__).resolve().parents[2]
D=Path(sys.argv[1]);j=json.loads((D/'wave/wave_result.json').read_text());p=Path(j['readable_detail_vcd'])
data={};t=0
for line in p.open():
 if line.startswith('#'):t=int(line[1:])
 elif line.startswith('b'):
  bits,c=line[1:].split();v=int(bits,2)
  if len(bits)==192:v=v.to_bytes(24,'big').decode('ascii').strip()
  data.setdefault(c,[]).append((t,v))
td=json.loads((D/'timeline_data.json').read_text());task=td['runs']['new']['jobs'][j['chosen_pw8_node']];u=task['unit_id'];first=j['first_mac_ns'];t0,t1=j['sessions']['pw8_detail']['time_range_ns']
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc');plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False})
fig,axs=plt.subplots(7,1,figsize=(15,8),sharex=True,gridspec_kw={'height_ratios':[1.2,1,1,1,1,1.2,1.2]})
tracks=[('v'+str(12+u),task['unit']+' 状态',True),('v6','实际MAC退休',False),('v8','存储请求尚未应答',False),('v9','读取/写入请求valid',False),('v10','读取/写入应答',False),('v4','共享存储状态',True),('v5','MOVER状态',True)]
colors={'IREQ':'#78a4ce','WREQ':'#e4b05d','MAC_RUN':'#239577','OREQ':'#946ab6','OWAIT':'#d492a7','DRAIN':'#9eafbe','IDLE':'#dfe5ec','ACCESS':'#8dbad7','REPLY':'#cad7e2','FILL_WAIT':'#e7c482','WB_WAIT':'#e7c482'}
for ax,(code,label,is_text) in zip(axs,tracks):
 events=data[code];assert events[0][0]<=t0
 if is_text:
  for i,(t,v) in enumerate(events):
   end=events[i+1][0] if i+1<len(events) else t1
   a=max(t,t0);b=min(end,t1)
   if b<=a:continue
   ax.broken_barh([((a-t0)/1000,(b-a)/1000)],(.15,.7),facecolors=colors.get(v,'#b8c4d2'))
   if b-a>=420:ax.text(((a+b)/2-t0)/1000,.5,str(v),ha='center',va='center',fontsize=9)
 else:
  times=[max(t,t0) for t,v in events if t<=t1];vals=[(int(v)>>u)&1 for t,v in events if t<=t1]
  times.append(t1);vals.append(vals[-1]);xs=[(t-t0)/1000 for t in times]
  ax.step(xs,vals,where='post',color='#239577' if code=='v6' else '#3975b8',lw=1.2);ax.fill_between(xs,0,vals,step='post',alpha=.12,color='#239577' if code=='v6' else '#3975b8')
 ax.set_ylim(-.15,1.15);ax.set_yticks([]);ax.set_ylabel(label,rotation=0,ha='right',va='center',labelpad=12,fontsize=10)
 ax.axvline((first-t0)/1000,color='#666',ls='--',lw=.8);ax.grid(axis='x',alpha=.17)
 for side in ['top','right','left']:ax.spines[side].set_visible(False)
axs[-1].set_xlim(0,(t1-t0)/1000);axs[-1].set_xlabel(f'局部时间 / µs；窗口绝对起点 {t0/1e6:.6f} ms（100MHz条件换算）')
fig.suptitle(f"任务{task['node']} / L{task['layer']}：{task['width']}×{task['height']}，1×1卷积 {task['ci']}→{task['co']}\n虚线为本任务首次实际MAC退休；pending与MAC可重叠，不能直接算作浪费时间",fontsize=13)
fig.tight_layout(rect=(0,0,1,.92));fig.savefig(D/'control_detail.png',dpi=140,bbox_inches='tight');plt.close(fig)
print(D/'control_detail.png')
