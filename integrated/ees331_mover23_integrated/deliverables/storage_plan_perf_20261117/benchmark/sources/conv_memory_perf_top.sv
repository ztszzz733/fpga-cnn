module conv_memory_perf_top #(parameter bit PLAN=0)(
 input logic clk,rst_n,kind,
 input logic [1:0] start,
 input logic [31:0] input_base0,input_base1,weight_base,output_base0,output_base1,
 input logic [31:0] width,height,ci,co,
 output wire [1:0] busy,done,error,mac_work,
 output wire [31:0] macs0,macs1,
 input logic [31:0] cache_csr_addr,cache_csr_wdata,
 input logic cache_csr_re,cache_csr_we,
 output wire [31:0] cache_csr_rdata,
 output wire cache_csr_ready,
 input logic plan_cmd_valid,
 output wire plan_cmd_ready,
 input logic [31:0] plan_cmd_epoch,plan_cmd_frame_id,plan_cmd_id,
 input logic plan_cmd_direction,
 input logic [31:0] plan_cmd_ddr_offset,plan_cmd_local_offset,plan_cmd_bytes,
 output wire plan_rsp_valid,
 input logic plan_rsp_ready,
 output wire [31:0] plan_rsp_epoch,plan_rsp_frame_id,plan_rsp_id,plan_rsp_kind,plan_rsp_status,
 input logic plan_recover,
 output wire plan_busy,plan_drained,plan_fault,
 output wire cnn_mem_fault,
 output wire [31:0] S_AXI_HP0_AWADDR,S_AXI_HP0_ARADDR,
 output wire [63:0] S_AXI_HP0_WDATA,
 input wire [63:0] S_AXI_HP0_RDATA,
 output wire [5:0] S_AXI_HP0_AWID,S_AXI_HP0_ARID,S_AXI_HP0_WID,
 input wire [5:0] S_AXI_HP0_BID,S_AXI_HP0_RID,
 output wire [3:0] S_AXI_HP0_AWLEN,S_AXI_HP0_ARLEN,
 output wire [2:0] S_AXI_HP0_AWSIZE,S_AXI_HP0_ARSIZE,
 output wire [1:0] S_AXI_HP0_AWBURST,S_AXI_HP0_ARBURST,
 output wire [1:0] S_AXI_HP0_AWLOCK,S_AXI_HP0_ARLOCK,
 output wire [3:0] S_AXI_HP0_AWCACHE,S_AXI_HP0_ARCACHE,
 output wire [2:0] S_AXI_HP0_AWPROT,S_AXI_HP0_ARPROT,
 output wire [3:0] S_AXI_HP0_AWQOS,S_AXI_HP0_ARQOS,
 output wire [7:0] S_AXI_HP0_WSTRB,
 output wire S_AXI_HP0_AWVALID,S_AXI_HP0_WVALID,S_AXI_HP0_WLAST,
 output wire S_AXI_HP0_BREADY,S_AXI_HP0_ARVALID,S_AXI_HP0_RREADY,
 input wire S_AXI_HP0_AWREADY,S_AXI_HP0_WREADY,S_AXI_HP0_BVALID,
 input wire S_AXI_HP0_ARREADY,S_AXI_HP0_RVALID,S_AXI_HP0_RLAST,
 input wire [1:0] S_AXI_HP0_BRESP,S_AXI_HP0_RRESP
);
 wire [1:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
 wire [63:0] cnn_addr,cnn_wdata,cnn_rdata;
 wire cnn_cancel=1'b0;
 wire [1:0][31:0] inputs={input_base1,input_base0};
 wire [1:0][31:0] outputs={output_base1,output_base0};
 wire [1:0][31:0] counts;
 assign macs0=counts[0];assign macs1=counts[1];
 for(genvar u=0;u<2;u++)begin:units
  wire pv,pw,pbyte,pbusy,pdone,perror,pfire;
  wire kv,kw,kbyte,kbusy,kdone,kerror,kfire;
  wire [31:0] pa,pdata,ka,kdata,pmacs,kmacs;
  self_pw8_engine #(.MAX_CHANNELS(512)) pointwise(
   .clk,.rst_n,.clear(1'b0),.start(start[u] && !kind),.depthwise(1'b0),
   .input_base(inputs[u]),.weight_base,.output_base(outputs[u]),.width,.height,
   .in_channels(ci),.out_channels(co),.kernel(32'd1),.stride(32'd1),
   .busy(pbusy),.done(pdone),.error(perror),.valid(pv),.write(pw),.byte_access(pbyte),
   .addr(pa),.wdata(pdata),.ready(cnn_ready[u] && !kind),
   .response(cnn_response[u] && !kind),.rdata(cnn_rdata[u*32+:32]),
   .mac_fire(pfire),.phase(),.input_reads(),.weight_reads(),.mac_count(pmacs));
  self_conv_spatial4_engine #(.MAX_CHANNELS(512),.MAX_KERNEL(3),.TILE(2),.DW_CACHE(1)) spatial(
   .clk,.rst_n,.clear(1'b0),.start(start[u] && kind),.depthwise(1'b0),
   .input_base(inputs[u]),.weight_base,.output_base(outputs[u]),.width,.height,
   .in_channels(ci),.out_channels(co),.kernel(32'd3),.stride(32'd1),
   .busy(kbusy),.done(kdone),.error(kerror),.valid(kv),.write(kw),.byte_access(kbyte),
   .addr(ka),.wdata(kdata),.ready(cnn_ready[u] && kind),
   .response(cnn_response[u] && kind),.rdata(cnn_rdata[u*32+:32]),
   .mac_fire(kfire),.phase(),.input_reads(),.weight_reads(),.mac_count(kmacs));
  assign cnn_valid[u]=kind?kv:pv;
  assign cnn_write[u]=kind?kw:pw;
  assign cnn_byte[u]=kind?kbyte:pbyte;
  assign cnn_addr[u*32+:32]=kind?ka:pa;
  assign cnn_wdata[u*32+:32]=kind?kdata:pdata;
  assign busy[u]=kind?kbusy:pbusy;assign done[u]=kind?kdone:pdone;
  assign error[u]=kind?kerror:perror;assign mac_work[u]=kind?kfire:pfire;
  assign counts[u]=kind?kmacs:pmacs;
 end
 generate if(PLAN)begin:planned
  cnn_plan_storage #(.CLIENTS(2),.LOCAL_BYTES(401408),.MOVER_TIMEOUT_CYCLES(100000)) memory(.*);
 end else begin:legacy
  cnn_paged_mover #(.CLIENTS(2),.LOCAL_BYTES(401408),.LOGICAL_BYTES(32'h01000000)) memory(.*);
  assign plan_cmd_ready=0;assign plan_rsp_valid=0;
  assign plan_rsp_epoch=0;assign plan_rsp_frame_id=0;assign plan_rsp_id=0;
  assign plan_rsp_kind=0;assign plan_rsp_status=0;
  assign plan_busy=0;assign plan_drained=1;assign plan_fault=0;
 end endgenerate
endmodule
