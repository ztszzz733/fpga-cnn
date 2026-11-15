"""Build/run real CPU + GP0 control test, with register-level CNN/cache responders."""
from pathlib import Path
from datetime import datetime
import subprocess,json,time
from bootstrap_verilator_native import build_native
from gen_ees331_cpu import generate
ROOT=Path(__file__).resolve().parents[1]
def main():
    generate()
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_ees331_control')
    out.mkdir(parents=True)
    lines=(ROOT/'rtl/filelists/system_cnn.f').read_text().splitlines()
    sources=[ROOT/p for p in lines if p.strip() and not p.startswith('#')]
    sources=sources[:sources.index(ROOT/'rtl/soc/datasram.sv')]
    sources += [ROOT/'rtl/soc/ees331/image_control_bridge.sv',ROOT/'tb/ees331_control_tb.sv']
    started=time.perf_counter()
    exe=build_native(sources,'ees331_control_tb',out/'compile',jobs=2)
    r=subprocess.run([str(exe)],cwd=ROOT,capture_output=True,text=True,timeout=120)
    (out/'sim.log').write_text(r.stdout+r.stderr)
    status='PASS' if r.returncode==0 and 'PASS EES331' in r.stdout else 'FAIL'
    (out/'result.json').write_text(json.dumps({'status':status,'seconds':time.perf_counter()-started,
        'scope':'real unchanged CPU, generated ROM, bridge RTL; register-level CNN/cache responders'},indent=2)+'\n')
    print(out);print(r.stdout[-2000:]);print(r.stderr[-1000:]);raise SystemExit(0 if status=='PASS' else 1)
if __name__=='__main__':main()
