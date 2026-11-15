"""Preserve completed demo and observed full-run windows after user stop."""
from pathlib import Path
import json,shutil,subprocess,hashlib,csv
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
active=json.loads((SIM/'build/five_soc_active.json').read_text());run=Path(active['run_dir'])
record=json.loads((run/'result.json').read_text());assert record['status']=='STOPPED_BY_USER'
out=BASE/'deliverables/five_soc_working_demo_20261112';out.mkdir(parents=True,exist_ok=True)
tool=SIM/'build/state_export_tool/export_soc_states'
subprocess.run([str(tool),str(run/'full/soc_five.fst'),str(out/'full_start_states.fst'),'0','300000000000'],check=True)
subprocess.run([str(tool),str(run/'full/soc_five.fst'),str(out/'full_overlap_states.fst'),'7000000000000','7002000000000'],check=True)
shutil.copyfile(run/'small/soc_states.fst',out/'small_complete_states.fst')
for n in ('metrics.json','outputs.bin','events.csv','output_timing.csv','simulation.log'):
 shutil.copyfile(run/'small'/n,out/('small_'+n))
for n in ('user_requested_stop.json','result.json'):shutil.copyfile(run/n,out/n)
units=['K3_'+str(i) for i in range(4)]+['K1_'+str(i) for i in range(12)]+['DW7']+['POST_'+str(i) for i in range(4)]+['ADD','PAD']
configs=[('full_overlap_states','open_states.cmd',False),('full_start_states','open_full_start.cmd',False),('small_complete_states','open_small_end_to_end.cmd',False),('full_overlap_states','open_operators.cmd',True)]
for stem,launcher,detail in configs:
 view=stem+('_detail' if detail else '')
 lines=['[*]','[dumpfile] "'+stem+'.fst"','[size] 1800 1050','[signals_width] 430','[sst_width] 240'];names=[]
 def group(name):lines.extend(['@200','-'+name])
 def sig(name,width=1,color=3,dec=False):
  full='SOC.'+name+(('['+str(width-1)+':0]') if width>1 and not name.endswith('STATE_TEXT') else '')
  display=('+{'+name.replace('.','_').replace('_STATE_TEXT','_STATE')+'} '+full) if '.' in name else full
  lines.extend(['@24' if dec else '@28' if width==1 else '@22','[color] '+str(color),display]);names.append(full)
 group('CPU AND PS')
 for n in ('RESET_RELEASED','PS_MAILBOX_READ','PS_MAILBOX_WRITE','CPU_WRITE_CNN','CPU_RAM_READ','CPU_RAM_WRITE'):sig(n,color=2)
 for n in ('CPU_LAST_CFG_ADDR','CPU_LAST_CFG_DATA'):sig(n,32,2)
 group('CNN AND MEMORY STATES')
 for n in ('CNN_RUNNING','CNN_COMPUTE_DONE','CNN_ERROR','MEMORY_FAULT'):sig(n)
 for n in ('MEMORY_STATE_TEXT','MOVER_STATE_TEXT'):sig(n,8,5)
 for n in ('DDR_RETURNING_DATA','DDR_SENDING_DATA'):sig(n,color=6)
 sig('COMPLETED_TASKS',12,3,True)
 for n in ('PAGE_MISSES','DDR_READ_BYTES','DDR_WRITE_BYTES'):sig(n,32,5,True)
 group('INDIVIDUAL OPERATOR STATES')
 for k,u in enumerate(units):
  if detail:group(u)
  sig(u+'.STATE_TEXT',8,3+k//4%4)
  if detail:
   for n in ('ACTIVE','WORK'):sig(u+'.'+n,color=3+k//4%4)
   for n,w in (('TASK',11),('FRAME_SLOT',3),('STEP',8)):sig(u+'.'+n,w,3+k//4%4,True)
 (out/(view+'.gtkw')).write_text('\n'.join(lines)+'\n')
 (out/(view+'_signals.json')).write_text(json.dumps(names,indent=2)+'\n')
 gtk='D:\\code\\FPGA1\\cpu_control (2)\\cpu_control\\tools\\gtkwave\\portable\\gtkwave64\\bin'
 (out/launcher).write_text('@echo off\nsetlocal\nset "GTK_BIN='+gtk+'"\nset "PATH=%GTK_BIN%;%SystemRoot%\\System32;%SystemRoot%"\nstart "" /D "%~dp0" "%GTK_BIN%\\gtkwave.exe" -g -f "%~dp0'+stem+'.fst" -a "%~dp0'+view+'.gtkw"\n')

metrics=json.loads((run/'small/metrics.json').read_text());assert metrics['status']=='PASS' and metrics['results']==5 and metrics['jobs']==40
summary={'status':'STOPPED_BY_USER','full_network_completed':False,'full_stopped_progress':record['stopped_progress'],'small_complete_soc_demo':metrics,
 'waves':{'full_start_states.fst':'Actual full-network startup, cycles 0..30000000; interrupted source, complete recorded blocks only','full_overlap_states.fst':'Actual full-network overlap window, cycles 700000000..700200000','small_complete_states.fst':'Completed five-image small SoC case, input through final DDR outputs'},
 'frame_mapping':'slots 0..4 correspond to images 1..5; task = step*5+slot','clock':'100MHz simulation reference, not board timing closure',
 'raw_full_wave':str(run/'full/soc_five.fst'),'raw_full_wave_note':'Interrupted FST with .hier sidecar; final unflushed tail may be missing. Exported windows lie within completed blocks.',
 'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.fst')}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
readme='''# 新版SoC工作过程与逐算子状态波形

用户确认以理解系统工作过程为目的，完整网络长仿真已主动停止。本目录保留实际发生的状态，不将未跑完的完整网络标成PASS。

## 打开哪一个

1. **open_states.cmd**：长仿真的算子重叠片段。把游标放在任意时刻，就能同时看CPU接口活动、存储状态、MOVER状态和23个算子各自的状态。
2. **open_operators.cmd**：同一片段展开每个算子的ACTIVE、WORK、任务号、图片上下文、步骤号。
3. **open_full_start.cmd**：之前那五张图的完整网络启动片段，含CPU配置、送图、Pad和卷积陆续启动。
4. **open_small_end_to_end.cmd**：已完整通过的五图小规模SoC验证，从输入到最终DDR输出。它是每图8任务的小任务链，不能当作每图131任务的完整网络结果。

时间按100MHz仿真参考时钟记录，每周期10ns；这是仿真时间，不是电脑等待时间或板级时序验收。长仿真重叠窗口保留7秒附近的原始时间坐标，没有移动时间轴。

## 系统实际怎样工作

```mermaid
flowchart LR
 PS[PS仿真模型：输入与邮箱命令] --> CPU[真实软CPU：执行固件、写配置]
 CPU --> S[CNN调度器：选择空闲实例]
 S --> O[K3 / K1 / DW7 / Post / Add / Pad]
 O <--> P[分页存储与32KiB本地RAM]
 P <--> M[真实DATA MOVER]
 M <--> D[DDR仿真模型]
 D --> R[PS侧核对最终输出]
```

算子不直接把数据递给下一个算子。上一个算子把输出写入存储，调度器在完成条件满足后启动后继算子，后继再从对应地址读取。数据页不在本地时，由MOVER从DDR调入；替换脏页或提交结果时再写回DDR。

## 状态文字怎么读

| 名称 | 含义 |
|---|---|
| IDLE_NO_TASK | 该实例没有在途任务 |
| SETUP / CHECK / TILE_BEGIN | 准备参数、检查、准备计算块 |
| INPUT_REQ / INPUT_WAIT / INPUT_LOAD | 请求或等待输入数据 |
| WEIGHT_REQ / WEIGHT_WAIT / WEIGHT_LOAD | 请求或等待权重 |
| MAC_READ / MAC_ACC / MAC_RUN / MAC | 乘加流水阶段 |
| PARAM_REQ / PARAM_WAIT | 读取后处理参数 |
| OUTPUT_REQ / OUTPUT_WAIT / WRITE_REQ / WRITE_WAIT | 输出请求或等待写入 |
| FINISH / FAIL | 内部完成状态或错误状态 |

STATE_TEXT的活动部分直接来自对应实例的真实RTL状态机；当unit_active=0时，统一显示IDLE_NO_TASK，避免内部寄存器停在FINISH造成误读。它不是另造一个控制算子的状态机。

ACTIVE=1包含等待数据；WORK=1才表示本拍实际工作推进。K3/K1/DW7的WORK是MAC推进，Post/Add/Pad的WORK是输出写请求被接受。因此MAC阶段不保证每拍都有有效乘加。

FRAME_SLOT为0～4，对应第1～5张图；STEP为从0开始的每图步骤号；TASK为全局任务号。空闲实例保留的任务编号是上一次任务，不表示它仍在执行。DW7/Add等在所选片段未启动时，显示空闲是正常的。

CPU_WRITE_CNN是实际写CNN寄存器的指示；为0不能说明CPU停止，它还会执行程序和轮询邮箱。CPU_LAST_CFG_ADDR/DATA保留最近一次实际写入值。CPU本身由指令控制，这里显示真实接口活动，不宣称增加了CPU硬件状态机。

MEMORY_STATE_TEXT：LOCAL_ACCESS/LOCAL_REPLY是片内访问；PAGE_FILL_*是DDR调入；WRITEBACK_*是脏页写回；FENCE_SCAN是维护扫描。

MOVER_STATE_TEXT：DDR_READ_REQ/WAIT读取DDR，LOCAL_REQ/WAIT访问本地RAM，DDR_WRITE/WAIT写DDR，PREPARE/NEXT_BEAT准备或推进传输，RESPONSE是本次搬运完成响应。

## 已验证到哪里

五图小规模整机检查PASS：40项任务、89820字节中间结果核对、5份DDR最终结果，共5120字节；真实CPU本地RAM读写已覆盖，跨图实际工作和MAC重叠均存在，峰值5个图片上下文在途。CPU、CNN、分页存储、本地RAM和MOVER均为真实RTL；PS GP0和DDR使用测试模型。

完整五图网络计划655项任务，在54项完成、累计核对28831992字节时按用户要求停止；没有完整网络最终结果，也没有全网PASS结论。长仿真原始FST未正常收尾，最后未刷新的尾段可能缺失；本目录仅从已写完的数据块提取明确时间窗口。完整过程的可关闭、可回放波形使用已PASS的小规模案例。

源码采用本分支集成包，增加五上下文支持和观察信号；默认生产参数仍为四上下文。算子算术、CPU Control/Datapath、MOVER和分页策略未更改。算子池沿用新版23路，和之前16算子独立CNN五图不是同一性能配置。

详细统计见summary.json；小规模结果见small_metrics.json与small_outputs.bin；停止记录见user_requested_stop.json。
'''
(out/'README.md').write_text(readme,encoding='utf-8')
print(out,flush=True)
