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
 wire comp_ok = comp_addr[1:0]==0 && {1'b0,comp_addr}+33'd4<=33'(BYTES);
 wire dma_ok = dma_addr[1:0]==0 && {1'b0,dma_addr}+33'd4<=33'(BYTES);
 wire conflict = comp_req && comp_ok && dma_ok && comp_addr==dma_addr;
 assign dma_ready = rst_n && !conflict;
 wire dma_take = dma_valid && dma_ready;

 // Explicit power-of-two chunks prevent Vivado from rounding the entire
 // 392 KiB array up to 512 KiB. Its three chunks are 256+128+8 KiB.
 // The registered bank selection preserves the original one-cycle read.
 wire [AW-1:0] comp_word=comp_addr[2+:AW],dma_word=dma_addr[2+:AW];
 wire [AW:0][31:0] comp_bank_data,dma_bank_data;
 for(genvar g=0;g<=AW;g++)begin:banks
  if((WORDS & (2**g))!=0)begin:present
   localparam integer DEPTH=2**g,BASE_WORD=(WORDS/(2*DEPTH))*(2*DEPTH);
   localparam integer BAW=(g==0)?1:g;
   (* ram_style="block" *) logic [31:0] mem[0:DEPTH-1];
   logic [31:0] comp_q,dma_q;
   logic comp_selected,dma_selected;
   wire comp_hit=comp_word>=BASE_WORD && comp_word<BASE_WORD+DEPTH;
   wire dma_hit=dma_word>=BASE_WORD && dma_word<BASE_WORD+DEPTH;
   wire [BAW-1:0] comp_index=BAW'(comp_word-BASE_WORD);
   wire [BAW-1:0] dma_index=BAW'(dma_word-BASE_WORD);
   always @(posedge clk)begin
    if(comp_req && comp_ok && comp_hit)begin
     if(!comp_we)comp_q<=mem[comp_index];
     else for(integer k=0;k<4;k++)
      if(comp_wstrb[k])mem[comp_index][8*k+:8]<=comp_wdata[8*k+:8];
    end
   end
   always @(posedge clk)begin
    if(dma_take && dma_ok && dma_hit)begin
     if(!dma_write)dma_q<=mem[dma_index];
     else for(integer k=0;k<4;k++)
      if(dma_wstrb[k])mem[dma_index][8*k+:8]<=dma_wdata[8*k+:8];
    end
   end
   always @(posedge clk)begin
    if(!rst_n)begin comp_selected<=0;dma_selected<=0;end
    else begin
     if(comp_req && comp_ok && !comp_we)comp_selected<=comp_hit;
     if(dma_take && dma_ok && !dma_write)dma_selected<=dma_hit;
    end
   end
   assign comp_bank_data[g]=comp_selected?comp_q:32'b0;
   assign dma_bank_data[g]=dma_selected?dma_q:32'b0;
  end else begin:absent
   assign comp_bank_data[g]=32'b0;
   assign dma_bank_data[g]=32'b0;
  end
 end
 always_comb begin
  comp_rdata=0;dma_rdata=0;
  for(integer g=0;g<=AW;g++)begin
   comp_rdata=comp_rdata|comp_bank_data[g];
   dma_rdata=dma_rdata|dma_bank_data[g];
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
 initial assert(BYTES>=8 && BYTES%4==0)
  else $fatal(1,"tile RAM geometry");
`endif
endmodule
