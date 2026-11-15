"""Run in the existing WSL toolchain; no simulation rerun is needed."""
import subprocess,tempfile,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'deliverables/stream_six_images'
p=json.loads((out/'provenance.json').read_text());run=root/'build/runs'/Path(p['run'].replace('\\','/')).name
g=root/'.tools/verilator-linux/verilator/include/gtkwave';z=root/'.tools/zlib-linux/usr'
with tempfile.TemporaryDirectory(prefix='two_frames_') as tmp:
    t=Path(tmp);objects=[]
    for n in ['fstapi','fastlz','lz4']:
        obj=t/(n+'.o');subprocess.run(['cc','-O2','-I'+str(z/'include'),'-c',str(g/(n+'.c')),'-o',str(obj)],check=True);objects.append(obj)
    exe=t/'extract';subprocess.run(['c++','-O2','-std=c++17','-I'+str(g),'-I'+str(z/'include'),str(root/'scripts/extract_two_frame_activity.cpp'),*map(str,objects),str(z/'lib/x86_64-linux-gnu/libz.a'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),str(run/'wave.fst'),str(out)],check=True)
