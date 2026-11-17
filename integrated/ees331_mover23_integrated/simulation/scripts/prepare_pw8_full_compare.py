from pathlib import Path
import csv,json,hashlib,shutil,sys,math,html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from PIL import Image
B=Path(__file__).resolve().parents[2];S=B/'simulation'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def local(p):return Path('D:/'+p[len('/mnt/d/'):] if p.startswith('/mnt/d/') else p)
R=local(json.loads((S/'build/pw8_linear_full_active.json').read_text())['run_dir']) if len(sys.argv)<2 else local(sys.argv[1])
j=json.loads((R/'result.json').read_text());assert j['status']=='PASS'
for n,h in j['sources'].items():assert sha(B/n)==h,n
for v,r in j['variants'].items():
 assert r['status']=='PASS'
 for n,h in r['snapshot_hashes'].items():assert sha(R/v/'source'/n)==h,(v,n)
 for size in ['small','full']:
  assert r[size]['metrics']['status']=='PASS'
  assert sha(R/v/size/'outputs.bin')==j['fixtures'][size]['expected_sha256']
fixture=local(j['fixtures']['full']['directory']);m=json.loads((fixture/'manifest.json').read_text())
for n,h in m['files_sha256'].items():assert sha(fixture/n)==h,n
assert m['final_bytes']==6272 and m['total_tasks']==129 and m['expected_bytes']==19365452
assert j['changed_sources']==['rtl/cnn_self/self_pw8_engine.sv']
D=B/('deliverables/pw8_linear_full_'+R.name);D.mkdir(exist_ok=True)
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc');plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False,'figure.dpi':120})
def readcsv(p):return list(csv.DictReader(p.open(encoding='utf-8')))
cmd=[int(s,16) for s in (fixture/'commands.hex').read_text().split()]
# Classify by the actual executing unit, not guessed descriptor bit positions.
unit_names=['K3_0','K3_1']+['PW8_'+str(i) for i in range(6)]+['POST_0','POST_1','ADD_0','PAD_0']
colors={'K3/DW3':'#3975b8','PW8':'#239577','Post':'#9364b7','Add':'#dc9a2a','Pad':'#cf605c'}
data={};summary={}
for v in ['old','new']:
 r=R/v/'full';events=readcsv(r/'events.csv');timing={k:int(a) for k,a in readcsv(r/'output_timing.csv')[0].items()}
 profiles={int(x['node']):{k:int(val) for k,val in x.items() if k!='node'} for x in readcsv(r/'operator_profile.csv')}
 starts={};jobs=[]
 for e in events:
  n=int(e['node']);t=int(e['cycle']);u=int(e['unit'])
  if e['event']=='START':assert n not in starts;starts[n]=(t,u)
  elif e['event']=='COMPLETE':
   a,k=starts[n];assert k==u
   c=cmd[n*16:(n+1)*16];kind='K3/DW3' if u<2 else 'PW8' if u<8 else 'Post' if u<10 else 'Add' if u==10 else 'Pad'
   jobs.append({'node':n,'layer':m['jobs'][n]['layer'],'name':m['jobs'][n]['name'],'kind':kind,'unit':unit_names[u],'unit_id':u,'begin':a,'end':t,'cycles':t-a,'start_ms':(a-timing['input_cycle'])/100000,'duration_ms':(t-a)/100000,'width':c[7],'height':c[8],'ci':c[6],'co':c[9],'stride':c[10],**profiles[n]})
 jobs.sort(key=lambda x:x['node']);assert [x['node'] for x in jobs]==list(range(129))
 assert all(x['begin']>=timing['input_cycle'] and x['end']<=timing['ddr_result_cycle'] for x in jobs)
 cats={k:sum(x['cycles'] for x in jobs if x['kind']==k) for k in colors}
 other=timing['latency_cycles']-sum(cats.values());assert other>=0
 summary[v]={'latency_cycles':timing['latency_cycles'],'latency_ms_100MHz':timing['latency_cycles']/100000,'total_simulation_cycles':j['variants'][v]['full']['metrics']['cycles'],'task_cycles_by_kind':cats,'outside_task_cycles':other,'ddr_read_bytes':j['variants'][v]['full']['metrics']['ddr_read_bytes'],'ddr_write_bytes':j['variants'][v]['full']['metrics']['ddr_write_bytes'],'compile_seconds':j['variants'][v]['compile_seconds'],'full_simulation_seconds':j['variants'][v]['full_seconds'],'output_sha256':j['variants'][v]['full']['output_sha256'],'mac_retire_cycles':sum(x['mac_cycles'] for x in jobs),'pw8_mac_retire_cycles':sum(x['mac_cycles'] for x in jobs if x['kind']=='PW8')}
 data[v]={'timing':timing,'jobs':jobs,'summary':summary[v]}
