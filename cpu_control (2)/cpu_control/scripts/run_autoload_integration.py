"""Run power-on -> UART external storage -> CPU -> real CNN integration."""
from datetime import datetime
import hashlib
import json
import re
import shutil
from run_tests import ROOT, tools, tool_env, execute
from gen_autoload_demo import generate


def main():
    assets = generate()
    run = ROOT / 'build/runs' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_autoload_integration')
    run.mkdir(parents=True)
    print(f'RUN_DIR={run}', flush=True)
    shutil.copy2(assets/'program.mem', run/'autoload_program.mem')
    shutil.copy2(assets/'external_bytes.mem', run/'autoload_external.mem')
    shutil.copy2(assets/'manifest.json', run/'demo_manifest.json')
    src = [ROOT/s.strip() for s in (ROOT/'rtl/filelists/system_autoload.f').read_text().splitlines()
           if s.strip() and not s.lstrip().startswith('#')]
    src += [ROOT/'tb/integration/tb_soc_autoload.sv']
    result = {'status':'RUNNING', 'run_dir':str(run), 'tests':{},
              'source_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in src},
              'asset_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.iterdir() if p.is_file()}}
    found=tools(); env=tool_env(found)
    try:
        execute([found['xvlog'],'-sv',*src],run,env,run/'compile.log')
        execute([found['xelab'],'tb_soc_autoload','-s','autoload','-debug','typical','-mt','2'],run,env,run/'compile.log',timeout=240)
        execute([found['xelab'],'tb_soc_autoload','-generic_top','CHUNK_BYTES=63','-s','autoload_tail',
                 '-debug','typical','-mt','2'],run,env,run/'compile.log',timeout=240)
        cases=[(0,'power_on_success','autoload'),(1,'packet_crc_failure','autoload'),
               (2,'timeout_and_late_reply','autoload'),(3,'batch_crc_failure','autoload'),
               (4,'wrong_response_tag','autoload'),(0,'partial_last_chunk','autoload_tail')]
        for mode,name,snapshot in cases:
            tcl=run/(name+'.tcl')
            tcl.write_text(f'open_vcd {{{name}.vcd}}\nlog_vcd [get_objects /tb_soc_autoload/*]\nlog_vcd [get_objects /tb_soc_autoload/dut/*]\nrun all\nclose_vcd\nquit\n')
            log=run/(name+'.log')
            execute([found['xsim'],snapshot,'-testplusarg',f'TEST_MODE={mode}','-tclbatch',tcl.name,'-onerror','quit'],run,env,log,timeout=240)
            content=log.read_text(encoding='utf-8',errors='replace')
            if f'PASS tb_soc_autoload mode={mode}' not in content or re.search(r'^(?:Error:|Fatal:|ERROR:|FAIL)',content,re.M):
                raise RuntimeError(f'Test failed: {log}')
            result['tests'][name]='PASS'
            print(f'PASS {name}',flush=True)
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc))
        print(str(exc),flush=True)
    (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return int(result['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
