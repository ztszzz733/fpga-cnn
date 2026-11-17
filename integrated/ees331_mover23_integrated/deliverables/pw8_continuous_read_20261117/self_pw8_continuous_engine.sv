// Opt-in PW8 wrapper; external bank protocol supports up to four ordered
// outstanding reads. Byte/single-word accesses and writes remain scalar.
// Neither this wrapper nor its new bank frontend is installed in production.
module self_pw8_continuous_engine #(parameter MAX_CHANNELS=512)(
 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,
 input logic [31:0] in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,
 output wire [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata,
 output wire mac_fire,output wire [3:0] phase,
 output wire [31:0] input_reads,weight_reads,mac_count
);
 wire cv,cw,cb,cr,cp,core_error,core_done,adapter_idle,adapter_fault;wire [31:0] ca,cd,cdata,read_run_end;
 assign error=core_error || adapter_fault;
 assign done=core_done && adapter_idle;
 self_pw8_read_source #(.MAX_CHANNELS(MAX_CHANNELS),.INPUT_WORD_FILL(0)) core(
  .clk,.rst_n,.clear,.start,.depthwise,.input_base,.weight_base,.output_base,.width,.height,
  .in_channels,.out_channels,.kernel,.stride,.busy,.done(core_done),.error(core_error),
  .valid(cv),.write(cw),.byte_access(cb),.addr(ca),.wdata(cd),.ready(cr),.response(cp),.rdata(cdata),
  .mac_fire,.phase,.input_reads,.weight_reads,.mac_count,.read_run_end);
 continuous_read_adapter adapter(
  .clk,.rst_n,.clear,.c_valid(cv),.c_write(cw),.c_byte(cb),.c_addr(ca),.c_wdata(cd),.read_end(read_run_end),
  .c_ready(cr),.c_response(cp),.c_rdata(cdata),
  .m_valid(valid),.m_write(write),.m_byte(byte_access),.m_addr(addr),.m_wdata(wdata),
  .m_ready(ready),.m_response(response),.m_rdata(rdata),.idle(adapter_idle),.read_pending(),.fault(adapter_fault));
endmodule
