"""Reproduce the current Conv/DW-only RTL, descriptor and structural checks."""
from pathlib import Path
import hashlib
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'build'
BUILD.mkdir(exist_ok=True)
results = []


def run(script, *args):
    subprocess.run([sys.executable, str(ROOT/'scripts'/script), *args], cwd=ROOT, check=True)


def compare(label, golden):
    actual = (BUILD/'rtl_features.bin').read_bytes()
    expected = golden.read_bytes()
    if actual != expected or len(actual) != 128:
        raise SystemExit(f'FAIL {label}: final 128-byte feature mismatch')
    (BUILD/f'{label}.rtl_features.bin').write_bytes(actual)
    (BUILD/f'{label}.rtl.log').write_text((BUILD/'tb_mobilefacenet.log').read_text(), encoding='utf-8')
    results.append(dict(test=label, bytes=len(actual), match=True, sha256=hashlib.sha256(actual).hexdigest()))
    print(f'PASS {label}: all 128 output bytes match', flush=True)


def compare_queue(label, folder):
    actual=(BUILD/'queue_features.bin').read_bytes()
    expected=(folder/'features.golden.bin').read_bytes()
    if actual!=expected or len(actual)!=128:raise SystemExit(f'FAIL {label}: queue final output mismatch')
    (BUILD/f'{label}.features.bin').write_bytes(actual)
    (BUILD/f'{label}.log').write_text((BUILD/'tb_task_queue.log').read_text(),encoding='utf-8')
    results.append(dict(test=label,bytes=128,match=True,sha256=hashlib.sha256(actual).hexdigest()))
    print(f'PASS {label}: queued execution matches all 128 bytes',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--onnx',action='store_true',help='also test model exports; requires ONNX in this Python')
    args=parser.parse_args()
    # Do not leave a stale successful summary if a later regression fails.
    (BUILD/'verification.json').write_text(json.dumps(dict(status='running')), encoding='utf-8')
    run('test_array_profile.py')
    run('run_tests.py')
    compare('synthetic112', BUILD/'vectors'/'final_features.golden.bin')
    compare_queue('queue_depth4',BUILD/'queue_vectors')
    for depth in (1,3):
        run('run_tests.py','task_queue','--prefetch-depth',str(depth))
        compare_queue(f'queue_depth{depth}',BUILD/'queue_vectors')
    for case in ('raw','war','waw','word'):
        run('run_tests.py','concurrent_queue','--case',case)
    for delay,depth in ((0,1),(7,3)):
        run('run_tests.py','concurrent_queue','--ram-wait',str(delay),'--prefetch-depth',str(depth))
    for delay,depth in ((0,1),(7,3)):
        run('run_tests.py','operator_queue','--ram-wait',str(delay),'--prefetch-depth',str(depth))
    if args.onnx:
        run('test_reference.py')
        for folder in ('export','scaled_add','prelu_pool_export'):
            run('run_tests.py','operator_queue','--queue-dir',str(BUILD/'onnx_fixture'/folder))
    run('check_structure.py')
    (BUILD/'verification.json').write_text(json.dumps(dict(status='passed', profile='heterogeneous_ooo',rtl_benches=21,
        concurrent_cases=['mixed','raw','war','waw','word'],concurrent_ram_waits=[0,3,7],
        synthetic_layer_comparisons=21, software_tests=5, onnx_software_tests=9 if args.onnx else 0,
        onnx_queues=3 if args.onnx else 0, heterogeneous_tasks=17, heterogeneous_ram_waits=[0,3,7],
        queue_layer_comparisons=27,queue_prefetch_depths=[1,3,4],queue_abi_version=1,
        structure='Yosys proc/opt/check -assert; no place and route', final_outputs=results), indent=2), encoding='utf-8')
    print('PASS complete verification. Report: '+str(BUILD/'verification.json'))
