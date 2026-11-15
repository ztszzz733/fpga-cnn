module self_pw4_unit_top(
 input logic optimized,
 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,
 input logic [31:0] in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,
 output wire [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata,
 output wire mac_fire,output wire [3:0] phase,
 output wire [31:0] input_reads,weight_reads,mac_count
);
 wire busy_old, busy_new;
 assign busy=optimized?busy_new:busy_old;
 wire done_old, done_new;
 assign done=optimized?done_new:done_old;
 wire error_old, error_new;
 assign error=optimized?error_new:error_old;
 wire valid_old, valid_new;
 assign valid=optimized?valid_new:valid_old;
 wire write_old, write_new;
 assign write=optimized?write_new:write_old;
 wire byte_access_old, byte_access_new;
 assign byte_access=optimized?byte_access_new:byte_access_old;
 wire [31:0] addr_old, addr_new;
 assign addr=optimized?addr_new:addr_old;
 wire [31:0] wdata_old, wdata_new;
 assign wdata=optimized?wdata_new:wdata_old;
 wire mac_fire_old, mac_fire_new;
 assign mac_fire=optimized?mac_fire_new:mac_fire_old;
 wire [3:0] phase_old, phase_new;
 assign phase=optimized?phase_new:phase_old;
 wire [31:0] input_reads_old, input_reads_new;
 assign input_reads=optimized?input_reads_new:input_reads_old;
 wire [31:0] weight_reads_old, weight_reads_new;
 assign weight_reads=optimized?weight_reads_new:weight_reads_old;
 wire [31:0] mac_count_old, mac_count_new;
 assign mac_count=optimized?mac_count_new:mac_count_old;
self_conv_engine #(.MAX_KERNEL(1)) engine_old(
.clk(clk),.rst_n(rst_n),.depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),.width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),.rdata(rdata),
.clear(clear || !(!optimized)),.start(start && (!optimized)),.ready(ready && (!optimized)),.response(response && (!optimized)),
.busy(busy_old),.done(done_old),.error(error_old),.valid(valid_old),.write(write_old),.byte_access(byte_access_old),.addr(addr_old),.wdata(wdata_old),.mac_fire(mac_fire_old),.phase(phase_old),.input_reads(input_reads_old),.weight_reads(weight_reads_old),.mac_count(mac_count_old));
self_pw4_engine #() engine_new(
.clk(clk),.rst_n(rst_n),.depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),.width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),.rdata(rdata),
.clear(clear || !(optimized)),.start(start && (optimized)),.ready(ready && (optimized)),.response(response && (optimized)),
.busy(busy_new),.done(done_new),.error(error_new),.valid(valid_new),.write(write_new),.byte_access(byte_access_new),.addr(addr_new),.wdata(wdata_new),.mac_fire(mac_fire_new),.phase(phase_new),.input_reads(input_reads_new),.weight_reads(weight_reads_new),.mac_count(mac_count_new));
endmodule
