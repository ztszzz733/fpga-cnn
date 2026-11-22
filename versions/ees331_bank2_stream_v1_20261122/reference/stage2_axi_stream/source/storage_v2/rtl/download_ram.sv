// Registered store port. A load one cycle after a store retains its original
// latency and forwards any overlapping byte directly from the store register.
module download_ram #(
 parameter integer BYTES=16384,
 parameter logic [31:0] BASE=32'h00010000,
 parameter bit READ_ONLY_CPU=0
)(
 input logic clk,rst_n,app_reset,app_halted,
 input logic [31:0] cpu_addr,cpu_wdata,
 input logic cpu_re,cpu_we,
 input logic [3:0] cpu_wstrb,
 output wire [31:0] cpu_rdata,
 output logic cpu_error,
 input logic ld_valid,ld_write,
 output wire ld_ready,
 input logic [31:0] ld_addr,ld_wdata,
 input logic [3:0] ld_wstrb,
 output logic ld_rsp_valid,ld_error,
 input logic ld_rsp_ready,
 output wire [31:0] ld_rdata
);
 localparam integer WORDS=BYTES/4, AW=$clog2(WORDS), AB=AW+2;
 wire [31:0] cpu_offset=cpu_addr-BASE,ld_offset=ld_addr-BASE;
 wire cpu_active=rst_n && !app_reset && (cpu_re || cpu_we);
 wire cpu_ok=cpu_offset<BYTES && (!READ_ONLY_CPU || cpu_addr[1:0]==0);
 wire cpu_load=cpu_active && cpu_re && cpu_ok;
 logic posted;
 logic [AW-1:0] posted_addr;
 logic [31:0] posted_data;
 logic [3:0] posted_bytes;
 assign ld_ready=rst_n && !ld_rsp_valid && !posted;
 wire ld_accept=ld_valid && ld_ready;
 wire ld_allowed=app_halted && !cpu_active && ld_offset<BYTES && ld_addr[1:0]==0;
 wire ld_load=ld_accept && ld_allowed && !ld_write;
 wire ld_store=ld_accept && ld_allowed && ld_write;
 wire [AW-1:0] read_addr=ld_load?ld_offset[AB-1:2]:cpu_offset[AB-1:2];
 wire [AW-1:0] write_addr=posted?posted_addr:ld_offset[AB-1:2];
 wire [31:0] write_data=posted?posted_data:ld_wdata;
 wire [3:0] write_bytes=posted?posted_bytes:ld_store?ld_wstrb:4'b0;
 logic cpu_read_valid,ld_read_valid;
 wire [31:0] output_data;

 // Byte lanes allow an adjacent store and load of the same word. Only the
 // bytes enabled by the queued store are forwarded instead of read.
 for(genvar n=0;n<4;n++)begin:lanes
  (* ram_style="block" *) logic [7:0] mem[WORDS];
  logic [7:0] mem_q,bypass_data;
  logic bypass;
  always_ff @(posedge clk)begin
   if(write_bytes[n])mem[write_addr]<=write_data[8*n+:8];
   // The CPU valid bit qualifies the output. Only a pending loader read
   // must hold the RAM output for backpressure.
   if(!ld_rsp_valid || cpu_load)mem_q<=mem[read_addr];
   bypass<=posted && posted_bytes[n] && posted_addr==read_addr;
   bypass_data<=posted_data[8*n+:8];
  end
  assign output_data[8*n+:8]=bypass?bypass_data:mem_q;
 end
 assign cpu_rdata=cpu_read_valid?output_data:32'b0;
 assign ld_rdata=ld_read_valid?output_data:32'b0;
 always_ff @(posedge clk)begin
  if(!rst_n)begin
   posted<=0;cpu_read_valid<=0;cpu_error<=0;ld_rsp_valid<=0;ld_error<=0;ld_read_valid<=0;
  end else begin
   posted<=cpu_active && cpu_we && cpu_ok && !READ_ONLY_CPU;
   // The posted flag alone qualifies the payload. Avoid distributing the
   // CPU's address/enable decode to every payload register.
   posted_addr<=cpu_offset[AB-1:2];posted_data<=cpu_wdata;posted_bytes<=cpu_wstrb;
   cpu_read_valid<=cpu_load;
   cpu_error<=cpu_active && (!cpu_ok || (cpu_we && READ_ONLY_CPU));
   if(ld_rsp_valid && ld_rsp_ready)ld_rsp_valid<=0;
   if(ld_accept)begin
    ld_rsp_valid<=1;ld_error<=!ld_allowed;ld_read_valid<=ld_load;
   end
  end
 end

`ifndef SYNTHESIS
 initial begin
  assert(BYTES>=8 && (BYTES&(BYTES-1))==0) else $fatal(1,"RAM geometry");
  assert(BASE[1:0]==0 && {1'b0,BASE}+BYTES<=33'h100000000) else $fatal(1,"RAM range");
 end
`endif
endmodule
