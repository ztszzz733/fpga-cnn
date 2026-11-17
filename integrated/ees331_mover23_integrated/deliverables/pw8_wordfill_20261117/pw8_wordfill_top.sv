module pw8_wordfill_top(
 input logic [2:0] optimized,
 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,mac_fire,queue_full,input_fill_busy,input_write_fire,
 output wire [31:0] addr,wdata,input_reads,weight_reads,mac_count,
 output wire [3:0] phase,
 input logic ready,response,input logic [31:0] rdata
);
 wire [4:0] bs,ds,es,vs,ws,by,mf,fb,fw;
 assign input_fill_busy=fb[optimized];assign input_write_fire=fw[optimized];
 wire [31:0] ad[5],wd[5],ir[5],wr[5],mc[5];wire [3:0] ph[5];
 assign busy=bs[optimized];assign done=ds[optimized];assign error=es[optimized];
 assign valid=vs[optimized];assign write=ws[optimized];assign byte_access=by[optimized];
 assign mac_fire=mf[optimized];assign addr=ad[optimized];assign wdata=wd[optimized];
 assign input_reads=ir[optimized];assign weight_reads=wr[optimized];assign mac_count=mc[optimized];assign phase=ph[optimized];
 assign queue_full=optimized && engines[1].tuned.engine.q_count==8;
 for(genvar i=0;i<5;i++)begin:engines
 if(i==0 || i==3)begin:baseline
 baseline_pw8_wordfill #(.LINEAR_GROUPS(i!=3)) engine(
 .clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 assign fb[i]=engine.input_fill_left!=0 || engine.prefetch_valid;
 assign fw[i]=engine.input_fill_left!=0;
 end else begin:tuned
 self_pw8_engine #(.OUTPUT_PAR(2),.LINEAR_GROUPS(i!=4),.INPUT_WORD_FILL(i!=2)) engine(
 .clk(clk),.rst_n(rst_n),.clear(clear || optimized!=i),.start(start && optimized==i),
 .depthwise(depthwise),.input_base(input_base),.weight_base(weight_base),.output_base(output_base),
 .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.kernel(kernel),.stride(stride),
 .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),.addr(ad[i]),.wdata(wd[i]),
 .ready(ready && optimized==i),.response(response && optimized==i),.rdata(rdata),
 .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
 assign fb[i]=engine.word_fill_mode ? engine.word_ready!=0 : (engine.input_fill_left!=0 || engine.prefetch_valid);
 assign fw[i]=engine.word_fill_mode ? engine.word_commit : engine.input_fill_left!=0;
 end
 end
endmodule
