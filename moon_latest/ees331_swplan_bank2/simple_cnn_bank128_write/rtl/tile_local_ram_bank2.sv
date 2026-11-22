// Two independent compute banks plus one linear DMA port.
module tile_local_ram_bank2 #(
 parameter integer BYTES=196608, parameter bit TWO_BANKS=1,
 parameter bit DISJOINT_PORTS=0, parameter bit READ64=1, parameter bit WRITE128=1
)(
 input logic clk,rst_n,
 input logic [1:0] comp_req,comp_we,comp_double,comp_quad,
 input logic [1:0][31:0] comp_addr,
 input logic [1:0][127:0] comp_wdata,
 input logic [1:0][3:0] comp_wstrb,
 output wire [1:0][63:0] comp_rdata,
 output wire [1:0] comp_error,
 input logic dma_valid,dma_write,
 output wire dma_ready,
 input logic [31:0] dma_addr,dma_wdata,
 input logic [3:0] dma_wstrb,
 output wire dma_rsp_valid,dma_error,
 output wire [31:0] dma_rdata
);
 generate if(TWO_BANKS)begin:two_banks
  localparam integer BANK_BYTES=BYTES/2;
  wire in_range=dma_addr<BYTES;
  wire dma_bank=dma_addr>=BANK_BYTES;
  wire [1:0] bank_ready,bank_response,bank_error;
  wire [1:0][31:0] bank_data;
  logic reply_bank,invalid_reply;
  for(genvar b=0;b<2;b++)begin:bank
   tile_read_width #(.READ64(READ64),.WRITE128(WRITE128),.BYTES(BANK_BYTES),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
    .clk,.rst_n,.comp_req(comp_req[b]),.comp_we(comp_we[b]),
    .comp_addr(comp_addr[b]-32'(b*BANK_BYTES)),.comp_wdata(comp_wdata[b]),
    .comp_wstrb(comp_wstrb[b]),.comp_double(comp_double[b]),.comp_quad(comp_quad[b]),.comp_rdata(comp_rdata[b]),.comp_error(comp_error[b]),
    .dma_valid(dma_valid && in_range && dma_bank==1'(b)),.dma_write,
    .dma_ready(bank_ready[b]),.dma_addr(dma_addr-32'(b*BANK_BYTES)),.dma_wdata,.dma_wstrb,
    .dma_rsp_valid(bank_response[b]),.dma_error(bank_error[b]),.dma_rdata(bank_data[b]));
  end
  assign dma_ready=rst_n && (!in_range || bank_ready[dma_bank]);
  always_ff @(posedge clk)begin
   if(!rst_n)begin reply_bank<=0;invalid_reply<=0;end
   else begin
    invalid_reply<=dma_valid && dma_ready && !in_range;
    if(dma_valid && dma_ready && in_range)reply_bank<=dma_bank;
   end
  end
  assign dma_rsp_valid=invalid_reply || bank_response[reply_bank];
  assign dma_error=invalid_reply || bank_error[reply_bank];
  assign dma_rdata=bank_data[reply_bank];
 end else begin:one_bank
  tile_read_width #(.READ64(READ64),.WRITE128(WRITE128),.BYTES(BYTES),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
   .clk,.rst_n,.comp_req(comp_req[0]),.comp_we(comp_we[0]),.comp_addr(comp_addr[0]),
   .comp_wdata(comp_wdata[0]),.comp_wstrb(comp_wstrb[0]),.comp_double(comp_double[0]),.comp_quad(comp_quad[0]),.comp_rdata(comp_rdata[0]),
   .comp_error(comp_error[0]),.dma_valid,.dma_write,.dma_ready,.dma_addr,.dma_wdata,
   .dma_wstrb,.dma_rsp_valid,.dma_error,.dma_rdata);
  assign comp_rdata[1]=0;assign comp_error[1]=0;
 end endgenerate
endmodule
