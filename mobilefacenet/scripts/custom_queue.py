"""Editable three-task RAM queue: Conv3 -> Conv1(128 channels) -> FINAL128."""
from pathlib import Path
import argparse
import csv
import json
import subprocess
import sys
import numpy as np
from custom_wave import read_case, golden, integer
from reference import execute, write_golden
from pack_queue import pack

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args):
    subprocess.run([sys.executable, str(ROOT/'scripts'/script), *map(str,args)], cwd=ROOT.parent, check=True)


def prepare(case, out):
    memory = bytearray([0xa5])*262144
    memory[0x101:0x10a] = np.asarray(case['input'], dtype=np.int8).tobytes()
    memory[0x8000:0x8009] = np.asarray(case['weight'], dtype=np.int8).tobytes()
    memory[0x9000:0x9004] = int(case['bias']).to_bytes(4, 'little', signed=True)
    memory[0x8100:0x8180] = np.full(128,case['projection_weight'],dtype=np.int8).tobytes()
    memory[0x9100:0x9300] = np.full(128,case['projection_bias'],dtype='<i4').tobytes()
    base = dict(stride=1,padding=0,relu_enable=False,relu6_enable=False)
    layers = [
        dict(base,layer_id=0,name='editable_conv3',op='conv',input_addr=0x101,output_addr=0x1001,
             weight_addr=0x8000,bias_addr=0x9000,width=3,height=3,in_channels=1,out_channels=1,kernel=3,
             quant_shift=case['quant_shift'],relu_enable=case['relu_enable'],relu6_enable=case['relu6_enable']),
        dict(base,layer_id=1,name='projection128',op='conv',input_addr=0x1001,output_addr=0x2001,
             weight_addr=0x8100,bias_addr=0x9100,width=1,height=1,in_channels=1,out_channels=128,kernel=1,
             quant_shift=case['projection_quant_shift']),
        dict(base,layer_id=2,name='final128',op='final_output',input_addr=0x2001,output_addr=0x3001,
             weight_addr=0,bias_addr=0,width=1,height=1,in_channels=128,out_channels=128,kernel=0,stride=0,quant_shift=0)
    ]
    (out/'ram_init.bin').write_bytes(memory)
    (out/'layer_config.json').write_text(json.dumps(dict(layers=layers,relu6_max=96),indent=2),encoding='utf-8')
    outputs=[]
    for i,layer in enumerate(layers):
        y=execute(memory,layer)
        outputs.append(y.reshape(-1).tolist())
        write_golden(out/f'layer_{i:03d}.golden.hex',y)
    (out/'features.golden.bin').write_bytes(y.tobytes())
    pack(out,0x12000)
    return outputs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'examples'/'custom_queue_input.json')
    p.add_argument('--output',type=Path,default=ROOT/'build'/'custom_queue')
    p.add_argument('--prefetch-depth',type=int,default=4)
    p.add_argument('--open',action='store_true',help='open GTKWave after successful comparison')
    args=p.parse_args()
    try:
        case=read_case(args.input)
        integer(case['projection_weight'],-128,127,'projection_weight')
        integer(case['projection_bias'],-2**31,2**31-1,'projection_bias')
        integer(case['projection_quant_shift'],0,255,'projection_quant_shift')
        integer(args.prefetch_depth,1,4096,'prefetch_depth')
        out=args.output.resolve()
        if any(c.isspace() for c in str(out)):raise ValueError('Output path must not contain whitespace')
    except (ValueError,KeyError,OSError) as exc:p.exit(2,f'INPUT ERROR: {exc}\n')
    out.mkdir(parents=True,exist_ok=True)
    old=(out/'features.actual.bin').read_bytes() if (out/'features.actual.bin').is_file() else None
    (out/'result.json').write_text(json.dumps(dict(status='running')),encoding='utf-8')
    (out/'case_used.json').write_text(json.dumps(case,indent=2),encoding='utf-8')
    steps,first=golden(case)
    outputs=prepare(case,out)
    if outputs[0]!=[first['output']]:raise RuntimeError('Independent scalar/NumPy golden mismatch')
    print(f"EXPECTED: Conv3 acc={first['acc']}, shift={first['shifted']}, INT8={outputs[0][0]}",flush=True)
    print(f'EXPECTED: final feature[0..127] = {outputs[2][0]} (128 identical values)',flush=True)
    run('run_tests.py','task_queue','--queue-dir',out,'--queue-experiment','--waves','--prefetch-depth',args.prefetch_depth)
    actual=(out/'features.actual.bin').read_bytes()
    if len(actual)!=128 or actual!=(out/'features.golden.bin').read_bytes():raise RuntimeError('Final RAM mismatch')
    with (out/'actual_mac.csv').open() as f:mac=list(csv.DictReader(f))
    if len(mac)!=9:raise RuntimeError('Expected exactly nine first-task MAC samples')
    for expected,observed in zip(steps,mac):
        for key in ('tap','input','weight','acc_after'):
            if expected[key]!=int(observed[key]):raise RuntimeError(f'MAC mismatch: {key}')
    with (out/'actual_outputs.csv').open() as f:captures=list(csv.DictReader(f))
    if len(captures)!=257:raise RuntimeError('Expected 1 + 128 + 128 output captures')
    for task,values in enumerate(outputs):
        rows=[r for r in captures if int(r['task'])==task]
        if [int(r['value']) for r in rows]!=values:raise RuntimeError(f'Output latch mismatch: task {task}')
    changed=sum(a!=b for a,b in zip(old,actual)) if old is not None and len(old)==128 else None
    rows=['# 自己改输入：任务队列波形对照','',
          '该教学实验只START一次，执行3条RAM任务；不代表训练过的人脸特征。',
          f"\n输入文件：`{args.input.resolve()}`。本次快照见 `case_used.json`。",
          f"\n第一层：累加 **{first['acc']}** → 右移后 **{first['shifted']}** → 激活后 **{first['activated']}** → INT8 **{outputs[0][0]}**。",
          f"\n最终128个值全部为 **{outputs[2][0]}**，写入RAM **0x3001～0x3080**；STATUS=2。",
          '', '| 任务编号 | 运算 | 输出数量 | 预期值 | RTL实际值 | 首个输出采样时间 ns |',
          '|---|---|---|---|---|---|']
    for task,name in enumerate(('3×3 Conv','1×1 Conv → 128通道','FINAL_OUTPUT')):
        r=next(x for x in captures if int(x['task'])==task)
        rows.append(f"| {task} | {name} | {len(outputs[task])} | {outputs[task][0]} | {r['value']} | {r['time_ns']} |")
    rows += ['', '## 第一层的9次乘加','',
             '| tap | 采样时间 ns | 输入 av | 权重 wv | 乘积 | 预期累加 | RTL normal_result |',
             '|---|---|---|---|---|---|---|']
    for e,a in zip(steps,mac):
        rows.append(f"| {e['tap']} | {a['time_ns']} | {e['input']} | {e['weight']} | {e['product']} | {e['acc_after']} | {a['acc_after']} |")
    rows += ['', '## 如何看','',
             '- 先打开 `wave_mac_detail.png`：av是输入，wv是权重，normal_result是累加结果。',
             '- `sv=1`且引擎ready的上升沿接收乘加数据；输入取沿前值，累加结果看沿后。',
             '- `out_we=1`的上升沿锁存输出，随后看out_value。本表时间是上升沿后1ns的实际采样时间。',
             '- RAM实际写回稍晚。`ram_comparison.csv`记录每层完成时RAM的逐字节比对；`actual_outputs.csv`记录输出锁存时间。',
             '- `wave_overview.png`显示整条队列；queue_completed从0到3，最终STATUS.DONE保持1。内部done是单周期完成脉冲。',
             '- 两层使用相同权重且没有通道特有Bias，因此128个最终值相同；这是方便手算的有意设置。',
             '- 输入变动不一定改变输出：右移会丢低位，ReLU会将负数清零，INT8饱和会截在-128或127。']
    if changed is not None:rows += ['',f'与上次运行相比，128个最终输出中有 **{changed}** 个发生变化。']
    (out/'comparison.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    run('render_wave.py','--queue-dir',out)
    result=dict(status='passed',tasks=3,mac_samples=9,first_layer=first,
                final_values=outputs[2],changed_since_previous=changed,final_address='0x3001')
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'ACTUAL: final feature[0..127] = {outputs[2][0]}; PASS 9 MAC steps and all 257 RAM output bytes',flush=True)
    if changed is not None:print(f'CHANGED SINCE LAST RUN: {changed}/128 final bytes',flush=True)
    print(f'Read: {out / "comparison.md"}',flush=True)
    if args.open:run('view_wave.py','--vcd',out/'custom_queue.vcd','--scope','tb_task_queue.dut')


if __name__=='__main__':main()
