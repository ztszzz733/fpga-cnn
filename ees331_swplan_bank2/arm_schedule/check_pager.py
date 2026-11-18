"""Run directed cache, bank concurrency and page-DMA fault regressions."""
import json
import argparse
from pathlib import Path
import subprocess
import simulate

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'source'
OUT = HERE / 'pager_regression'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(exist_ok=True)
    native = simulate.native_tools(
        simulate.REFERENCE / '.tools/verilator-native/verilator', Path('D:/visual studio2'))
    sources = [source / name for name in (
        'rtl/cnn_ddr/cnn_paged_mover.sv', 'storage_v2/rtl/data_mover.sv',
        'storage_v2/rtl/tile_local_ram.sv', 'storage_v2/rtl/tile_local_ram_bank2.sv')]
    executable = native.build_native(sources, 'cnn_paged_mover', output / 'compile',
        main=HERE / 'pager_regression.cpp', jobs=2,
        verilator_args=['--no-timing', '--assert', '-GCLIENTS=10', '-GLOCAL_BYTES=401408'])
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=180)
    (output / 'simulation.log').write_text(result.stdout + result.stderr)
    (output / 'result.json').write_text(json.dumps({
        'status': 'PASS' if result.returncode == 0 else 'FAIL',
        'sources_sha256': {str(p.relative_to(source)): simulate.sha(p) for p in sources},
        'test_sha256': simulate.sha(HERE / 'pager_regression.cpp'),
        'output': result.stdout + result.stderr}, indent=2) + '\n')
    print(result.stdout + result.stderr, flush=True)
    result.check_returncode()

if __name__ == '__main__':
    main()
