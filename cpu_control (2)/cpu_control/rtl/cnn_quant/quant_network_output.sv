// Full command-table capacity; isolated CNN integration, unchanged production SoC.
module quant_network_output(
 input logic clk,rst_n,clear,start,memory_fault,
 input logic [1:0] engine_enable,
 input logic program_result_valid,
 input logic [31:0] program_result_frame,program_result_addr,program_result_bytes,
 input logic result_ready,
 output wire result_valid,result_accept,outputs_pending,compute_done,
 output wire [31:0] result_frame,result_addr,result_bytes,
 output wire [7:0] result_error,external_hold,
 input logic program_allocate_valid,input logic [2:0] program_allocate_slot,
 input logic [1023:0] program_hold_mask,
 input logic [2:0] program_use_valid,input logic [8:0] program_use_slots,input logic [29:0] program_use_owners,
 output wire [7:0] buffer_live,buffer_release,buffer_allocate,
 output wire [79:0] buffer_owners,output wire wait_buffer,
 input logic program_valid,input logic [9:0] program_index,
 input logic [511:0] program_command,
 input logic [1:0] program_dep_valid,input logic [9:0] program_dep0,program_dep1,
 input logic [10:0] task_count,
 output wire program_ready,busy,done,error,cancel,
 output wire [22:0] mem_valid,mem_write,mem_byte,
 output wire [735:0] mem_addr,mem_wdata,
 input wire [22:0] mem_ready,mem_response,input wire [735:0] mem_rdata,
 output wire [4:0] unit_start,unit_active,completion_pulse,
 output wire [4:0][9:0] unit_node,
 output wire [10:0] completed_count,
 output wire [1023:0] completed_mask,
 output wire [4:0] operator_busy,
 output wire dw7_mac
);
 wire [4:0][511:0] unit_command;
 wire [4:0][15:0][31:0] cmd=unit_command;
 wire [4:0] ub,ud,ue;
 wire [1:0] core_busy,mem_idle;
 wire abort_ops=cancel;
 assign operator_busy=ub;
 wire buffer_ready,reserve_commit;
 wire [9:0] candidate_node;
 wire compute_busy,configuration_error;
 assign busy=compute_busy || outputs_pending || (|buffer_live);
 assign done=compute_done && !outputs_pending && !(|buffer_live) && !cancel;
 network_result_handoff results(.*,.program_accept(program_valid && program_ready));
 network_buffer_leases leases(.*,.program_accept(program_valid && program_ready));
 network_dispatch_buffered dispatch(.*,.busy(compute_busy),.done(compute_done),.memory_fault(memory_fault || configuration_error),.unit_busy(ub),.unit_done(ud),.unit_error(ue));
 logic [1:0] conv_enable;
 wire [1:0] conv_clk={2{clk}} & conv_enable;
 always_ff @(negedge clk or negedge rst_n)
  if(!rst_n)conv_enable<=3;else conv_enable<={2{abort_ops}} | unit_active[1:0] | unit_start[1:0] | ub[1:0];
 for(genvar e=0;e<2;e++)begin:engines
 neureka_conv_engine convolution(.clk(conv_clk[e]),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[e]),
  .config_address(cmd[e][1]),.busy(ub[e]),.done(ud[e]),.error(ue[e]),
  .cfg_valid(mem_valid[e*10+9]),.cfg_addr(mem_addr[(e*10+9)*32+:32]),.cfg_ready(mem_ready[e*10+9]),.cfg_response(mem_response[e*10+9]),.cfg_rdata(mem_rdata[(e*10+9)*32+:32]),
  .valid(mem_valid[e*10+:9]),.write(mem_write[e*10+:9]),.byte_access(mem_byte[e*10+:9]),.addr(mem_addr[e*320+:288]),.wdata(mem_wdata[e*320+:288]),
  .ready(mem_ready[e*10+:9]),.response(mem_response[e*10+:9]),.rdata(mem_rdata[e*320+:288]),.core_busy(core_busy[e]),.memory_idle(mem_idle[e]));
 assign mem_write[e*10+9]=0;assign mem_byte[e*10+9]=0;assign mem_wdata[(e*10+9)*32+:32]=0;
 end
 quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[2]),
  .mode_add(cmd[2][0]==2),.src_a(cmd[2][1]),.src_b(cmd[2][2]),.destination(cmd[2][3]),.parameter_base(cmd[2][4]),.count(cmd[2][5]),.channels(cmd[2][6]),
  .busy(ub[2]),.done(ud[2]),.error(ue[2]),.valid(mem_valid[20]),.write(mem_write[20]),.byte_access(mem_byte[20]),
  .addr(mem_addr[640+:32]),.wdata(mem_wdata[640+:32]),.ready(mem_ready[20]),.response(mem_response[20]),.rdata(mem_rdata[640+:32]));
 dw7_cached_engine #(.MAX_WIDTH(7)) dw7(.clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[3]),.reuse_weights(1'b0),
  .input_base(cmd[3][1]),.weight_base(cmd[3][2]),.output_base(cmd[3][3]),.width(cmd[3][7]),.height(cmd[3][8]),.channels(cmd[3][6]),
  .busy(ub[3]),.done(ud[3]),.error(ue[3]),.valid(mem_valid[21]),.write(mem_write[21]),.byte_access(mem_byte[21]),.cancel(),
  .addr(mem_addr[672+:32]),.wdata(mem_wdata[672+:32]),.ready(mem_ready[21]),.response(mem_response[21]),.rdata(mem_rdata[672+:32]),
  .phase(),.mac_fire(dw7_mac),.weights_cached(),.cache_hit());
 pad_hwc_engine padding(.clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(unit_start[4]),
  .source(cmd[4][1]),.destination(cmd[4][3]),.width(cmd[4][7]),.height(cmd[4][8]),.channels(cmd[4][6]),.zero_point(cmd[4][9][7:0]),
  .busy(ub[4]),.done(ud[4]),.error(ue[4]),.valid(mem_valid[22]),.write(mem_write[22]),.byte_access(mem_byte[22]),
  .addr(mem_addr[704+:32]),.wdata(mem_wdata[704+:32]),.ready(mem_ready[22]),.response(mem_response[22]),.rdata(mem_rdata[704+:32]));
endmodule
