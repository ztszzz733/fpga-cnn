import json,subprocess,tempfile,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'deliverables/stream_six_images'
p=json.loads((out/'provenance.json').read_text());run=ROOT/'build/runs'/Path(p['run'].replace('\\','/')).name
sig=json.loads((out/'signal_catalog.json').read_text());r=json.loads((run/'result.json').read_text())
events=list(csv.DictReader((run/'events.csv').open()));first=int(events[0]['cycle'])*10000
states=['cpu_state','cnn_state','sram_state','imem_state','bridge_state','clock_state','soc_module_state','soc_active','soc_fault','frame_done','frames_done','pixel_frame']
g=ROOT/'.tools/verilator-linux/verilator/include/gtkwave';z=ROOT/'.tools/zlib-linux/usr'
with tempfile.TemporaryDirectory(prefix='fst_filter_') as tmp:
    t=Path(tmp);objects=[]
    for n in ['fstapi','fastlz','lz4']:
        obj=t/(n+'.o');subprocess.run(['cc','-O2','-I'+str(z/'include'),'-c',str(g/(n+'.c')),'-o',str(obj)],check=True);objects.append(obj)
    exe=t/'filter';subprocess.run(['c++','-O2','-std=c++17','-I'+str(g),'-I'+str(z/'include'),str(ROOT/'scripts/filter_stream_fst.cpp'),*map(str,objects),str(z/'lib/x86_64-linux-gnu/libz.a'),'-o',str(exe)],check=True)
    slices=[]
    for name,names,begin,end in [('all_modules',list(sig),first-500000,first+35000000),('all_frames',states,0,r['metrics']['total_cycles']*10000+100000),('power_on',list(sig),0,1500000)]:
        f=t/(name+'.txt');f.write_text('\n'.join(names)+'\n')
        subprocess.run([str(exe),str(run/'wave.fst'),str(out/(name+'.fst')),str(f),str(begin),str(end)],check=True)
        slices.append(dict(name=name,start_ps=begin,end_ps=end,signals=names))
    (out/'wave_windows.json').write_text(json.dumps(slices,indent=2))
