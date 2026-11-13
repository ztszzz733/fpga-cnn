"""Read-only Linux tool probe for the isolated Vicuna evaluation."""
import json, shutil, subprocess
from pathlib import Path

names = ['cmake', 'g++', 'make', 'python3', 'clang', 'clang-18', 'ld.lld',
         'riscv64-unknown-elf-gcc', 'riscv32-unknown-elf-gcc', 'verilator']
print(json.dumps({n: shutil.which(n) for n in names}, indent=2), flush=True)
for folder in ['/opt', '/usr/local/bin']:
    print(folder, list(str(p) for p in Path(folder).glob('*')), flush=True)
