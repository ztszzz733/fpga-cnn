module resource_k3 #(parameter integer READ_WORD_BUFFER=0)(

 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,
 input logic [31:0] width,height,in_channels,out_channels,stride,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,
 input logic [31:0] rdata,
 output wire mac_fire,
 output wire [3:0] phase,
 output logic [31:0] input_reads,weight_reads,mac_count
);
self_conv_spatial4_engine #(.MAX_CHANNELS(512),.MAX_KERNEL(3),.TILE(2),.DW_CACHE(1),.READ_WORD_BUFFER(1),.INPUT_HALO_REUSE(READ_WORD_BUFFER),.WEIGHT_LAYER_REUSE(READ_WORD_BUFFER)) dut(.*, .kernel(32'd3));
endmodule
