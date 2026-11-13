"""Create a portable source-and-evidence archive for the 23-client MOVER top."""
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile, ZIP_DEFLATED
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'delivery/ees331_mover23_integrated_20261111.zip'
ROOT_FILES = ('.gitattributes', '.gitignore', 'README.md', 'README_正式集成工程.md',
              'face_recognition_soc_spec_v0.1.md')
TREES = ('constraints', 'docs', 'firmware', 'network', 'partners', 'rtl', 'scripts',
         'simulation', 'storage_v2', 'sw', 'tb', 'tests', 'third_party', 'vivado', '说明文档')
EXCLUDED_DIRS = {'build', '.Xil', '.git', '.venv', '__pycache__', '.pytest_cache',
                 '.self_full_native', '.ees331_full_native'}
EXCLUDED_SUFFIXES = {'.pyc', '.vcd', '.fst', '.wdb', '.jou', '.log', '.pb'}

def allowed(path):
    rel = path.relative_to(ROOT)
    return not any(part in EXCLUDED_DIRS for part in rel.parts) and path.suffix.lower() not in EXCLUDED_SUFFIXES

files = [ROOT / name for name in ROOT_FILES]
for tree in TREES:
    files.extend(p for p in (ROOT / tree).rglob('*') if p.is_file() and allowed(p))
files.extend(p for p in (ROOT / 'deliverables/self_cnn_four_frames/data').rglob('*') if p.is_file())
files = sorted(set(files), key=lambda p: p.relative_to(ROOT).as_posix())
for path in files:
    if not path.is_file():
        raise FileNotFoundError(path)

evidence = {
    'evidence/synth/synth_status.txt': ROOT / 'build/mover23_pl_synth/synth_status.txt',
    'evidence/synth/utilization.rpt': ROOT / 'build/mover23_pl_synth/utilization.rpt',
    'evidence/synth/source_sha256.json': ROOT / 'build/mover23_pl_synth/source_sha256.json',
}
for case in ('short_row_2x2x2', 'tile_8x8x32', 'tile_8x8x32_four_frames',
             'four_frame_all_ops', 'four_frame_all_ops_k1_bank1',
             'four_frame_all_ops_k1_bank2'):
    for name in ('result.json', 'metrics.json', 'simulation.log', 'outputs.bin'):
        evidence[f'evidence/simulation/{case}/{name}'] = ROOT / f'simulation/build/mover23_soc/{case}/{name}'
evidence['evidence/simulation/coverage23.json'] = ROOT / 'simulation/build/mover23_soc/coverage23.json'
for name in ('result.json', 'simulation.log'):
    path = ROOT / 'simulation/build/mover23_faults' / name
    if path.exists():
        evidence[f'evidence/faults/{name}'] = path
for path in evidence.values():
    if not path.is_file():
        raise FileNotFoundError(path)

DEST.parent.mkdir(parents=True, exist_ok=True)
manifest = []
with ZipFile(DEST, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        name = 'ees331_mover23_integrated/' + path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        archive.writestr(name, data)
        manifest.append(f'{sha256(data).hexdigest()}  {name}')
    for name, path in sorted(evidence.items()):
        name = 'ees331_mover23_integrated/' + name
        data = path.read_bytes()
        archive.writestr(name, data)
        manifest.append(f'{sha256(data).hexdigest()}  {name}')
    archive.writestr('ees331_mover23_integrated/MANIFEST_SHA256.txt', '\n'.join(manifest) + '\n')
digest = sha256(DEST.read_bytes()).hexdigest()
(DEST.parent / (DEST.name + '.sha256')).write_text(f'{digest}  {DEST.name}\n')
shutil.copy2(ROOT / 'docs/存储系统集成进度_2026-11-11.md',
             DEST.parent / '存储系统集成进度_2026-11-11.md')
print(f'{DEST}\nfiles={len(files) + len(evidence) + 1}\nbytes={DEST.stat().st_size}\nsha256={digest}')
