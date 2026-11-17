module bank_benchmark_top(
 input logic optimized,clk,rst_n,clear,start,stall,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,in_channels,out_channels,kernel,stride,
 output wire busy,done,error,mac_fire,
 output wire [31:0] input_reads,weight_reads,mac_count,
 output wire [3:0] phase,
 output wire bank_idle,bank_fault,queue_stall,
 output wire [31:0] write_commands,write_completions,write_service_cycles,read_commands,write_commits,
 output wire commit_valid,output wire [31:0] commit_addr,commit_data,
 output wire debug_valid,debug_ready,debug_write,debug_byte,debug_response,
 output wire [31:0] debug_addr,debug_data,
 output wire debug_block_valid,debug_block_ready,debug_data_valid,debug_data_ready,debug_block_response,
 output wire [31:0] debug_block_base,debug_block_stride,debug_block_data,
 output wire [3:0] debug_block_words,
 input wire dma_valid,dma_write,input wire [31:0] dma_addr,dma_wdata,
 input wire [3:0] dma_wstrb,
 output wire dma_ready,dma_rsp_valid,dma_error,output wire [31:0] dma_rdata
);
 wire [1:0] bs,ds,es,mf,vs,rs,ws,by,resp,bi,bf,qs,cv;
 wire [1:0] bv,br,bdv,bdr,bresp,berr;
 wire [1:0][31:0] ir,wr,mc,ad,wd,rd,wc,wa,wt,rc,wcomm,ca,cd,bb,bst,bd;
 wire [1:0][3:0] ph,bn;
 wire [1:0] drdy,drsp,derr;wire [1:0][31:0] drdata;
 assign busy=bs[optimized];assign done=ds[optimized];assign error=es[optimized];assign mac_fire=mf[optimized];
 assign input_reads=ir[optimized];assign weight_reads=wr[optimized];assign mac_count=mc[optimized];assign phase=ph[optimized];
 assign bank_idle=bi[optimized];assign bank_fault=bf[optimized];assign queue_stall=qs[optimized];
 assign write_commands=wc[optimized];assign write_completions=wa[optimized];assign write_service_cycles=wt[optimized];
 assign read_commands=rc[optimized];assign write_commits=wcomm[optimized];
 assign commit_valid=cv[optimized];assign commit_addr=ca[optimized];assign commit_data=cd[optimized];
 assign debug_valid=vs[optimized];assign debug_ready=rs[optimized];assign debug_write=ws[optimized];
 assign debug_byte=by[optimized];assign debug_response=resp[optimized];assign debug_addr=ad[optimized];assign debug_data=wd[optimized];
 assign debug_block_valid=bv[optimized];assign debug_block_ready=br[optimized];
 assign debug_data_valid=bdv[optimized];assign debug_data_ready=bdr[optimized];assign debug_block_response=bresp[optimized];
 assign debug_block_base=bb[optimized];assign debug_block_stride=bst[optimized];assign debug_block_data=bd[optimized];assign debug_block_words=bn[optimized];
 assign dma_ready=drdy[optimized];assign dma_rsp_valid=drsp[optimized];assign dma_error=derr[optimized];assign dma_rdata=drdata[optimized];
 for(genvar i=0;i<2;i++)begin:variants
  if(i==0)begin:old
   self_pw8_engine #(.INPUT_WORD_FILL(0)) core(
    .clk,.rst_n,.clear(clear || optimized!=i),.start(start && optimized==i),.depthwise,
    .input_base,.weight_base,.output_base,.width,.height,.in_channels,.out_channels,.kernel,.stride,
    .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),
    .addr(ad[i]),.wdata(wd[i]),.ready(rs[i]),.response(resp[i]),.rdata(rd[i]),
    .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]));
   assign bv[i]=0;assign bdv[i]=0;assign bb[i]=0;assign bst[i]=0;assign bd[i]=0;assign bn[i]=0;
   assign qs[i]=core.state==7 && core.q_count==8;
  end else begin:new_core
   self_pw8_block_engine #(.INPUT_WORD_FILL(0),.BLOCK_OUTPUT(1)) core(
    .clk,.rst_n,.clear(clear || optimized!=i),.start(start && optimized==i),.depthwise,
    .input_base,.weight_base,.output_base,.width,.height,.in_channels,.out_channels,.kernel,.stride,
    .busy(bs[i]),.done(ds[i]),.error(es[i]),.valid(vs[i]),.write(ws[i]),.byte_access(by[i]),
    .addr(ad[i]),.wdata(wd[i]),.ready(rs[i]),.response(resp[i]),.rdata(rd[i]),
    .mac_fire(mf[i]),.phase(ph[i]),.input_reads(ir[i]),.weight_reads(wr[i]),.mac_count(mc[i]),
    .block_valid(bv[i]),.block_ready(br[i]),.block_base(bb[i]),.block_stride(bst[i]),.block_words(bn[i]),
    .block_data_valid(bdv[i]),.block_data_ready(bdr[i]),.block_data(bd[i]),
    .block_response(bresp[i]),.block_response_error(berr[i]));
   assign qs[i]=core.state==7 && core.q_count==8;
  end
  block_bank bank(
   .clk,.rst_n,.clear(clear || optimized!=i),.stall,
   .mem_valid(vs[i]),.mem_write(ws[i]),.mem_byte(by[i]),.mem_addr(ad[i]),.mem_wdata(wd[i]),
   .mem_ready(rs[i]),.mem_response(resp[i]),.mem_rdata(rd[i]),
   .block_valid(bv[i]),.block_ready(br[i]),.block_base(bb[i]),.block_stride(bst[i]),.block_words(bn[i]),
   .block_data_valid(bdv[i]),.block_data_ready(bdr[i]),.block_data(bd[i]),
   .block_response(bresp[i]),.block_response_error(berr[i]),.idle(bi[i]),.fault(bf[i]),
   .write_commands(wc[i]),.write_completions(wa[i]),.write_service_cycles(wt[i]),.read_commands(rc[i]),.write_commits(wcomm[i]),
   .commit_valid(cv[i]),.commit_addr(ca[i]),.commit_data(cd[i]),
   .dma_valid(dma_valid && optimized==i),.dma_write,.dma_addr,.dma_wdata,.dma_wstrb,
   .dma_ready(drdy[i]),.dma_rsp_valid(drsp[i]),.dma_error(derr[i]),.dma_rdata(drdata[i]));
 end
endmodule
