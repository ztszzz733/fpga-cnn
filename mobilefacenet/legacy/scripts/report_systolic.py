"""Publish measured results after both simulation and gate synthesis succeed."""
from pathlib import Path
import csv,json,shutil
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'build'/'systolic_report';OUT=ROOT/'reports'/'systolic8'
verification=json.loads((SRC/'verification.json').read_text())
if verification['status']!='passed':raise SystemExit('Verification has not passed')
synthesis=json.loads((SRC/'synthesis_summary.json').read_text())
OUT.mkdir(parents=True,exist_ok=True)
for name in ('verification.json','performance.csv','synthesis_summary.json','resources_serial.json','resources_systolic.json'):
    shutil.copyfile(SRC/name,OUT/name)
    if name.endswith('.json'):
        (OUT/name).write_text((OUT/name).read_text(encoding='utf-8').rstrip()+'\n',encoding='utf-8')
for suite in ('original','tails','queue','onnx','onnx_queue'):
    shutil.copyfile(SRC/f'{suite}_systolic_comparison.csv',OUT/f'{suite}_comparison.csv')
shutil.copyfile(ROOT/'build'/'systolic_matmul.csv',OUT/'matrix_comparison.csv')
rows=verification['performance']
text=['# 8×8阵列实测结果（2026-09-17）','',
      '基线为保存于00eb8e3的串行路径，使用USE_SYSTOLIC=0；新路径为USE_SYSTOLIC=1。相同输入、权重、Bias、任务格式、RAM模型与3周期等待设置。',
      '', '## 验证结果','',
      '- 20个RTL testbench通过；PE覆盖65536组signed INT8乘法。',
      '- 分块矩阵包含小尺寸、8倍数、非8倍数、跨K块、独立DW通道和暂停/复位；564个INT32结果逐项一致。',
      '- 原34层用例、新增7组边界卷积、9层任务队列、ONNX 9层逐任务及9层队列均在两种路径运行，每个输出字节一致。',
      '- 队列暂存深度1/3/4通过；包含参数错误、未来任务表保护、RAM等待、忙时START、取数/计算/写回阶段复位、重新启动。',
      '- Python参考模型7项自检通过；数据路径复用原INT32回绕、算术右移、激活与INT8饱和约定。',
      '', '## 每任务周期与RAM访问','',
      'RAM计数为已握手的32位事务：读次数包括INT8写回所需的读改写；写次数为整字写事务。未增加byte-enable，因此每个输出INT8仍执行一次读改写。比值>1表示周期减少，<1表示新路径更慢。',
      '', '| 测试组 / 任务 | 旧周期 | 新周期 | 周期比 旧/新 | 旧读 | 新读 | 旧写 | 新写 |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:
    text.append(f"| {r['suite']} / {r['task']} | {r['serial_cycles']} | {r['systolic_cycles']} | {r['serial_cycles']/r['systolic_cycles']:.2f} | {r['serial_reads']} | {r['systolic_reads']} | {r['serial_writes']} | {r['systolic_writes']} |")
chain=[r for r in rows if r['suite']=='original' and r['task'].startswith('chain_')]
old=sum(r['serial_cycles'] for r in chain);new=sum(r['systolic_cycles'] for r in chain)
text += ['',f'112×112测试链15个任务周期合计：{old} → {new}，比值{old/new:.2f}。这是测试链周期计数，不能当作真实训练MobileFaceNet的耗时或识别帧率。',
         '', '单算子行含MMIO轮询及收尾开销；队列逐层行从dispatch到exec_done计数，TOTAL含描述符读取、队列提交和收尾。不同统计口径不要直接相加。',
         '', '## 综合资源','',
         '工具流程为Yosys `synth -top mobilefacenet_accelerator_top -flatten -noabc`，随后 `check -assert`。已完成存储映射与技术无关门级综合，未执行器件库/FPGA映射或布局布线。',
         '', '| 项目 | 串行 | 8×8阵列 |','|---|---:|---:|']
design=synthesis['results'];a=design['serial'];b=design['systolic']
def ff(d):return sum(v for k,v in d['num_cells_by_type'].items() if 'DFF' in k)
def hardware(d):return d['num_cells']-d['num_cells_by_type'].get('$scopeinfo',0)
text += [f"| 通用单比特硬件单元总数（排除scope元数据） | {hardware(a)} | {hardware(b)} |",
         f"| 其中DFF类单元 | {ff(a)} | {ff(b)} |",
         f"| 其余组合单元 | {hardware(a)-ff(a)} | {hardware(b)-ff(b)} |",
         '| 数据乘法器（架构数量） | 2个串行引擎各1个 | 64个PE |',
         '', 'DFF包含不同复位/使能形式。通用门数不是LUT数；综合后的乘法器已展开为门，不能把通用逻辑单元数解释成DSP数。具体类型明细见resources_serial.json和resources_systolic.json。',
         '', '## 逐项结果文件','',
         '- matrix_comparison.csv：原始INT32矩阵结果，共564项。',
         '- original_comparison.csv / tails_comparison.csv：普通算子与分块边界的每个输出INT8。',
         '- queue_comparison.csv / onnx_comparison.csv / onnx_queue_comparison.csv：多层实际RAM结果，未注入中间Golden。',
         '- performance.csv：完整的同任务前后周期/访问次数，可自行筛选和计算。',
         '', '逐项对照CSV包含expected/actual；验证脚本还比较了两条路径的完整逐项CSV完全相等。原始仿真及综合日志可由脚本重建，保存在build/systolic_report。',
         '', '## 未完成或不在此次结论内','',
         '- 未指定目标器件，未提供LUT/DSP/BRAM映射数、最高频率、时序收敛、布局布线或板级结果。',
         '- 无真实训练模型，因此无真实识别准确率、全MobileFaceNet模型帧率和功耗结论。',
         '- 未做加载/计算双缓冲重叠；RAM、可变地址乘除法和多路buffer选择仍可能是瓶颈。小任务可能因初始化/排空而变慢。',
         '- 普通卷积的K块固定最多8项，满块RUN阶段理想平均PE利用率为8/22≈36.4%，还未计入加载和写回；当前并非持续64 MAC/周期。']
(OUT/'README.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
print(OUT/'README.md')
