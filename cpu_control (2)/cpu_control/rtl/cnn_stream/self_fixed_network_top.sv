// Actual bai-datasram SRAM plus configurable CNN operator pools. Four complete
// image commits may arrive during computation. No arithmetic/memory TB model.
module self_fixed_network_top #(
 parameter MAX_TASKS=64,IW=$clog2(MAX_TASKS),SLOTS=16,SW=$clog2(SLOTS),
 parameter K3_UNITS=4,K1_UNITS=2,POST_UNITS=1,
 parameter UNITS=K3_UNITS+K1_UNITS+POST_UNITS+3,
 parameter SRAM_SIZE=262144
)(
 input logic clk,rst_n,clear,start,
 input logic [UNITS-1:0] unit_enable,
 input logic frame_valid,input logic [1:0] frame_slot,input logic [31:0] frame_id,
 output wire frame_ready,output wire [3:0] frames_ready,
 input logic [2:0] image_count,
 input logic template_valid,input logic [$clog2(MAX_TASKS/4)-1:0] template_index,
 input logic [511:0] template_command,input logic [3:0] template_source_modes,
 input logic [1:0] template_dep_valid,
 input logic [$clog2(MAX_TASKS/4)-1:0] template_dep0,template_dep1,
 input logic [1:0] template_allocate_slot,
 input logic [MAX_TASKS/4-1:0] template_hold_mask,
 input logic [2:0] template_use_valid,input logic [5:0] template_use_slots,
 input logic [3*$clog2(MAX_TASKS/4)-1:0] template_use_owners,
 input logic template_result_valid,input logic [31:0] template_result_bytes,
 input logic address_valid,input logic [1:0] address_slot,
 input logic [31:0] image_base,workspace_base,address_frame,
 output wire configuration_ready,
 input logic result_ready,
 output wire result_valid,result_accept,outputs_pending,compute_done,
 output wire [31:0] result_frame,result_addr,result_bytes,
 output wire [7:0] result_error,
 output wire [SLOTS-1:0] external_hold,buffer_live,buffer_release,buffer_allocate,
 output wire [SLOTS*IW-1:0] buffer_owners,
 output wire wait_buffer,wait_input,busy,done,error,cancel,memory_fault,
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
 // The fixed program is expanded inside the CNN from image/workspace addresses.
 wire program_valid,program_ready,program_allocate_valid,program_result_valid;
 wire [IW-1:0] program_index,program_dep0,program_dep1;
 wire [511:0] program_command;wire [1:0] program_dep_valid;
 wire [IW:0] task_count;wire [3:0] program_allocate_slot;
 wire [MAX_TASKS-1:0] program_hold_mask;wire [2:0] program_use_valid;
 wire [11:0] program_use_slots;wire [3*IW-1:0] program_use_owners;
 wire [31:0] program_result_frame,program_result_addr,program_result_bytes;
 wire core_start,core_busy,core_error,expanding,configuration_error;
 assign busy=expanding || core_busy;
 assign error=configuration_error || core_error;
 stream_fixed_programmer #(.MAX_TASKS(MAX_TASKS),.IW(IW)) fixed_program(.*);
 self_stream_top #(.MAX_TASKS(MAX_TASKS),.IW(IW),.SLOTS(SLOTS),.SW(SW),.K3_UNITS(K3_UNITS),.K1_UNITS(K1_UNITS),.POST_UNITS(POST_UNITS),.SRAM_SIZE(SRAM_SIZE)) core(
  .*,.start(core_start),.clear(clear || configuration_error),.busy(core_busy),.error(core_error));
endmodule
