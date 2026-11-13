"""Package verified four-image SRAM/compute evidence and native GTKWave views."""
from pathlib import Path
import argparse,csv,hashlib,json,shutil,xml.etree.ElementTree as ET
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from plot_waveforms import read_vcd

ROOT=Path(__file__).resolve().parents[1]
COLORS={0:'#2563eb',1:'#16a34a',2:'#dc2626',3:'#7c3aed',4:'#94a3b8',5:'#ea580c'}
NAMES={0:'3x3 / DW3',1:'Post',2:'Add',3:'DW7',4:'Pad',5:'1x1'}
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cp(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)
def loadrun(p):
    r=json.loads((p/'result.json').read_text())
    if r['status']!='PASS':raise RuntimeError('Not PASS: '+str(p))
    for name,value in r['source_sha256'].items():
        if sha(ROOT/name)!=value:raise RuntimeError('Changed source: '+name)
    return r

def diagram(path):
    mx=ET.Element('mxfile',host='app.diagrams.net');d=ET.SubElement(mx,'diagram',name='四图固定流程 CNN')
    m=ET.SubElement(d,'mxGraphModel',page='1',pageWidth='1600',pageHeight='1100');r=ET.SubElement(m,'root')
    ET.SubElement(r,'mxCell',id='0');ET.SubElement(r,'mxCell',id='1',parent='0')
    def box(i,label,x,y,w,h,color):
        c=ET.SubElement(r,'mxCell',id=i,value=label,style='rounded=1;whiteSpace=wrap;html=1;fontSize=16;fillColor='+color,vertex='1',parent='1')
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
    def edge(i,a,b,label):
        c=ET.SubElement(r,'mxCell',id=i,value=label,style='edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;fontSize=13;',edge='1',parent='1',source=a,target=b)
        ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
    box('host','外部配置端<br>一份固定流程 + 1~4 张图片地址<br>图片写完后提交 frame_valid',30,40,360,120,'#f1f5f9')
    box('expand','CNN: stream_fixed_programmer<br>模板地址重定位、依赖/owner 展开<br>11 个模板步骤 → 44 个四图任务',470,40,430,120,'#dbeafe')
    box('dispatch','CNN: stream_dispatch<br>按输入就绪、依赖、槽所有权调度<br>空闲算子池轮转，图片不绑定实例',470,230,430,130,'#dbeafe')
    box('leases','CNN: stream_buffer_leases<br>16 个物理工作槽<br>所有消费者完成 + 外部取走后释放',1030,40,440,120,'#ede9fe')
    box('results','CNN: stream_result_handoff<br>frame / addr / bytes 各 32 位<br>result_ready = 最后读响应已到达',1030,230,440,130,'#dcfce7')
    box('ops','CNN 算子池（10 个独立 SRAM 客户端）<br><br>自研 K3 ×4（普通 + DW3）　自研 K1 ×2<br>原 DW7 ×1　原 Post ×1　原 Add ×1　原 Pad ×1<br><br>operator_work：卷积真实 MAC；其他算子接受输出写回',300,470,1100,170,'#dbeafe')
    box('sram','bai-datasram：256 KiB，4 个真双口 bank<br>A：CPU 固定一拍；B：10 个 CNN 客户端 + 图像 IO 轮转<br>bank=(addr>>2)&3；同字 A 优先；CNN 写等 response，IO 写 gnt 即完成',300,760,1100,150,'#ffedd5')
    box('io','外部图像 IO<br>逐张写入 / 结果读出<br>本测试为请求驱动器',30,750,230,150,'#f1f5f9')
    edge('e1','host','expand','template_valid + address_valid')
    edge('e2','expand','dispatch','program_* / start')
    edge('e3','dispatch','ops','command[511:0], start / done')
    edge('e4','dispatch','leases','reserve / buffer_ready')
    edge('e5','results','leases','external_hold[15:0]')
    edge('e6','dispatch','results','completed_mask[63:0]')
    edge('e7','ops','sram','每客户端 valid/write/byte/addr32/wdata32 → ready/response/rdata32')
    edge('e8','io','sram','req/we/addr/wdata/be → gnt/rvalid/rdata/error')
    ET.ElementTree(mx).write(path,encoding='utf-8',xml_declaration=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--sweep',type=Path,required=True);p.add_argument('--programmer',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve();sweep=a.sweep.resolve();pr=a.programmer.resolve();r=loadrun(run);s=loadrun(sweep);prog=loadrun(pr)
    out=ROOT/'deliverables/self_cnn_four_frames';out.mkdir(parents=True,exist_ok=True)
    chosen='four_k1_overlap';metric=r['scenarios'][chosen];serial=r['scenarios']['four_k1_serial'];manifest=r['fixture']
    cp(run/'result.json',out/'regression.json');cp(sweep/'result.json',out/'sweep.json');cp(pr/'result.json',out/'programmer/result.json');cp(pr/'sim.log',out/'programmer/sim.log')
    for f in (run/'data').iterdir():
        if f.is_file():cp(f,out/'data'/f.name)
    for n in r['scenarios']:
        for name in ('metrics.json','sim.log','outputs.hex','events.csv'):
            cp(run/n/name,out/'tests'/n/name)
    for name in ('trace.csv','control.vcd'):cp(run/chosen/name,out/'overlap'/name)
    for n in s['scenarios']:
        for name in ('metrics.json','sim.log','outputs.hex'):cp(sweep/n/name,out/'sweep'/n/name)
    cp(ROOT/'rtl/cnn_stream/bai/SOURCE.json',out/'bai_source.json')
    cp(ROOT/'docs/self_cnn_four_frames.md',out/'interface.md')
    trace=[{k:int(v) for k,v in x.items()} for x in csv.DictReader((out/'overlap/trace.csv').open())]
    events=list(csv.DictReader((run/chosen/'events.csv').open()));starts={};tasks=[]
    for e in events:
        if e['event']=='launch':starts[int(e['node'])]=(int(e['cycle']),int(e['unit']))
        if e['event']=='done':
            n=int(e['node']);beg,u=starts[n];tasks.append(dict(node=n,begin=beg,end=int(e['cycle']),unit=u,frame=n%4,**{k:manifest['jobs'][n][k] for k in ('name','opcode')}))
    if len(tasks)!=44:raise RuntimeError('Incomplete task events')
    def timeline(filename,limit):
        fig,ax=plt.subplots(figsize=(15,5.5));ax.set_axisbelow(True);ax.grid(axis='x',alpha=.2)
        for f in range(4):
            info=metric['frames'][f];y=3-f
            ax.broken_barh([(info['input_begin'],info['input_commit']-info['input_begin'])],(y+.2,.12),facecolors='#0891b2',label='')
            ax.plot([info['input_commit']]*2,[y-.3,y+.38],color='#0891b2',lw=1,ls=':')
            for t in tasks:
                if t['frame']==f:
                    ax.broken_barh([(t['begin'],t['end']-t['begin'])],(y-.24,.35),facecolors=COLORS[t['opcode']])
                    if t['end']-t['begin']>limit*.038 and t['begin']<limit:
                        ax.text((t['begin']+min(t['end'],limit))/2,y-.06,t['name']+'\nU'+str(t['unit']),ha='center',va='center',fontsize=8,color='white' if t['opcode']!=4 else '#0f172a')
            if info['read_complete']<limit:ax.plot(info['read_complete'],y-.05,'k|',ms=16)
        ax.set(yticks=[3,2,1,0],yticklabels=['图 0 / frame 100','图 1 / frame 101','图 2 / frame 102','图 3 / frame 103'],xlim=(0,limit),ylim=(-.6,3.6),xlabel='开始后的周期数（含硬件任务展开；不含仿真预加载）')
        ax.set_title('四图依次输入，CNN 按固定流程重叠计算'+('：输入阶段放大' if limit<20000 else ''),loc='left',fontsize=16,pad=20)
        legend=[Patch(color='#0891b2',label='图像 IO 写入区间')]+[Patch(color=COLORS[i],label=NAMES[i]) for i in (4,0,5,3,1,2)]
        ax.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,-.19),ncol=7,frameon=False)
        fig.text(.13,.01,'彩色任务条包含访存等待；真实 MAC / 写回重叠见 mac_detail.png。竖线：图像提交；黑标记：结果读完。',fontsize=9,color='#475569')
        fig.subplots_adjust(left=.13,right=.98,top=.86,bottom=.24);fig.savefig(out/filename,dpi=150);plt.close(fig)
    timeline('frame_pipeline.png',metric['cycles']);timeline('input_overlap.png',14000)
    # Exact clock-level work strobes, without interpreting busy as arithmetic.
    detail=next(x['cycle'] for x in trace if (x['work']&15).bit_count()>=3)
    left,right=detail-20,detail+140;selected=[x for x in trace if left<=x['cycle']<=right]
    labels=['K3 #0 MAC','K3 #1 MAC','K3 #2 MAC','K3 #3 MAC','K1 #0 MAC','K1 #1 MAC','DW7 MAC','Post 写回','Add 写回','Pad 写回']
    fig,axes=plt.subplots(10,1,figsize=(15,8),sharex=True)
    for k,ax in enumerate(axes):
        ax.step([x['cycle'] for x in selected],[(x['work']>>k)&1 for x in selected],where='post',color='#2563eb' if k<7 else '#16a34a',lw=1.3)
        ax.set(ylim=(-.1,1.2),yticks=[0,1],ylabel=labels[k]);ax.yaxis.label.set_rotation(0);ax.yaxis.set_label_coords(-.09,.3);ax.grid(axis='x',alpha=.2)
    axes[0].set_title('实际工作脉冲：多套卷积同拍执行 MAC',loc='left',fontsize=16,pad=15);axes[-1].set_xlabel('周期（trace.csv 逐拍数据）')
    fig.subplots_adjust(left=.14,right=.98,top=.9,bottom=.08,hspace=.25);fig.savefig(out/'mac_detail.png',dpi=150);plt.close(fig)
    rows=[]
    for n,m in s['scenarios'].items():
        c=m['config'];rows.append(dict(case=n,k3=c['k3'],k1=c['k1'],post=c['post'],cycles=m['cycles'],speedup=s['scenarios']['base_overlap']['cycles']/m['cycles']))
    with (out/'operator_comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    fig,ax=plt.subplots(figsize=(12,6));y=range(len(rows));ax.barh(y,[v['cycles'] for v in rows],color=['#16a34a' if v['case']=='four_k1_overlap' else '#94a3b8' for v in rows])
    ax.set(yticks=list(y),yticklabels=[f"K3×{v['k3']} / K1×{v['k1']} / Post×{v['post']}" for v in rows],xlabel='四图总周期（相同 SRAM、输入节奏、结果读取节奏）',xlim=(0,max(v['cycles'] for v in rows)*1.16));ax.invert_yaxis()
    for i,v in enumerate(rows):ax.text(v['cycles']+800,i,f"{v['cycles']:,}",va='center')
    ax.set_title('增加算子的收益：第二套后处理没有继续缩短最快配置',loc='left',fontsize=15,pad=15);fig.tight_layout();fig.savefig(out/'operator_comparison.png',dpi=150);plt.close(fig)
    # Native VCD sessions: actual parameterized hierarchy, never rewritten data.
    vcd=read_vcd(out/'overlap/control.vcd');paths={name.rsplit('.',1)[1]:name for name in vcd.signals}
    signals='clk clear start unit_enable frame_valid frame_ready frame_slot frames_ready unit_start unit_active operator_work mem_valid mem_write mem_ready mem_response completed_count buffer_live external_hold result_valid result_ready result_accept result_frame compute_done done error'.split()
    if set(paths)!=set(signals):raise RuntimeError('VCD signal inventory mismatch')
    first_trace=next(x['cycle'] for x in trace if x['start']);first_vcd=next(t for t,b in vcd.signals[paths['unit_start']].events if int(b,2));origin=first_vcd-first_trace*10
    ack=max(x['cycle'] for x in trace if x['result_valid'] and x['result_ready'])
    windows=[('overview',0,metric['cycles']),('input',0,14000),('mac',left,right),('result',ack-180,metric['cycles'])]
    for name,lo,hi in windows:
        gtk=['[dumpfile] "'+(out/'overlap/control.vcd').as_posix()+'"','[size] 1800 1100','[signals_width] 340']
        for sig in signals:
            path=paths[sig];width=vcd.signals[path].width
            gtk+=['@28' if width==1 else '@24' if sig in ('completed_count','result_frame') else '@22',path+(f'[{width-1}:0]' if width>1 else '')]
        (out/(name+'.gtkw')).write_text('\n'.join(gtk)+'\n')
        zoom=f'gtkwave::setZoomRangeTimes {int((origin+lo*10)*1000)} {int((origin+hi*10)*1000)}\ngtkwave::/View/Scale_To_Time_Dimension/ns\n'
        (out/(name+'.tcl')).write_text(zoom)
        verify='set log [open [file join [file dirname [info script]] validation_'+name+'.log] w]\nset failure [catch {\n'+zoom
        verify+='set shown [gtkwave::getDisplayedSignals]\nputs $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\n'
        verify+=f'if {{[llength $shown] != {len(signals)} || [llength [lsort -unique $shown]] != {len(signals)}}} {{error "missing or duplicate signals"}}\n'
        verify+='puts $log "PASS '+name+'"\n} message]\nif {$failure} {puts $log "FAIL $message"}\nclose $log\ngtkwave::/File/Quit\n'
        (out/('verify_'+name+'.tcl')).write_text(verify)
        (out/('open_'+name+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0overlap\\control.vcd" -a "%~dp0'+name+'.gtkw" -S "%~dp0'+name+'.tcl"\n')
    (out/'wave_windows.json').write_text(json.dumps({'origin_ns':origin,'windows':windows,'physical_signals':len(signals)},indent=2))
    # Reuse the already verified native launch harness, with this run's inventory.
    harness=(ROOT/'deliverables/self_cnn_pair/validate_gtkwave.ps1').read_text(encoding='utf-8-sig')
    harness=harness.replace("@('overview','dual_mac','conv_write','post_write','result_ack')","@('overview','input','mac','result')").replace('dual/','overlap/').replace('dual\\','overlap\\').replace('26',str(len(signals)))
    (out/'validate_gtkwave.ps1').write_text(harness,encoding='utf-8')
    diagram(out/'architecture.drawio')
    baseline=s['scenarios']['base_overlap']['cycles'];table='\n'.join(f"| {v['k3']} | {v['k1']} | {v['post']} | {v['cycles']:,} | {v['speedup']:.3f}× |" for v in rows)
    testtable='\n'.join(f"| {n.removeprefix('four_k1_')} | PASS | {m['cycles']:,} |" for n,m in r['scenarios'].items())
    frames='\n'.join(f"| {f['frame']} | {f['input_begin']:,} | {f['input_commit']:,} | {f['first_launch']:,} | {f['read_complete']:,} |" for f in metric['frames'])
    report=f'''# 四图固定流程并行 / 流水验证

已经实现：CNN 接收一份固定流程和图片地址表，自主展开任务、处理层间依赖、分配算子。默认 **3×3 四套、1×1 两套，DW7 / Post / Add / Pad 各一套**。真实接入 bai-datasram 的四 bank、256 KiB SRAM；没有 NEureka 运行依赖。

四图重叠执行 **{metric['cycles']:,} 拍**；同配置逐张算完再输入下一张 **{serial['cycles']:,} 拍**，整批吞吐加速 **{serial['cycles']/metric['cycles']:.3f}×**。相对两套 K3、一套 K1 的重叠基线，周期减少 **{(1-metric['cycles']/baseline)*100:.2f}%**。串行对照包含每张相同输入传输和读结果成本，因此这是批次端到端对照，不能当作单层 MAC 加速比。

这轮为四张不同 7×7 RGB、诊断权重、每图 11 步短流程。所有算子都是实际 RTL。不是完整 MobileFaceNet、识别准确率或上板验收；完整综合的旧 Post / DW7 RAM 推断问题尚待解决。

## 看结果

- [四图流水时间线](frame_pipeline.png)：按图展示输入、各步骤和结果读取完成。
- [边输入边计算](input_overlap.png)：前 14,000 拍放大。
- [真实 MAC 同拍脉冲](mac_detail.png)：逐拍工作信号，不用 busy 冒充运算。
- [算子数量比较](operator_comparison.png)、[原始表格](operator_comparison.csv)。
- [接口和接入顺序](interface.md)、[可编辑架构图](architecture.drawio)。
- 原始波形 `overlap/control.vcd`；双击 `open_overview.cmd / open_input.cmd / open_mac.cmd / open_result.cmd` 打开 GTKWave。PNG 从实际 CSV 绘制，不是软件界面截图。

## 算子数量比较

其余 DW7 / Add / Pad 各一套。扫描采用同一个最大实例池，禁用未选单元；最终候选另行编译为实际 10 实例，再验证同样周期。

| K3 | K1 | Post | 四图周期 | 相对基线吞吐 |
|---:|---:|---:|---:|---:|
{table}

在四套 K3 后增加第二套 K1 有明显收益；第二套 Post 不再改善最快配置。三套 K3 的较省资源配置为 101,109 拍，可通过参数保留。此选择只适用于当前短流程，完整 MobileFaceNet 各层尺寸和通道不同，必须重新测量。

## 确实发生的重叠

- 最多 {metric['peak_active_frames']} 张图同时有在途任务；跨图片的实际 MAC / 接受写回同拍发生 {metric['multi_frame_work_cycles']:,} 拍。
- 多套 K3 同拍 MAC 共 {metric['multi_k3_mac_cycles']:,} 拍，峰值 {metric['peak_simultaneous_k3_mac']} 套；配置了四套不代表每拍四套都在 MAC。
- 不同种类算子实际工作同拍 {metric['cross_operator_work_cycles']:,} 拍，体现跨图阶段流水。
- 后续图片输入期间，已有图片实际 MAC {metric['input_mac_cycles']:,} 拍；IO 写接受与算子工作同拍 {metric['input_write_compute_cycles']} 拍。
- busy 含等待：多图在途 {metric['multi_frame_cycles']:,} 拍，不把它计作实际运算次数。

| frame | 首次输入 | 输入提交 | 首任务启动 | 结果读完 |
|---:|---:|---:|---:|---:|
{frames}

图 0 在图 1 的输入期间已经开始执行，其他图片亦按就绪逐张进入。所有首任务均晚于本图输入提交。图片早已在 SRAM 的 preloaded 场景同样通过，为 {r['scenarios']['four_k1_preloaded']['cycles']:,} 拍。

## 验证范围

| 场景 | 结果 | 周期 |
|---|---|---:|
{testtable}

每个场景检查 44 个硬件展开命令、28,812 个中间/最终字节、44 次槽分配和释放、四份真实 IO 读取的最终结果，以及输入/只读保护、槽尾保护、请求反压稳定、写响应排空后完成、慢读期间结果保持。结果总计 32 字节，SHA256：`{metric['output_sha256']}`。

预期中间值只在 checker 中；初始工作区和流式输入区为 A5。流式场景图像通过实际 SRAM IO 写入，preloaded 场景经 CPU A 口预装。CPU A 口初始化与背景访问是真实端口请求；压力场景制造同字 CPU 读碰撞，不能将其描述成完整 CPU 指令执行。清除场景在第二张图片部分写入、计算有未完成访问时取消并重启；内存故障场景使用全局复位恢复 bai 的锁存 fault。

独立地址展开控制测试还覆盖 1、2、3、4 张图、配置反压，以及四类非法配置。1～3 张的这项测试是控制验证，四张才是本轮完整短流程算术回归。

## 可追溯证据

- 算术/协议回归：`{run}`。
- 九组算子扫描：`{sweep}`。
- 地址展开控制：`{pr}`。
- 原始数据、输出、日志、计数分别在 `data/`、`tests/`、`sweep/`、`programmer/`。
- `regression.json` / `sweep.json` 保存源和输入哈希；`bai_source.json` 固定 SRAM 来源；`provenance.json` 保存交付文件哈希。
- 本轮先前调试运行曾因 XSim 参数化根层级名字导致 VCD 为空；最终运行已按真实层级选取并校验全部 {len(signals)} 个物理信号，未用空波形作证据。

100 MHz 只是仿真时钟。没有以 OOC 单算子资源推断整网可放入 FPGA，也没有执行旧版完整 MobileFaceNet 长仿真。下一步可在此地址驱动入口上扩展完整网络模板和缓存计划，而不改变“主机给图片地址、CNN 自主调度”的控制方式。
'''
    (out/'README.md').write_text(report,encoding='utf-8')
    provenance={'run':str(run),'sweep':str(sweep),'programmer':str(pr),'source_sha256':r['source_sha256'],'artifacts':{}}
    for f in out.rglob('*'):
        if f.is_file() and f.name!='provenance.json':provenance['artifacts'][f.relative_to(out).as_posix()]=sha(f)
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8');print(out)
if __name__=='__main__':main()
