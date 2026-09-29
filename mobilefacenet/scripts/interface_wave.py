# -*- coding: utf-8 -*-
"""Run three chained tasks and capture all requested hardware-interface signals."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from pack_queue import pack
from reference import execute, output_shape, write_golden, write_memh

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'interface_wave'
TB = 'tb_interface_wave.'
DUT = TB + 'dut.'
QUEUE = DUT + 'task_queue.'
ENG = DUT + 'systolic_path.engine.'
SUITE = Path(r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite')


def sig(scope, name, bits=32, fmt='22', meaning=''):
    return (scope + name, bits, '28' if bits == 1 else fmt, meaning)


# Hex for packed words/addresses, decimal for indices, signed decimal for results.
GROUPS = {
    'mmio': [
        sig(DUT, 'mmio_addr'), sig(DUT, 'mmio_wdata'), sig(DUT, 'mmio_we', 1),
        sig(DUT, 'regs.input_addr'), sig(DUT, 'regs.feature_size', fmt='24'),
        sig(DUT, 'regs.op_type', 4, '24'), sig(DUT, 'start', 1)],
    'queue': [
        sig(QUEUE, 'head_data', 256), sig(QUEUE, 'head_valid', 1), sig(QUEUE, 'head_ready', 1),
        sig(QUEUE, 'buffered', fmt='24'), sig(QUEUE, 'queue_base'), sig(QUEUE, 'queue_end', 64),
        *[sig(QUEUE, 'task_' + n) for n in ('input', 'output', 'weight', 'bias')],
        sig(QUEUE, 'task_op', 4, '24'),
        *[sig(QUEUE, 'task_' + n) for n in ('size', 'channels', 'param')],
        sig(QUEUE, 'exec_start', 1), sig(QUEUE, 'exec_done', 1), sig(QUEUE, 'completed', fmt='24')],
    'reader_fifo': [
        sig(QUEUE, 'reader.start', 1), sig(QUEUE, 'reader.base_address'),
        sig(QUEUE, 'reader.cmd_addr'), sig(QUEUE, 'reader.cmd_valid', 1), sig(QUEUE, 'reader.cmd_ready', 1),
        sig(QUEUE, 'reader.rsp_data'), sig(QUEUE, 'reader.rsp_valid', 1),
        sig(QUEUE, 'reader.descriptor', 256), sig(QUEUE, 'reader.descriptor_valid', 1),
        sig(QUEUE, 'fifo.in_data', 256), sig(QUEUE, 'fifo.in_valid', 1), sig(QUEUE, 'fifo.in_ready', 1),
        sig(QUEUE, 'fifo.level', fmt='24'), sig(QUEUE, 'fifo.out_data', 256),
        sig(QUEUE, 'fifo.out_valid', 1), sig(QUEUE, 'fifo.out_ready', 1)],
    'control': [
        sig(ENG, 'state', 4, '24'),
        *[sig(ENG, n, fmt='24') for n in ('mb', 'nb', 'kb')],
        *[sig(ENG, n, 4, '24') for n in ('nr', 'nc', 'nk')],
        *[sig(ENG, n, 3, '24') for n in ('row', 'col', 'kidx')],
        sig(ENG, 'clp'), sig(TB, 'quant_shift', 8, '24', 'clp[19:12] 的观察别名'),
        sig(ENG, 'read_address'), sig(ENG, 'output_address'),
        *[sig(ENG, n, 1) for n in ('a_we', 'b_we', 'bias_we')]],
    'cache': [
        sig(ENG, 'reads.req_addr'), sig(ENG, 'reads.req_valid', 1), sig(ENG, 'reads.req_ready', 1),
        sig(ENG, 'reads.req_byte', 1), sig(ENG, 'reads.req_bank', 1),
        sig(ENG, 'reads.cmd_addr'), sig(ENG, 'reads.cmd_valid', 1), sig(ENG, 'reads.cmd_ready', 1),
        sig(ENG, 'reads.rsp_data'), sig(ENG, 'reads.rsp_valid', 1),
        sig(ENG, 'reads.response_data'), sig(ENG, 'reads.response_valid', 1)],
    'array_output': [
        *[sig(ENG, 'tile.' + n, 3, '24') for n in ('wr_row', 'wr_col', 'wr_k')],
        sig(ENG, 'tile.wr_value', 8, '420'), sig(ENG, 'tile.wr_bias', 32, '420'),
        sig(ENG, 'tile.start', 1), sig(ENG, 'tile.accumulate', 1), sig(ENG, 'tile.done', 1),
        sig(ENG, 'sums', 2048),
        *[sig(TB, n, 32, '420') for n in ('sum_00', 'sum_01', 'sum_10', 'sum_11')],
        sig(ENG, 'row', 3, '24'), sig(ENG, 'col', 3, '24'),
        sig(TB, 'quant_shift', 8, '24', 'clp[19:12]'),
        sig(ENG, 'raw', 32, '420'), sig(ENG, 'out_value', 8, '420'),
        sig(ENG, 'output_store.we', 1), sig(ENG, 'output_address'),
        sig(ENG, 'cmd_valid', 1), sig(ENG, 'cmd_write', 1), sig(ENG, 'cmd_ready', 1)],
}
COMMON = [sig(TB, 'clk', 1), sig(TB, 'rst_n', 1), sig(TB, 'active_task', 32, '420'),
          sig(DUT, 'regs.done_sticky', 1), sig(DUT, 'regs.error_sticky', 1)]


def generate():
    folder = OUT / 'vectors'
    folder.mkdir(parents=True, exist_ok=True)
    memory = bytearray([0xa5]) * 16384
    x = np.arange(-9, 9, dtype=np.int8).reshape(2, 3, 3)
    memory[0x101:0x101+x.size] = x.tobytes()
    rng = np.random.default_rng(927)
    layers = []
    for i, (op, co, k, pad, shift) in enumerate([
        ('conv', 2, 1, 0, 1), ('depthwise', 2, 3, 1, 2), ('conv', 3, 3, 0, 1)
    ]):
        layer = dict(layer_id=i, name=f'task_{i}_{op}_{k}x{k}', op=op,
                     input_addr=[0x101, 0x401, 0x801][i], output_addr=[0x401, 0x801, 0xc01][i],
                     weight_addr=0x1001+0x100*i, bias_addr=0x1800+0x10*i,
                     width=3, height=3, in_channels=2, out_channels=co,
                     kernel=k, stride=1, padding=pad, quant_shift=shift,
                     relu_enable=False, relu6_enable=False)
        weights = rng.integers(-2, 3, (co, 1 if op == 'depthwise' else 2, k, k), dtype=np.int8)
        bias = np.array([3, -2, 5][:co], dtype='<i4')
        wa, ba = layer['weight_addr'], layer['bias_addr']
        memory[wa:wa+weights.size] = weights.tobytes()
        memory[ba:ba+bias.nbytes] = bias.tobytes()
        layers.append(layer)
    (folder/'ram_init.bin').write_bytes(memory)
    (folder/'layer_config.json').write_text(json.dumps({'layers': layers}, indent=2), encoding='utf-8')
    golden_memory = memory.copy()
    goldens = [execute(golden_memory, layer).copy() for layer in layers]
    for i, golden in enumerate(goldens):
        write_golden(folder/f'layer_{i:03d}.golden.hex', golden)
    pack(folder, 0x3000)
    golden_memory[0x3000:0x3060] = (folder/'queue.bin').read_bytes()
    write_memh(OUT/'expected_ram.hex', [(0, golden_memory)])
    return layers, goldens


def declarations(path):
    stack, result = [], {}
    with path.open(encoding='ascii') as stream:
        for line in stream:
            p = line.split()
            if not p: continue
            if p[0] == '$scope': stack.append(p[2])
            elif p[0] == '$upscope': stack.pop()
            elif p[0] == '$var': result['.'.join(stack + [p[4]])] = int(p[2])
            elif p[0] == '$enddefinitions': break
    return result


def make_views(wave):
    declared = declarations(wave)
    inventory = []
    for view, signals in GROUPS.items():
        for name, bits, fmt, meaning in COMMON + signals:
            if declared.get(name) != bits:
                raise RuntimeError(f'Missing signal or width mismatch: {name} ({bits})')
            inventory.append(dict(view=view, signal=name, bits=bits, meaning=meaning))
    with (OUT/'signals.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['view', 'signal', 'bits', 'meaning'])
        writer.writeheader(); writer.writerows(inventory)
    for view in ['all', *GROUPS]:
        groups = GROUPS if view == 'all' else {view: GROUPS[view]}
        lines = [f'[dumpfile] "{wave.as_posix()}"', '[timestart] 0', '[size] 1600 1000', '[signals_width] 520']
        for title, signals in {'common': COMMON, **groups}.items():
            lines += ['@200', '-' + title]
            for name, bits, fmt, _ in signals:
                lines += ['@' + fmt, name + (f'[{bits-1}:0]' if bits > 1 else '')]
        (OUT/f'{view}.gtkw').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return len({r['signal'] for r in inventory})


def open_view(view, wave=None):
    viewer = shutil.which(os.environ.get('GTKWAVE', 'gtkwave')) or str(SUITE/'bin'/'gtkwave.exe')
    root = Path(viewer).resolve().parent.parent
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([str(root/'bin'), str(root/'lib'), env.get('PATH', '')])
    if os.name == 'nt':
        env['GTK_EXE_PREFIX'] = str(root); env['GTK_DATA_PREFIX'] = str(root)
        cache = root/'lib'/'gdk-pixbuf-2.0'/'2.10.0'/'loaders.cache'
        if cache.is_file(): env['GDK_PIXBUF_MODULE_FILE'] = str(cache)
    with (OUT/'gtkwave.log').open('w') as log:
        proc = subprocess.Popen([viewer, '-f', str(wave or OUT/'interfaces.vcd'), '-a', str(OUT/f'{view}.gtkw'),
                                 '-4', 'do_initial_zoom_fit 1'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try: code = proc.wait(timeout=2)
    except subprocess.TimeoutExpired: print(f'GTKWave opened: PID {proc.pid}, view={view}')
    else: raise RuntimeError(f'GTKWave exited ({code}); see gtkwave.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--view', choices=['all', *GROUPS], default='all')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'result.json').write_text('{"status":"running"}', encoding='utf-8')
    layers, goldens = generate()
    subprocess.run([sys.executable, str(ROOT/'scripts'/'run_tests.py'), 'interface_wave'], check=True)
    signals = make_views(OUT/'interfaces.vcd')
    with (OUT/'events.csv').open() as f: events = list(csv.DictReader(f))
    starts = [e for e in events if e['event'] == 'TASK_START']
    ends = [e for e in events if e['event'] == 'TASK_DONE']
    if len(starts) != 3 or len(ends) != 3: raise RuntimeError('Expected three completed tasks')
    comparisons = []
    for i, (layer, golden) in enumerate(zip(layers, goldens)):
        writes = [e for e in events if e['event'] == 'OUTPUT' and int(e['task']) == i]
        expected = golden.reshape(-1)
        if len(writes) != expected.size: raise RuntimeError(f'Task {i} output count')
        offsets = [int(e['address_hex'], 16)-layer['output_addr'] for e in writes]
        if sorted(offsets) != list(range(expected.size)): raise RuntimeError(f'Task {i} output address coverage')
        for e, offset in zip(writes, offsets):
            raw = int(e['value_hex'], 16) & 255
            actual = raw if raw < 128 else raw-256
            if actual != int(expected[offset]): raise RuntimeError(f'Task {i} output value mismatch')
            comparisons.append(dict(task=i, time_ns=e['time_ns'], address=e['address_hex'],
                                    expected=int(expected[offset]), actual=actual))
    with (OUT/'comparison.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(comparisons[0])); writer.writeheader(); writer.writerows(comparisons)
    doc = ['# 三任务接口波形', '', '本文件中的时间来自本次实际仿真，时钟周期 10 ns。任务编号从 0 开始。',
           '', '默认打开 all.gtkw，包含全部指定信号及必要的有效/握手标志。同名信号使用完整模块路径区分。',
           '', '|任务|计算|输入 CHW|输出 CHW|启动 ns|完成 ns|', '|---|---|---|---|---|---|']
    for i, layer in enumerate(layers):
        doc.append(f"|{i}|{layer['op']} {layer['kernel']}×{layer['kernel']}|2×3×3|"
                   + '×'.join(map(str, output_shape(layer))) + f"|{starts[i]['time_ns']}|{ends[i]['time_ns']}|")
    doc += ['', '三个任务依次使用前一任务的输出，共核对 39 个结果字节；整片 16384 字节 RAM 与参考结果一致，包含输出周围的保护字节和任务表。',
            '', '## 分视图', '', '|保存文件|内容|', '|---|---|',
            '|all.gtkw|全部指定信号，按模块分组|', '|mmio.gtkw|CPU 写寄存器、任务表地址、数量和 op_type|',
            '|queue.gtkw|head_data、buffered、全部 task_* 与执行握手|',
            '|reader_fifo.gtkw|base_address、读取器 rsp_data/cmd_addr、descriptor、FIFO in_data/out_data/level|',
            '|control.gtkw|nr/nc/nk、row/col/kidx、clp、clp[19:12]、read_address/output_address|',
            '|cache.gtkw|req_addr、缓存 rsp_data/response_data/cmd_addr 和有效标志|',
            '|array_output.gtkw|缓冲写入、sums、结果选择 row/col、量化与 out_value|',
            '', '## 看波形时的对应关系', '',
            '- `.task_queue.reader.rsp_data/cmd_addr` 是任务读取器侧；`.systolic_path.engine.reads.rsp_data/cmd_addr` 是数据缓存侧。',
            '- `quant_shift[7:0]` 是 `clp[19:12]` 的纯观察别名；完整 clp 同时保留。',
            '- 装载位置 row/col 和输出选择 row/col 是同一组实际控制器寄存器，在 control 和 array_output 两个视图重复展示。',
            '- sums 保留完整 2048 位十六进制总线；sum_00/01/10/11 是其中四个 32 位结果的有符号十进制观察别名。raw 是当前选中的结果。',
            '- 地址和打包任务按十六进制显示，计数/索引按十进制，结果按有符号十进制。',
            '- 请求地址在 valid=1 时解读；rsp_data/response_data 在对应有效信号为 1 时解读；task_* 在 exec_start 的采样沿前查看。',
            '- 缓冲未写入时可能出现 X，最终有效结果已经全部核对。',
            '- 任务 0 含空间尾块；任务 1 的 9 项累加分成 8+1；任务 2 的 18 项累加分成 8+8+2，可看 kb/nk/accumulate。',
            '', '## 重新运行', '', '```powershell', 'python mobilefacenet/scripts/interface_wave.py --open', '```',
            '', '选择缓存视图：`python mobilefacenet/scripts/interface_wave.py --open --view cache`。',
            '', '完整信号路径清单见 signals.csv；逐次写回对照见 comparison.csv；时序事件见 events.csv。']
    (OUT/'guide.md').write_text('\n'.join(doc)+'\n', encoding='utf-8')
    result = dict(status='passed', tasks=3, descriptor_words=24, checked_outputs=len(comparisons),
                  checked_ram_bytes=16384, selected_unique_signals=signals,
                  tasks_timing=[dict(task=i, start_ns=int(starts[i]['time_ns']), done_ns=int(ends[i]['time_ns'])) for i in range(3)])
    (OUT/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    print(f'Wave: {OUT / "interfaces.vcd"}\nGuide: {OUT / "guide.md"}')
    if args.open: open_view(args.view)


if __name__ == '__main__':
    main()
