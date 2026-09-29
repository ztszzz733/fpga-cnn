"""Generate a readable real-array waveform; compare every PE step with Python."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'systolic_wave'


def wrap(value):
    return (value + 2**31) % 2**32 - 2**31


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'examples' / 'systolic_wave.json')
    parser.add_argument('--open', action='store_true', help='open the selected signals in GTKWave')
    args = parser.parse_args()
    case = json.loads(args.input.read_text(encoding='utf-8-sig'))
    for key in ('weights', 'input_windows'):
        matrix = case[key]
        if len(matrix) != 2 or any(len(row) != 3 for row in matrix):
            parser.error(f'{key} must have two rows of three integers')
        if any(type(v) is not int or not -128 <= v <= 127 for row in matrix for v in row):
            parser.error(f'{key} values must be signed INT8')
    if len(case['bias']) != 2 or any(type(v) is not int or not -2**31 <= v < 2**31 for v in case['bias']):
        parser.error('bias must have two signed INT32 integers')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'result.json').write_text(json.dumps({'status': 'running'}), encoding='utf-8')
    (OUT / 'case_used.json').write_text(json.dumps(case, indent=2), encoding='utf-8')
    values = sum(case['weights'], []) + sum(case['input_windows'], []) + case['bias']
    (OUT / 'input.hex').write_text(''.join(f'{v & 0xffffffff:08x}\n' for v in values), encoding='ascii')
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'run_tests.py'), 'systolic_wave'], check=True)
    with (OUT / 'actual.csv').open() as stream:
        samples = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    if len(samples) != 17:
        raise RuntimeError(f'Expected 3 + 14 RUN cycles; observed {len(samples)}')
    acc = {(r, c): case['bias'][r] for r in range(2) for c in range(2)}
    comparison = []
    for tick, sample in enumerate(samples):
        assert sample['tick'] == tick
        for r in range(2):
            for c in range(2):
                cell = f'{r}{c}'
                k = tick-r-c
                valid = int(0 <= k < 3)
                assert sample['fire'+cell] == valid, (tick, cell, 'valid timing')
                weight = case['weights'][r][k] if valid else None
                value = case['input_windows'][c][k] if valid else None
                if valid:
                    assert sample['w'+cell] == weight and sample['x'+cell] == value, (tick, cell, 'operands')
                    acc[r, c] = wrap(acc[r, c] + weight*value)
                assert sample['acc'+cell] == acc[r, c], (tick, cell, 'accumulator')
                comparison.append(dict(time_ns=sample['time_ns'], tick=tick, pe=cell, fire=valid,
                                       weight=weight, input=value, expected=acc[r, c], actual=sample['acc'+cell]))
    with (OUT / 'comparison.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(comparison[0]));writer.writeheader();writer.writerows(comparison)
    rows=['# 阵列波形逐拍对照', '', '输入/权重/fire 看上升沿之前；acc 看同一个上升沿更新之后。',
          '矩阵只使用真实 8×8 阵列左上角 2×2 个 PE；没有 MMIO、RAM、量化等外围流程。', '',
          '| 时间 ns | RUN tick | PE00 | PE01 | PE10 | PE11 |', '|---|---|---|---|---|---|']
    for sample in samples:
        cells=[]
        for r,c in ((0,0),(0,1),(1,0),(1,1)):
            cell=f'{r}{c}'
            cells.append(f"{sample['w'+cell]} × {sample['x'+cell]} → {sample['acc'+cell]}" if sample['fire'+cell]
                         else f"保持 {sample['acc'+cell]}")
        rows.append('| '+' | '.join(map(str,[sample['time_ns'],sample['tick'],*cells]))+' |')
    rows += ['', '输入可以编辑 mobilefacenet/examples/systolic_wave.json，重新运行后本表自动更新。',
             'fire 是便于观察的组合信号，等于 ce && !load && a_valid && b_valid；它本身不是额外硬件控制。',
             'tick 在每个计算沿之后递增；表内 tick 是沿之前的值。最后一拍 tick 保持 16，done 拉高。']
    (OUT / 'comparison.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    wave=OUT / 'systolic.vcd';save=wave.with_suffix('.gtkw')
    # GTKWave: 0x28 binary, 0x420 signed decimal (right-justified).
    signals=[('28',n) for n in ('clk','rst_n','start','busy','array_ce','load_bias')]
    signals += [('24','run_tick[5:0]'),('28','done')]
    for cell in ('00','01','10','11'):
        signals += [('28','fire'+cell),('420','w'+cell+'[7:0]'),('420','x'+cell+'[7:0]'),('420','acc'+cell+'[31:0]')]
    save.write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1400 1000\n[signals_width] 240\n'
                    + ''.join(f'@{fmt}\ntb_systolic_wave.{name}\n' for fmt,name in signals),encoding='utf-8')
    result=[[acc[r,c] for c in range(2)] for r in range(2)]
    (OUT / 'result.json').write_text(json.dumps({'status':'passed','pe_samples':len(comparison),'result':result},indent=2),encoding='utf-8')
    print(f'PASS: all {len(comparison)} PE samples match Python. Final sums: {result}')
    print(f'Waveform: {wave}\nSelected signals: {save}\nComparison: {OUT / "comparison.md"}')
    if args.open:
        suite=Path(r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite')
        viewer=shutil.which(os.environ.get('GTKWAVE','gtkwave')) or str(suite/'bin'/'gtkwave.exe')
        tool_root=Path(viewer).resolve().parent.parent
        env=dict(os.environ)
        env['PATH']=os.pathsep.join([str(tool_root/'bin'),str(tool_root/'lib'),env.get('PATH','')])
        if os.name=='nt':
            env['GTK_EXE_PREFIX']=str(tool_root);env['GTK_DATA_PREFIX']=str(tool_root)
            cache=tool_root/'lib'/'gdk-pixbuf-2.0'/'2.10.0'/'loaders.cache'
            if cache.is_file():env['GDK_PIXBUF_MODULE_FILE']=str(cache)
        with (OUT/'gtkwave.log').open('w') as log:
            process=subprocess.Popen([viewer,'-f',str(wave),'-a',str(save),'-4','do_initial_zoom_fit 1'],
                                     env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                code=process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print(f'GTKWave started: PID {process.pid}')
            else:
                raise RuntimeError(f'GTKWave exited ({code}); see {OUT / "gtkwave.log"}')


if __name__=='__main__':
    main()
