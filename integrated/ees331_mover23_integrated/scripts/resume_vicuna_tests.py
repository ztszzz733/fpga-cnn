"""Run fresh tests using an explicitly selected, successfully compiled model."""
import argparse, datetime, hashlib, json, subprocess, sys
from run_vicuna_small import ROOT, STAGE

def main():
    p=argparse.ArgumentParser(); p.add_argument('compiled_run'); a=p.parse_args()
    source=ROOT/a.compiled_run
    old=json.loads((source/'result.json').read_text())
    assert 'compile_seconds' in old
    assert 'Built target verilated_model' in (source/'compile.log').read_text()
    exe=STAGE/'model/verilated_model'
    digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    if 'simulator_sha256' in old: assert old['simulator_sha256']==digest
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_vicuna_small')
    out.mkdir(parents=True)
    result={k:old[k] for k in ['scope','upstream_commit','configuration','dependencies']}
    result.update(status='COMPILED_NOT_TESTED',reused_model_from=str(source.relative_to(ROOT)),
                  simulator_sha256=digest,configure_seconds=0,compile_seconds=0,
                  original_compile_seconds=old['compile_seconds'])
    (out/'result.json').write_text(json.dumps(result,indent=2))
    print('RUN_DIR='+str(out),flush=True)
    with (out/'tests.log').open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'scripts/test_vicuna_small.py'),str(out)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    print((out/'result.json').read_text(),flush=True)

if __name__=='__main__': main()
