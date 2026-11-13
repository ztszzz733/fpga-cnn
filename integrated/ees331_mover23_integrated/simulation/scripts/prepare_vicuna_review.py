"""Export prepared programs with an explicit NOT RUN status; never claims PASS."""
import hashlib, json
from pathlib import Path
from test_vicuna_small import programs, ROOT, LINK

out=ROOT/'deliverables/vicuna2_preparation'
out.mkdir(parents=True,exist_ok=True)
items=[]
for name,asm,golden,values in programs():
    folder=out/name;folder.mkdir(exist_ok=True)
    (folder/'test.S').write_text(asm,encoding='utf-8')
    (folder/'link.ld').write_text(LINK,encoding='utf-8')
    (folder/'expected.bin').write_bytes(golden)
    record={'name':name,'status':'NOT_RUN','input_elements':19,'expected':values,
            'program_sha256':hashlib.sha256(asm.encode()).hexdigest()}
    (folder/'expected.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    items.append(record)
result={'status':'BLOCKED_ENVIRONMENT','error':'Wsl/Service/CreateInstance/CreateVm/HCS_E_CONNECTION_TIMEOUT',
        'compiled':False,'simulated':False,'passed_tests':0,'prepared_tests':items,
        'toolchain_sha256':'aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758',
        'production_rtl_changed':False}
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(out/'resume.cmd').write_text('@echo off\r\nwsl.exe -d Ubuntu-22.04 -e python3 "/mnt/d/code/FPGA1/cpu_control (2)/cpu_control/scripts/run_vicuna_small.py" --run-tests\r\npause\r\n',encoding='ascii')
print(out)
