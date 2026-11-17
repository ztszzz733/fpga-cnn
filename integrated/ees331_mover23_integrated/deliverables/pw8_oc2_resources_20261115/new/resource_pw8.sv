module resource_pw8(

 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,
 input logic [31:0] in_channels,out_channels,stride,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata,
 output wire mac_fire,output wire [3:0] phase,
 output logic [31:0] input_reads,weight_reads,mac_count
);
self_pw8_engine #(.MAX_CHANNELS(512)) dut(.*, .kernel(32'd1));
endmodule
