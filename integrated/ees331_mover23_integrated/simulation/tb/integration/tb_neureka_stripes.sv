`timescale 1ns/1ps
module tb_neureka_stripes;
 localparam SRAM_BYTES=65536;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,overlap_enable=1;
 logic tile_valid=0,tile_slot=0,tile_last=0;
 logic [31:0] tile_config=0;
 logic [255:0] tile_relu_descriptor=0;
 wire tile_ready,busy,done,error,memory_fault;
 wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
 wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
 wire cnn_cancel,conv_start,post_start,conv_done,post_done,core_busy;
 wire [31:0] conv_tile,post_tile,accepted_tiles,completed_tiles;
 wire [5:0] slot_states;
 logic io_mem_req=0;wire io_mem_we=1;
 logic [31:0] io_mem_addr=0,io_mem_wdata=0;logic [3:0] io_mem_be=0;
 wire io_mem_gnt,io_mem_rvalid,io_mem_error;wire [31:0] io_mem_rdata;
 neureka_stripe_pipeline dut(.*);
 datasram_banked #(.SRAM_SIZE(SRAM_BYTES),.BANKS(4)) mem(
  .dmem_addr(32'b0),.dmem_wdata(32'b0),.dmem_wstrb(4'b0),.dmem_re(1'b0),.dmem_we(1'b0),.dmem_rdata(),
  .cnn_mem_fault(memory_fault),.*);
 reg [31:0] meta[0:10],jobs[0:191];
 reg [7:0] initial_mem[0:SRAM_BYTES-1],source_mem[0:SRAM_BYTES-1];
 reg [7:0] conv_gold[0:SRAM_BYTES-1],relu_gold[0:SRAM_BYTES-1];
 logic input_active=0,pixel_eof=0;
 integer input_frame=0,input_bytes=0,stall=0;
 integer cycles=0,overlap_cycles=0,input_overlap_cycles=0,input_write_compute_cycles=0;
 integer conv_checked=0,post_checked=0,first_compute=-1,first_eof=-1,backpressure_cycles=0;
 integer conv_writes=0,post_writes=0,events,metrics;
 logic verification_enabled=0;
 logic [11:0] conv_finished=0,post_finished=0;
 wire [5:0] core_state=dut.convolution.core.i_ctrl.i_ctrl_fsm.state_q;
 // MATRIXVEC is the real compute phase, but not a claim that every PE fires.
 wire compute_active=core_busy && core_state==4;
 wire post_busy=dut.pbusy;
 wire input_write_fire=io_mem_req && io_mem_gnt;
 wire conv_read_fire=|(cnn_valid[8:0] & cnn_ready[8:0] & ~cnn_write[8:0]);
 wire conv_write_fire=|(cnn_valid[8:0] & cnn_ready[8:0] & cnn_write[8:0]);
 wire post_read_fire=cnn_valid[10] && cnn_ready[10] && !cnn_write[10];
 wire post_write_fire=cnn_valid[10] && cnn_ready[10] && cnn_write[10];
 wire [31:0] post_addr=cnn_addr[320+:32];
 wire compute_post_overlap=compute_active && post_busy;
 wire input_compute_overlap=compute_active && input_active;
 `include "stripe_monitor.svh"

 function automatic [7:0] peek(input integer a);
  return mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8];
 endfunction
 task automatic initialize_memory;
  for(integer a=0;a<SRAM_BYTES;a++) mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8]=initial_mem[a];
 endtask
 task automatic send_job(input integer j);
  integer frame,target,a;
  begin
   frame=jobs[j*16+3];target=jobs[j*16+2];
   if(input_frame!=frame) begin input_frame=frame;input_bytes=0;end
   while(input_bytes<target) begin
    a=meta[4]+frame*meta[5]+input_bytes;
    @(negedge clk);
    io_mem_req=1;io_mem_addr=a&32'hfffffffc;
    io_mem_be=4'b1<<(a%4);io_mem_wdata={24'b0,source_mem[a]}<<(8*(a%4));
    do @(posedge clk);while(!io_mem_gnt);
    @(negedge clk);io_mem_req=0;input_bytes=input_bytes+1;
    // Deterministic variable input gaps; no UART baud emulation.
    repeat(12+(stall==0 ? 0:(input_bytes*7)%stall)) @(negedge clk);
   end
   if(input_bytes==meta[0]*meta[1]*meta[2]) begin
    pixel_eof=1;@(negedge clk);pixel_eof=0;
   end
   tile_slot=1'(jobs[j*16+1]);tile_config=jobs[j*16];tile_last=j+1==meta[9];
   for(integer k=0;k<8;k++) tile_relu_descriptor[k*32+:32]=jobs[j*16+8+k];
   tile_valid=1;
   do @(posedge clk);while(!tile_ready);
   @(negedge clk);tile_valid=0;
  end
 endtask
 initial begin:driver
  integer fd,n;
  overlap_enable=!$test$plusargs("serial");
  n=$value$plusargs("stall=%d",stall);
  $readmemh("meta.hex",meta);
  $readmemh("jobs.hex",jobs,0,meta[9]*16-1);
  $readmemh("conv.hex",conv_gold);$readmemh("relu.hex",relu_gold);
  fd=$fopen("memory.bin","rb");n=$fread(initial_mem,fd);$fclose(fd);
  if(n!=SRAM_BYTES) $fatal(1,"bad init image");
  fd=$fopen("source.bin","rb");n=$fread(source_mem,fd);$fclose(fd);
  if(n!=SRAM_BYTES) $fatal(1,"bad pixel image");
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,tile\n");
  #1;initialize_memory();
  repeat(6) @(negedge clk);rst_n=1;input_active=1;
  if($test$plusargs("restart")) begin
   send_job(0);
   wait(core_busy);repeat(20) @(negedge clk);
   clear=1;repeat(3) @(negedge clk);
   if(cnn_valid!=0 || busy || done) $fatal(1,"clear failed to abort pipeline");
   rst_n=0;clear=0;input_active=0;input_bytes=0;input_frame=0;
   repeat(4) @(negedge clk);initialize_memory();rst_n=1;input_active=1;
  end
  verification_enabled=1;
  for(integer j=0;j<meta[9];j++) send_job(j);
  input_active=0;
  wait(done);repeat(2) @(negedge clk);
  if(conv_checked!=meta[9] || post_checked!=meta[9]) $fatal(1,"lost or duplicate jobs");
  if(first_compute<0 || first_eof<0 || first_compute>=first_eof)
   $fatal(1,"first frame did not start compute before EOF compute=%0d EOF=%0d",first_compute,first_eof);
  if(overlap_enable && overlap_cycles==0) $fatal(1,"no real compute/ReLU overlap");
  if(!overlap_enable && overlap_cycles!=0) $fatal(1,"serial mode overlapped");
  if(input_write_compute_cycles==0) $fatal(1,"no input writes during compute phase");
  for(integer f=0;f<meta[8];f++) begin
   for(integer b=0;b<meta[10];b++)
    if(peek(meta[6]+f*meta[7]+b)!==relu_gold[meta[6]+f*meta[7]+b]) $fatal(1,"final output mismatch");
   for(integer b=0;b<32;b++) begin
    if(peek(meta[6]+f*meta[7]-1-b)!==8'ha5 || peek(meta[6]+f*meta[7]+meta[10]+b)!==8'ha5)
      $fatal(1,"output guard corrupted");
   end
   for(integer b=0;b<meta[0]*meta[1]*meta[2];b++)
    if(peek(meta[4]+f*meta[5]+b)!==source_mem[meta[4]+f*meta[5]+b]) $fatal(1,"input corrupted");
  end
  for(integer s=0;s<2;s++) for(integer b=0;b<32;b++)
   if(peek(32'h2000+s*32'h800-1-b)!==8'ha5 ||
      peek(32'h2000+s*32'h800+4*(meta[1]-2)*meta[3]+b)!==8'ha5) $fatal(1,"scratch guard corrupted");
  if(tile_ready) $fatal(1,"accepted submission after last tile");
  metrics=$fopen("metrics.json","w");
  $fwrite(metrics,"{\"cycles\":%0d,\"tiles\":%0d,\"frames\":%0d,\"checked_output_bytes\":%0d,",cycles,post_checked,meta[8],meta[8]*meta[10]);
  $fwrite(metrics,"\"compute_post_overlap_cycles\":%0d,\"input_compute_overlap_cycles\":%0d,",overlap_cycles,input_overlap_cycles);
  $fwrite(metrics,"\"input_write_compute_cycles\":%0d,\"slot_backpressure_cycles\":%0d,",input_write_compute_cycles,backpressure_cycles);
  $fwrite(metrics,"\"first_compute_cycle\":%0d,\"first_frame_eof_cycle\":%0d,",first_compute,first_eof);
  $fwrite(metrics,"\"conv_write_cycles\":%0d,\"relu_write_cycles\":%0d}\n",conv_writes,post_writes);
  $fclose(metrics);$fclose(events);$fclose(wave_fd);
  $display("PASS tb_neureka_stripes cycles=%0d tiles=%0d overlap=%0d",cycles,post_checked,overlap_cycles);$finish;
 end
 always @(posedge clk) begin:checks
  integer j,a,n;
  if(!rst_n) begin
   cycles=0;overlap_cycles=0;input_overlap_cycles=0;input_write_compute_cycles=0;backpressure_cycles=0;
   conv_checked=0;post_checked=0;conv_finished=0;post_finished=0;first_compute=-1;first_eof=-1;
   conv_writes=0;post_writes=0;
  end else if(verification_enabled) begin
   cycles++;
   if(error || memory_fault || io_mem_error) $fatal(1,"pipeline/memory fault");
   if(compute_active && first_compute<0) first_compute=cycles;
   if(pixel_eof && first_eof<0) first_eof=cycles;
   if(pixel_eof) $fwrite(events,"%0d,input_eof,%0d\n",cycles,input_frame);
   if(compute_post_overlap) overlap_cycles++;
   if(input_compute_overlap) input_overlap_cycles++;
   if(compute_active && input_write_fire) input_write_compute_cycles++;
   if(tile_valid && !tile_ready) backpressure_cycles++;
   if(conv_write_fire) conv_writes++;
   if(post_write_fire) post_writes++;
   if(tile_valid && tile_ready) $fwrite(events,"%0d,submit,%0d\n",cycles,accepted_tiles);
   if(conv_start) $fwrite(events,"%0d,conv_start,%0d\n",cycles,conv_tile);
   if(post_start) begin
    if(!conv_finished[post_tile]) $fatal(1,"activation before producer completion");
    $fwrite(events,"%0d,relu_start,%0d\n",cycles,post_tile);
   end
   if(conv_done) begin
    if(dut.convolution.tcdm.req || !dut.convolution.memory_idle)
      $fatal(1,"completion while HCI write still outstanding");
    j=conv_tile;if(conv_finished[j]) $fatal(1,"duplicate conv completion");
    a=jobs[j*16+4];n=jobs[j*16+5];
    for(integer b=0;b<n;b++) if(peek(a+b)!==conv_gold[jobs[j*16+6]+b])
     $fatal(1,"conv tile=%0d byte=%0d got=%0d expected=%0d",j,b,$signed(peek(a+b)),$signed(conv_gold[jobs[j*16+6]+b]));
    conv_finished[j]=1;conv_checked++;
    $fwrite(events,"%0d,conv_done,%0d\n",cycles,j);
   end
   if(post_done) begin
    j=post_tile;if(post_finished[j]) $fatal(1,"duplicate ReLU completion");
    a=jobs[j*16+6];n=jobs[j*16+5];
    for(integer b=0;b<n;b++) if(peek(a+b)!==relu_gold[a+b]) $fatal(1,"ReLU mismatch tile=%0d byte=%0d",j,b);
    post_finished[j]=1;post_checked++;
    $fwrite(events,"%0d,relu_done,%0d\n",cycles,j);
   end
   if(cycles>200000) $fatal(1,"bounded small test timeout");
  end
 end
endmodule