old=summary['old'];new=summary['new'];gain=(1-new['latency_cycles']/old['latency_cycles'])*100
comparison=[]
for a,b in zip(data['old']['jobs'],data['new']['jobs']):
 assert a['node']==b['node'] and a['kind']==b['kind'] and a['name']==b['name']
 comparison.append({'node':a['node'],'layer':a['layer'],'kind':a['kind'],'name':a['name'],'width':a['width'],'height':a['height'],'ci':a['ci'],'co':a['co'],'old_cycles':a['cycles'],'new_cycles':b['cycles'],'saved_cycles':a['cycles']-b['cycles'],'reduction_percent':100*(1-b['cycles']/a['cycles']),'old_read_bytes':a['read_bytes'],'new_read_bytes':b['read_bytes'],'old_mac_cycles':a['mac_cycles'],'new_mac_cycles':b['mac_cycles']})
summary.update({'status':'PASS','reduction_percent':gain,'speedup':old['latency_cycles']/new['latency_cycles'],'wall_seconds':j['wall_seconds'],'full_network_original':False,'network_variant':j['network_variant'],'cpu_real_rtl':True,'uart':False,'timing_100MHz_verified':False,'resource_measurement':'deferred by user','source_hashes_unchanged':True,'jobs':129,'checked_output_bytes':19365452,'output_bytes':6272})
(D/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(D/'timeline_data.json').write_text(json.dumps({'runs':data,'comparison':comparison},ensure_ascii=False)+'\n',encoding='utf-8')
with (D/'per_task_comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(comparison[0]));w.writeheader();w.writerows(comparison)
for v in ['old','new']:
 dest=D/v;dest.mkdir(exist_ok=True)
 for name in ['metrics.json','events.csv','output_timing.csv','operator_profile.csv','outputs.bin','simulation.log']:shutil.copy2(R/v/'full'/name,dest/name)
shutil.copy2(R/'result.json',D/'run_result.json')
shutil.copy2(fixture/'manifest.json',D/'fixture_manifest.json')
# Stage wave once without duplicating the large raw VCD. FST conversion follows.
(D/'wave_source.json').write_text(json.dumps({'vcd':str(R/'new/full/control.vcd'),'signals':24,'complete_run':True,'timescale':'1ns','sample_clock_reference_ns':10},indent=2)+'\n')
img=np.frombuffer((fixture/'images.bin').read_bytes(),dtype=np.uint8);assert img.size==112*112*3
Image.fromarray(img.reshape(112,112,3)).resize((336,336)).save(D/'input_tensor.png')
# Latency broken down by real START->COMPLETE intervals, plus polling/fence gaps.
fig,ax=plt.subplots(figsize=(12,3.7));left=[0.,0.]
for kind,color in colors.items():
 vals=[summary[v]['task_cycles_by_kind'][kind]/100000 for v in ['old','new']]
 ax.barh([1,0],vals,left=left,color=color,label=kind,height=.48)
 left=[l+x for l,x in zip(left,vals)]
vals=[summary[v]['outside_task_cycles']/100000 for v in ['old','new']];ax.barh([1,0],vals,left=left,color='#a9b1bd',label='任务外控制/换页收尾')
ax.set_yticks([1,0],['原4×2分组','连续8像素分组']);ax.set_xlabel('图片提交完成 → DDR结果可见 / ms（按100MHz换算）')
for y,v in [(1,'old'),(0,'new')]:ax.text(summary[v]['latency_ms_100MHz']+1,y,f"{summary[v]['latency_ms_100MHz']:.3f} ms",va='center')
ax.set_xlim(0,max(old['latency_ms_100MHz'],new['latency_ms_100MHz'])*1.15);ax.set_title(f'同一张112×112 RGB，129任务：整图周期减少 {gain:.2f}%')
ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.25),ncol=6,frameon=False,fontsize=9);fig.tight_layout();fig.savefig(D/'overview.png',bbox_inches='tight');plt.close(fig)
pw=[x for x in comparison if x['kind']=='PW8'];fig,axs=plt.subplots(1,2,figsize=(13,6),gridspec_kw={'width_ratios':[1,1]})
sizes=sorted(set(x['width'] for x in pw),reverse=True);y=np.arange(len(sizes))
for i,v in enumerate(['old','new']):
 vals=[sum(x[v+'_cycles'] for x in pw if x['width']==size)/100000 for size in sizes]
 axs[0].barh(y+(-.18 if i==0 else .18),vals,height=.34,label='原分组' if i==0 else '新分组',color='#a6b6c8' if i==0 else '#239577')
