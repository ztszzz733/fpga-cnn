"""Compile/test the portable PS task service with local MSVC; no BSP or board."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib
from bootstrap_verilator_native import native_environment,run_logged
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_ees331_server');out.mkdir(parents=True)
    env=native_environment();src=ROOT/'firmware/ps_image_server'
    tracked=[src/n for n in ('server.c','server.h','test_server.c')]
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    cl='D:/visual studio2/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe'
    run_logged([cl,'/nologo','/std:c11','/W4','/O2',str(src/'server.c'),str(src/'test_server.c'),'/Fe:'+str(out/'server_test.exe')],out,env,out/'compile.log')
    r=subprocess.run([str(out/'server_test.exe')],cwd=out,capture_output=True,text=True)
    (out/'test.log').write_text(r.stdout+r.stderr);status='PASS' if r.returncode==0 and 'PASS EES331' in r.stdout else 'FAIL'
    same=all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.relative_to(ROOT).as_posix()] for p in tracked)
    if not same:status='FAIL'
    (out/'result.json').write_text(json.dumps({'status':status,'scope':'portable PS server C, mock CPU command callback; not ARM BSP/board execution',
        'source_sha256':hashes,'sources_unchanged':same,
        'executable_sha256':hashlib.sha256((out/'server_test.exe').read_bytes()).hexdigest()},indent=2)+'\n')
    print(out);print(r.stdout);print(r.stderr);raise SystemExit(0 if status=='PASS' else 1)
if __name__=='__main__':main()
