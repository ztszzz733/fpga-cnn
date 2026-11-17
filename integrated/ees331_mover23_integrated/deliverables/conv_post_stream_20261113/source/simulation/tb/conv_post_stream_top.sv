module conv_post_stream_top(
 input logic clk,rst_n,clear,start,k1,request_stream,depthwise,post_add,
 input logic [1:0] consumer_count,
 input logic [31:0] input_base,weight_base,raw_base,output_base,parameter_base,src_b,
 input logic [31:0] width,height,in_channels,out_channels,stride,post_count,post_channels,
 output wire busy,done,error,stream_active,
 output wire [3:0] decision_reason,
 output wire [1:0] mem_valid,mem_write,mem_byte,
 output wire [63:0] mem_addr,mem_wdata,
 input logic [1:0] mem_ready,mem_response,input logic [63:0] mem_rdata,
 output wire conv_work,post_work,raw_push,raw_pop,conv_finished,
 output wire [3:0] fifo_level,
 output wire [31:0] forwarded_count,conv_input_reads,conv_weight_reads,conv_mac_count
);
 wire [1:0] bs,ds,es,acts,cws,pws,pushs,pops,cfs;
 wire [3:0] reasons[2],levels[2];wire [31:0] forwarded[2],irs[2],wrs[2],mcs[2];
 wire [1:0] vs[2],ws[2],bys[2];wire [63:0] ads[2],wds[2];
 assign busy=bs[k1];assign done=ds[k1];assign error=es[k1];assign stream_active=acts[k1];
 assign decision_reason=reasons[k1];assign mem_valid=vs[k1];assign mem_write=ws[k1];assign mem_byte=bys[k1];
 assign mem_addr=ads[k1];assign mem_wdata=wds[k1];assign conv_work=cws[k1];assign post_work=pws[k1];
 assign raw_push=pushs[k1];assign raw_pop=pops[k1];assign conv_finished=cfs[k1];assign fifo_level=levels[k1];
 assign forwarded_count=forwarded[k1];assign conv_input_reads=irs[k1];assign conv_weight_reads=wrs[k1];assign conv_mac_count=mcs[k1];
 for(genvar i=0;i<2;i++)begin:pairs
  conv_post_pair_engine #(.KERNEL(i==1?1:3)) pair_engine(
   .clk(clk),.rst_n(rst_n),.clear(clear || k1!=i),.start(start && k1==i),
   .request_stream(request_stream),.depthwise(depthwise),.post_add(post_add),.consumer_count(consumer_count),
   .input_base(input_base),.weight_base(weight_base),.raw_base(raw_base),.output_base(output_base),.parameter_base(parameter_base),.src_b(src_b),
   .width(width),.height(height),.in_channels(in_channels),.out_channels(out_channels),.stride(stride),.post_count(post_count),.post_channels(post_channels),
   .busy(bs[i]),.done(ds[i]),.error(es[i]),.stream_active(acts[i]),.decision_reason(reasons[i]),
   .mem_valid(vs[i]),.mem_write(ws[i]),.mem_byte(bys[i]),.mem_addr(ads[i]),.mem_wdata(wds[i]),
   .mem_ready(k1==i?mem_ready:2'b0),.mem_response(k1==i?mem_response:2'b0),.mem_rdata(mem_rdata),
   .conv_work(cws[i]),.post_work(pws[i]),.raw_push(pushs[i]),.raw_pop(pops[i]),.conv_finished(cfs[i]),
   .fifo_level(levels[i]),.forwarded_count(forwarded[i]),.conv_input_reads(irs[i]),.conv_weight_reads(wrs[i]),.conv_mac_count(mcs[i]));
 end
endmodule
