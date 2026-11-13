#!/usr/bin/env python3
"""Independent arithmetic and memory-handshake regression for self_conv_engine.

The integer reference runs only while generating files. The RTL testbench loads
input/weight files into SRAM and keeps expected output in a separate array.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from run_tests import ROOT, execute, tool_env, tools


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(data, weights, width, height, channels, outputs, kernel, stride, dw):
    """HWC UINT8 times OHWI INT8 (DW: [C,K,K]), wrapping INT32 output."""
    result = bytearray()
    for oy in range((height - kernel) // stride + 1):
        for ox in range((width - kernel) // stride + 1):
            for oc in range(outputs):
                acc = 0
                for ky in range(kernel):
                    for kx in range(kernel):
                        for ic in ([oc] if dw else range(channels)):
                            ai = (((oy * stride + ky) * width + ox * stride + kx)
                                  * channels + ic)
                            wi = ((oc * kernel + ky) * kernel + kx)
                            if not dw:
                                wi = wi * channels + ic
                            acc += data[ai] * weights[wi]
                result.extend((acc & 0xffffffff).to_bytes(4, 'little'))
    return result


def write_hex(path: Path, values):
    path.write_text(''.join(f'{v & 255:02x}\n' for v in values), encoding='ascii')


def generate(run: Path, seed: int):
    rng = random.Random(seed)
    # Odd output width/height force a partial 2x2 tile; non-powers-of-two channel
    # counts also guard against assuming the historical NEureka 32-channel pack.
    specs = [
        ('pw1_channel_tail', 5, 3, 3, 5, 1, 1, False),
        ('pw1_stride2', 7, 5, 5, 3, 1, 2, False),
        ('conv3_stride1_tail', 5, 5, 3, 5, 3, 1, False),
        ('conv3_stride2_tail', 7, 7, 5, 3, 3, 2, False),
        ('conv3_one_output', 3, 3, 1, 1, 3, 1, False),
        ('dw3_stride1_tail', 5, 5, 7, 7, 3, 1, True),
        ('dw3_stride2_tail', 7, 7, 5, 5, 3, 2, True),
        ('dw3_one_output', 3, 3, 3, 3, 3, 1, True),
        ('pw1_max_channels', 1, 1, 512, 3, 1, 1, False),
        ('conv3_unsigned_extremes', 5, 4, 3, 2, 3, 1, False),
        ('dw3_negative_128', 4, 5, 3, 3, 3, 1, True),
        ('pw1_clear_read_restart', 3, 3, 3, 3, 1, 1, False),
        ('conv3_clear_write_restart', 5, 5, 3, 3, 3, 1, False),
        ('conv3_config_latched', 5, 5, 3, 3, 3, 1, False),
    ]
    manifest, calls = [], []
    for case_id, (name, w, h, ci, co, k, stride, dw) in enumerate(specs):
        data = [rng.randrange(256) for _ in range(w * h * ci)]
        weights = [rng.randrange(-128, 128) for _ in range(co * k * k * (1 if dw else ci))]
        # Include signed and unsigned corners in every sufficiently large case.
        for j, value in enumerate((0, 255, 128, 127, 1, 254)):
            if j < len(data):
                data[j] = value
        for j, value in enumerate((-128, 127, -1, 0, 1, -127)):
            if j < len(weights):
                weights[j] = value
        if 'unsigned_extremes' in name:
            data = [255 if i % 2 == 0 else 128 for i in range(len(data))]
            weights = [-128 if i % 3 else 127 for i in range(len(weights))]
        if 'negative_128' in name:
            data = [255] * len(data)
            weights = [-128] * len(weights)
        expected = reference(data, weights, w, h, ci, co, k, stride, dw)
        prefix = f'case_{case_id:02d}'
        for suffix, values in [('input', data), ('weight', weights), ('expected', expected)]:
            write_hex(run / f'{prefix}_{suffix}.hex', values)
        restart = 1 if 'clear_read' in name else 2 if 'clear_write' in name else 0
        latch = int('config_latched' in name)
        calls.append(f'run_case({case_id}, "{name}", {w}, {h}, {ci}, {co}, {k}, {stride}, '
                     f'{int(dw)}, {len(data)}, {len(weights)}, {len(expected)}, {restart}, {latch});')
        naive_reads = ((w - k) // stride + 1) * ((h - k) // stride + 1) * co * k * k * (1 if dw else ci)
        manifest.append(dict(id=case_id, name=name, width=w, height=h, in_channels=ci,
                             out_channels=co, kernel=k, stride=stride, depthwise=dw,
                             input_bytes=len(data), weight_bytes=len(weights),
                             output_bytes=len(expected), macs=naive_reads,
                             no_reuse_input_byte_reads=naive_reads,
                             no_reuse_weight_byte_reads=naive_reads,
                             input_sha256=hashlib.sha256(bytes(data)).hexdigest(),
                             weights_sha256=hashlib.sha256(bytes(x & 255 for x in weights)).hexdigest(),
                             expected_sha256=hashlib.sha256(expected).hexdigest()))
    (run / 'self_conv_cases.svh').write_text('\n'.join(calls) + '\n', encoding='ascii')
    (run / 'vectors.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=733)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--out-root', type=Path, default=ROOT / 'build/runs')
    parser.add_argument('--generate-only', action='store_true')
    parser.add_argument('--waves', action='store_true')
    args = parser.parse_args(argv)
    run = args.out_root.resolve() / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_self_conv_unit')
    run.mkdir(parents=True)
    print('RUN_DIR=' + str(run), flush=True)
    started = time.monotonic()
    result = dict(status='RUNNING', seed=args.seed, run_dir=str(run), simulator='xsim',
                  reference='independent Python scalar UINT8*INT8, raw INT32',
                  boundary='isolated convolution unit; no full network or synthesis claim', errors=[])
    files = [ROOT / 'rtl/cnn_self/self_conv_engine.sv', ROOT / 'tb/self_conv_unit.sv']
    try:
        result['cases'] = generate(run, args.seed)
        if args.generate_only:
            result['status'] = 'GENERATED'
        else:
            found = tools()
            missing = [name for name in ('xvlog', 'xelab', 'xsim') if not found.get(name)]
            if missing:
                raise RuntimeError('Missing XSim tools: ' + ', '.join(missing))
            env = tool_env(found)
            result['source_sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in [*files, Path(__file__)]}
            result['tools'] = {key: found[key] for key in ('xvlog', 'xelab', 'xsim')}
            compile_start = time.monotonic()
            execute([found['xvlog'], '-sv', '-i', run, *files], run, env, run / 'compile.log', args.timeout)
            execute([found['xelab'], 'tb_self_conv_unit', '-s', 'self_conv_unit_sim', '-debug', 'typical', '-mt', '2'],
                    run, env, run / 'compile.log', args.timeout)
            result['compile_seconds'] = time.monotonic() - compile_start
            tcl = ('open_vcd {self_conv_unit.vcd}\nlog_vcd [get_objects /tb_self_conv_unit/*]\n'
                   if args.waves else '')
            tcl += 'run all\n' + ('close_vcd\n' if args.waves else '') + 'quit\n'
            (run / 'run.tcl').write_text(tcl, encoding='ascii')
            simulation_start = time.monotonic()
            execute([found['xsim'], 'self_conv_unit_sim', '-tclbatch', 'run.tcl', '-onerror', 'quit'],
                    run, env, run / 'simulation.log', args.timeout)
            result['simulation_seconds'] = time.monotonic() - simulation_start
            log = (run / 'simulation.log').read_text(encoding='utf-8', errors='replace')
            if 'PASS tb_self_conv_unit' not in log or not (run / 'metrics.json').exists():
                clues = [line for line in log.splitlines() if any(x in line for x in ('Fatal:', 'ERROR:', 'FAIL'))]
                raise RuntimeError('Missing valid unit PASS: ' + ' | '.join(clues[-5:]))
            result['metrics'] = json.loads((run / 'metrics.json').read_text())
            for expected, actual in zip(result['cases'], result['metrics']['cases']):
                if actual['mac_count'] != expected['macs']:
                    raise RuntimeError(f"MAC count mismatch: {expected['name']}")
            if len(result['metrics']['cases']) != len(result['cases']):
                raise RuntimeError('Incomplete case list')
            result['outputs_sha256'] = digest(run / 'outputs.bin')
            result['status'] = 'PASS'
    except Exception as exc:
        result['status'] = 'FAIL'
        result['errors'].append(str(exc))
    result['total_seconds'] = time.monotonic() - started
    (run / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'run_dir', 'total_seconds', 'errors')}, ensure_ascii=False), flush=True)
    return 0 if result['status'] in ('PASS', 'GENERATED') else 1


if __name__ == '__main__':
    sys.exit(main())
