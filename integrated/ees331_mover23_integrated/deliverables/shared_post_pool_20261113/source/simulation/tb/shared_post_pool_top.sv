module shared_post_pool_top(
 input wire clk,rst_n,clear,input wire [9:0] unit_start,
 input wire [9:0][511:0] unit_command,input wire [1:0] post_enable,
 output wire [9:0] unit_busy,unit_done,unit_error,unit_work,
 output wire [9:0] mem_valid,mem_write,mem_byte,
 output wire [319:0] mem_addr,mem_wdata,input wire [9:0] mem_ready,mem_response,input wire [319:0] mem_rdata,
 output wire [7:0] waiting,stream_jobs,output wire [1:0] owned,fifo_push,fifo_pop,post_retire,final_write_ack,
 output wire [1:0][2:0] owner_id,output wire [1:0][3:0] fifo_level
);
 conv_post_shared_pool pool(.*,.conv_input_reads(),.conv_weight_reads(),.conv_mac_count());
endmodule
