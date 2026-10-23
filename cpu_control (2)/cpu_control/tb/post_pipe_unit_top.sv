module post_pipe_unit_top(
 input logic optimized,clk,rst_n,clear,start,mode_add,
 input logic [31:0] src_a,src_b,destination,parameter_base,count,channels,
 output wire busy,done,error,valid,write,byte_access,pipe_active,
 output wire [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
 wire [1:0] bs,ds,es,vs,ws,by;wire [31:0] ad[2],wd[2];
 assign busy=bs[optimized];assign done=ds[optimized];assign error=es[optimized];
 assign valid=vs[optimized];assign write=ws[optimized];assign byte_access=by[optimized];
 assign addr=ad[optimized];assign wdata=wd[optimized];
 quant_post_engine old_post(.clk(clk),.rst_n(rst_n),.clear(clear||optimized),.start(start&&!optimized),
  .mode_add(mode_add),.src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(bs[0]),.done(ds[0]),.error(es[0]),.valid(vs[0]),.write(ws[0]),.byte_access(by[0]),.addr(ad[0]),.wdata(wd[0]),.ready(ready&&!optimized),.response(response&&!optimized),.rdata(rdata));
 quant_post_pipe_engine new_post(.clk(clk),.rst_n(rst_n),.clear(clear||!optimized),.start(start&&optimized),
  .mode_add(mode_add),.src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(bs[1]),.done(ds[1]),.error(es[1]),.valid(vs[1]),.write(ws[1]),.byte_access(by[1]),.addr(ad[1]),.wdata(wd[1]),.ready(ready&&optimized),.response(response&&optimized),.rdata(rdata));
 assign pipe_active=|new_post.pv;
endmodule
