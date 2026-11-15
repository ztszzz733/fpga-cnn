"""Run existing 128 KiB cache/CNN RTL with delivered self-contained tile fixtures.
This is an additional diagnostic baseline, explicitly not a four-image full net.
"""
from run_native import ROOT,b
from pathlib import Path
import shutil,json,subprocess,time
SRC=ROOT/'baseline'
if not (SRC/'rtl/filelists/cnn_ees331.f').exists():
    raise FileNotFoundError('Bundled baseline filelist is missing')
names=[n for n in (SRC/'rtl/filelists/cnn_ees331.f').read_text().splitlines() if n and not n.startswith('#')]
names+=['tb/ees331_cnn_ddr_sim_top.sv','tb/integration/ees331_cnn_ddr_main.cpp','tb/integration/ees331_axi_ddr_model.hpp']
for n in names:
    dst=ROOT/'baseline'/n
    if not dst.exists():raise FileNotFoundError(dst)
out=ROOT/'build/cache128_tiles';out.mkdir(parents=True,exist_ok=True)
diagnostic=ROOT/'tb/diagnostic_ddr_main.cpp'
original=(ROOT/'baseline/tb/integration/ees331_cnn_ddr_main.cpp').read_text()
# New fixture header has extra unused contexts. Keep all old address/numerical
# checks; a one-frame diagnostic cannot assert cross-frame compute overlap.
diagnostic.write_text(original.replace('"ees331_axi_ddr_model.hpp"','"../baseline/tb/integration/ees331_axi_ddr_model.hpp"').replace('info.size()==40','info.size()>=40').replace('else need(multi_work&&peak_frames>1','else if(nf>1) need(multi_work&&peak_frames>1'))
record={'status':'RUNNING','full_network':False,'cache_bytes':131072,'sources':{n:b.sha(ROOT/'baseline'/n) for n in names},'scenarios':{}}
start=time.monotonic()
try:
    record['diagnostic_main_sha256']=b.sha(diagnostic)
    exe=b.build_native([ROOT/'baseline'/n for n in names if n.endswith('.sv')],'ees331_cnn_ddr_sim_top',out,main=diagnostic,verilator_args=['--no-timing','-DSYNTHESIS','-GCACHE_BYTES=131072'],jobs=2)
    record['compile_seconds']=time.monotonic()-start
    for case in ['short_row_2x2x2','tile_8x8x32']:
        fixture=out/(case+'_fixture')
        shutil.copytree(ROOT/'incoming/CNN_storage_handoff_v0.2/cases'/case/'native_fixture',fixture,dirs_exist_ok=True)
        m=[int(w,16) for w in (fixture/'template_meta.hex').read_text().split()]
        assert len(m)==3*26
        reduced=[]
        for i in range(3):
            row=m[i*26:(i+1)*26]
            assert not any(row[13:21]),'cannot truncate active dependency bits'
            reduced+=row[:13]+row[21:]
        (fixture/'template_meta.hex').write_text(''.join(f'{v:08x}\n' for v in reduced))
        for mode in ['overlap','serial','preloaded','stress']:
            target=out/(case+'_'+mode);target.mkdir(exist_ok=True)
            with (target/'simulation.log').open('w') as f:
                r=subprocess.run([str(exe),str(fixture),str(target),mode,'80'],stdout=f,stderr=subprocess.STDOUT,timeout=300)
            assert r.returncode==0,str(target/'simulation.log')
            metrics=json.loads((target/'metrics.json').read_text());assert metrics['status']=='PASS'
            record['scenarios'][case+'_'+mode]=metrics
            print(case,mode,'PASS',metrics['cycles'],flush=True)
    record['status']='PASS'
except Exception as e:
    record.update(status='FAIL',error=str(e));raise
finally:
    record['seconds']=time.monotonic()-start
    (out/'result.json').write_text(json.dumps(record,indent=2))
