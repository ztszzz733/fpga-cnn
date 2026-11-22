// Parallel lower and upper 32-bit words of one aligned 64-bit address.
// The original 32-bit DMA and result write paths select a single stripe.
module tile_read_width #(
 parameter bit READ64=1, parameter bit WRITE128=1,
 parameter integer BYTES=200704,
 parameter bit DISJOINT_PORTS=1
)(
 input wire clk,rst_n,
 input wire comp_req,comp_we,comp_double,comp_quad,
 input wire [31:0] comp_addr,
 input wire [127:0] comp_wdata,
 input wire [3:0] comp_wstrb,
 output wire [63:0] comp_rdata,
 output wire comp_error,
 input wire dma_valid,dma_write,
 output wire dma_ready,
 input wire [31:0] dma_addr,dma_wdata,
 input wire [3:0] dma_wstrb,
 output wire dma_rsp_valid,dma_error,
 output wire [31:0] dma_rdata
);
 if(WRITE128)begin:quad_words
  // Each stripe owns one word of a 16-byte region.
  wire [31:0] comp_row={2'b00,comp_addr[31:4],comp_addr[1:0]};
  wire [31:0] dma_row={2'b00,dma_addr[31:4],dma_addr[1:0]};
  wire [31:0] words[4],dma_words[4];
  wire [3:0] errors,dma_errors,dma_valids,dma_readys;
  logic last_double;
  logic [1:0] last_lane,last_dma_lane;
  always_ff @(posedge clk)begin
   if(comp_req)begin
    last_double<=comp_double;
    last_lane<=comp_addr[3:2];
   end
   if(dma_valid && dma_ready)last_dma_lane<=dma_addr[3:2];
  end
  for(genvar stripe=0;stripe<4;stripe++)begin:word_stripe
   wire word_match=comp_addr[3:2]==2'(stripe);
   wire pair_match=comp_double && comp_addr[3]==1'(stripe/2);
   wire bank_select=comp_quad || pair_match || word_match;
   wire [31:0] word_data=comp_quad?comp_wdata[32*stripe+:32]:comp_wdata[31:0];
   tile_local_ram #(.BYTES(BYTES/4),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
    .clk,.rst_n,.comp_req(comp_req && bank_select),.comp_we,
    .comp_addr(comp_row),.comp_wdata(word_data),.comp_wstrb,.comp_rdata(words[stripe]),
    .comp_error(errors[stripe]),.dma_valid(dma_valid && dma_addr[3:2]==2'(stripe)),
    .dma_write,.dma_ready(dma_readys[stripe]),.dma_addr(dma_row),.dma_wdata,.dma_wstrb,
    .dma_rsp_valid(dma_valids[stripe]),.dma_error(dma_errors[stripe]),.dma_rdata(dma_words[stripe]));
  end
  assign comp_rdata=last_double?(last_lane[1]?{words[3],words[2]}:{words[1],words[0]}):{32'd0,words[last_lane]};
  assign comp_error=|errors;
  assign dma_ready=dma_readys[dma_addr[3:2]];
  assign dma_rsp_valid=|dma_valids;
  assign dma_error=dma_errors[last_dma_lane];
  assign dma_rdata=dma_words[last_dma_lane];
`ifndef SYNTHESIS
  always_ff @(posedge clk)if(rst_n && comp_req)begin
   if(comp_quad)assert(comp_we && !comp_double && comp_addr[3:0]==0 && comp_wstrb==4'hf);
   if(comp_double)assert(!comp_we && !comp_quad && comp_addr[2:0]==0);
  end
`endif
 end else if(READ64)begin:wide_words
  wire [31:0] comp_half={1'b0,comp_addr[31:3],comp_addr[1:0]};
  wire [31:0] dma_half={1'b0,dma_addr[31:3],dma_addr[1:0]};
  wire [31:0] words[2],dma_words[2];
  wire [1:0] errors,dma_errors,dma_valids,dma_readys;
  logic last_double,last_upper,last_dma_upper;
  always_ff @(posedge clk)begin
   if(comp_req)begin
    last_double<=comp_double;
    last_upper<=comp_addr[2];
   end
   if(dma_valid && dma_ready)last_dma_upper<=dma_addr[2];
  end
  for(genvar stripe=0;stripe<2;stripe++)begin:word_stripe
   wire comp_selected=comp_double || comp_addr[2]==1'(stripe);
   wire dma_selected=dma_addr[2]==1'(stripe);
   tile_local_ram #(.BYTES(BYTES/2),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
    .clk,.rst_n,.comp_req(comp_req && comp_selected),.comp_we,
    .comp_addr(comp_half),.comp_wdata(comp_wdata[31:0]),.comp_wstrb,.comp_rdata(words[stripe]),
    .comp_error(errors[stripe]),.dma_valid(dma_valid && dma_selected),
    .dma_write,.dma_ready(dma_readys[stripe]),.dma_addr(dma_half),.dma_wdata,.dma_wstrb,
    .dma_rsp_valid(dma_valids[stripe]),.dma_error(dma_errors[stripe]),.dma_rdata(dma_words[stripe]));
  end
  assign comp_rdata=last_double?{words[1],words[0]}:{32'd0,words[last_upper]};
  assign comp_error=|errors;
  assign dma_ready=dma_readys[dma_addr[2]];
  assign dma_rsp_valid=|dma_valids;
  assign dma_error=dma_errors[last_dma_upper];
  assign dma_rdata=dma_words[last_dma_upper];
`ifndef SYNTHESIS
  always_ff @(posedge clk)
   if(rst_n && comp_req && comp_double)assert(!comp_we && comp_addr[2:0]==0);
`endif
 end else begin:narrow_words
  assign comp_rdata[63:32]=0;
  tile_local_ram #(.BYTES(BYTES),.DISJOINT_PORTS(DISJOINT_PORTS)) ram(
   .clk,.rst_n,.comp_req,.comp_we,.comp_addr,.comp_wdata(comp_wdata[31:0]),.comp_wstrb,
   .comp_rdata(comp_rdata[31:0]),.comp_error,.dma_valid,.dma_write,.dma_ready,
   .dma_addr,.dma_wdata,.dma_wstrb,.dma_rsp_valid,.dma_error,.dma_rdata);
 end
endmodule

