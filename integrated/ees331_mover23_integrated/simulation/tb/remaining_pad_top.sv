module remaining_pad_top(
input logic optimized,output wire [3:0] phase,
 input logic clk,rst_n,clear,start,
 input logic [31:0] source,destination,width,height,channels,
 input logic [7:0] zero_point,
 output wire busy,done,error,valid,write,byte_access,
 output wire [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
wire[1:0] bs,ds,es,vs,ws,by;wire[31:0]ad[2],wd[2];
assign busy=bs[optimized];
assign done=ds[optimized];
assign error=es[optimized];
assign valid=vs[optimized];
assign write=ws[optimized];
assign byte_access=by[optimized];
assign addr=ad[optimized];
assign wdata=wd[optimized];
baseline_pad_hwc_engine_remaining e0(.clk(clk),.rst_n(rst_n),.clear(clear || optimized!=0),.start(start && optimized==0),.source(source),.destination(destination),.width(width),.height(height),.channels(channels),.zero_point(zero_point),.busy(bs[0]),.done(ds[0]),.error(es[0]),.valid(vs[0]),.write(ws[0]),.byte_access(by[0]),.addr(ad[0]),.wdata(wd[0]),.ready(ready && optimized==0),.response(response && optimized==0),.rdata(rdata));
pad_hwc_engine e1(.clk(clk),.rst_n(rst_n),.clear(clear || optimized!=1),.start(start && optimized==1),.source(source),.destination(destination),.width(width),.height(height),.channels(channels),.zero_point(zero_point),.busy(bs[1]),.done(ds[1]),.error(es[1]),.valid(vs[1]),.write(ws[1]),.byte_access(by[1]),.addr(ad[1]),.wdata(wd[1]),.ready(ready && optimized==1),.response(response && optimized==1),.rdata(rdata));
assign phase=optimized?e1.state:e0.state;
endmodule
