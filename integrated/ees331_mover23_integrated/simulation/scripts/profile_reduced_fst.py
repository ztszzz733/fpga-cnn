from pathlib import Path
import subprocess,json,csv,os
SIM=Path(__file__).resolve().parents[1]
g=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator/include/gtkwave');z=SIM/'.tools/zlib-linux/usr'
build=SIM/'build/reduced_state_export';exe=build/'profile_reduced_fst'
objects=[SIM/'build/state_export_tool'/(n+'.o') for n in ('fstapi','fastlz','lz4')]
subprocess.run(['c++','-O2','-std=c++17','-I'+str(g),'-I'+str(z/'include'),str(SIM/'scripts/profile_reduced_fst.cpp'),*map(str,objects),str(z/'lib/x86_64-linux-gnu/libz.a'),'-o',str(exe)],check=True)
run=Path(os.environ.get('SOC_RUN_DIR',json.loads((SIM/'build/reduced_soc_active.json').read_text())['run_dir']))
t=next(csv.DictReader((run/'full/output_timing.csv').open()))
out=run/'full/recorded_performance_profile.json'
subprocess.run([str(exe),str(run/'full/soc_reduced.fst'),str(int(t['input_cycle'])*10000),str(int(t['ddr_result_cycle'])*10000),str(out)],check=True)
print(out.read_text(),flush=True)
