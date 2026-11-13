module self_optimized_unit_top #(parameter K3_TEST=0)(
 input logic optimized,clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,mac_fire,queue_full,
 output wire [31:0] addr,wdata,input_reads,weight_reads,mac_count,
 output wire [3:0] phase,
 input logic ready,response,input logic [31:0] rdata
);
 wire [1:0] bs,ds,es,vs,ws,by,mf;
 wire [31:0] ad[2],wd[2],ir[2],wr[2],mc[2];wire [3:0] ph[2];
 assign busy=bs[optimized];assign done=ds[optimized];assign error=es[optimized];
 assign valid=vs[optimized];assign write=ws[optimized];assign byte_access=by[optimized];
 assign mac_fire=mf[optimized];assign addr=ad[optimized];assign wdata=wd[optimized];
 assign input_reads=ir[optimized];assign weight_reads=wr[optimized];assign mac_count=mc[optimized];assign phase=ph[optimized];
 for(genvar i=0;i<2;i++)begin:engines
 if(K3_TEST && i==0) begin:self_conv_engine
 self_conv_engine engine(.clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 end
 else if(K3_TEST) begin:self_conv_pipe_engine
 self_conv_pipe_engine engine(.clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 end
 else if(i==0) begin:self_pw4_engine
 self_pw4_engine engine(.clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 end
 else begin:prefetch
 self_pw4_overlap_engine engine(.clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 assign queue_full=optimized && engine.q_count==8;
 end
 end
 if(K3_TEST)assign queue_full=0;
endmodule
