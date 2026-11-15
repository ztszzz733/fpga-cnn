// One-cycle compute port plus a backpressured, word-addressed DMA port.
// Compute access owns a same-word collision. The memory array is not reset.
module tile_local_ram #(
 parameter integer BYTES = 32768
)(
 input  logic        clk,
 input  logic        rst_n,
 input  logic        comp_req,
 input  logic        comp_we,
 input  logic [31:0] comp_addr,
 input  logic [31:0] comp_wdata,
 input  logic [3:0]  comp_wstrb,
 output logic [31:0] comp_rdata,
 output logic        comp_error,
 input  logic        dma_valid,
 input  logic        dma_write,
 output wire         dma_ready,
 input  logic [31:0] dma_addr,
 input  logic [31:0] dma_wdata,
 input  logic [3:0]  dma_wstrb,
 output logic        dma_rsp_valid,
 output logic        dma_error,
 output logic [31:0] dma_rdata
);
 localparam integer WORDS = BYTES/4;
 localparam integer AW = $clog2(WORDS);
 (* ram_style="block" *) logic [31:0] mem [0:WORDS-1];
 wire comp_ok = comp_addr[1:0]==0 && {1'b0,comp_addr}+33'd4<=33'(BYTES);
 wire dma_ok = dma_addr[1:0]==0 && {1'b0,dma_addr}+33'd4<=33'(BYTES);
 wire conflict = comp_req && comp_ok && dma_ok && comp_addr==dma_addr;
 assign dma_ready = rst_n && !conflict;
 wire dma_take = dma_valid && dma_ready;

 // Separate RAM ports permit block-RAM inference. Collision suppression is
 // applied before the DMA port reaches the array.
 always @(posedge clk) begin
  if(comp_req && comp_ok) begin
   if(!comp_we) comp_rdata <= mem[comp_addr[2+:AW]];
   else for(integer k=0;k<4;k++)
    if(comp_wstrb[k]) mem[comp_addr[2+:AW]][8*k+:8] <= comp_wdata[8*k+:8];
  end
 end
 always @(posedge clk) begin
  if(dma_take && dma_ok) begin
   if(!dma_write) dma_rdata <= mem[dma_addr[2+:AW]];
   else for(integer k=0;k<4;k++)
    if(dma_wstrb[k]) mem[dma_addr[2+:AW]][8*k+:8] <= dma_wdata[8*k+:8];
  end
 end
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   comp_error <= 0;
   dma_rsp_valid <= 0;
   dma_error <= 0;
  end else begin
   comp_error <= comp_req && !comp_ok;
   dma_rsp_valid <= dma_take;
   if(dma_take) dma_error <= !dma_ok;
  end
 end
`ifndef SYNTHESIS
 initial assert(BYTES>=8 && BYTES%4==0 && (BYTES&(BYTES-1))==0)
  else $fatal(1,"tile RAM geometry");
`endif
endmodule
