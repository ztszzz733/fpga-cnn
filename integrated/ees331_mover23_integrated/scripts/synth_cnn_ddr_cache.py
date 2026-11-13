"""Synthesize the default 128KiB cache + 16KiB CPU RAM, OOC at 50MHz."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
from run_tests import ROOT, tools, tool_env
from synth_self_cnn import utilization_rows

if __name__=='__main__':
    work=ROOT/'build/runs'/f'{datetime.now():%Y%m%d_%H%M%S_%f}_cnn_ddr_cache_synth'
    work.mkdir(parents=True)
    paths=[ROOT/'rtl/cnn_ddr'/s for s in ('cnn_cache.sv','cnn_ddr_bridge.sv','datasram_ddr_subsystem.sv')]
    paths += [Path(__file__).resolve(),ROOT/'scripts/synth_cnn_ddr_cache.tcl']
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result={'status':'RUNNING','part':'xc7z020clg484-1','period_ns':20.0,
            'cache_bytes':131072,'cpu_ram_bytes':16384,'sources_sha256':hashes,
            'place_route_performed':False,'stage':'out_of_context_synthesis',
            'timing_scope':'Clock-to-clock estimates only; no board/PS IO delay constraints.'}
    def save(): (work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    save();print(work,flush=True);started=time.perf_counter()
    try:
        found=tools();base=Path(found['vivado_root']);env=tool_env(found)
        for key in ('RDI_DATADIR','RDI_APPROOT','RDI_LIBDIR','RDI_BINDIR','RDI_BASEROOT',
                    'XILINX_VIVADO','HDI_APPROOT','TCL_LIBRARY'):
            if key in env: env[key]=env[key].replace('\\','/')
        env['RDI_BINROOT']=(base/'bin').as_posix()
        env['RT_LIBPATH']=(base/'scripts/rt/data').as_posix()
        env['RT_TCL_PATH']=(base/'scripts/rt/base_tcl/tcl').as_posix()
        env['SYNTH_COMMON']=env['RT_LIBPATH'];env['XILINX_LOCAL_USER_DATA']='no'
        command=[str(base/'bin/unwrapped/win64.o/vivado.exe'),'-mode','batch','-nojournal',
                 '-log',str(work/'vivado.log'),'-source',str(ROOT/'scripts/synth_cnn_ddr_cache.tcl'),
                 '-tclargs',str(ROOT),str(work),result['part'],str(result['period_ns'])]
        with (work/'process.log').open('w',encoding='utf-8') as f:
            proc=subprocess.run(command,cwd=work,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600)
        log=(work/'process.log').read_text(encoding='utf-8',errors='replace')
        result['returncode']=proc.returncode
        if proc.returncode or 'CNN_DDR_CACHE_SYNTH_COMPLETE' not in log:
            raise RuntimeError('Vivado failed: '+' | '.join(x for x in log.splitlines() if x.startswith('ERROR:')))
        result['utilization']=utilization_rows((work/'utilization.rpt').read_text(encoding='utf-8',errors='replace'))
        result['primitives']={}
        for line in (work/'primitive_counts.tsv').read_text().splitlines():
            name,value=line.split('\t')
            if name=='worst_setup_slack_ns':result[name]=float(value)
            else:result['primitives'][name]=int(value)
        result['sources_unchanged_during_run']=all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.relative_to(ROOT).as_posix()] for p in paths)
        if not result['sources_unchanged_during_run']:raise RuntimeError('Source changed during synthesis')
        result['status']='PASS'
    except Exception as e:
        result['status']='FAIL';result['error']=str(e)
    result['elapsed_seconds']=time.perf_counter()-started;save();print(json.dumps(result,indent=2),flush=True)
    if result['status']!='PASS':raise SystemExit(1)
