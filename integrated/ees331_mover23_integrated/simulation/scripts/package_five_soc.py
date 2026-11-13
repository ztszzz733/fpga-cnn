"""Package only a completed, byte-checked full-SoC run and its actual states."""
from pathlib import Path
import json,csv,hashlib,shutil,subprocess
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
active=json.loads((SIM/'build/five_soc_active.json').read_text())
run=Path(active['run_dir']);record=json.loads((run/'result.json').read_text())
assert record['status']=='PASS'
out=BASE/'deliverables'/run.name;out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for rel,digest in record['sources'].items():assert sha(BASE/rel)==digest,rel
tool=SIM/'build/state_export_tool/export_soc_states'
subprocess.run([str(tool),str(run/'full/soc_five.fst'),str(out/'soc_states.fst')],check=True)
for name in ('metrics.json','outputs.bin','output_timing.csv','events.csv','simulation.log'):
 shutil.copyfile(run/'full'/name,out/name)
shutil.copyfile(run/'result.json',out/'result.json')
shutil.copyfile(SIM/'build/five_soc_adaptation.json',out/'five_context_changes.json')
for p in run.glob('checkpoint_*.json'):shutil.copyfile(p,out/p.name)
events=list(csv.DictReader((out/'events.csv').open()))
starts=[e for e in events if e['event']=='START'];ends=[e for e in events if e['event']=='COMPLETE']
assert len(starts)==len(ends)==655
assert sorted(int(e['node']) for e in starts)==list(range(655))
assert sorted(int(e['node']) for e in ends)==list(range(655))
assert sha(out/'outputs.bin')=='08863d5da4d2febb5a6f60ee8abd41712a48c53ff0c997161e283a87a11fa709'
units=['K3_'+str(i) for i in range(4)]+['K1_'+str(i) for i in range(12)]+['DW7']+['POST_'+str(i) for i in range(4)]+['ADD','PAD']
names=[]
def group(lines,title):lines.extend(['@200','-'+title])
def signal(lines,name,width=1,color=1,decimal=False):
 full='SOC.'+name+(('['+str(width-1)+':0]') if width>1 and not name.endswith('STATE_TEXT') else '')
 display=('+{'+name.replace('.','_').replace('_STATE_TEXT','_STATE')+'} '+full) if '.' in name else full
 lines.extend(['@24' if decimal else '@28' if width==1 else '@22','[color] '+str(color),display]);names.append(full)
