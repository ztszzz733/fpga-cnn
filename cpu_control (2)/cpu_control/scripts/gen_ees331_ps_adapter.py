"""Verify generated vendor ports, then generate diagram-named PS wrapper."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('wrapper',type=Path);a=ap.parse_args()
    text=a.wrapper.read_text();ports={}
    for direction,hi,lo,name in re.findall(r'^\s*(input|output|inout)\s*(?:\[(\d+):(\d+)\])?\s*(\w+)\s*;',text,re.M):
        ports[name]=(direction,abs(int(hi)-int(lo))+1 if hi else 1)
    mapping={'DDR_Addr':'DDR_addr','DDR_BankAddr':'DDR_ba','DDR_DM':'DDR_dm','DDR_DQ':'DDR_dq','DDR_DQS':'DDR_dqs_p','DDR_DQS_n':'DDR_dqs_n',
             'DDR_Clk':'DDR_ck_p','DDR_Clk_n':'DDR_ck_n','DDR_CKE':'DDR_cke','DDR_CS_n':'DDR_cs_n','DDR_RAS_n':'DDR_ras_n','DDR_CAS_n':'DDR_cas_n','DDR_WEB':'DDR_we_n','DDR_ODT':'DDR_odt','DDR_DRSTB':'DDR_reset_n',
             'DDR_VRN':'FIXED_IO_ddr_vrn','DDR_VRP':'FIXED_IO_ddr_vrp','FIXED_IO_MIO':'FIXED_IO_mio','FIXED_IO_PS_CLK':'FIXED_IO_ps_clk','FIXED_IO_PS_PORB':'FIXED_IO_ps_porb','FIXED_IO_PS_SRSTB':'FIXED_IO_ps_srstb'}
    links=json.loads((ROOT/'deliverables/ees331_ddr_io/io_manifest.json').read_text(encoding='utf-8'))['after']
    expected={}
    for link in links:
        if link['id'] not in ['G','H','B']:continue
        for group in ['address','data','control']:
            for s in link[group]:
                n=s['name'];expected[n]=s['width']
                if link['id'] in ['G','H']:
                    prefix='M_AXI_GP0_' if link['id']=='G' else 'S_AXI_HP0_'
                    mapping[n]=prefix+n[len(prefix):].lower()
    for n in ['FCLK_CLK0','FCLK_RESET0_N','M_AXI_GP0_ACLK','S_AXI_HP0_ACLK']:mapping[n]=n;expected[n]=1
    for suffix,w in [('RCOUNT',8),('WCOUNT',8),('RACOUNT',3),('WACOUNT',6),('RDISSUECAP1_EN',1),('WRISSUECAP1_EN',1)]:
        n='S_AXI_HP0_'+suffix;mapping[n]=n;expected[n]=w
    expected.update(DDR_VRN=1,DDR_VRP=1,FIXED_IO_MIO=54,FIXED_IO_PS_CLK=1,FIXED_IO_PS_PORB=1,FIXED_IO_PS_SRSTB=1)
    assert set(mapping.values())==set(ports),'Vendor port set differs'
    for n,v in mapping.items():assert ports[v][1]==expected[n],f'Width mismatch: {n}'
    lines=['// Names and widths audited against the generated Vivado PS7 wrapper.',
           '// Adapter only renames standard BD interface suffixes; no logic/CDC.', 'module ees331_ps_wrapper (']
    for i,(n,v) in enumerate(mapping.items()):
        direction,w=ports[v];lines.append(' '+direction+' wire '+(f'[{w-1}:0] ' if w>1 else '')+n+(',' if i<len(mapping)-1 else ''))
    lines+=[');',' ees331_ps_bd_wrapper u_ps7 (']
    lines += ['  .'+v+'('+n+')'+(',' if i<len(mapping)-1 else '') for i,(n,v) in enumerate(mapping.items())]
    lines+=[' );','endmodule','']
    (ROOT/'rtl/soc/ees331/ees331_ps_wrapper.sv').write_text('\n'.join(lines))
    out=ROOT/'build/ees331_ps_port_audit.json';out.write_text(json.dumps(dict(status='PASS',vendor_wrapper=str(a.wrapper),ports=len(ports),mapping=mapping),indent=2)+'\n')
    old=(ROOT/'rtl/filelists/system_cnn.f').read_text().splitlines()
    cpu=old[:old.index('rtl/soc/datasram.sv')]
    cnn=(ROOT/'rtl/filelists/cnn_ees331.f').read_text().splitlines()
    files=['# EES331 production top: updated CNN and DDR/cache, six peers plus PS7.']+cpu+cnn+['rtl/soc/clock_unit.sv','rtl/soc/ees331/image_control_bridge.sv','rtl/soc/ees331/ees331_ps_wrapper.sv','rtl/soc/ees331/face_soc_ees331_top.sv']
    (ROOT/'rtl/filelists/system_ees331.f').write_text('\n'.join(files)+'\n')
    print('PASS',len(ports),'vendor PS ports; generated adapter and production filelist')
if __name__=='__main__':main()
