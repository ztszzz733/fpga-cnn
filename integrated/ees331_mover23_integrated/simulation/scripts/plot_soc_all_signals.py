"""One sheet: every previously plotted SoC signal, with aligned time windows."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.collections import PolyCollection, LineCollection
from plot_waveforms import read_vcd, segments
from plot_soc_autoload_flow import LABELS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/figures/soc_autoload_flow'
GROUPS=[
    ('时钟复位',['clk','rst_n_in','rst_n']),
    ('CPU 与 IMEM',['imem_re','imem_addr','imem_rdata']),
    ('加载握手',['load_req','load_complete','load_error']),
    ('外部 UART',['uart_tx','uart_rx']),
    ('图像桥与 SRAM',['io_mem_req','io_mem_we','io_mem_gnt','io_mem_error','io_mem_addr','io_mem_be','io_mem_wdata']),
    ('CPU 与 CNN',['cnn_mmio_re','cnn_mmio_we','cnn_mmio_ready','cnn_mmio_addr','cnn_mmio_wdata','cnn_mmio_rdata']),
    ('CNN 与 SRAM',['mem_read','mem_write','mem_ready','mem_addr','mem_wdata','mem_rdata']),
    ('CPU 与 SRAM',['dmem_re','dmem_we','dmem_wstrb','dmem_addr','dmem_wdata','dmem_rdata']),
]
WINDOWS=[
    ('全程总览',0,315000,6.0,'us'),
    ('上电与取指',0,280,4.5,'ns'),
    ('首四字节写入',77520,77595,4.0,'ns'),
    ('加载交接与启动',311900,312490,6.0,'ns'),
    ('CNN 读数与写回',312850,313510,7.5,'ns'),
    ('CPU 读回与结束',313550,313835,5.0,'ns'),
]


def main():
    audit=json.loads((OUT/'waveform_audit.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(Path(audit['source_vcd']).read_bytes()).hexdigest()==audit['source_vcd_sha256']
    names=[n for group,items in GROUPS for n in items]
    assert len(names)==len(set(names))==36
    assert set(names)==set(audit['plotted_signals'])
    vcd=read_vcd(OUT/'soc_wires_only.vcd')
    font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
    plt.rcParams.update({'font.family':'Microsoft YaHei','svg.fonttype':'none','axes.unicode_minus':False})
    fig=plt.figure(figsize=(39,22),facecolor='#f6f9fc')
    grid=fig.add_gridspec(1,len(WINDOWS),left=.135,right=.985,bottom=.095,top=.86,
                         width_ratios=[w[3] for w in WINDOWS],wspace=.06)
    axes=[fig.add_subplot(grid[0,i]) for i in range(len(WINDOWS))]
    palette=['#426778','#20748c','#855496','#16816f','#16816f','#ae6221','#ae6221','#246891']
    label_entries=[]
    for group_idx,(group,items) in enumerate(GROUPS):
        for n in items: label_entries.append((n,group,group_idx))
    for column,(ax,(title,start,end,inches,unit)) in enumerate(zip(axes,WINDOWS)):
        scale=1000 if unit=='us' else 1
        span=end-start
        ax.set_facecolor('#f6f9fc');ax.set_xlim(start/scale,end/scale);ax.set_ylim(-.6,35.9)
        ax.set_yticks([]);ax.ticklabel_format(axis='x',style='plain',useOffset=False)
        ax.tick_params(axis='x',labelsize=10)
        ax.xaxis.set_major_locator(plt.MaxNLocator(5))
        ax.grid(axis='x',color='#abc1cd',alpha=.35,lw=.6)
        ax.set_xlabel('时间 / μs' if unit=='us' else '时间 / ns',fontsize=12,labelpad=12)
        ax.set_title(f'{title}\n{start/scale:g}～{end/scale:g} {"μs" if unit=="us" else "ns"}',
                     fontsize=17,fontweight='bold',pad=25,color='#153c53')
        for spine in ax.spines.values():spine.set_visible(False)
        previous_group=-1
        for row,(n,group,group_idx) in enumerate(label_entries):
            y=35-row; color=palette[group_idx]
            sig=vcd.signals['soc_wires.'+n]
            if row%2==0:ax.axhspan(y-.45,y+.45,color='#e8f0f5',alpha=.50,zorder=0)
            if group_idx!=previous_group:
                ax.axhline(y+.49,color='#7996a5',lw=1.0,alpha=.7)
                previous_group=group_idx
            if column==0:
                suffix=f' [{sig.width-1}:0]' if sig.width>1 else ''
                ax.text(-.038,y+.15,n+suffix,transform=ax.get_yaxis_transform(),ha='right',va='center',
                        fontsize=13,fontfamily='DejaVu Sans Mono',color=color)
                ax.text(-.038,y-.19,LABELS.get(n,group),transform=ax.get_yaxis_transform(),ha='right',va='center',
                        fontsize=10,color='#577080')
            sections=list(segments(sig,start,end))
            if sig.width==1:
                xx=[];yy=[];unknown=[]
                for a,b,bits in sections:
                    if bits in ('0','1'):
                        xx.extend([a/scale,b/scale]);yy.extend([y-.29+.58*int(bits)]*2)
                    else:
                        xx.extend([a/scale,b/scale]);yy.extend([float('nan')]*2)
                        unknown.append([(a/scale,y-.29),(a/scale,y+.29),(b/scale,y+.29),(b/scale,y-.29)])
                ax.plot(xx,yy,lw=.85,color=color)
                if unknown:ax.add_collection(PolyCollection(unknown,facecolor='#ecd393',edgecolor='none'))
            else:
                polys=[];fills=[]
                for a,b,bits in sections:
                    bevel=min(span*.003,(b-a)/5)
                    pts=[(a,y),(a+bevel,y-.29),(b-bevel,y-.29),(b,y),(b-bevel,y+.29),(a+bevel,y+.29)]
                    polys.append([(x/scale,z) for x,z in pts])
                    unknown=not set(bits)<={'0','1'}
                    fills.append('#ecd393' if unknown else '#dcebf0')
                    value='X' if unknown else f'{int(bits,2):X}'
                    # Labels stay inside their actual interval; narrow intervals remain unlabeled.
                    available_points=(b-a)/span*inches*65
                    if available_points>=len(value)*5.6+5:
                        ax.text((a+b)/2/scale,y,value,ha='center',va='center',fontsize=9,
                                fontfamily='DejaVu Sans Mono',color='#183948',clip_on=True,zorder=4)
                ax.add_collection(PolyCollection(polys,facecolors=fills,edgecolors='#628296',linewidths=.45))
        if column>0:
            ax.text(-.035,1.028,'//',transform=ax.transAxes,fontsize=16,color='#798f9b',ha='center')
    fig.text(.135,.963,'SoC 六模块 · 全部 36 根已展示信号合并波形',fontsize=29,fontweight='bold',color='#153c53')
    fig.text(.135,.937,'每根信号一行，各列严格按同一行对齐。第一列为全程，其余列是独立放大窗口，时间范围有重叠；不同列横轴比例不同。',fontsize=16,color='#486473')
    fig.text(.135,.917,'来自同一次真实 XSim 仿真；仅使用原接线图中的线路。总线为十六进制并省略前导零；高为 1、低为 0，黄色 X 表示未定义。',fontsize=14,color='#486473')
    fig.text(.135,.047,'看有效写入：时钟上升沿前 mem_write=1 且 mem_ready=1，再读 mem_wdata。显示 5 时尚在读旧字；合并为 A5A505A5 后才提交写入。',fontsize=15,color='#365465')
    fig.text(.135,.026,'本图仍是之前的 2×2 卷积演示（UART 加载输入、权重和任务表），不是“外部只传图像”的后续方案。原图和 RTL 保留。',fontsize=13,color='#587180')
    base=OUT/'soc_all_36_signals'
    fig.savefig(base.with_suffix('.png'),dpi=180,facecolor=fig.get_facecolor())
    fig.savefig(base.with_suffix('.svg'),facecolor=fig.get_facecolor())
    plt.close(fig)
    (OUT/'soc_all_36_signals_audit.json').write_text(json.dumps({
        'status':'PASS','signals':names,'same_signal_set_as_previous_figures':True,
        'source_vcd_sha256':audit['source_vcd_sha256'],
        'windows':[{'title':w[0],'start_ns':w[1],'end_ns':w[2]} for w in WINDOWS],
        'png_pixels':[7020,3960],'independent_zoom_columns':True,
    },ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: all 36 previous signals, each on one aligned row; 6 labeled time windows.')
    print(base.with_suffix('.png'))


if __name__=='__main__':main()
