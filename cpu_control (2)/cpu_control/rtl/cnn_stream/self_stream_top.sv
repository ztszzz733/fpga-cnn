// Actual bai-datasram SRAM plus configurable CNN operator pools. Four complete
// image commits may arrive during computation. No arithmetic/memory TB model.
module self_stream_top #(
 parameter MAX_TASKS=64,IW=$clog2(MAX_TASKS),SLOTS=16,SW=$clog2(SLOTS),
 parameter K3_UNITS=3,K1_UNITS=1,POST_UNITS=1,
 parameter UNITS=K3_UNITS+K1_UNITS+POST_UNITS+3,
 parameter SRAM_SIZE=262144
)(
 input logic clk,rst_n,clear,start,
 input logic [UNITS-1:0] unit_enable,
 input logic frame_valid,input logic [1:0] frame_slot,input logic [31:0] frame_id,
 output wire frame_ready,output wire [3:0] frames_ready,
 input logic program_valid,input logic [IW-1:0] program_index,
 input logic [511:0] program_command,input logic [1:0] program_dep_valid,
 input logic [IW-1:0] program_dep0,program_dep1,input logic [IW:0] task_count,
 input logic program_allocate_valid,input logic [SW-1:0] program_allocate_slot,
 input logic [MAX_TASKS-1:0] program_hold_mask,
 input logic [2:0] program_use_valid,input logic [3*SW-1:0] program_use_slots,
 input logic [3*IW-1:0] program_use_owners,
 input logic program_result_valid,
 input logic [31:0] program_result_frame,program_result_addr,program_result_bytes,
 input logic result_ready,
 output wire result_valid,result_accept,outputs_pending,compute_done,
 output wire [31:0] result_frame,result_addr,result_bytes,
 output wire [7:0] result_error,
 output wire [SLOTS-1:0] external_hold,buffer_live,buffer_release,buffer_allocate,
 output wire [SLOTS*IW-1:0] buffer_owners,
 output wire wait_buffer,wait_input,program_ready,busy,done,error,cancel,memory_fault,
 input logic [31:0] dmem_addr,dmem_wdata,input logic [3:0] dmem_wstrb,
 input logic dmem_re,dmem_we,output wire [31:0] dmem_rdata,
 input logic io_mem_req,io_mem_we,input logic [31:0] io_mem_addr,io_mem_wdata,
 input logic [3:0] io_mem_be,output wire io_mem_gnt,io_mem_rvalid,io_mem_error,
 output wire [31:0] io_mem_rdata,
 output wire [UNITS-1:0] mem_valid,mem_write,mem_byte,mem_ready,mem_response,
 output wire [UNITS*32-1:0] mem_addr,mem_wdata,mem_rdata,
 output wire [UNITS-1:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work,
 output wire [UNITS-1:0][IW-1:0] unit_node,
 output wire [IW:0] completed_count,output wire [MAX_TASKS-1:0] completed_mask,
 output wire [K3_UNITS+K1_UNITS-1:0][31:0] conv_input_reads,conv_weight_reads,conv_mac_count
);
 localparam DW=K3_UNITS+K1_UNITS,POST=DW+1,ADD=POST+POST_UNITS,PAD=ADD+1;
 wire [UNITS-1:0][511:0] unit_command;
 wire [UNITS-1:0][15:0][31:0] cmd=unit_command;
 wire [UNITS-1:0] ub,ud,ue;
 wire buffer_ready,reserve_commit,compute_busy,configuration_error;
 wire [IW-1:0] candidate_node;
 wire program_accept=program_valid && program_ready && program_index<MAX_TASKS;
 assign operator_busy=ub;
 assign busy=compute_busy || outputs_pending || (|buffer_live);
 assign done=compute_done && !outputs_pending && !(|buffer_live) && !cancel;
 stream_result_handoff #(.MAX_TASKS(MAX_TASKS),.IW(IW),.SLOTS(SLOTS),.SW(SW)) results(.*);
 stream_buffer_leases #(.MAX_TASKS(MAX_TASKS),.IW(IW),.SLOTS(SLOTS),.SW(SW)) leases(.*);
 stream_dispatch #(.MAX_TASKS(MAX_TASKS),.IW(IW),.K3_UNITS(K3_UNITS),.K1_UNITS(K1_UNITS),.POST_UNITS(POST_UNITS)) dispatch(
  .*,.busy(compute_busy),.done(compute_done),.memory_fault(memory_fault || configuration_error),
  .unit_busy(ub),.unit_done(ud),.unit_error(ue));
 for(genvar e=0;e<DW;e++)begin:engines
  localparam KERNEL=e<K3_UNITS?3:1;
  self_conv_engine #(.MAX_CHANNELS(512),.MAX_KERNEL(KERNEL),.TILE(2)) convolution(
   .clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[e]),.depthwise(cmd[e][11][0]),
   .input_base(cmd[e][1]),.weight_base(cmd[e][2]),.output_base(cmd[e][3]),
   .width(cmd[e][7]),.height(cmd[e][8]),.in_channels(cmd[e][6]),.out_channels(cmd[e][9]),.kernel(32'(KERNEL)),.stride(cmd[e][10]),
   .busy(ub[e]),.done(ud[e]),.error(ue[e]),.valid(mem_valid[e]),.write(mem_write[e]),.byte_access(mem_byte[e]),
   .addr(mem_addr[e*32+:32]),.wdata(mem_wdata[e*32+:32]),.ready(mem_ready[e]),.response(mem_response[e]),.rdata(mem_rdata[e*32+:32]),
   .mac_fire(operator_work[e]),.phase(),.input_reads(conv_input_reads[e]),.weight_reads(conv_weight_reads[e]),.mac_count(conv_mac_count[e]));
 end
 dw7_cached_engine #(.MAX_WIDTH(7),.MAX_CHANNELS(512),.LANES(8)) dw7(
  .clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[DW]),.reuse_weights(1'b0),
  .input_base(cmd[DW][1]),.weight_base(cmd[DW][2]),.output_base(cmd[DW][3]),.width(cmd[DW][7]),.height(cmd[DW][8]),.channels(cmd[DW][6]),
  .busy(ub[DW]),.done(ud[DW]),.error(ue[DW]),.valid(mem_valid[DW]),.write(mem_write[DW]),.byte_access(mem_byte[DW]),.cancel(),
  .addr(mem_addr[DW*32+:32]),.wdata(mem_wdata[DW*32+:32]),.ready(mem_ready[DW]),.response(mem_response[DW]),.rdata(mem_rdata[DW*32+:32]),
  .phase(),.mac_fire(operator_work[DW]),.weights_cached(),.cache_hit());
 for(genvar e=POST;e<=ADD;e++)begin:postprocessing
  quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[e]),.mode_add(e==ADD),
   .src_a(cmd[e][1]),.src_b(cmd[e][2]),.destination(cmd[e][3]),.parameter_base(cmd[e][4]),.count(cmd[e][5]),.channels(cmd[e][6]),
   .busy(ub[e]),.done(ud[e]),.error(ue[e]),.valid(mem_valid[e]),.write(mem_write[e]),.byte_access(mem_byte[e]),
   .addr(mem_addr[e*32+:32]),.wdata(mem_wdata[e*32+:32]),.ready(mem_ready[e]),.response(mem_response[e]),.rdata(mem_rdata[e*32+:32]));
  assign operator_work[e]=mem_valid[e] && mem_ready[e] && mem_write[e];
 end
 pad_hwc_engine padding(.clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[PAD]),
  .source(cmd[PAD][1]),.destination(cmd[PAD][3]),.width(cmd[PAD][7]),.height(cmd[PAD][8]),.channels(cmd[PAD][6]),.zero_point(cmd[PAD][9][7:0]),
  .busy(ub[PAD]),.done(ud[PAD]),.error(ue[PAD]),.valid(mem_valid[PAD]),.write(mem_write[PAD]),.byte_access(mem_byte[PAD]),
  .addr(mem_addr[PAD*32+:32]),.wdata(mem_wdata[PAD*32+:32]),.ready(mem_ready[PAD]),.response(mem_response[PAD]),.rdata(mem_rdata[PAD*32+:32]));
 assign operator_work[PAD]=mem_valid[PAD] && mem_ready[PAD] && mem_write[PAD];
 datasram_banked #(.SRAM_BASE(0),.SRAM_SIZE(SRAM_SIZE),.BANKS(4),.CLIENTS(UNITS)) storage(
  .clk(clk),.rst_n(rst_n),.dmem_addr(dmem_addr),.dmem_wdata(dmem_wdata),.dmem_wstrb(dmem_wstrb),.dmem_re(dmem_re),.dmem_we(dmem_we),.dmem_rdata(dmem_rdata),
  .cnn_valid(mem_valid),.cnn_write(mem_write),.cnn_byte(mem_byte),.cnn_addr(mem_addr),.cnn_wdata(mem_wdata),
  .cnn_ready(mem_ready),.cnn_response(mem_response),.cnn_rdata(mem_rdata),.cnn_cancel(cancel),.cnn_mem_fault(memory_fault),
  .io_mem_req(io_mem_req),.io_mem_we(io_mem_we),.io_mem_addr(io_mem_addr),.io_mem_wdata(io_mem_wdata),.io_mem_be(io_mem_be),
  .io_mem_gnt(io_mem_gnt),.io_mem_rvalid(io_mem_rvalid),.io_mem_rdata(io_mem_rdata),.io_mem_error(io_mem_error));
endmodule
