module resource_pair(input wire clk,rst_n,clear,start,request_stream,depthwise,post_add,
 input wire [1:0] consumer_count,
 input wire [31:0] input_base,weight_base,raw_base,output_base,parameter_base,src_b,
 input wire [31:0] width,height,in_channels,out_channels,stride,post_count,post_channels,
 output wire busy,done,error,stream_active,output wire [3:0] decision_reason,
 output wire [1:0] mem_valid,mem_write,mem_byte,output wire [63:0] mem_addr,mem_wdata,
 input wire [1:0] mem_ready,mem_response,input wire [63:0] mem_rdata);
conv_post_pair_engine #(.KERNEL(3),.MAX_CHANNELS(512),.FIFO_DEPTH(8)) dut(.*, .conv_work(),.post_work(),.raw_push(),.raw_pop(),.conv_finished(),.fifo_level(),.forwarded_count(),.conv_input_reads(),.conv_weight_reads(),.conv_mac_count());
endmodule
