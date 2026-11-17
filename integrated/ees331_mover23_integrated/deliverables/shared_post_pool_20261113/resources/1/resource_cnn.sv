module resource_cnn #(parameter FRAME_CONTEXTS=4,FW=2,STEPS=256,LW=8,IW=10,K3_UNITS=2,K1_UNITS=6,POST_UNITS=2,UNITS=12)(

 input logic clk,rst_n,
 input logic [31:0] cnn_mmio_addr,cnn_mmio_wdata,
 input logic cnn_mmio_re,cnn_mmio_we,
 output logic [31:0] cnn_mmio_rdata,output wire cnn_mmio_ready,
 output wire [UNITS-1:0] cnn_valid,cnn_write,cnn_byte,
 output wire [UNITS*32-1:0] cnn_addr,cnn_wdata,
 input logic [UNITS-1:0] cnn_ready,cnn_response,
 input logic [UNITS*32-1:0] cnn_rdata,
 output wire cnn_cancel,input logic cnn_mem_fault,
 output wire busy,done,error,
 output wire [UNITS-1:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work,
 output wire [UNITS-1:0][IW-1:0] unit_node,
 output wire [IW:0] completed_count
);
cnn_ees331 #(.FRAME_CONTEXTS(4),.K3_UNITS(2),.K1_UNITS(6),.POST_UNITS(2),.LATEST_OPERATORS(1),.ENABLE_DW7(0),.SHARED_POST_STREAM(1)) dut(.*);
endmodule
