"""Run one real-CPU/23-CNN graph through all twelve physical K1 clients."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name('run_mover23_soc.py')
CASES = ('four_frame_all_ops', 'four_frame_all_ops_k1_bank1',
         'four_frame_all_ops_k1_bank2')
OUT = ROOT / 'build/mover23_soc/coverage23.json'

records = []
for case in CASES:
    print('running', case, flush=True)
    subprocess.run([sys.executable, str(SCRIPT), case], cwd=ROOT, check=True,
                   timeout=600)
    folder = ROOT / 'build/mover23_soc' / case
    result = json.loads((folder / 'result.json').read_text())
    metrics = json.loads((folder / 'metrics.json').read_text())
    assert result['status'] == metrics['status'] == 'PASS', case
    assert len(metrics['unit_starts']) == 23, case
    records.append(dict(case=case, jobs=metrics['jobs'],
                        unit_starts=metrics['unit_starts'],
                        output_sha256=hashlib.sha256((folder / 'outputs.bin').read_bytes()).hexdigest()))

totals = [sum(row['unit_starts'][i] for row in records) for i in range(23)]
assert all(totals), f'unused physical CNN clients: {[i for i, n in enumerate(totals) if not n]}'
assert len({row['output_sha256'] for row in records}) == 1, 'output differs by K1 bank'
summary = dict(status='PASS', actual_physical_clients_covered=23,
               total_physical_clients=23, combined_unit_starts=totals,
               output_sha256=records[0]['output_sha256'], cases=records)
OUT.write_text(json.dumps(summary, indent=2) + '\n')
print('PASS physical client coverage 23/23; identical output SHA-256',
      summary['output_sha256'])
