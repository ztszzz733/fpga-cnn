module remaining_post_top(
 input logic optimized,clk,rst_n,clear,start,mode_add,
 input logic [31:0] src_a,src_b,destination,parameter_base,count,channels,
 output wire busy,done,error,valid,write,byte_access,pipe_active,
 output wire [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
 logic selected_add;
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)selected_add<=0;else if(clear)selected_add<=0;else if(start)selected_add<=mode_add;
 end
 wire selection_add=start?mode_add:selected_add;
 wire [1:0] selected=optimized?(selection_add?2'd2:2'd1):2'd0;
 wire [2:0] bs,ds,es,vs,ws,by;wire [31:0] ad[3],wd[3];
 assign busy=bs[selected];assign done=ds[selected];assign error=es[selected];
 assign valid=vs[selected];assign write=ws[selected];assign byte_access=by[selected];
 assign addr=ad[selected];assign wdata=wd[selected];
 baseline_quant_post_pipe_engine_remaining #(.GROUP_BYTES(16)) old_post(.clk(clk),.rst_n(rst_n),.clear(clear||optimized),.start(start&&!optimized),
  .mode_add(mode_add),.src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(bs[0]),.done(ds[0]),.error(es[0]),.valid(vs[0]),.write(ws[0]),.byte_access(by[0]),.addr(ad[0]),.wdata(wd[0]),.ready(ready&&!optimized),.response(response&&!optimized),.rdata(rdata));
 quant_post_pipe_engine #(.GROUP_BYTES(16)) new_post(.clk(clk),.rst_n(rst_n),.clear(clear||!optimized||selection_add),.start(start&&optimized&&!selection_add),
  .mode_add(1'b0),.src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(bs[1]),.done(ds[1]),.error(es[1]),.valid(vs[1]),.write(ws[1]),.byte_access(by[1]),.addr(ad[1]),.wdata(wd[1]),.ready(ready&&optimized&&!selection_add),.response(response&&optimized&&!selection_add),.rdata(rdata));
 quant_post_pipe_engine #(.GROUP_BYTES(32)) new_add(.clk(clk),.rst_n(rst_n),.clear(clear||!optimized||!selection_add),.start(start&&optimized&&selection_add),
  .mode_add(1'b1),.src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(bs[2]),.done(ds[2]),.error(es[2]),.valid(vs[2]),.write(ws[2]),.byte_access(by[2]),.addr(ad[2]),.wdata(wd[2]),.ready(ready&&optimized&&selection_add),.response(response&&optimized&&selection_add),.rdata(rdata));
 assign pipe_active=selection_add?(|new_add.pv):(|new_post.pv);
endmodule
