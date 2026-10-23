#!/usr/bin/env python3
"""Synthesize all seven self-CNN units, preserving every run and failure log."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from run_tests import ROOT, tools, tool_env


def utilization_rows(report: str) -> dict:
    rows = {}
    for line in report.splitlines():
        columns = [c.strip().rstrip('*').strip() for c in line.split('|')[1:-1]]
        if len(columns) < 5 or not re.fullmatch(r'[\d,.]+', columns[1]):
            continue
        if columns[0] not in ('Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'):
            continue
        def numeric(value):
            value = value.replace(',', '')
            return float(value) if '.' in value else int(value)
        rows[columns[0]] = {'used': numeric(columns[1]), 'available': numeric(columns[-2]),
                            'utilization_percent': numeric(columns[-1])}
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--part', default='xc7z020clg484-1')
    parser.add_argument('--top', choices=['self_network_top', 'self_conv_engine'], default='self_network_top')
    parser.add_argument('--max-kernel', choices=[1, 3], type=int, default=3,
                        help='Only applies to --top self_conv_engine')
    parser.add_argument('--period-ns', type=float, default=10.0)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--out-root', type=Path, default=ROOT / 'build/runs')
    args = parser.parse_args()
    if args.period_ns <= 0 or args.timeout <= 0:
        parser.error('period and timeout must be positive')
    run = args.out_root.resolve() / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_self_cnn_synth')
    run.mkdir(parents=True)
    result = {'status': 'RUNNING', 'run_dir': str(run), 'top': args.top,
              'part': args.part, 'period_ns': args.period_ns, 'max_tasks': 64,
              'max_channels': 512, 'units': {'k3': 2, 'k1': 1, 'dw7': 1, 'post': 1, 'add': 1, 'pad': 1},
              'stage': 'out_of_context_synthesis', 'place_route_performed': False,
              'sources_sha256': {}, 'errors': []}
    if args.top == 'self_conv_engine':
        result.update(max_tasks=None, max_kernel=args.max_kernel, units={'convolution': 1})
    output = run / 'result.json'
    def save():
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    save()
    print('RUN_DIR=' + str(run), flush=True)
    started = time.monotonic()
    try:
        manifest = ROOT / 'rtl/filelists/cnn_self.f'
        sources = [ROOT / x.strip() for x in manifest.read_text().splitlines()
                   if x.strip() and not x.lstrip().startswith(('#', '//'))]
        sources += [manifest, Path(__file__).resolve(), ROOT / 'scripts/synth_self_cnn.tcl']
        result['sources_sha256'] = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        found = tools()
        base = Path(found.get('vivado_root', '/not-found'))
        vivado = base / ('bin/unwrapped/win64.o/vivado.exe' if os.name == 'nt' else 'bin/vivado')
        if not vivado.exists():
            candidate = shutil.which('vivado')
            if not candidate:
                raise RuntimeError('Vivado executable not found; set XILINX_VIVADO')
            vivado = Path(candidate)
        command = [str(vivado), '-mode', 'batch', '-nojournal', '-log', str(run / 'vivado.log'),
                   '-source', str(ROOT / 'scripts/synth_self_cnn.tcl'), '-tclargs', str(ROOT), str(run), args.part, str(args.period_ns), args.top, str(args.max_kernel)]
        result['command'] = command
        result['vivado'] = str(vivado)
        save()
        env = tool_env(found)
        # Match Vivado loader.bat's synthesis-library setup. The existing helper
        # only configures XSim, and Tcl interprets Windows backslashes as escapes.
        for key in ('RDI_DATADIR', 'RDI_APPROOT', 'RDI_LIBDIR', 'RDI_BINDIR',
                    'RDI_BASEROOT', 'XILINX_VIVADO', 'HDI_APPROOT', 'TCL_LIBRARY'):
            if key in env:
                env[key] = env[key].replace('\\', '/')
        env['RDI_BINROOT'] = (base / 'bin').as_posix()
        env['RT_LIBPATH'] = (base / 'scripts/rt/data').as_posix()
        env['RT_TCL_PATH'] = (base / 'scripts/rt/base_tcl/tcl').as_posix()
        env['SYNTH_COMMON'] = env['RT_LIBPATH']
        # OOC synthesis needs no user Tcl Store. Keep automatic package/cache
        # updates out of the user's profile (also avoids non-ASCII path issues).
        env['XILINX_LOCAL_USER_DATA'] = 'no'
        with (run / 'process.log').open('w', encoding='utf-8') as log:
            completed = subprocess.run(command, cwd=run, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=args.timeout)
        log_text = (run / 'process.log').read_text(encoding='utf-8', errors='replace')
        result['returncode'] = completed.returncode
        if completed.returncode or 'SELF_CNN_SYNTH_COMPLETE' not in log_text:
            errors = [line for line in log_text.splitlines() if line.startswith('ERROR:')]
            raise RuntimeError('Vivado synthesis did not complete: ' + (' | '.join(errors[-5:]) or str(completed.returncode)))
        result['utilization'] = utilization_rows((run / 'utilization.rpt').read_text(encoding='utf-8', errors='replace'))
        result['primitive_counts'] = {}
        for line in (run / 'primitive_counts.tsv').read_text().splitlines():
            name, value = line.split('\t')
            if name == 'worst_setup_slack_ns':
                result[name] = float(value)
            else:
                result['primitive_counts'][name] = int(value)
        complete_resources = {'Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'} <= result['utilization'].keys()
        result['resource_fit'] = all(v['used'] <= v['available'] for v in result['utilization'].values()) if complete_resources else None
        slack = result.get('worst_setup_slack_ns')
        result['synthesis_setup_met'] = slack >= 0 if slack is not None else None
        result['status'] = 'PASS'
    except subprocess.TimeoutExpired:
        result['status'] = 'TIMEOUT'
        result['errors'].append(f'Synthesis exceeded {args.timeout} s; no utilization/timing claim.')
    except Exception as exc:
        result['status'] = 'FAIL'
        result['errors'].append(str(exc))
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        save()
    print(result['status'] + ' ' + str(output), flush=True)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
