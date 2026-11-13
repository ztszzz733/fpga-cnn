"""Synthesize only the production image bridge on xc7z020clg484-1, out of context.

This checks RTL, primitive use, package pin names and clock/CDC constraints.
It does not place/route the full SoC, establish external timing, or emit a bitstream.
"""
import datetime,hashlib,json
from pathlib import Path
from run_tests import ROOT,tools,tool_env,execute
from run_fx8 import FX8_FILES

def main():
    out=ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_fx8_synth')
    out.mkdir(parents=True);print('RUN_DIR='+str(out),flush=True)
    result={'status':'RUNNING','scope':'image_bridge_fx8 only, out-of-context synthesis, no routing'}
    src=[ROOT/'rtl/fx8'/n for n in FX8_FILES if not n.startswith('face_soc')]
    constraints=[ROOT/'constraints'/n for n in ['ees331_fx8_pins.xdc','ees331_fx8_timing.xdc']]
    result['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src+constraints}
    try:
        f=tools();env=tool_env(f)
        # Match Vivado's loader.bat synthesis runtime, beyond XSim's DLL setup.
        base=Path(f['vivado_root'])
        for key in ['RDI_DATADIR','RDI_APPROOT','RDI_LIBDIR','RDI_BINDIR','RDI_BASEROOT','HDI_APPROOT','XILINX_VIVADO']:
            if key in env:env[key]=env[key].replace('\\','/')
        env.update(RT_LIBPATH=(base/'scripts/rt/data').as_posix(),
                   SYNTH_COMMON=(base/'scripts/rt/data').as_posix(),
                   RT_TCL_PATH=(base/'scripts/rt/base_tcl/tcl').as_posix())
        script='\n'.join('read_verilog -sv [list {'+p.as_posix()+'}]' for p in src)
        script+='\nsynth_design -top image_bridge_fx8 -part xc7z020clg484-1 -mode out_of_context\n'
        script+='create_clock -name sys_clk -period 10.000 [get_ports clk]\n'
        script+='set_false_path -from [get_ports rst_n]\n'
        script+='\n'.join('read_xdc [list {'+p.as_posix()+'}]' for p in constraints)
        script+='''
# Fail rather than silently accepting empty XDC selectors or missing pin maps.
foreach stem {wr rd} {
    if {[llength [get_cells -hier -filter "NAME =~ *u_link/*_fifo/${stem}_gray_reg*"]]!=16} {error "Missing Gray source registers"}
    if {[llength [get_cells -hier -filter "NAME =~ *u_link/*_fifo/${stem}_gray_meta_reg*"]]!=16} {error "Missing Gray CDC first stages"}
}
foreach port [get_ports fx8_*] {
    if {[get_property PACKAGE_PIN $port] eq ""} {error "Missing FX8 package pin: $port"}
}
if {[get_property PERIOD [get_clocks fx8_link_clk]]!=40.0} {error "Incorrect link clock constraint"}
report_utilization -file utilization.rpt
report_clocks -file clocks.rpt
report_cdc -details -file cdc.rpt
report_timing_summary -report_unconstrained -file timing.rpt
report_exceptions -file exceptions.rpt
write_checkpoint -force bridge_synth.dcp
puts "PASS fx8_bridge_synthesis"
exit
'''
        (out/'synth.tcl').write_text(script)
        vivado=Path(f['vivado_root'])/'bin/unwrapped/win64.o/vivado.exe'
        execute([vivado,'-mode','batch','-source',out/'synth.tcl','-notrace'],out,env,out/'synth.log',600)
        log=(out/'synth.log').read_text(errors='replace')
        if 'PASS fx8_bridge_synthesis' not in log or '\nERROR:' in log or 'CRITICAL WARNING:' in log:raise RuntimeError('Synthesis/constraints failed; see synth.log')
        result['status']='PASS'
    except Exception as exc:result.update(status='FAIL',error=str(exc));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2));print('STATUS='+result['status'],flush=True)

if __name__=='__main__':main()
