"""Actual CNN/MMIO protocol regression; uses arithmetic RTL and a delayed RAM TB."""
from pathlib import Path
from datetime import datetime
import hashlib,json,subprocess,time
from bootstrap_verilator_native import build_native,native_environment
ROOT=Path(__file__).resolve().parents[1]
names=['rtl/cnn_self/self_conv_engine.sv','rtl/cnn_quant/pad_hwc_engine.sv',
       'rtl/cnn_ddr/quant_post_bram_engine.sv','rtl/cnn_ddr/dw7_bram_engine.sv',
       'rtl/cnn_ddr/fixed_schedule_compact.sv','rtl/cnn_ddr/cnn_ees331.sv','tb/compact_cnn_mmio_tb.sv']
out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_compact_cnn')
out.mkdir(parents=True)
start=time.perf_counter()
exe=build_native([ROOT/n for n in names],'compact_cnn_mmio_tb',out, jobs=2)
compiled=time.perf_counter()-start
with (out/'simulation.log').open('w') as log:
    p=subprocess.run([str(exe)],cwd=out,env=native_environment(),stdout=log,stderr=subprocess.STDOUT)
text=(out/'simulation.log').read_text()
passed=p.returncode==0 and 'PASS compact_cnn_mmio_tb' in text
result={'status':'PASS' if passed else 'FAIL','compile_seconds':compiled,'total_seconds':time.perf_counter()-start,
        'sources_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},'log':text}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'out':str(out),**result},indent=2))
if not passed:raise SystemExit(1)
