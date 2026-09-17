"""Comparable technology-independent gate synthesis; no device/Fmax claim."""
from pathlib import Path
import os,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build'/'systolic_report'
OUT.mkdir(parents=True,exist_ok=True)
tool=shutil.which(os.environ.get('YOSYS','yosys')) or r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite\bin\yosys.exe'
env=dict(os.environ);folder=Path(tool).parent
env['PATH']=os.pathsep.join([str(folder),str(folder.parent/'lib'),env.get('PATH','')])
results={}
for mode,enabled in [('serial',0),('systolic',1)]:
    print(f'Synthesizing {mode}: generic gates, no ABC or FPGA mapping',flush=True)
    output=OUT/f'resources_{mode}.json';script=OUT/f'synth_{mode}.ys'
    script.write_text('read_verilog -sv '+' '.join(p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'rtl').glob('*.sv')))+
        f'\nchparam -set USE_SYSTOLIC {enabled} mobilefacenet_accelerator_top\n'+
        'synth -top mobilefacenet_accelerator_top -flatten -noabc\ncheck -assert\n'+
        f'tee -o {output.relative_to(ROOT).as_posix()} stat -json\n',encoding='ascii')
    with (OUT/f'synth_{mode}.log').open('w',encoding='utf-8') as f:
        subprocess.run([tool,'-Q','-T','-s',str(script)],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=1200)
    stats=json.loads(output.read_text());design=stats['modules']['\\mobilefacenet_accelerator_top']
    results[mode]=design
    print(f"PASS {mode}: {design['num_cells']} generic cells",flush=True)
(OUT/'synthesis_summary.json').write_text(json.dumps(dict(flow='Yosys synth -flatten -noabc; generic gates, not LUT/DSP/BRAM or timing',results=results),indent=2),encoding='utf-8')
