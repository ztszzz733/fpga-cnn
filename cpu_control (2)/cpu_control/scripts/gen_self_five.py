"""Select five verified inputs and independent integer references; never RTL outputs."""
from pathlib import Path
from gen_self_fifteen import generate

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    for size in ('small','full'):
        generate(ROOT/('build/self_ten_'+size),ROOT/('build/self_five_'+size),
                 nf=5,tasks=1024,capacity=32*1024*1024)
