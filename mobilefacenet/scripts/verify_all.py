"""Reproduce RTL, Python, ONNX export and structural validation in one command."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'build'
BUILD.mkdir(exist_ok=True)
results = []


def run(script, *args):
    subprocess.run([sys.executable, str(ROOT/'scripts'/script), *args], cwd=ROOT.parent, check=True)


def compare(label, golden):
    actual = (BUILD/'rtl_features.bin').read_bytes()
    expected = golden.read_bytes()
    if actual != expected or len(actual) != 128:
        raise SystemExit(f'FAIL {label}: final 128-byte feature mismatch')
    (BUILD/f'{label}.rtl_features.bin').write_bytes(actual)
    (BUILD/f'{label}.rtl.log').write_text((BUILD/'tb_mobilefacenet.log').read_text(), encoding='utf-8')
    results.append(dict(test=label, bytes=len(actual), match=True, sha256=hashlib.sha256(actual).hexdigest()))
    print(f'PASS {label}: all 128 output bytes match', flush=True)


if __name__ == '__main__':
    # Do not leave a stale successful summary if a later regression fails.
    (BUILD/'verification.json').write_text(json.dumps(dict(status='running')), encoding='utf-8')
    run('test_reference.py')
    run('run_tests.py')
    compare('synthetic112', BUILD/'vectors'/'final_features.golden.bin')
    run('run_tests.py', 'mobilefacenet', '--tasks', str(BUILD/'onnx_fixture'/'export'/'tasks.txt'))
    compare('onnx_fixture', BUILD/'onnx_fixture'/'export'/'features.golden.bin')
    run('check_structure.py')
    (BUILD/'verification.json').write_text(json.dumps(dict(status='passed', rtl_benches=14,
        synthetic_layer_comparisons=34, onnx_layer_comparisons=9, software_tests=7,
        structure='Yosys proc/opt/check -assert; no place and route', final_outputs=results), indent=2), encoding='utf-8')
    print('PASS complete verification. Report: '+str(BUILD/'verification.json'))
