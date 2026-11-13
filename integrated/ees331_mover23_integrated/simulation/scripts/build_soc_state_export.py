from pathlib import Path
import subprocess,json
root=Path(__file__).resolve().parents[1]
g=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator/include/gtkwave')
z=root/'.tools/zlib-linux/usr'
out=root/'build/state_export_tool';out.mkdir(exist_ok=True)
objects=[]
for n in ('fstapi','fastlz','lz4'):
 p=out/(n+'.o');objects.append(p)
 if not p.exists():subprocess.run(['cc','-O2','-I'+str(z/'include'),'-c',str(g/(n+'.c')),'-o',str(p)],check=True)
exe=out/'export_soc_states'
subprocess.run(['c++','-O2','-std=c++17','-I'+str(g),'-I'+str(z/'include'),str(root/'scripts/export_soc_states.cpp'),*map(str,objects),str(z/'lib/x86_64-linux-gnu/libz.a'),'-o',str(exe)],check=True)
run=Path(json.loads((root/'build/five_soc_active.json').read_text())['run_dir'])
subprocess.run([str(exe),str(run/'small/soc_five.fst'),str(run/'small/soc_states.fst')],check=True)
print(exe,flush=True)
