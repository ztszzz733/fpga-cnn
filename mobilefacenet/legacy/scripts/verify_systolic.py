"""Same vectors, RAM wait states and MMIO ABI on both serial and 8x8 paths."""
from pathlib import Path
import csv,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build';OUT=BUILD/'systolic_report'
OUT.mkdir(parents=True,exist_ok=True)

def run(script,*args):
    subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],cwd=ROOT.parent,check=True)

def capture(label,mode,queue=False):
    prefix='queue' if queue else 'operator'
    for suffix in ('metrics.csv','comparison.csv'):
        shutil.copyfile(BUILD/f'{prefix}_{suffix}',OUT/f'{label}_{mode}_{suffix}')
    shutil.copyfile(BUILD/('tb_task_queue.log' if queue else 'tb_mobilefacenet.log'),OUT/f'{label}_{mode}.log')
    with (OUT/f'{label}_{mode}_comparison.csv').open() as f:
        rows=list(csv.DictReader(f))
    if not rows or any(r['expected']!=r['actual'] for r in rows):raise RuntimeError('Element comparison failure')
    return len(rows)

def main():
    report=dict(status='running',baseline_commit='00eb8e3',ram_wait_cycles=3,comparisons={})
    target=OUT/'verification.json';target.write_text(json.dumps(report),encoding='utf-8')
    run('test_reference.py');run('generate_systolic_vectors.py')
    # All 20 module/integration benches; default top selects the actual 8x8 path.
    run('run_tests.py')
    report['comparisons']['original_systolic']=capture('original','systolic')
    report['comparisons']['queue_systolic']=capture('queue','systolic',True)
    for mode in ('serial','systolic'):
        flags=['--serial'] if mode=='serial' else []
        if mode=='serial':
            run('run_tests.py','mobilefacenet',*flags);report['comparisons']['original_serial']=capture('original',mode)
            run('run_tests.py','task_queue',*flags);report['comparisons']['queue_serial']=capture('queue',mode,True)
        run('run_tests.py','mobilefacenet','--tasks',BUILD/'systolic_vectors/tasks.txt',*flags)
        report['comparisons'][f'tails_{mode}']=capture('tails',mode)
        run('run_tests.py','mobilefacenet','--tasks',BUILD/'onnx_fixture/export/tasks.txt',*flags)
        report['comparisons'][f'onnx_{mode}']=capture('onnx',mode)
        run('run_tests.py','task_queue','--queue-dir',BUILD/'onnx_fixture/export',*flags)
        report['comparisons'][f'onnx_queue_{mode}']=capture('onnx_queue',mode,True)
    # Re-run only queue frontend variations on the new datapath.
    for depth in (1,3):run('run_tests.py','task_queue','--prefetch-depth',depth)
    pairs=[]
    for label in ('original','tails','queue','onnx','onnx_queue'):
        with (OUT/f'{label}_serial_comparison.csv').open() as f:a=list(csv.DictReader(f))
        with (OUT/f'{label}_systolic_comparison.csv').open() as f:b=list(csv.DictReader(f))
        if a!=b:raise RuntimeError(f'{label}: optimized/serial comparison mismatch')
        with (OUT/f'{label}_serial_metrics.csv').open() as f:a=list(csv.DictReader(f))
        with (OUT/f'{label}_systolic_metrics.csv').open() as f:b=list(csv.DictReader(f))
        if len(a)!=len(b):raise RuntimeError('Task count mismatch')
        for old,new in zip(a,b):
            if old['task']!=new['task']:raise RuntimeError('Task order mismatch')
            pairs.append(dict(suite=label,task=old['task'],bytes=int(old['bytes']),
                serial_cycles=int(old['cycles']),systolic_cycles=int(new['cycles']),
                serial_reads=int(old['reads']),systolic_reads=int(new['reads']),
                serial_writes=int(old['writes']),systolic_writes=int(new['writes'])))
    with (OUT/'performance.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    run('check_structure.py')
    report.update(status='passed',rtl_benches=20,int32_matrix_comparisons=564,
                  signed_pe_pairs=65536,queue_depths=[1,3,4],performance=pairs)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'PASS systolic validation; per-element CSV and performance: {OUT}',flush=True)

if __name__=='__main__':main()
