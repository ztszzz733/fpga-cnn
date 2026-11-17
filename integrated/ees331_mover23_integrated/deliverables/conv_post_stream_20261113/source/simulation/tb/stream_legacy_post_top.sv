module stream_legacy_post_top(
 input logic optimized,clk,rst_n,clear,start,mode_add,
 input logic [31:0] src_a,src_b,destination,parameter_base,count,channels,
 output wire busy,done,error,valid,write,byte_access,pipe_active,
 output wire [31:0] addr,wdata,input logic ready,response,input logic [31:0] rdata
);
 logic selected_add;
 always_ff @(posedge clk or negedge rst_n)if(!rst_n)selected_add<=0;else if(clear)selected_add<=0;else if(start)selected_add<=mode_add;
 wire selection_add=start?mode_add:selected_add;
 wire [1:0] selected={optimized,selection_add};
 wire [3:0] bs,ds,es,vs,ws,by;wire [31:0] ad[4],wd[4];
 assign busy=bs[selected];assign done=ds[selected];assign error=es[selected];assign valid=vs[selected];
 assign write=ws[selected];assign byte_access=by[selected];assign addr=ad[selected];assign wdata=wd[selected];
 assign pipe_active=selection_add?(|units[3].newer.engine.pv):(|units[2].newer.engine.pv);
 for(genvar i=0;i<4;i++)begin:units
 if(i<2)begin:older
 stream_legacy_post_frozen #(.GROUP_BYTES(i%2?32:16)) engine(
 .clk(clk),.rst_n(rst_n),.clear(clear||selected!=i),.start(start&&selected==i),.mode_add(i%2==1),
 .src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready&&selected==i),.response(response&&selected==i),.rdata(rdata));
 end else begin:newer
 quant_post_pipe_engine #(.GROUP_BYTES(i%2?32:16)) engine(
 .clk(clk),.rst_n(rst_n),.clear(clear||selected!=i),.start(start&&selected==i),.mode_add(i%2==1),
 .src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready&&selected==i),.response(response&&selected==i),.rdata(rdata),
 .stream_mode(1'b0),.s_valid(1'b0),.s_data(32'b0),.s_index(32'b0),.s_channel(32'b0),.s_ready(),.stream_work());
 end
 end
endmodule
