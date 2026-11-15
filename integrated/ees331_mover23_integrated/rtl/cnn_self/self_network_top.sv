// Isolated CNN: two K3 engines, one K1, one DW7, one post, one Add, one pad.
// Unit number equals memory port number. Commands are sixteen little-endian
// 32-bit words; see docs/self_cnn_interface.md for the complete descriptor ABI.
// clear/cancel requires the memory fabric to discard ALL in-flight requests,
// responses, and external reader acknowledgements before a new batch starts.
// Every operator publishes done only after its final write response drains.
module self_network_top #(
 parameter integer MAX_TASKS=64, IW=$clog2(MAX_TASKS)
)(
 input logic clk,rst_n,clear,start,memory_fault,
 input logic [1:0] engine_enable,
 input logic program_result_valid,
 input logic [31:0] program_result_frame,program_result_addr,program_result_bytes,
 input logic result_ready,
 output wire result_valid,result_accept,outputs_pending,compute_done,
 output wire [31:0] result_frame,result_addr,result_bytes,
 output wire [7:0] result_error,external_hold,
 input logic program_allocate_valid,input logic [2:0] program_allocate_slot,
 input logic [MAX_TASKS-1:0] program_hold_mask,
 input logic [2:0] program_use_valid,input logic [8:0] program_use_slots,
 input logic [3*IW-1:0] program_use_owners,
 output wire [7:0] buffer_live,buffer_release,buffer_allocate,
 output wire [8*IW-1:0] buffer_owners,output wire wait_buffer,
 input logic program_valid,input logic [IW-1:0] program_index,
 input logic [511:0] program_command,
 input logic [1:0] program_dep_valid,input logic [IW-1:0] program_dep0,program_dep1,
 input logic [IW:0] task_count,
 output wire program_ready,busy,done,error,cancel,
 output wire [6:0] mem_valid,mem_write,mem_byte,
 output wire [223:0] mem_addr,mem_wdata,
 input wire [6:0] mem_ready,mem_response,input wire [223:0] mem_rdata,
 output wire [6:0] unit_start,unit_active,completion_pulse,
 output wire [6:0][IW-1:0] unit_node,
 output wire [IW:0] completed_count,
 output wire [MAX_TASKS-1:0] completed_mask,
 output wire [6:0] operator_busy,operator_work,
 output wire [2:0][31:0] conv_input_reads,conv_weight_reads,conv_mac_count,
 output wire dw7_mac
);
 wire [6:0][511:0] unit_command;
 wire [6:0][15:0][31:0] cmd=unit_command;
 wire [6:0] ub,ud,ue;
 wire abort_ops=cancel;
 wire buffer_ready,reserve_commit;
 wire [IW-1:0] candidate_node;
 wire compute_busy,configuration_error;
 wire program_accept=program_valid && program_ready && program_index<MAX_TASKS;
 assign operator_busy=ub;
 assign busy=compute_busy || outputs_pending || (|buffer_live);
 assign done=compute_done && !outputs_pending && !(|buffer_live) && !cancel;

 self_result_handoff #(.MAX_TASKS(MAX_TASKS),.IW(IW)) results(.*);
 self_buffer_leases #(.MAX_TASKS(MAX_TASKS),.IW(IW)) leases(.*);
 self_dispatch #(.MAX_TASKS(MAX_TASKS),.IW(IW)) dispatch(
  .*,.busy(compute_busy),.done(compute_done),
  .memory_fault(memory_fault || configuration_error),
  .unit_busy(ub),.unit_done(ud),.unit_error(ue));

 // K3 engines accept ordinary or multiplier-one depthwise convolution. The
 // dispatcher selects either idle K3 from engine_enable, without frame binding.
 for(genvar e=0;e<3;e++)begin:engines
  localparam integer KERNEL=e==2 ? 1:3;
  self_conv_engine #(.MAX_CHANNELS(512),.MAX_KERNEL(KERNEL),.TILE(2)) convolution(
   .clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[e]),
   .depthwise(cmd[e][11][0]),
   .input_base(cmd[e][1]),.weight_base(cmd[e][2]),.output_base(cmd[e][3]),
   .width(cmd[e][7]),.height(cmd[e][8]),.in_channels(cmd[e][6]),
   .out_channels(cmd[e][9]),.kernel(32'(KERNEL)),.stride(cmd[e][10]),
   .busy(ub[e]),.done(ud[e]),.error(ue[e]),
   .valid(mem_valid[e]),.write(mem_write[e]),.byte_access(mem_byte[e]),
   .addr(mem_addr[e*32+:32]),.wdata(mem_wdata[e*32+:32]),
   .ready(mem_ready[e]),.response(mem_response[e]),.rdata(mem_rdata[e*32+:32]),
   .mac_fire(operator_work[e]),.phase(),.input_reads(conv_input_reads[e]),
   .weight_reads(conv_weight_reads[e]),.mac_count(conv_mac_count[e]));
 end

 dw7_cached_engine #(.MAX_WIDTH(7),.MAX_CHANNELS(512),.LANES(8)) dw7(
  .clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[3]),.reuse_weights(1'b0),
  .input_base(cmd[3][1]),.weight_base(cmd[3][2]),.output_base(cmd[3][3]),
  .width(cmd[3][7]),.height(cmd[3][8]),.channels(cmd[3][6]),
  .busy(ub[3]),.done(ud[3]),.error(ue[3]),.valid(mem_valid[3]),
  .write(mem_write[3]),.byte_access(mem_byte[3]),.cancel(),
  .addr(mem_addr[96+:32]),.wdata(mem_wdata[96+:32]),
  .ready(mem_ready[3]),.response(mem_response[3]),.rdata(mem_rdata[96+:32]),
  .phase(),.mac_fire(dw7_mac),.weights_cached(),.cache_hit());
 assign operator_work[3]=dw7_mac;

 // Preserve the proven arithmetic RTL verbatim. Independent instances allow
 // affine postprocessing and residual Add to make progress concurrently.
 for(genvar e=4;e<6;e++)begin:postprocessing
  quant_post_engine post(
   .clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[e]),.mode_add(e==5),
   .src_a(cmd[e][1]),.src_b(cmd[e][2]),.destination(cmd[e][3]),
   .parameter_base(cmd[e][4]),.count(cmd[e][5]),.channels(cmd[e][6]),
   .busy(ub[e]),.done(ud[e]),.error(ue[e]),.valid(mem_valid[e]),
   .write(mem_write[e]),.byte_access(mem_byte[e]),
   .addr(mem_addr[e*32+:32]),.wdata(mem_wdata[e*32+:32]),
   .ready(mem_ready[e]),.response(mem_response[e]),.rdata(mem_rdata[e*32+:32]));
  // Actual accepted output progress; excludes merely waiting with busy high.
  assign operator_work[e]=mem_valid[e] && mem_ready[e] && mem_write[e];
 end

 pad_hwc_engine padding(
  .clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[6]),
  .source(cmd[6][1]),.destination(cmd[6][3]),.width(cmd[6][7]),
  .height(cmd[6][8]),.channels(cmd[6][6]),.zero_point(cmd[6][9][7:0]),
  .busy(ub[6]),.done(ud[6]),.error(ue[6]),.valid(mem_valid[6]),
  .write(mem_write[6]),.byte_access(mem_byte[6]),
  .addr(mem_addr[192+:32]),.wdata(mem_wdata[192+:32]),
  .ready(mem_ready[6]),.response(mem_response[6]),.rdata(mem_rdata[192+:32]));
 assign operator_work[6]=mem_valid[6] && mem_ready[6] && mem_write[6];
endmodule
