// Isolated storage integration: row controller -> mover -> local BRAM -> AXI3.
// Board PS configuration, CNN compute adapter and production reset are external.
module tile_dma_system #(
 parameter integer LOCAL_BYTES=32768,
 parameter integer TIMEOUT_CYCLES=1024
)(
 input logic clk,rst_n,enable,recover,
 input logic [31:0] cfg_ddr_base,cfg_ddr_bytes,
 input logic start_valid,start_write,
 output wire start_ready,
 input logic [31:0] start_ddr,start_local,start_row_bytes,
 input logic [31:0] start_rows,start_ddr_stride,start_local_stride,
 output wire done_valid,
 input logic done_ready,
 output wire [31:0] done_status,done_rows,
 output wire fault_locked,drained,busy,
 input logic comp_req,comp_we,
 input logic [31:0] comp_addr,comp_wdata,
 input logic [3:0] comp_wstrb,
 output wire [31:0] comp_rdata,
 output wire comp_error,
 output wire [31:0] araddr,awaddr,
 output wire [5:0] arid,awid,wid,
 output wire [3:0] arlen,awlen,
 output wire [2:0] arsize,awsize,
 output wire [1:0] arburst,awburst,arlock,awlock,
 output wire [3:0] arcache,awcache,arqos,awqos,
 output wire [2:0] arprot,awprot,
 output wire arvalid,awvalid,wvalid,wlast,rready,bready,
 input logic arready,awready,wready,rvalid,rlast,bvalid,
 input logic [63:0] rdata,
 input logic [5:0] rid,bid,
 input logic [1:0] rresp,bresp,
 output wire [63:0] wdata,
 output wire [7:0] wstrb
);
 wire cmd_valid,cmd_ready,rsp_valid,rsp_ready;
 wire [31:0] cmd_src,cmd_dst,cmd_bytes,cmd_flags,rsp_status,rsp_bytes_done;
 wire local_valid,local_write,local_ready,local_rsp_valid,local_error;
 wire [31:0] local_addr,local_wdata,local_rdata;
 wire [3:0] local_wstrb;
 logic job_active;
 logic [31:0] ddr_base_q,ddr_bytes_q;
 always_ff @(posedge clk) begin
  if(!rst_n) begin job_active<=0;ddr_base_q<=0;ddr_bytes_q<=0;end
  else begin
   if(start_valid && start_ready) begin
    job_active<=1;ddr_base_q<=cfg_ddr_base;ddr_bytes_q<=cfg_ddr_bytes;
   end
   if(done_valid && done_ready) job_active<=0;
  end
 end
 tile_row_dma rows(
  .clk,.rst_n,.enable(enable && !fault_locked),.start_valid,.start_ready,.start_write,
  .start_ddr,.start_local,.start_row_bytes,.start_rows,
  .start_ddr_stride,.start_local_stride,
  .cfg_ddr_bytes(ddr_bytes_q),.cfg_local_bytes(32'(LOCAL_BYTES)),
  .cmd_valid,.cmd_ready,.cmd_src,.cmd_dst,.cmd_bytes,.cmd_flags,
  .rsp_valid,.rsp_ready,.rsp_status,
  .done_valid,.done_ready,.done_status,.done_rows
 );
 data_mover #(.TIMEOUT_CYCLES(TIMEOUT_CYCLES)) mover(
  .clk,.rst_n,.enable(enable || job_active),.recover,
  .cfg_ddr_base(ddr_base_q),.cfg_ddr_bytes(ddr_bytes_q),
  .cfg_local_bytes(32'(LOCAL_BYTES)),
  .cmd_valid,.cmd_ready,.cmd_src,.cmd_dst,.cmd_bytes,.cmd_flags,
  .rsp_valid,.rsp_ready,.rsp_status,.rsp_bytes_done,
  .fault_locked,.drained,.busy,
  .local_valid,.local_write,.local_ready,.local_addr,.local_wdata,
  .local_wstrb,.local_rsp_valid,.local_error,.local_rdata,
  .araddr,.awaddr,.arid,.awid,.wid,.arlen,.awlen,.arsize,.awsize,
  .arburst,.awburst,.arlock,.awlock,.arcache,.awcache,.arqos,.awqos,
  .arprot,.awprot,.arvalid,.awvalid,.wvalid,.wlast,.rready,.bready,
  .arready,.awready,.wready,.rvalid,.rlast,.bvalid,
  .rdata,.rid,.bid,.rresp,.bresp,.wdata,.wstrb
 );
 tile_local_ram #(.BYTES(LOCAL_BYTES)) local_ram(
  .clk,.rst_n,.comp_req,.comp_we,.comp_addr,.comp_wdata,.comp_wstrb,
  .comp_rdata,.comp_error,
  .dma_valid(local_valid),.dma_write(local_write),.dma_ready(local_ready),
  .dma_addr(local_addr),.dma_wdata(local_wdata),.dma_wstrb(local_wstrb),
  .dma_rsp_valid(local_rsp_valid),.dma_error(local_error),.dma_rdata(local_rdata)
 );
endmodule
