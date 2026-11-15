"""Actual six-peer RTL with real CPU firmware and GP0/HP0 bus models."""
from pathlib import Path
from datetime import datetime
import hashlib,json,subprocess,time
from bootstrap_verilator_native import build_native,native_environment
from gen_ees331_soc_tb import generate
ROOT=Path(__file__).resolve().parents[1]
def main():
    generate();out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_ees331_soc');out.mkdir(parents=True)
    listed=[ROOT/x for x in (ROOT/'rtl/filelists/system_cnn.f').read_text().splitlines() if x.strip() and not x.startswith('#')]
    sources=listed[:listed.index(ROOT/'rtl/soc/datasram.sv')]
    sources += [ROOT/x for x in (ROOT/'rtl/filelists/cnn_ees331.f').read_text().splitlines() if x.strip() and not x.startswith('#')]
    sources += [ROOT/'rtl/soc/clock_unit.sv',ROOT/'rtl/soc/ees331/image_control_bridge.sv',
        ROOT/'rtl/soc/ees331/face_soc_ees331_top.sv',ROOT/'tb/ees331_soc_sim_top.sv']
    maincpp=ROOT/'tb/integration/ees331_soc_main.cpp'
    tracked=sources+[maincpp,ROOT/'tb/integration/ees331_axi_ddr_model.hpp',ROOT/'firmware/ees331_cpu/program.mem']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    start=time.perf_counter();exe=build_native(sources,'ees331_soc_sim_top',out/'compile',main=maincpp,
        verilator_args=['--no-timing','-DEES331_EXTERNAL_PS','--output-split-cfuncs','500'],jobs=2)
    built=time.perf_counter()
    with (out/'sim.log').open('w') as log:r=subprocess.run([str(exe),str(ROOT/'build/self_full_small'),str(out)],cwd=ROOT,env=native_environment(),stdout=log,stderr=subprocess.STDOUT,timeout=900)
    good=r.returncode==0 and 'PASS EES331' in (out/'sim.log').read_text()
    same=all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p.relative_to(ROOT))] for p in tracked)
    report={'status':'PASS' if good and same else 'FAIL','compile_seconds':built-start,'simulation_seconds':time.perf_counter()-built,
        'scope':'actual six-peer top; real CPU/ROM/bridge/CNN/cache, AXI bus PS/DDR model; not board',
        'source_sha256':hashes,'sources_unchanged':same}
    if (out/'outputs.bin').exists():
        report['outputs_sha256']=hashlib.sha256((out/'outputs.bin').read_bytes()).hexdigest()
        expected=json.loads((ROOT/'build/self_full_small/manifest.json').read_text())['final_expected_sha256']
        report['expected_sha256']=expected
        if report['outputs_sha256']!=expected:report['status']='FAIL'
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out);print((out/'sim.log').read_text()[-3000:]);raise SystemExit(0 if report['status']=='PASS' else 1)
if __name__=='__main__':main()
