// Four independent compute ports over the existing 392 KiB of true-dual-port
// tile RAM. DATA MOVER keeps one linear, 32-bit local DMA port.
// Small RAM configurations use bank 0 so the existing pager regressions keep
// their original capacity and timing contract.
module tile_local_ram_bank4 #(
 parameter integer BYTES=401408, parameter bit DISJOINT_PORTS=0
)(
 input  logic clk,rst_n,
 input  logic [3:0] comp_req,comp_we,
 input  logic [3:0][31:0] comp_addr,comp_wdata,
 input  logic [3:0][3:0] comp_wstrb,
 output wire [3:0][31:0] comp_rdata,
 output wire [3:0] comp_error,
 input  logic dma_valid,dma_write,
 output wire dma_ready,
 input  logic [31:0] dma_addr,dma_wdata,
 input  logic [3:0] dma_wstrb,
 output wire dma_rsp_valid,dma_error,
 output wire [31:0] dma_rdata
);
 generate if(BYTES==401408)begin:four_banks
  // 96 + 96 + 100 + 100 KiB = 392 KiB = 98 RAMB36 at x32 TDP.
  localparam integer BASE1=98304,BASE2=196608,BASE3=299008;
  wire in_range=dma_addr<32'(BYTES);
  wire [1:0] dma_bank=dma_addr<32'(BASE1)?2'd0:
                      dma_addr<32'(BASE2)?2'd1:
                      dma_addr<32'(BASE3)?2'd2:2'd3;
  wire [3:0] bank_dma_ready,bank_dma_rsp_valid,bank_dma_error;
  wire [3:0][31:0] bank_dma_rdata;
  logic [1:0] reply_bank;
  logic invalid_reply;
  for(genvar b=0;b<4;b++)begin:bank
   localparam integer BASE=b==0?0:b==1?BASE1:b==2?BASE2:BASE3;
   localparam integer SIZE=b<2?98304:102400;
   tile_local_ram #(.BYTES(SIZE),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
    .clk,.rst_n,
    .comp_req(comp_req[b]),.comp_we(comp_we[b]),
    .comp_addr(comp_addr[b]-32'(BASE)),.comp_wdata(comp_wdata[b]),
    .comp_wstrb(comp_wstrb[b]),.comp_rdata(comp_rdata[b]),
    .comp_error(comp_error[b]),
    .dma_valid(dma_valid && in_range && dma_bank==2'(b)),
    .dma_write,.dma_ready(bank_dma_ready[b]),
    .dma_addr(dma_addr-32'(BASE)),.dma_wdata,.dma_wstrb,
    .dma_rsp_valid(bank_dma_rsp_valid[b]),.dma_error(bank_dma_error[b]),
    .dma_rdata(bank_dma_rdata[b])
   );
  end
  assign dma_ready=rst_n && (!in_range || bank_dma_ready[dma_bank]);
  always_ff @(posedge clk)begin
   if(!rst_n)begin reply_bank<=0;invalid_reply<=0;end
   else begin
    invalid_reply<=dma_valid && dma_ready && !in_range;
    if(dma_valid && dma_ready && in_range)reply_bank<=dma_bank;
   end
  end
  assign dma_rsp_valid=invalid_reply || bank_dma_rsp_valid[reply_bank];
  assign dma_error=invalid_reply || bank_dma_error[reply_bank];
  assign dma_rdata=bank_dma_rdata[reply_bank];
 end else begin:one_bank
  tile_local_ram #(.BYTES(BYTES),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
   .clk,.rst_n,.comp_req(comp_req[0]),.comp_we(comp_we[0]),
   .comp_addr(comp_addr[0]),.comp_wdata(comp_wdata[0]),
   .comp_wstrb(comp_wstrb[0]),.comp_rdata(comp_rdata[0]),
   .comp_error(comp_error[0]),
   .dma_valid,.dma_write,.dma_ready,.dma_addr,.dma_wdata,.dma_wstrb,
   .dma_rsp_valid,.dma_error,.dma_rdata
  );
  for(genvar b=1;b<4;b++)begin:absent
   assign comp_rdata[b]=32'b0;
   assign comp_error[b]=1'b0;
  end
 end endgenerate
endmodule
