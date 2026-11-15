"""Run EES331 project creation/build using the installed Vivado environment."""
import argparse
import os
from datetime import datetime
import json
import hashlib
import shutil
import subprocess
import time
from pathlib import Path
from run_tests import ROOT,tools,tool_env

def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['ps','synth','impl'])
    p.add_argument('--project',type=Path)
    p.add_argument('--board-preset',type=Path)
    a=p.parse_args()
    out=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_ees331_'+a.stage)
    out.mkdir(parents=True)
    found=tools();env=tool_env(found)
    base=Path(found['vivado_root'])
    for key in ('RDI_DATADIR','RDI_APPROOT','RDI_LIBDIR','RDI_BINDIR','RDI_BASEROOT','XILINX_VIVADO','HDI_APPROOT','TCL_LIBRARY'):
        if key in env:env[key]=env[key].replace('\\','/')
    env.update(RDI_BINROOT=(base/'bin').as_posix(),RT_LIBPATH=(base/'scripts/rt/data').as_posix(),RT_TCL_PATH=(base/'scripts/rt/base_tcl/tcl').as_posix(),SYNTH_COMMON=(base/'scripts/rt/data').as_posix(),XILINX_LOCAL_USER_DATA='no')
    # Project-mode launch_runs locates loader.bat through PATH (OOC does not).
    env['PATH']=str(base/'bin')+os.pathsep+env['PATH']
    exe=base/'bin/unwrapped/win64.o/vivado.exe'
    script=ROOT/'scripts'/('create_ees331_bd.tcl' if a.stage=='ps' else 'build_ees331.tcl')
    # Vivado project names reject parentheses, including parent directories.
    # Keep generated vendor data outside the source path; no source is moved.
    project=a.project or Path('D:/zhang/ees331_build')/out.name
    build_root=ROOT
    source_hashes={}
    if a.stage!='ps':
        listing=ROOT/'rtl/filelists/system_ees331.f'
        names=[x.strip() for x in listing.read_text().splitlines() if x.strip() and not x.startswith('#')]
        names+=['rtl/filelists/system_ees331.f','firmware/ees331_cpu/program.mem']
        source_hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
        build_root=project/'source_snapshot'
        stamp=project/'source_snapshot.json'
        if a.stage=='impl':
            assert json.loads(stamp.read_text())==source_hashes,'Sources changed since synthesis; rebuild synthesis first'
        else:
            for n in names:
                target=build_root/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,target)
            stamp.write_text(json.dumps(source_hashes,indent=2)+'\n')
        for n,h in source_hashes.items():assert hashlib.sha256((build_root/n).read_bytes()).hexdigest()==h
    args=[str(exe),'-mode','batch','-source',str(script),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou'),'-tclargs',str(build_root),str(project)]
    if a.stage=='ps':
        if a.board_preset:args.append(str(a.board_preset.resolve()))
    else:args.extend([a.stage,str(out)])
    print('RUN_DIR='+str(out),flush=True)
    print('PROJECT='+str(project),flush=True)
    start=time.monotonic()
    with (out/'console.log').open('w',encoding='utf-8') as f:
        proc=subprocess.run(args,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
    unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in source_hashes.items())
    record=dict(stage=a.stage,status='PASS' if proc.returncode==0 and unchanged else 'FAIL',returncode=proc.returncode,seconds=time.monotonic()-start,project=str(project),run=str(out),source_hashes=source_hashes,sources_unchanged_during_run=unchanged)
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    raise SystemExit(0 if record['status']=='PASS' else (proc.returncode or 1))

if __name__=='__main__':main()
