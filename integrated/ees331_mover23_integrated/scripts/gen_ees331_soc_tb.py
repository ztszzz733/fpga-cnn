"""Expose existing six-module internal signals for simulation monitoring only."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate():
    source=(ROOT/'rtl/soc/ees331/face_soc_ees331_top.sv').read_text(encoding='utf-8')
    ports=source.split('`ifdef EES331_EXTERNAL_PS',1)[1].split('`else',1)[0].strip()
    debug='''
 output wire [9:0] debug_unit_start,debug_unit_active,debug_completion,debug_work,
 output wire [99:0] debug_node,
 output wire [9:0] debug_valid,debug_write,debug_byte,debug_ready,debug_response,
 output wire [319:0] debug_addr,debug_wdata,debug_rdata,
 output wire [10:0] debug_completed,
 output wire debug_error,debug_fault
'''
    body='''
 face_soc_ees331_top dut(.*);
 assign debug_unit_start=dut.u_cnn.unit_start;
 assign debug_unit_active=dut.u_cnn.unit_active;
 assign debug_completion=dut.u_cnn.completion_pulse;
 assign debug_work=dut.u_cnn.operator_work;
 assign debug_node=dut.u_cnn.unit_node;
 assign debug_completed=dut.u_cnn.completed_count;
 assign debug_error=dut.u_cnn.error;
 assign debug_fault=dut.cnn_mem_fault;
 assign debug_valid=dut.cnn_valid;assign debug_write=dut.cnn_write;
 assign debug_byte=dut.cnn_byte;assign debug_ready=dut.cnn_ready;
 assign debug_response=dut.cnn_response;assign debug_addr=dut.cnn_addr;
 assign debug_wdata=dut.cnn_wdata;assign debug_rdata=dut.cnn_rdata;
endmodule
'''
    (ROOT/'tb/ees331_soc_sim_top.sv').write_text('// Generated simulation observation wrapper; production wiring unchanged.\nmodule ees331_soc_sim_top (\n'+ports+','+debug+');\n'+body)
if __name__=='__main__':generate()
