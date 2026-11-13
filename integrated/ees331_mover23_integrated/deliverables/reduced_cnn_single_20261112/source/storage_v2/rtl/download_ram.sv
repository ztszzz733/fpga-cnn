// Fixed one-cycle CPU port; loader is permitted only after application quiescence.
// Reset affects interface state only, never the memory array.
module download_ram #(
 parameter integer BYTES=16384,
 parameter logic [31:0] BASE=32'h00010000,
 parameter bit READ_ONLY_CPU=0
)(
 input logic clk,rst_n,app_reset,app_halted,
 input logic [31:0] cpu_addr,cpu_wdata,
 input logic cpu_re,cpu_we,
 input logic [3:0] cpu_wstrb,
 output logic [31:0] cpu_rdata,
 output logic cpu_error,
 input logic ld_valid,ld_write,
 output wire ld_ready,
 input logic [31:0] ld_addr,ld_wdata,
 input logic [3:0] ld_wstrb,
 output logic ld_rsp_valid,ld_error,
 input logic ld_rsp_ready,
 output logic [31:0] ld_rdata
);
 localparam integer WORDS=BYTES/4,AW=$clog2(WORDS);
 (* ram_style="block" *) logic [31:0] mem[0:WORDS-1];
 wire [31:0] cpu_offset=cpu_addr-BASE,ld_offset=ld_addr-BASE;
 // LSU supplies byte address plus shifted data/strobes (SB/LB need low bits).
 wire cpu_ok=cpu_addr>=BASE && cpu_offset<BYTES && (!READ_ONLY_CPU || cpu_addr[1:0]==0);
 wire ld_ok=ld_addr>=BASE && {1'b0,ld_offset}+33'd4<={1'b0,32'(BYTES)} && ld_addr[1:0]==0;
 wire cpu_active=rst_n && !app_reset && (cpu_re || cpu_we);
 wire ld_accept=ld_valid && ld_ready;
 wire ld_allowed=app_halted && !cpu_active && ld_ok;
 logic [31:0] cpu_q,ld_q;
 logic cpu_read_valid,ld_read_valid;
 assign ld_ready=rst_n && !ld_rsp_valid;
 assign cpu_rdata=cpu_read_valid ? cpu_q : 32'b0;
 assign ld_rdata=ld_read_valid ? ld_q : 32'b0;
 // No reset or enable-dependent asynchronous data access on either RAM port.
 always @(posedge clk) begin
  if(cpu_active && cpu_ok) begin
   if(cpu_re) cpu_q<=mem[cpu_offset[2+:AW]];
   if(cpu_we && !READ_ONLY_CPU)
    for(integer k=0;k<4;k++) if(cpu_wstrb[k]) mem[cpu_offset[2+:AW]][8*k+:8]<=cpu_wdata[8*k+:8];
  end
 end
 always @(posedge clk) begin
  if(ld_accept && ld_allowed) begin
   if(!ld_write) ld_q<=mem[ld_offset[2+:AW]];
   if(ld_write)
    for(integer k=0;k<4;k++) if(ld_wstrb[k]) mem[ld_offset[2+:AW]][8*k+:8]<=ld_wdata[8*k+:8];
  end
 end
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   cpu_read_valid<=0;cpu_error<=0;ld_rsp_valid<=0;ld_error<=0;ld_read_valid<=0;
  end else begin
   cpu_read_valid<=cpu_active && cpu_re && cpu_ok;
   cpu_error<=cpu_active && (!cpu_ok || (cpu_we && READ_ONLY_CPU));
   if(ld_rsp_valid && ld_rsp_ready) ld_rsp_valid<=0;
   if(ld_accept) begin
    ld_rsp_valid<=1;ld_error<=!ld_allowed;ld_read_valid<=ld_allowed && !ld_write;
   end
  end
 end
`ifndef SYNTHESIS
 initial begin
  assert(BYTES>=8 && BYTES%4==0 && (BYTES&(BYTES-1))==0) else $fatal(1,"RAM geometry");
  assert(BASE[1:0]==0 && {1'b0,BASE}+BYTES<=33'h100000000) else $fatal(1,"RAM range");
 end
`endif
endmodule
