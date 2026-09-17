from pathlib import Path
import copy, json, subprocess, sys
root=Path(__file__).resolve().parents[1]
base=dict(input=[[1,2,3],[4,5,6],[7,8,9]],weight=[[1,1,1],[1,1,1],[1,1,1]],
          bias=0,quant_shift=0,relu_enable=False,relu6_enable=False,
          projection_weight=1,projection_bias=0,projection_quant_shift=0)
cases=[('default',copy.deepcopy(base),45)]
c=copy.deepcopy(base);c['input'][2][2]=10;cases.append(('changed',c,46))
c=copy.deepcopy(base);c['input']=[[-v for v in row] for row in c['input']];c['quant_shift']=1;cases.append(('negative_shift',c,-23))
c=copy.deepcopy(base);c['bias']=2000;c['relu6_enable']=True;c['projection_weight']=2;cases.append(('relu6_saturate',c,127))
for name,case,expected in cases:
    out=root/'build'/'custom_queue_checks'/name;out.mkdir(parents=True,exist_ok=True)
    source=out/'input.json';source.write_text(json.dumps(case),encoding='utf-8')
    subprocess.run([sys.executable,str(root/'scripts/custom_queue.py'),'--input',str(source),'--output',str(out)],check=True)
    result=json.loads((out/'result.json').read_text())
    assert result['status']=='passed' and result['final_values']==[expected]*128
    print(f'PASS independent expectation {name}: {expected}',flush=True)
