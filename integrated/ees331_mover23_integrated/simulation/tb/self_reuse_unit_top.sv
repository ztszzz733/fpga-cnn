module self_reuse_unit_top(
 input logic [1:0] optimized,
 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,mac_fire,queue_full,
 output wire [31:0] addr,wdata,input_reads,weight_reads,mac_count,
 output wire [3:0] phase,
 input logic ready,response,input logic [31:0] rdata
);
 wire [3:0] bs,ds,es,vs,ws,by,mf;
 wire [31:0] ad[4],wd[4],ir[4],wr[4],mc[4];wire [3:0] ph[4];
 assign busy=bs[optimized];assign done=ds[optimized];assign error=es[optimized];
 assign valid=vs[optimized];assign write=ws[optimized];assign byte_access=by[optimized];
 assign mac_fire=mf[optimized];assign addr=ad[optimized];assign wdata=wd[optimized];
 assign input_reads=ir[optimized];assign weight_reads=wr[optimized];assign mac_count=mc[optimized];assign phase=ph[optimized];
 assign queue_full=0;
 for(genvar i=0;i<4;i++)begin:engines
 self_conv_spatial4_engine #(.DW_CACHE(1),.READ_WORD_BUFFER(1),.INPUT_HALO_REUSE(i%2),.WEIGHT_LAYER_REUSE(i/2)) engine(
 .clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 end
endmodule