for detailed in (False,True):
 lines=['[*]','[dumpfile] "soc_states.fst"','[size] 1800 1050','[signals_width] 450','[sst_width] 240'];names=[]
 group(lines,'CPU AND PS CONTROL')
 for n in ('RESET_RELEASED','PS_MAILBOX_WRITE','PS_MAILBOX_READ','CPU_WRITE_CNN','CPU_RAM_READ','CPU_RAM_WRITE'):signal(lines,n,color=2)
 for n in ('CPU_LAST_CFG_ADDR','CPU_LAST_CFG_DATA'):signal(lines,n,32,2)
 group(lines,'CNN AND STORAGE STATES')
 for n in ('CNN_RUNNING','CNN_COMPUTE_DONE','CNN_ERROR','MEMORY_FAULT'):signal(lines,n,color=3)
 for n in ('MEMORY_STATE_TEXT','MOVER_STATE_TEXT'):signal(lines,n,8,5)
 for n in ('DDR_RETURNING_DATA','DDR_SENDING_DATA'):signal(lines,n,color=6)
 signal(lines,'COMPLETED_TASKS',12,3,True)
 for n in ('PAGE_MISSES','DDR_READ_BYTES','DDR_WRITE_BYTES'):signal(lines,n,32,5,True)
 group(lines,'INDIVIDUAL CNN OPERATORS')
 for k,u in enumerate(units):
  if detailed:group(lines,u)
  signal(lines,u+'.STATE_TEXT',8,3+k//4%4)
  if detailed:
   for n in ('ACTIVE','WORK'):signal(lines,u+'.'+n,color=3+k//4%4)
   for n,bits in (('TASK',11),('FRAME_SLOT',3),('STEP',8)):signal(lines,u+'.'+n,bits,3+k//4%4,True)
 view='operators_detail' if detailed else 'soc_states'
 (out/(view+'.gtkw')).write_text('\n'.join(lines)+'\n')
 (out/(view+'_signals.json')).write_text(json.dumps(names,indent=2)+'\n')

markers=[(5,'RESET_RELEASED'),(int(starts[0]['cycle']),'FIRST_OPERATOR_START'),(max(int(e['cycle']) for e in ends),'ALL_655_TASKS_DONE')]
for e in events:
 if e['event']=='INPUT_READY':markers.append((int(e['cycle']),'INPUT_'+str(int(e['frame'])+1)+'_READY'))
 if e['event']=='DDR_RESULT':markers.append((int(e['cycle']),'OUTPUT_'+str(int(e['frame'])+1)+'_IN_DDR'))
markers.sort()
(out/'milestones.tcl').write_text('\n'.join('gtkwave::setNamedMarker %s %d %s'%(chr(65+i),cycle*10000,label) for i,(cycle,label) in enumerate(markers))+'\n')
windows_base='D:\\code\\FPGA1\\cpu_control (2)\\cpu_control\\tools\\gtkwave\\portable\\gtkwave64\\bin'
for view,filename in [('soc_states','open_states.cmd'),('operators_detail','open_operators.cmd')]:
 (out/filename).write_text('@echo off\nsetlocal\nset "GTK_BIN='+windows_base+'"\nset "PATH=%GTK_BIN%;%SystemRoot%\\System32;%SystemRoot%"\nstart "" /D "%~dp0" "%GTK_BIN%\\gtkwave.exe" -g -f "%~dp0soc_states.fst" -a "%~dp0'+view+'.gtkw" -S "%~dp0milestones.tcl"\n')
timings=list(csv.DictReader((out/'output_timing.csv').open()))
summary={'status':'PASS','frames':5,'tasks':655,'checked_intermediate_bytes':96686460,'output_bytes':640,
 'matches_previous_five_outputs':True,'output_sha256':sha(out/'outputs.bin'),'metrics':record['full']['metrics'],
 'compile_seconds':record['compile_seconds'],'simulation_seconds':record['full_seconds'],'raw_wave':str(run/'full/soc_five.fst'),
 'state_wave_sha256':sha(out/'soc_states.fst'),'timing_reference':'100MHz simulation clock, not board timing closure',
 'outputs':[dict(frame=int(t['frame'])+1,input_cycle=int(t['input_cycle']),ddr_result_cycle=int(t['ddr_result_cycle']),latency_cycles=int(t['latency_cycles']),result_ms=int(t['ddr_result_cycle'])/100000) for t in timings]}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
readme='''# 新版完整 SoC 五图仿真与状态波形

本次使用之前同一组五张 112×112 输入、每图131步，共655项任务。真实 CPU Control/Datapath、CNN、32 KiB tile RAM、分页适配和 DATA MOVER 均参与执行。PS 的 GP0 请求和 AXI3 DDR 使用仿真模型。

## 打开方式

- 双击 `open_states.cmd`：整机与23个算子的状态总览。
- 双击 `open_operators.cmd`：逐算子的状态、工作脉冲、任务、图片上下文和层步骤。
- `soc_states.fst` 来自本轮原始波形逐事件提取，保留原始时间戳，无抽样、无插值、无虚构活动。

## 放下游标后怎么看

每个算子 `STATE_TEXT` 为 `IDLE_NO_TASK`，表示没有在途任务；其余名称直接来自该实例的内部状态机。该文字是 `unit_active` 对实际FSM的限定：没有任务时统一显示空闲，避免完成状态寄存器停在FINISH被误认为仍在运行。

`INPUT_REQ/INPUT_WAIT` 是请求/等待输入，`WEIGHT_REQ/WEIGHT_WAIT` 是请求/等待权重，`MAC_READ/MAC_ACC/MAC_RUN/MAC` 是乘加计算阶段，`OUTPUT_REQ/OUTPUT_WAIT/WRITE_REQ/WRITE_WAIT` 是输出阶段。`PARAM_REQ/PARAM_WAIT` 是后处理参数读取。`SETUP/CHECK/TILE_BEGIN` 是准备和检查。

`WORK=1` 表示本拍实际工作推进。K3/K1/DW7是MAC推进；Post/Add/Pad是输出写请求被接受。MAC阶段不等于每一拍都有有效乘加，应结合WORK观察。`ACTIVE=1` 表示持有任务，包括等待数据。

`TASK` 是0～654的全局任务号；`FRAME_SLOT` 是0～4的图片上下文，对应第1～5张图；`STEP` 是每图0～130的任务步骤。空闲实例保留的TASK/FRAME_SLOT/STEP属于上一次任务。

## 整机各部分

`CPU_WRITE_CNN=1` 表示CPU此刻写CNN控制寄存器；为0不能推出CPU停止运行，它还会执行程序、读取邮箱和轮询状态。`CPU_LAST_CFG_ADDR/DATA` 保留最近一次实际写CNN的内容，不把无效时的地址变化当作配置。

`PS_MAILBOX_READ/WRITE` 表示PS模型发起的邮箱读/写请求；`CPU_RAM_READ/WRITE` 是真实软CPU本地RAM访问指示。它们属于接口活动观察，不是额外设计的CPU硬件状态机。

`CNN_RUNNING` 表示调度批次正在运行；`CNN_COMPUTE_DONE` 表示算子任务全部完成。`MEMORY_STATE_TEXT` 是分页存储FSM：LOCAL_ACCESS/LOCAL_REPLY为片内访问，PAGE_FILL_*为DDR调入，WRITEBACK_*为脏页写回，FENCE_SCAN为维护扫描。

`MOVER_STATE_TEXT` 是真实MOVER FSM：DDR_READ_REQ/WAIT读取DDR，LOCAL_REQ/WAIT访问tile RAM，DDR_WRITE/WAIT写DDR，PREPARE/NEXT_BEAT准备或推进传输，RESPONSE报告本次搬页完成。

`DDR_RETURNING_DATA/DDR_SENDING_DATA` 显示有效数据出现的时间，不单凭该信号计数传输。总搬运量看DDR_READ_BYTES/DDR_WRITE_BYTES。缺页PAGE_MISSES不是错误计数；CNN_ERROR/MEMORY_FAULT才是错误指示。

## 验证与范围

先在同一可执行程序上完成五图40任务小规模门槛，再运行完整五图。每次算子输出均与独立整数参考逐字节核对；655项任务全部启动、完成；最终结果须经真实MOVER写回，再由PS侧DDR模型读出核对。检查20个工作区保护区和模型只读区。最终640字节与之前五图结果完全一致。

新版原始入口只支持四上下文。本次把紧凑调度、CNN寄存器及真实RV32I固件的容量扩到五个上下文、20个槽；保留生产模块默认四上下文。算子算术、CPU Control/Datapath、32 KiB tile RAM、MOVER和分页策略未更改；沿用新版23路池（K3×4、K1×12、Post×4、DW7/Add/Pad各1）。

波形按100MHz仿真参考时钟记录，每周期10ns；这不是板级时序验收结果。计算完成、结果写回DDR、外部读取与批次收尾分别保留事件，不能只看末尾被清零的完成计数。

详细统计见summary.json；逐图输出时间见output_timing.csv；任务分配、完成和CPU请求事件见events.csv。原始完整接口波形位置记录在summary.json的raw_wave中。
'''
(out/'README.md').write_text(readme,encoding='utf-8')
(out/'validation.json').write_text(json.dumps({'status':'PASS','source_hashes_checked':len(record['sources']),'starts':655,'completions':655,'output_matches_previous_five':True,'state_export':'lossless, exact timestamps; task-qualified raw FSM'},indent=2)+'\n')
print(out)