axs[0].set_yticks(y,[f'{s}×{s}（{sum(x["width"]==s for x in pw)}层）' for s in sizes]);axs[0].invert_yaxis();axs[0].set_xlabel('1×1任务累计耗时 / ms @100MHz条件');axs[0].legend();axs[0].set_title('相同空间尺寸的1×1卷积汇总');axs[0].grid(axis='x',alpha=.18)
top=sorted(pw,key=lambda x:x['saved_cycles'],reverse=True)[:8];yy=np.arange(len(top))
axs[1].barh(yy,[x['saved_cycles']/100000 for x in top],color='#239577');axs[1].set_yticks(yy,[f"L{x['layer']}  {x['width']}×{x['height']}  {x['ci']}→{x['co']}" for x in top]);axs[1].invert_yaxis();axs[1].set_xlabel('本层节省时间 / ms @100MHz条件');axs[1].set_title('节省周期最多的8个1×1任务');axs[1].grid(axis='x',alpha=.18)
fig.suptitle('整图真实执行中的各层收益（含片上访问及DDR换页）');fig.tight_layout();fig.savefig(D/'pw8_layers.png',bbox_inches='tight');plt.close(fig)
fig,axes=plt.subplots(2,1,figsize=(15,8),sharex=True)
for ax,v,title in zip(axes,['old','new'],['原4×2分组','连续8像素分组']):
 kinds=list(colors)
 for x in data[v]['jobs']:ax.broken_barh([(x['start_ms'],x['duration_ms'])],(kinds.index(x['kind'])-.33,.66),facecolors=colors[x['kind']])
 ax.set_yticks(range(len(kinds)),kinds);ax.invert_yaxis();ax.set_title(title);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
 ax.axvline(summary[v]['latency_ms_100MHz'],color='#444',ls='--',lw=1)
