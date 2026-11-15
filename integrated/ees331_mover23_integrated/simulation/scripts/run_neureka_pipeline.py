"""Build real NEureka + CV32E40X/Vicuna + unchanged CPU/SRAM with native XSim."""
import argparse,datetime,hashlib,json,re
from run_tests import ROOT,tools,tool_env,execute
from neureka_pipeline_sources import sources

def compile_real(out,f,env,bench=None,result=None,snapshot='soc',extra_sources=()):
    if result is None:result={}
    src,inc,defs=sources();defs=defs+['XSIM'];top='face_soc_neureka_pipeline_top'
    src+=list(extra_sources)
    if bench is not None:src.append(bench);top=bench.stem
    result['sources']={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in src}
    compiled=[]
    for source in src:
        if source.name=='vproc_core.sv':
            text=source.read_text(encoding="utf-8")
            declaration='    logic result_fifo_full_stall;'
            text=text.replace(declaration,'    // declaration moved before first use:')
            text=text.replace('    logic instr_valid, issue_id_used;',declaration+'\n    logic instr_valid, issue_id_used;')
            # This build fixes every register read port at VREG_W. XSim
            # mis-sizes a genvar-dependent unpacked array slice.
            text=text.replace('= VPORT_RD_W[PIPE_VPORT_IDX[i] +: PIPE_VPORT_CNT[i]];', "= '{default: VREG_W};")
            text=text.replace('= VADDR_RD_W[PIPE_VPORT_IDX[i] +: PIPE_VPORT_CNT[i]];', "= '{default: 5};")
            text=text.replace('MAX_VPORT_RD_SLICE(VPORT_RD_W, PIPE_VPORT_IDX[i], PIPE_VPORT_CNT[i])','VREG_W')
            text=text.replace('MAX_VPORT_RD_SLICE(VADDR_RD_W, PIPE_VPORT_IDX[i], PIPE_VPORT_CNT[i])','5')
            copy=out/'vproc_core.sv';copy.write_text(text,encoding="utf-8");compiled.append(copy)
        elif source.name=='vproc_pipeline_wrapper.sv':
            text=source.read_text(encoding='utf-8')
            parts=re.split(r'(if \(OP_CNT == \d+ && RES_CNT == \d+\) begin)',text)
            for i in range(1,len(parts),2):
                decl='            OBI_BUS obi_unused [1]();'
                if decl in parts[i+1]:parts[i+1]='\n'+decl+parts[i+1].replace(decl,'')
            copy=out/source.name;copy.write_text(''.join(parts),encoding='utf-8');compiled.append(copy)
        elif source.name=='neureka_streamer.sv':
            text=source.read_text(encoding='utf-8').replace('tcdm_premux.target','tcdm_premux').replace('virt_source.source','virt_source')
            copy=out/source.name;copy.write_text(text,encoding='utf-8');compiled.append(copy)
        else:compiled.append(source)
    result['compiled_sha256']={s.name:hashlib.sha256(s.read_bytes()).hexdigest() for s in compiled}
    (out/'sources.prj').write_text(''.join('sv work "'+s.as_posix()+'"\n' for s in compiled))
    execute([f['xvlog'],'--relax','-sv','-prj','sources.prj',*[a for p in inc for a in ['-i',p]],*[a for d in defs for a in ['-d',d]]],out,env,out/'compile.log',600)
    result['status']='COMPILED';result['compiled']=True
    execute([f['xelab'],'--relax',top,'--O0','-s',snapshot,'--debug','typical'],out,env,out/'elaborate.log',900)
    result['status']='ELABORATED_NOT_SIMULATED';result['elaborated']=True
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--elaborate-only',action='store_true');a=ap.parse_args()
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka_pipeline')
    out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'real pinned NEureka and Vicuna RTL; no arithmetic replacement'}
    try:
        if not a.elaborate_only:
            from gen_neureka_pipeline import generate
            generate(out)
        f=tools();env=tool_env(f)
        compile_real(out,f,env,None if a.elaborate_only else ROOT/'tb/integration/tb_neureka_pipeline.sv',result)
        if not a.elaborate_only:
            execute([f['xsim'],'soc','-runall'],out,env,out/'sim.log',1200)
            log=(out/'sim.log').read_text(errors='replace')
            if 'FATAL_ERROR: Vivado Simulator kernel' in log:
                raise RuntimeError('XSim kernel crashed; see sim.log. Real-core numerical verification did not pass.')
            if 'PASS tb_neureka_pipeline' not in log:raise RuntimeError('Missing real-core PASS marker; see sim.log')
            match=re.search(r'REAL_METRICS serial=(\d+) pipeline=(\d+) overlap=(\d+) concurrent_requests=(\d+)',log)
            if match:
                result['metrics']=dict(zip(['serial_cycles','pipeline_cycles','overlap_cycles','concurrent_requests'],map(int,match.groups())))
            result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2));print('STATUS='+result['status'],flush=True)
if __name__=='__main__':main()
