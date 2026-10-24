"""Production-only source list for the EES-331 parallel-interface entry."""
from neureka_pipeline_sources import ROOT,sources as pipeline_sources

def sources():
    src,inc,defs=pipeline_sources()
    src=[p for p in src if p.name!='face_soc_neureka_pipeline_top.sv']
    src += [ROOT/'rtl/fx8'/n for n in ['fx8_async_fifo.sv','fx8_link.sv','image_load_stream.sv',
                                    'image_bridge_fx8.sv','face_soc_neureka_fx8_top.sv']]
    return src,inc,defs

if __name__=='__main__':
    src,inc,defs=sources()
    lines=['+define+'+d for d in defs]+['+incdir+'+p.relative_to(ROOT).as_posix() for p in inc]+[p.relative_to(ROOT).as_posix() for p in src]
    (ROOT/'rtl/filelists/system_neureka_fx8.f').write_text('\n'.join(lines)+'\n')
    print('Generated system_neureka_fx8.f:',len(src),'production RTL files')