axes[-1].set_xlabel('图片提交完成后 / ms（100MHz条件换算）');axes[0].set_xlim(0,max(old['latency_ms_100MHz'],new['latency_ms_100MHz'])*1.01)
fig.suptitle('单图任务时间线：每块是一个任务，包含读取、计算和写回应答\n单图依赖顺序执行，此图不证明多图并行');fig.tight_layout();fig.savefig(D/'task_timeline.png',bbox_inches='tight');plt.close(fig)
# Self-contained interactive view: same recorded jobs, task click opens duration comparison.
payload=json.dumps({'runs':data,'comparison':comparison,'colors':colors,'summary':summary},ensure_ascii=False).replace('</','<\\/')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>单图PW8优化对比</title>
<style>*{box-sizing:border-box}body{font:16px system-ui,"Microsoft YaHei";color:#1e293b;background:#f4f7fa;margin:0;padding:28px;max-width:1600px;margin:auto}h1{font-size:28px;margin:0 0 10px}p{line-height:1.65}.cards{display:flex;gap:16px;flex-wrap:wrap}.card,section{background:white;border:1px solid #dce3eb;border-radius:12px;padding:20px;margin:16px 0}.card{flex:1;min-width:220px}.big{font-size:30px;font-weight:650;margin-top:8px}button,select{padding:9px 14px;border:1px solid #bcc9d7;border-radius:7px;background:white;cursor:pointer;margin:3px}button.active{background:#d8eee6}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:right;padding:10px;border-bottom:1px solid #e3e9ef}th:first-child,td:first-child{text-align:left}tbody tr{cursor:pointer}tbody tr:hover{background:#e8f5ef}.scroll{overflow:auto;max-height:520px}svg{width:100%;height:470px}.legend span{display:inline-block;margin:8px 16px 8px 0}i{display:inline-block;width:14px;height:14px;margin-right:6px;border-radius:3px}.muted{color:#62738a;font-size:14px}#detail{background:#eef5f9;padding:16px;border-radius:8px;line-height:1.75}img{max-width:100%}</style>
<h1>一张112×112 RGB：1×1卷积优化前后</h1><p>当前129任务网络，去掉DW7，最终输出7×7×128。真实CPU、CNN、共享RAM、MOVER运行RTL；PS和DDR为仿真环境。所有中间结果逐字节核对。以下毫秒均为100MHz条件换算。</p>
<div class="cards"><div class="card">原分组整图延迟<div class="big" id="old"></div></div><div class="card">新分组整图延迟<div class="big" id="new"></div></div><div class="card">整图周期减少<div class="big" id="gain"></div></div></div>
<section><h2>数据流</h2><p>PS写入整张图片 → CPU提交 → 算子读取共享RAM（缺页由MOVER搬DDR）→ 卷积/后处理/Add/Pad → 中间结果写存储 → 下一任务 → 最终结果写回DDR → CPU取回。</p><p class="muted">本次为单图、整图提交。单图各任务存在依赖，不用于证明多图并行；没有UART输入、同图条带流水或识别准确率结论。LUT和新版100MHz时序仍待补测。</p></section>
<section><h2>真实任务时间线</h2><button id="bnew" class="active" onclick="setrun('new')">新分组</button><button id="bold" onclick="setrun('old')">原分组</button><span class="muted">点击任务块查看该层对比；整块时间包含访存和写回等待。</span><div class="legend" id="legend"></div><svg id="timeline" viewBox="0 0 1400 450"></svg><div id="detail">点击时间线或下面的表格查看具体任务。</div></section>
<section><h2>每个1×1卷积任务的收益</h2><select id="filter" onchange="table()"><option value="all">全部空间尺寸</option><option>56</option><option>28</option><option>14</option><option>7</option></select><div class="scroll"><table><thead><tr><th>任务 / 层</th><th>尺寸</th><th>通道</th><th>原耗时ms</th><th>新耗时ms</th><th>减少%</th><th>节省周期</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><h2>整体对比图</h2><img src="overview.png"><img src="pw8_layers.png"></section>
<script id="data" type="application/json">PAYLOAD</script><script>
const D=JSON.parse(document.getElementById('data').textContent);let run='new';
document.getElementById('old').textContent=D.summary.old.latency_ms_100MHz.toFixed(3)+' ms';document.getElementById('new').textContent=D.summary.new.latency_ms_100MHz.toFixed(3)+' ms';document.getElementById('gain').textContent=D.summary.reduction_percent.toFixed(2)+'%';
document.getElementById('legend').innerHTML=Object.entries(D.colors).map(([k,c])=>`<span><i style="background:${c}"></i>${k}</span>`).join('');
function setrun(v){run=v;document.getElementById('bnew').className=v==='new'?'active':'';document.getElementById('bold').className=v==='old'?'active':'';draw()}
function draw(){const kinds=Object.keys(D.colors),x0=110,w=1250,max=Math.max(D.summary.old.latency_ms_100MHz,D.summary.new.latency_ms_100MHz),scale=w/max;let s='';for(let t=0;t<=max;t+=max/10){const x=x0+t*scale;s+=`<line x1="${x}" x2="${x}" y1="20" y2="395" stroke="#d9e2ec"/><text x="${x}" y="420" font-size="14" text-anchor="middle">${t.toFixed(0)}</text>`}kinds.forEach((k,i)=>{s+=`<text x="90" y="${55+i*65}" font-size="15" text-anchor="end">${k}</text>`});D.runs[run].jobs.forEach(j=>{let x=x0+j.start_ms*scale,y=30+kinds.indexOf(j.kind)*65;s+=`<rect onclick="detail(${j.node})" x="${x}" y="${y}" width="${Math.max(.5,j.duration_ms*scale)}" height="38" fill="${D.colors[j.kind]}" stroke="white" stroke-width=".4"><title>任务${j.node} / L${j.layer} ${j.kind}: ${j.duration_ms.toFixed(4)}ms</title></rect>`});document.getElementById('timeline').innerHTML=s}
function detail(n){let c=D.comparison[n],a=D.runs.old.jobs[n],b=D.runs.new.jobs[n];document.getElementById('detail').textContent=`任务${n}，L${c.layer}，${c.kind}。${['PW8','K3/DW3'].includes(c.kind)?c.width+'×'+c.height+'，'+c.ci+'→'+c.co+'通道。':''}原版${c.old_cycles.toLocaleString()}周期，新版${c.new_cycles.toLocaleString()}周期，减少${c.reduction_percent.toFixed(2)}%。总读取${c.old_read_bytes.toLocaleString()}→${c.new_read_bytes.toLocaleString()}字节；实际MAC工作拍${c.old_mac_cycles.toLocaleString()}→${c.new_mac_cycles.toLocaleString()}。新任务从提交后${b.start_ms.toFixed(4)}ms开始，持续${b.duration_ms.toFixed(4)}ms。`}
function table(){let f=document.getElementById('filter').value;document.getElementById('rows').innerHTML=D.comparison.filter(c=>c.kind==='PW8'&&(f==='all'||c.width===+f)).map(c=>`<tr onclick="detail(${c.node})"><td>${c.node} / L${c.layer}</td><td>${c.width}×${c.height}</td><td>${c.ci}→${c.co}</td><td>${(c.old_cycles/100000).toFixed(4)}</td><td>${(c.new_cycles/100000).toFixed(4)}</td><td>${c.reduction_percent.toFixed(2)}</td><td>${c.saved_cycles.toLocaleString()}</td></tr>`).join('')}
draw();table();</script></html>'''.replace('PAYLOAD',payload)
(D/'index.html').write_text(page,encoding='utf-8')
pw_gain=(1-new['task_cycles_by_kind']['PW8']/old['task_cycles_by_kind']['PW8'])*100
rows='\n'.join(f"| {kind} | {old['task_cycles_by_kind'][kind]:,} | {new['task_cycles_by_kind'][kind]:,} |" for kind in colors)
report=f'''# 单图SoC：PW8连续分组前后对比

同一张112×112 RGB测试张量、同一129任务网络，两版完整通过。仅PW8源码不同；CPU、K3、后处理、Add、Pad、共享RAM、MOVER和DDR模型完全相同。整图提交到DDR结果可见的周期减少 **{gain:.2f}%**，其中1×1卷积任务累计周期减少 **{pw_gain:.2f}%**。

| 口径 | 原4×2分组 | 连续8像素分组 |
|---|---:|---:|
| 图片提交完成→DDR结果可见 | {old['latency_cycles']:,}周期 | {new['latency_cycles']:,}周期 |
| 按100MHz条件换算 | {old['latency_ms_100MHz']:.5f}ms | {new['latency_ms_100MHz']:.5f}ms |
| DDR总读字节 | {old['ddr_read_bytes']:,} | {new['ddr_read_bytes']:,} |
| DDR总写字节 | {old['ddr_write_bytes']:,} | {new['ddr_write_bytes']:,} |
| 电脑实际整图仿真时间 | {old['full_simulation_seconds']:.3f}s | {new['full_simulation_seconds']:.3f}s |
| 电脑编译时间 | {old['compile_seconds']:.3f}s | {new['compile_seconds']:.3f}s |

电脑总运行{j['wall_seconds']:.3f}s，含两版编译、小图门槛和两次整图；不含本说明/图片整理。原版不记录全程控制波形，新版记录，因此两版电脑运行时间不能当硬件性能比较。硬件性能比较只看同口径周期数。新版100MHz时序与资源仍按用户要求稍后补测。

## 看哪里

- [交互时间线](index.html)：切换原/新分组，点击任一任务查看尺寸、通道、耗时、读取字节和实际MAC工作拍；可筛选7×7、14×14等1×1层。
- [整体延迟图](overview.png)、[各1×1层收益图](pw8_layers.png)、[全程任务时间线](task_timeline.png)。
- [每个任务的对比表](per_task_comparison.csv)、[测量汇总](summary.json)、[原始运行记录](run_result.json)。
- GTKWave控制波形与打开方式见后续的`wave/`目录和验证记录；原始VCD在`{(R/'new/full/control.vcd').as_posix()}`。未采集模拟电压波形或板级时序。

## 各类任务累计周期

以下是实际START→COMPLETE区间，包含读取、计算和写回应答；其中等待不能一概算为MAC计算。读取、权重预取、内部写队列可以与MAC重叠，因此各类访存活动不能直接相加成总时间。

| 类别 | 原周期 | 新周期 |
|---|---:|---:|
{rows}

此处为单图，当前调度以任务依赖顺序推进；这次不验证多图同时计算。若其它算子任务耗时略变，是输入请求顺序改变后共享存储/DDR模型时序变化，不能当成这些算子RTL自身又优化了。

## 计算与结果

这是沿用的合成测试图和诊断量化，不是人脸识别准确率测试。运行当前缩减版MobileFaceNet：跳过DW7及其关联Post，保留尾部原参数并在7×7运算，最终输出UINT8/HWC、7×7×128=6272字节；不等价于原模型128维嵌入。

两版129个任务的 **19,365,452字节中间结果** 均逐字节匹配独立整数参考，最终结果完全一致，SHA256：`{new['output_sha256']}`。同时检查只读模型、写覆盖、缓冲区保护、CPU配置、MOVER双向传输、结果写回fence和批次复位。参考数据没有注入中间执行内存。

PS将输入整图写入DDR后由CPU提交；不含UART串口或边收同一张图边计算。CPU是真实项目RTL，PS GP0和带反压的AXI3 DDR是环境模型；DDR为64MiB仿真地址空间，共享tile RAM为392KiB。

## 波形信号说明

全程按每10ns采样稳定的时钟沿前信号，只记录变化，没有额外记录每拍时钟。GTKWave显示时间为假定100MHz时钟下的仿真时间。

| 信号 | 含义 |
|---|---|
| INPUT_COMMITTED | TB已完成整图写入，随后CPU提交该帧；不等同UART接收完成 |
| CNN_RUNNING | 调度器处于执行批次 |
| COMPLETED_TASKS | 已完成任务计数，最终129；测试最后复位会清零 |
| RESULT_IN_DDR | TB经CPU得到结果描述符，并核对DDR最终结果后置1 |
| OPERATOR_BUSY[11:0] | 各算子忙碌，包含数据准备及等待 |
| ACTUAL_WORK[11:0] | 卷积位表示实际MAC退休；Post/Add/Pad位表示写请求活动，含义不同 |
| REQUEST_VALID[11:0] | 算子向共享存储提出请求；不表示请求已被接受 |
| MEM_PENDING[11:0] | 观察器跟踪已接受、尚未应答的请求；应答当拍清除，是派生观测量 |
| RESPONSE[11:0] | 共享存储返回该算子的读/写应答 |
| MEMORY_STATE / MOVER_STATE | 分页存储控制器与DDR搬运器状态编号 |
| K3_0/1_STATE、PW8_0..5_STATE | 对应实例真实RTL状态编号；不是自创的算子利用率 |
| POST_0/1_STATE、ADD_0_STATE、PAD_0_STATE | 其它算子状态编号 |
| FAULT | CNN或存储错误，成功过程中保持0 |

12位向量的位0/1=K3_0/1，位2..7=PW8_0..5，位8/9=POST_0/1，位10=ADD，位11=PAD。PW8状态依次0IDLE、1SETUP、2CHECK、3TILE_BEGIN、4IREQ、5WREQ、6MAC_RUN、7OREQ、8OWAIT、9DRAIN、10FINISH、11FAIL；K3依次0IDLE、1SETUP、2CHECK、3TILE_BEGIN、4IREQ、5IWAIT、6WREQ、7WWAIT、8MAC_READ、9MAC_ACC、10OREQ、11OWAIT、12FINISH、13FAIL。

MEM_PENDING高不一定表示浪费：PW8可能一边MAC一边预取/写回。`operator_profile.csv`中的pending_no_mac_cycles也只代表“请求未回应且该拍无work”，并非全部可消除的停顿；request_wait_cycles是valid高但ready低。各层任务条同样包含访存等待。

## 复现和源码

入口`simulation/scripts/run_pw8_linear_full_soc.py`。每版使用独立源码快照，生产源码不被切换。原版PW8使用本次优化前已保存的准确源码，其他文件逐项核对相同。原/新版小门槛均通过，新版小门槛的控制记录开/关逐周期结果、事件和统计一致。

运行目录：`{R.as_posix()}`；两版的`source/`及可执行程序留在那里。无自动重复执行、综合或资源测试。
'''
(D/'README.md').write_text(report,encoding='utf-8')
print(D);print(json.dumps(summary,ensure_ascii=False,indent=2))
