`timescale 1ns/1ps
module tb_mobilefacenet_chain;
 localparam SIZE=262144;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,conv_start=0,post_start=0,mode_add=0;
 logic [31:0] config_address=0,src_a=0,src_b=0,destination=0,parameter_base=0,count=0,channels=0;
 wire cbusy,cdone,cerror,pbusy,pdone,perror,core_busy,memory_idle;
 wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response,mem_ready;
 wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
 wire memory_fault,cnn_cancel=clear;
 integer cycles=0,job=0,stall=0,last_progress=0;
 wire allow_request=stall==0 || cycles%7!=3;
 neureka_conv_engine convolution(
  .clk(clk),.rst_n(rst_n),.clear(clear),.start(conv_start),.config_address(config_address),
  .busy(cbusy),.done(cdone),.error(cerror),.cfg_valid(cnn_valid[9]),.cfg_addr(cnn_addr[288+:32]),
  .cfg_ready(cnn_ready[9]),.cfg_response(cnn_response[9]),.cfg_rdata(cnn_rdata[288+:32]),
  .valid(cnn_valid[8:0]),.write(cnn_write[8:0]),.byte_access(cnn_byte[8:0]),
  .addr(cnn_addr[0+:288]),.wdata(cnn_wdata[0+:288]),.ready(cnn_ready[8:0]),
  .response(cnn_response[8:0]),.rdata(cnn_rdata[0+:288]),.core_busy(core_busy),.memory_idle(memory_idle));
 assign cnn_write[9]=0;assign cnn_byte[9]=0;assign cnn_wdata[288+:32]=0;
 quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(clear),.start(post_start),.mode_add(mode_add),
  .src_a(src_a),.src_b(src_b),.destination(destination),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(pbusy),.done(pdone),.error(perror),.valid(cnn_valid[10]),.write(cnn_write[10]),.byte_access(cnn_byte[10]),
  .addr(cnn_addr[320+:32]),.wdata(cnn_wdata[320+:32]),.ready(cnn_ready[10]),.response(cnn_response[10]),.rdata(cnn_rdata[320+:32]));
 assign cnn_ready=mem_ready & {11{allow_request}};
 datasram_banked #(.SRAM_SIZE(SIZE),.BANKS(4)) mem(
  .clk(clk),.rst_n(rst_n),.cnn_cancel(cnn_cancel),.cnn_valid(cnn_valid & {11{allow_request}}),.cnn_write(cnn_write),.cnn_byte(cnn_byte),
  .cnn_addr(cnn_addr),.cnn_wdata(cnn_wdata),.cnn_ready(mem_ready),.cnn_response(cnn_response),.cnn_rdata(cnn_rdata),.cnn_mem_fault(memory_fault),
  .dmem_addr(32'b0),.dmem_wdata(32'b0),.dmem_wstrb(4'b0),.dmem_re(1'b0),.dmem_we(1'b0),.dmem_rdata(),
  .io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'b0),.io_mem_wdata(32'b0),.io_mem_be(4'b0),.io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error());
 reg [31:0] meta[0:0],jobs[0:319];
 reg [7:0] initial_mem[0:SIZE-1],golden[0:SIZE-1];
 bit mutable_byte[0:SIZE-1];
 integer events,wave,metrics,checked=0;
 logic expect_error=0;
 wire [5:0] core_state=convolution.core.i_ctrl.i_ctrl_fsm.state_q;
 wire prefetch_done=convolution.core.i_ctrl.i_ctrl_fsm.prefetch_done_d;
 wire accum_done=convolution.core.i_ctrl.i_ctrl_fsm.accum_done_d;
 wire conv_read_fire=|(cnn_valid[8:0]&cnn_ready[8:0]&~cnn_write[8:0]);
 wire conv_write_fire=|(cnn_valid[8:0]&cnn_ready[8:0]&cnn_write[8:0]);
 wire post_read_fire=cnn_valid[10]&cnn_ready[10]&~cnn_write[10];
 wire post_write_fire=cnn_valid[10]&cnn_ready[10]&cnn_write[10];
 function automatic [7:0] peek(input integer a);
  return mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8];
 endfunction
 initial begin:driver
  integer fd,n,a,len;
  n=$value$plusargs("stall=%d",stall);
  $readmemh("meta.hex",meta);$readmemh("jobs.hex",jobs,0,meta[0]*10-1);
  fd=$fopen("memory.bin","rb");n=$fread(initial_mem,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"bad memory");
  fd=$fopen("golden.bin","rb");n=$fread(golden,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"bad golden");
  #1;for(integer i=0;i<SIZE;i++) mem.mem[(i/4)%4][(i/4)/4][(i%4)*8+:8]=initial_mem[i];
  for(integer j=0;j<meta[0];j++) for(integer b=0;b<jobs[j*10+9];b++) mutable_byte[jobs[j*10+8]+b]=1;
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,job,checked_bytes\n");
  repeat(6) @(negedge clk);rst_n=1;
  for(job=0;job<meta[0];job++) begin
   @(negedge clk);$fwrite(events,"%0d,start,%0d,0\n",cycles,job);$fflush(events);
   if(jobs[job*10]==0) begin
    config_address=jobs[job*10+1];conv_start=1;@(negedge clk);conv_start=0;wait(cdone);
    if(!memory_idle || convolution.tcdm.req)$fatal(1,"early convolution completion");
   end else begin
    mode_add=jobs[job*10]==2;src_a=jobs[job*10+2];src_b=jobs[job*10+3];destination=jobs[job*10+4];
    parameter_base=jobs[job*10+5];count=jobs[job*10+6];channels=jobs[job*10+7];
    post_start=1;@(negedge clk);post_start=0;wait(pdone);
   end
   @(negedge clk);a=jobs[job*10+8];len=jobs[job*10+9];
   for(integer b=0;b<len;b++) if(peek(a+b)!==golden[a+b])
    $fatal(1,"mismatch job=%0d addr=%h byte=%0d got=%h expected=%h",job,a+b,b,peek(a+b),golden[a+b]);
   checked=checked+len;$fwrite(events,"%0d,done,%0d,%0d\n",cycles,job,len);$fflush(events);
  end
  for(integer i=0;i<SIZE;i++) if(!mutable_byte[i] && peek(i)!==initial_mem[i])$fatal(1,"immutable/guard modified %h",i);
  // Invalid descriptor must fail without writing. clear aborts parameter load.
  @(negedge clk);expect_error=1;channels=0;post_start=1;
  @(negedge clk);post_start=0;if(!perror)$fatal(1,"invalid channels not rejected");
  @(negedge clk);expect_error=0;channels=4;post_start=1;
  @(negedge clk);post_start=0;repeat(5)@(negedge clk);clear=1;
  @(negedge clk);if(pbusy || cnn_valid!=0)$fatal(1,"clear did not abort");clear=0;
  repeat(5)@(negedge clk);
  metrics=$fopen("metrics.json","w");$fwrite(metrics,"{\"cycles\":%0d,\"jobs\":%0d,\"checked_bytes\":%0d,\"stall\":%0d}\n",cycles,meta[0],checked,stall);$fclose(metrics);
  $fclose(events);$fclose(wave);$display("PASS tb_mobilefacenet_chain cycles=%0d checked=%0d",cycles,checked);$finish;
 end
 `include "chain_monitor.svh"
 always @(posedge clk) if(rst_n) begin
  cycles++;
  if(cerror || memory_fault || (perror && !expect_error))$fatal(1,"engine error job=%0d",job);
  if(|(cnn_valid&cnn_ready) || cdone || pdone)last_progress=cycles;
  if(cycles-last_progress>12000 || cycles>400000)
   $fatal(1,"watchdog job=%0d state=%0d accum_done=%b prefetch_done=%b",job,core_state,accum_done,prefetch_done);
 end
endmodule
