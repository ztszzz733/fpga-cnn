"""Edit examples/custom_input.json, then run this script to compare each RTL MAC."""
from pathlib import Path
import argparse
import csv
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'custom_wave'


def integer(value,lo,hi,name):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{name} must be an integer in [{lo}, {hi}]')
    return value


def read_case(path):
    case=json.loads(path.read_text(encoding='utf-8-sig'))
    for name in ('input','weight'):
        matrix=case[name]
        if not isinstance(matrix,list) or len(matrix)!=3 or any(not isinstance(row,list) or len(row)!=3 for row in matrix):
            raise ValueError(f'{name} must be a 3x3 matrix')
        for row in matrix:
            for value in row:integer(value,-128,127,name)
    integer(case['bias'],-2**31,2**31-1,'bias')
    integer(case['quant_shift'],0,255,'quant_shift')
    for key in ('relu_enable','relu6_enable'):
        if type(case[key]) is not bool:raise ValueError(f'{key} must be true or false')
    return case


def golden(case):
    # Plain Python integers, independent of RTL and the NumPy convolution reference.
    acc=case['bias'];steps=[]
    for tap,(a,b) in enumerate(zip(sum(case['input'],[]),sum(case['weight'],[]))):
        before=acc
        acc=((acc+a*b+2**31) % 2**32)-2**31
        steps.append(dict(step=tap+1,tap=tap,input=a,weight=b,product=a*b,acc_before=before,acc_after=acc))
    shifted=acc >> case['quant_shift']
    activated=max(0,shifted) if case['relu_enable'] or case['relu6_enable'] else shifted
    if case['relu6_enable']:activated=min(96,activated)
    return steps,dict(acc=acc,shifted=shifted,activated=activated,output=max(-128,min(127,activated)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'examples'/'custom_input.json')
    p.add_argument('--open',action='store_true',help='also launch GTKWave with selected signals')
    args=p.parse_args()
    try:case=read_case(args.input)
    except (ValueError,KeyError,OSError) as exc:p.exit(2,f'INPUT ERROR: {exc}\n')
    steps,result=golden(case)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'case_used.json').write_text(json.dumps(case,indent=2),encoding='utf-8')
    (OUT/'result.json').write_text(json.dumps(dict(status='running',expected=result),indent=2),encoding='utf-8')
    with (OUT/'expected_steps.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(steps[0]));writer.writeheader();writer.writerows(steps)
    print('STEP TAP INPUT WEIGHT PRODUCT ACC_AFTER',flush=True)
    for s in steps:print(f"{s['step']:4} {s['tap']:3} {s['input']:5} {s['weight']:6} {s['product']:7} {s['acc_after']:9}",flush=True)
    print(f"EXPECTED: acc={result['acc']}, shifted={result['shifted']}, activated={result['activated']}, INT8={result['output']}",flush=True)
    lp=0x13 | case['quant_shift']<<12 | int(case['relu_enable'])<<20 | int(case['relu6_enable'])<<21
    words=[case['bias'],lp,result['output']]
    for s in steps:words.extend([s['input'],s['weight'],s['acc_after']])
    (OUT/'expected.hex').write_text('\n'.join(f'{v & 0xffffffff:08x}' for v in words)+'\n',encoding='ascii')
    segments=[(0x100,sum(case['input'],[])),(0x200,sum(case['weight'],[])),
              (0x300,(case['bias'] & 0xffffffff).to_bytes(4,'little'))]
    (OUT/'ram.hex').write_text(''.join(f'@{address:08x}\n'+'\n'.join(f'{v & 255:02x}' for v in data)+'\n' for address,data in segments),encoding='ascii')
    subprocess.run([sys.executable,str(ROOT/'scripts'/'run_tests.py'),'custom_wave'],cwd=ROOT.parent,check=True)
    actual=list(csv.DictReader((OUT/'actual_steps.csv').open(encoding='utf-8')))
    if len(actual)!=9:raise RuntimeError('Expected 9 captured RTL samples')
    for expected,observed in zip(steps,actual):
        for key in ('step','tap','input','weight','acc_before','acc_after'):
            if expected[key]!=int(observed[key]):raise RuntimeError(f'Mismatch: {key}, step {expected["step"]}')
    rows=['# 自定义输入：波形对照表','','输入及权重按从左到右、从上到下的顺序读取。每行对应一次有效时钟上升沿。',
          f"\n初始 Bias：**{case['bias']}**。以下时间来自真实 RTL 采样，累计值由 Python 独立计算。\n",
          '| 次数 | 时间 ns | tap | av | wv | 乘积 | 预期累加值 | RTL 累加值 |',
          '|---|---|---|---|---|---|---|---|']
    for s,a in zip(steps,actual):
        rows.append(f"| {s['step']} | {a['time_ns']} | {s['tap']} | {s['input']} | {s['weight']} | {s['product']} | {s['acc_after']} | {a['acc_after']} |")
    rows.extend(['',f"最终累加：{result['acc']}；右移 {case['quant_shift']} 位：{result['shifted']}；激活后：{result['activated']}；饱和 INT8：**{result['output']}**。",
                 '',f"RAM 地址 0x401 的期望字节：0x{result['output'] & 255:02x}；STATUS 期望为 2（DONE=1，BUSY=ERROR=0）。",
                 '', '在上升沿之前查看 tap/av/wv，在同一个沿更新之后查看 normal_result；tap 会在该沿跳到下一位置。',
                 'out_we=1 的上升沿后，out_value 才变成最终输出。未使能时 av/wv 的变化不算一次乘加。'])
    (OUT/'comparison.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'scripts'/'render_wave.py'),'--custom'],cwd=ROOT,check=True)
    (OUT/'result.json').write_text(json.dumps(dict(status='passed',expected=result,rtl_steps=9),indent=2),encoding='utf-8')
    print(f'PASS: 9 MAC steps and final RAM output match. See {OUT / "comparison.md"}',flush=True)
    if args.open:
        subprocess.run([sys.executable,str(ROOT/'scripts'/'view_wave.py'),'--vcd',str(OUT/'custom.vcd'),
                        '--scope','tb_custom_wave.dut'],cwd=ROOT,check=True)


if __name__=='__main__':main()
