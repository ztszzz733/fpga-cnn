"""Memoize settled, untimed generated RTL evaluation when ALL inputs are unchanged.

This only edits Verilator's generated DPI adapter, never RTL arithmetic/state.
All clock/reset transitions still evaluate; outputs and sequence numbers are
returned on every call. A baseline executable is retained for equivalence tests.
"""
import hashlib,json,os,shutil
from pathlib import Path
from run_tests import ROOT,execute
STAGE=ROOT.parents[1]/'.neureka_full_hier_build'

def install(logdir):
 obj=STAGE/'obj';lib=obj/'Vneureka_conv_engine';path=lib/'neureka_conv_engine.cpp'
 original=lib/'neureka_conv_engine.uncached.cpp';baseline=obj/'Vquant_network_sequential.uncached'
 if 'm_eval_initialized' not in path.read_text():
  shutil.copyfile(obj/'Vquant_network_sequential',baseline)
  shutil.copyfile(path,original)
 assert original.exists() and baseline.exists(),'missing uncached baseline'
 s=original.read_text();assert s.count('        handlep__V->eval();')==2
 s=s.replace('    long long m_seqnum;','    long long m_seqnum;\n    bool m_eval_initialized = false;\n    unsigned long long m_evals=0, m_skipped=0;')
 before='        handlep__V->clear = clear;'
 check='''        bool changed__C = !handlep__V->m_eval_initialized ||
            handlep__V->clear != clear || handlep__V->start != start ||
            handlep__V->config_address != VL_SET_I_SVLV(config_address) ||
            handlep__V->cfg_ready != cfg_ready || handlep__V->cfg_response != cfg_response ||
            handlep__V->cfg_rdata != VL_SET_I_SVLV(cfg_rdata) ||
            handlep__V->ready != VL_SET_I_SVLV(ready) || handlep__V->response != VL_SET_I_SVLV(response);
        VlWide<9> next_data__C;
        VL_SET_W_SVLV(288, next_data__C, rdata + 0);
        for (unsigned i=0;i<9;i++) if (next_data__C[i]!=handlep__V->rdata[i]) changed__C=true;
'''
 assert s.count(before)==1;s=s.replace(before,check+before)
 before='        handlep__V->clk = clk;'
 assert s.count(before)==1;s=s.replace(before,'''        bool changed__C = !handlep__V->m_eval_initialized || handlep__V->clk != clk || handlep__V->rst_n != rst_n;
'''+before)
 s=s.replace('        handlep__V->eval();','''        if (changed__C) {
            handlep__V->eval();
            handlep__V->m_eval_initialized=true;
            handlep__V->m_evals++;
        } else handlep__V->m_skipped++;''')
 s=s.replace('        handlep__V->final();','''        std::printf("RTL_EVAL_CACHE evaluated=%llu unchanged_skipped=%llu\\n",handlep__V->m_evals,handlep__V->m_skipped);
        handlep__V->final();''')
 changed=path.read_text()!=s
 if changed:path.write_text(s)
 vr=ROOT.parents[1]/'.neureka_build/neureka/verilator';env=os.environ.copy();env['VERILATOR_ROOT']=str(vr)
 flags=['CFG_CXXFLAGS_PCH_I=-include','PYTHON3=python3','OPT_FAST=-O2']
 if changed:
  execute(['make','-f','Vneureka_conv_engine.mk','-j','2',*flags,'libneureka_conv_engine.a'],lib,env,logdir/'cache_build.log',timeout=120)
  execute(['make','-f','Vquant_network_sequential.mk','-j','2',*flags,'Vquant_network_sequential'],obj,env,logdir/'cache_build.log',timeout=120)
 report=dict(original_wrapper_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),cached_wrapper_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
             original_executable_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),cached_executable_sha256=hashlib.sha256((obj/'Vquant_network_sequential').read_bytes()).hexdigest(),
             patch_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (STAGE/'eval_cache.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':
 out=ROOT/'build/eval_cache_validation';out.mkdir(parents=True,exist_ok=True);print(json.dumps(install(out),indent=2))
