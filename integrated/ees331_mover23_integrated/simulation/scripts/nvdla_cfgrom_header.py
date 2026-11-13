"""Extract CFGROM register addresses from the pinned upstream RDL.

Only address macros are needed by checked-in NV_NVDLA_CFGROM_rom.v.
Its configuration data/RTL remain upstream's, not a behavioral substitute.
"""
import re,sys
from pathlib import Path

def generate(hw,output_hw=None):
    text=(hw/'spec/manual/NVDLA_CFGROM.rdl').read_text()
    names=re.findall(r'}\s*(CFGROM_\w+)\s*;',text)
    assert names and len(names)==len(set(names))
    assert not re.search(r'}\s*CFGROM_\w+\s*@',text), 'update parser for explicit addresses'
    used=set(re.findall(r'\bNVDLA_CFGROM_(CFGROM_\w+)_0\b',(hw/'vmod/nvdla/cfgrom/NV_NVDLA_CFGROM_rom.v').read_text()))
    assert used==set(names), 'CFGROM address inventory mismatch'
    dest=(output_hw or hw)/'outdir/nv_small/spec/manual/NVDLA_CFGROM.vh';dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text('// Address macros extracted from upstream NVDLA_CFGROM.rdl\n'+
                    ''.join(f'#define NVDLA_CFGROM_{name}_0 {i*4}\n' for i,name in enumerate(names)))

if __name__=='__main__':generate(Path(sys.argv[1]),Path(sys.argv[2]) if len(sys.argv)>2 else None)
