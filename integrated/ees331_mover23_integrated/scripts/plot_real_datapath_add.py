"""Chinese ADD waveform and numeric trace for the isolated production-Datapath run."""
import argparse
import bisect
import json
import re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.patches import Polygon
from plot_waveforms import read_vcd, segments

parser=argparse.ArgumentParser()
parser.add_argument('--run-root',type=Path,required=True)
args=parser.parse_args()
job=args.run_root.resolve()/'add'
source_vcd=job/'waves/real_control_datapath.vcd'
vcd_text=source_vcd.read_text(encoding='utf-8')
# XSim emits integer MEM_BYTES parameters as width 0 despite the [31:0]
# declaration. Correct those header widths only in a separate plotting copy.
# The raw dump and every timestamp/value remain untouched.
def parameter_width(match):
    prefix, msb, lsb, suffix=match.groups()
    return prefix+str(abs(int(msb)-int(lsb))+1)+suffix
vcd_text, width_fixes=re.subn(r'(\$var\s+\w+\s+)0(?=\s+\S+\s+MEM_BYTES\s+\[(\d+):(\d+)\])(\s+\S+\s+MEM_BYTES\s+\[\d+:\d+\]\s+\$end)',parameter_width,vcd_text)
plot_vcd=job/'waves/real_control_datapath_plot.vcd'
plot_vcd.write_text(vcd_text,encoding='utf-8')
vcd=read_vcd(plot_vcd)
base='tb_cpu_datapath.'
entries=[
 ('clk','时钟',None),('rst_n','低有效复位',None),
 ('imem_addr','取指请求地址','hex'),('imem_re','允许取指请求',None),
 ('imem_rdata','同步返回的指令','hex'),('instr_d','译码级指令','hex'),
 ('dut.pc_d','译码级指令地址','hex'),
 ('rd_e','执行级目标编号','dec'),('dut.alu_a_e','运算输入甲','dec'),
 ('dut.alu_b_e','运算输入乙','dec'),('dut.alu_result_e','执行级计算结果','dec'),
 ('rd_m','访存级目标编号','dec'),('dut.alu_result_m','访存级暂存结果','dec'),
 ('dmem_re','数据存储器读请求',None),('dmem_we','数据存储器写请求',None),
 ('rd_w','写回级目标编号','dec'),('dut.wb_data_w','写回数据','dec'),
 ('dut.rf_we','寄存器实际写允许',None),('rf_writes','寄存器写入次数','dec'),
]
font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
plt.rcParams['font.family']='Microsoft YaHei'
plt.rcParams['axes.unicode_minus']=False
fig,axes=plt.subplots(len(entries),1,figsize=(13,13),sharex=True)
fig.patch.set_facecolor('#f7fafc')
start,end=28,95
for ax,(suffix,label,radix) in zip(axes,entries):
    signal=vcd.signals[base+suffix]
    ax.set_facecolor('#f7fafc');ax.set_ylim(-.2,1.2);ax.set_yticks([])
    ax.text(-.015,.5,label,transform=ax.transAxes,ha='right',va='center',fontsize=10)
    for left,right,bits in segments(signal,start,end):
        assert set(bits)<={'0','1'},(suffix,bits)
        value=int(bits,2)
        if signal.width==1:
            ax.plot([left,right],[value,value],color='#007e87',linewidth=1.5)
            if left>start:ax.plot([left,left],[0,1],color='#007e87',linewidth=1)
        else:
            bevel=min(.12,(right-left)/5)
            ax.add_patch(Polygon([(left,.5),(left+bevel,.12),(right-bevel,.12),(right,.5),(right-bevel,.88),(left+bevel,.88)],closed=True,facecolor='#cbe9ef',edgecolor='#496779',linewidth=.7))
            label_value=f'{value:08X}' if radix=='hex' else str(value)
            if right-left>len(label_value)*.25:ax.text((left+right)/2,.5,label_value,ha='center',va='center',fontsize=9)
    for edge in (35,45,55,65,75,85):ax.axvline(edge,color='#9db4c4',linewidth=.7,alpha=.65)
    for spine in ax.spines.values():spine.set_visible(False)
    ax.grid(axis='x',alpha=.15)
axes[-1].set_xlim(start,end);axes[-1].set_xticks(range(30,96,5));axes[-1].set_xlabel('仿真时间（纳秒）')
fig.suptitle('ADD（加法指令）：真实控制器＋真实数据通路，1 + 2 = 3',fontsize=16,fontweight='bold')
fig.text(.2,.025,'35：同步存储器接受取指请求  →  45：进入译码  →  55：进入执行\n65：进入访存  →  75：写回数据有效  →  85：寄存器完成写入',fontsize=10,color='#405060')
fig.subplots_adjust(left=.2,right=.98,top=.945,bottom=.09,hspace=.18)
(job/'figures').mkdir(exist_ok=True)
fig.savefig(job/'figures/add_real_datapath_cn.png',dpi=180,facecolor=fig.get_facecolor());plt.close(fig)

def at(suffix,time):
    signal=vcd.signals[base+suffix]
    index=bisect.bisect_right([t for t,_ in signal.events],time)-1
    bits=signal.events[index][1]
    assert set(bits)<={'0','1'},(suffix,time,bits)
    return int(bits,2)

fields=('instr_d','valid_d','valid_e','valid_m','valid_w','rd_e','rd_m','rd_w',
        'dut.pc_d','dut.pc_e','dut.alu_a_e','dut.alu_b_e','dut.alu_result_e',
        'dut.alu_result_m','dut.wb_data_w','dut.rf_we','rf_writes',
        'pc_sel','pc_en','if_id_en','if_id_flush','id_ex_flush','fwd_a','fwd_b',
        'dmem_re','dmem_we','dut.u_fetch.fetch_valid')
samples=[{'time_ns':time,**{suffix:at(suffix,time) for suffix in fields}} for time in (40,50,60,70,80,90)]
assert samples[1]['instr_d']==0x00208333
assert samples[2]['dut.alu_a_e']==1 and samples[2]['dut.alu_b_e']==2 and samples[2]['dut.alu_result_e']==3
assert samples[3]['dut.alu_result_m']==3 and samples[3]['rd_m']==6
assert samples[4]['dut.wb_data_w']==3 and samples[4]['rd_w']==6 and samples[4]['dut.rf_we']==1
assert samples[5]['rf_writes']==1
assert all(s['dmem_re']==0 and s['dmem_we']==0 for s in samples)
(job/'add_trace.json').write_text(json.dumps({'status':'PASS','raw_vcd':str(source_vcd),'plotting_header_width_corrections':width_fixes,'samples':samples},indent=2),encoding='utf-8')
print('PASS: real Datapath ADD numeric waveform checks')
print(job/'figures/add_real_datapath_cn.png')
