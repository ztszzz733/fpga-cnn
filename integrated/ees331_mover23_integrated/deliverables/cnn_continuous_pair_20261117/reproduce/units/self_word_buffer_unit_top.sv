module self_word_buffer_unit_top #(parameter K3=1)(
 input logic optimized,clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,mac_fire,queue_full,
 output wire [31:0] addr,wdata,input_reads,weight_reads,mac_count,output wire [3:0] phase,
 input logic ready,response,input logic [31:0] rdata
);
 wire [1:0] bs,ds,es,vs,ws,by,mf,qf;wire [1:0][31:0] ad,wd,ir,wr,mc;wire [1:0][3:0] ph;
 assign busy=bs[optimized];assign done=ds[optimized];assign error=es[optimized];assign valid=vs[optimized];assign write=ws[optimized];
 assign byte_access=by[optimized];assign mac_fire=mf[optimized];assign addr=ad[optimized];assign wdata=wd[optimized];
 assign input_reads=ir[optimized];assign weight_reads=wr[optimized];assign mac_count=mc[optimized];assign phase=ph[optimized];assign queue_full=qf[optimized];
 for(genvar i=0;i<2;i++)begin
 if(K3)begin
 self_conv_spatial4_engine #(.READ_AHEAD(i)) engine(
 .clk,.rst_n,.clear(clear || optimized!=i),.start(start && optimized==i),.depthwise,
 .input_base,.weight_base,.output_base,.width,.height,.in_channels,.out_channels,.kernel,.stride,
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata,.mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 assign qf[i]=0;
 end else begin
 self_pw8_engine #(.READ_AHEAD(i)) engine(
 .clk,.rst_n,.clear(clear || optimized!=i),.start(start && optimized==i),.depthwise,
 .input_base,.weight_base,.output_base,.width,.height,.in_channels,.out_channels,.kernel,.stride,
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata,.mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 assign qf[i]=engine.state==7 && engine.q_count==8;
 end
 end
endmodule
