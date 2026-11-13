"""Build a self-contained ordered filelist; no dependence on an old simulator cache."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
DEFINES=['COREV_ASSERT_OFF','OLD_VICUNA','FORCE_ALIGNED_READS','XIF_ON','RISCV_F','RISCV_ZFH','RISCV_ZVE32X','RISCV_ZVE32F','RISCV_ZVFH','VECTOR_CUSTOM']
def sources():
    up=ROOT/'third_party/vicuna2_tests';v=up/'rtl/vicuna2_core'
    variables={'DESIGN_RTL_DIR_CV32E40X':up/'rtl/cv32e40x/rtl','DESIGN_RTL_DIR_FPU_SS':up/'rtl/fpu_ss/src',
      'DESIGN_RTL_DIR_VICUNA':v/'rtl','DESIGN_RTL_DIR_CVFPU':v/'cvfpu/src','DESIGN_RTL_DIR_COMMON':v/'pulp_common_cells'}
    def selection(file,name):
        s=re.sub(r'#[^\n]*','',file.read_text())
        m=re.search(r'set\('+name+r'\s+(.*?)\)',s,re.S)
        result=[]
        for word in m.group(1).split():
            if word=='PARENT_SCOPE':continue
            for key,value in variables.items():word=word.replace('${'+key+'}',str(value))
            result.append(Path(word).resolve())
        return result
    cm=up/'build_model/CMakeLists.txt';vc=v/'CMakeLists.txt'
    inc=[ROOT/'third_party/hci/rtl/common',ROOT/'third_party/hwpe-stream/rtl',ROOT/'third_party/hwpe-ctrl/rtl',v/'obi']
    for file,name in [(cm,'CV32E40X_INCLUDE'),(cm,'FPU_SS_INCLUDE'),(vc,'VICUNA_INCLUDE'),(vc,'CVFPU_INCLUDE')]:inc+=selection(file,name)
    src=[]
    for line in (ROOT/'rtl/filelists/system_neureka.f').read_text().splitlines():
        if line.startswith('third_party/'):src.append(ROOT/line)
    src += [v/'cvfpu/src/common_cells/src/cf_math_pkg.sv',v/'obi/obi_pkg.sv',v/'obi/obi_intf.sv']
    src+=selection(cm,'CV32E40X_SOURCE')+selection(vc,'CVFPU_SOURCE')
    # Upstream Verilator resolves these from its -y include directories.
    src+=sorted((v/'cvfpu/src/fpu_div_sqrt_mvp/hdl').glob('*.sv'))
    vs=selection(vc,'VICUNA_SOURCE')
    vs=[ROOT/'rtl/neureka_pipeline/vproc_config.sv' if p.name=='vproc_config.sv' else p for p in vs]
    src+=vs+selection(cm,'FPU_SS_SOURCE')
    for line in (ROOT/'rtl/filelists/system_hybrid_local.f').read_text().splitlines():
        if line and 'nvdla' not in line and not line.endswith(('hybrid_cnn_top.sv','face_soc_hybrid_top.sv')):src.append(ROOT/line)
    src += [ROOT/'rtl/neureka/neureka_banked_bridge.sv',ROOT/'rtl/neureka/neureka_conv_engine.sv']
    src += [ROOT/'rtl/neureka_pipeline'/name for name in ['neureka_tile_scheduler.sv','neureka_pipeline_cnn_top.sv','face_soc_neureka_pipeline_top.sv']]
    src=list(dict.fromkeys(p.resolve() for p in src))
    missing=[str(p) for p in src if not p.is_file()]
    if missing:raise FileNotFoundError('Missing pinned dependencies: '+str(missing))
    return src,list(dict.fromkeys(p.resolve() for p in inc)),DEFINES

def main():
    src,inc,defs=sources()
    lines=['+define+'+d for d in defs]+['+incdir+'+p.relative_to(ROOT).as_posix() for p in inc]+[p.relative_to(ROOT).as_posix() for p in src]
    (ROOT/'rtl/filelists/system_neureka_pipeline.f').write_text('\n'.join(lines)+'\n')
    print('Generated system_neureka_pipeline.f:',len(src),'RTL files')
if __name__=='__main__':main()
