from pathlib import Path
import json,subprocess,hashlib
SIM=Path(__file__).resolve().parents[1]
m=json.loads((SIM/'build/mover_speed_baseline.json').read_text(encoding='utf-8-sig'))
bp=m['backup'];bp='/mnt/d/'+bp[3:].replace('\\','/') if bp[1:3]==':\\' else bp
old=Path(bp)/'simulation/tb/integration/ees331_axi_mover_model.hpp'
out=SIM/'build/mover_model_compat';out.mkdir(exist_ok=True)
(out/'legacy_axi_model.hpp').write_text(old.read_text().replace('struct AxiDdr','struct LegacyAxiDdr').replace('explicit AxiDdr','explicit LegacyAxiDdr'))
exe=out/'compat'
subprocess.run(['c++','-O2','-std=c++17','-I'+str(out),'-I'+str(SIM/'tb/integration'),str(SIM/'tb/integration/mover_model_compat.cpp'),'-o',str(exe)],check=True)
r=subprocess.run([str(exe)],text=True,capture_output=True,check=True);print(r.stdout,flush=True)
(out/'result.json').write_text(json.dumps({'status':'PASS','old_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'new_sha256':hashlib.sha256((SIM/'tb/integration/ees331_axi_mover_model.hpp').read_bytes()).hexdigest(),'result':r.stdout},indent=2)+'\n')
