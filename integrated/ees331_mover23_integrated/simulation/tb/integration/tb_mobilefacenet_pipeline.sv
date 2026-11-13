`timescale 1ns/1ps
module tb_mobilefacenet_pipeline;
 localparam SIZE=262144;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0,overlap_enable=1;
 logic [5:0] task_count;
 logic program_valid=0;logic [4:0] program_index=0;
 logic [31:0] program_deps,program_config,program_params,program_dst,program_elements,program_channels,program_tag;
 logic [1:0] program_layer;
 wire program_ready,busy,done,error,memory_fault,cnn_cancel;
 wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response,mem_ready;
 wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
 wire conv_start,post_start,conv_tile_done,post_done,core_busy,conv_slot,post_slot;
 wire [4:0] conv_node,post_node;
 wire [31:0] conv_tag,post_tag,completed_mask;
 wire [5:0] slot_states;
 integer cycles=0,stall=0,last_progress=0;
 wire allow_request=stall==0 || (cycles%11!=3 && cycles%11!=4);
 quant_stripe_scheduler dut(.*);
 assign cnn_ready=mem_ready & {11{allow_request}};
 datasram_banked #(.SRAM_SIZE(SIZE),.BANKS(4)) mem(
  .clk(clk),.rst_n(rst_n),.cnn_cancel(cnn_cancel),.cnn_valid(cnn_valid & {11{allow_request}}),.cnn_write(cnn_write),.cnn_byte(cnn_byte),
  .cnn_addr(cnn_addr),.cnn_wdata(cnn_wdata),.cnn_ready(mem_ready),.cnn_response(cnn_response),.cnn_rdata(cnn_rdata),.cnn_mem_fault(memory_fault),
  .dmem_addr(32'b0),.dmem_wdata(32'b0),.dmem_wstrb(4'b0),.dmem_re(1'b0),.dmem_we(1'b0),.dmem_rdata(),
  .io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'b0),.io_mem_wdata(32'b0),.io_mem_be(4'b0),.io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error());
 reg [31:0] meta[0:0],nodes[0:319];
 reg [7:0] initial_mem[0:SIZE-1],golden[0:SIZE-1];
 bit mutable_byte[0:SIZE-1];
 integer events,wave,metrics,checked=0,overlap_cycles=0,write_overlap_cycles=0;
 integer starts[32],slot_owner[2],first_conv[32],last_post[32];
 logic [31:0] conv_seen=0,post_seen=0;
 logic enabled=0,early_layer=0;
 wire [5:0] core_state=dut.convolution.core.i_ctrl.i_ctrl_fsm.state_q;
 wire compute_active=core_busy && core_state==4;
 wire post_busy=dut.pbusy;
 wire compute_post_overlap=compute_active && post_busy;
 wire conv_read_fire=|(cnn_valid[8:0]&cnn_ready[8:0]&~cnn_write[8:0]);
 wire conv_write_fire=|(cnn_valid[8:0]&cnn_ready[8:0]&cnn_write[8:0]);
 wire post_read_fire=cnn_valid[10]&cnn_ready[10]&~cnn_write[10];
 wire post_write_fire=cnn_valid[10]&cnn_ready[10]&cnn_write[10];
 wire [31:0] post_address=cnn_addr[320+:32];
 wire [7:0] conv_frame=conv_tag[23:16],conv_layer=conv_tag[15:8],conv_stripe=conv_tag[7:0];
 wire [7:0] post_frame=post_tag[23:16],post_layer=post_tag[15:8],post_stripe=post_tag[7:0];
 function automatic [7:0] peek(input integer a);
  return mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8];
 endfunction
 task automatic initialize_memory;
  for(integer i=0;i<SIZE;i++)mem.mem[(i/4)%4][(i/4)/4][(i%4)*8+:8]=initial_mem[i];
 endtask
 task automatic program_all;
  for(integer j=0;j<meta[0];j++) begin
   @(negedge clk);program_valid=1;program_index=5'(j);
   program_deps=nodes[j*10];program_config=nodes[j*10+1];program_params=nodes[j*10+2];program_dst=nodes[j*10+3];
   program_elements=nodes[j*10+4];program_channels=nodes[j*10+5];program_tag=nodes[j*10+6];program_layer=2'(nodes[j*10+7]);
   if(!program_ready)$fatal(1,"program interface not ready");
  end
  @(negedge clk);program_valid=0;start=1;
  @(negedge clk);start=0;
 endtask
 initial begin:driver
  integer fd,n,out,first_f1,last_f0;
  overlap_enable=!$test$plusargs("serial");n=$value$plusargs("stall=%d",stall);
  $readmemh("meta.hex",meta);task_count=6'(meta[0]);$readmemh("nodes.hex",nodes,0,meta[0]*10-1);
  fd=$fopen("memory.bin","rb");n=$fread(initial_mem,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"bad memory");
  fd=$fopen("golden.bin","rb");n=$fread(golden,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"bad golden");
  #1;initialize_memory();
  for(integer j=0;j<meta[0];j++)for(integer b=0;b<nodes[j*10+4];b++)mutable_byte[nodes[j*10+3]+b]=1;
  for(integer s=0;s<2;s++)for(integer b=0;b<8192;b++)mutable_byte[32'h38000+s*8192+b]=1;
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,node,tag,slot\n");
  repeat(6)@(negedge clk);rst_n=1;
  if($test$plusargs("restart"))begin
   program_all();wait(post_busy && core_busy);repeat(9)@(negedge clk);clear=1;
   repeat(3)@(negedge clk);if(cnn_valid!=0 || busy || done || completed_mask!=0)$fatal(1,"clear failed");
   rst_n=0;clear=0;repeat(4)@(negedge clk);initialize_memory();rst_n=1;
  end
  enabled=1;program_all();wait(done);repeat(3)@(negedge clk);
  if(post_seen != ((32'd1<<meta[0])-1) || conv_seen!=post_seen)$fatal(1,"lost tasks");
  if(overlap_enable && (overlap_cycles==0 || write_overlap_cycles==0))$fatal(1,"no useful post-write/compute overlap");
  if(!overlap_enable && overlap_cycles!=0)$fatal(1,"serial run overlapped");
  if(overlap_enable && !early_layer)$fatal(1,"no cross-layer stripe handoff before preceding full layer completed");
  first_f1=1000000;last_f0=0;
  for(integer j=0;j<meta[0];j++)begin
   if(nodes[j*10+6][23:16]==1 && first_conv[j]<first_f1)first_f1=first_conv[j];
   if(nodes[j*10+6][23:16]==0 && last_post[j]>last_f0)last_f0=last_post[j];
  end
  if(first_f1>=last_f0)$fatal(1,"frames did not interleave");
  for(integer i=0;i<SIZE;i++)if(!mutable_byte[i] && peek(i)!==initial_mem[i])$fatal(1,"immutable/guard changed %h",i);
  out=$fopen("outputs.bin","wb");
  for(integer j=0;j<meta[0];j++)for(integer b=0;b<nodes[j*10+4];b++)begin
   if(peek(nodes[j*10+3]+b)!==golden[nodes[j*10+3]+b])$fatal(1,"final output corrupted");
   $fwrite(out,"%c",peek(nodes[j*10+3]+b));
  end
  $fclose(out);
  metrics=$fopen("metrics.json","w");
  $fwrite(metrics,"{\"cycles\":%0d,\"nodes\":%0d,\"checked_bytes\":%0d,\"compute_post_overlap_cycles\":%0d,",cycles,meta[0],checked,overlap_cycles);
  $fwrite(metrics,"\"post_write_during_compute_cycles\":%0d,\"early_layer\":%0d,\"first_frame1_conv\":%0d,\"last_frame0_post\":%0d}\n",write_overlap_cycles,early_layer,first_f1,last_f0);
  $fclose(metrics);$fclose(events);$fclose(wave);
  $display("PASS tb_mobilefacenet_pipeline cycles=%0d overlap=%0d checked=%0d",cycles,overlap_cycles,checked);$finish;
 end
 `include "pipeline_monitor.svh"
 always @(posedge clk)begin:checks
  integer j,a,len;logic previous_layer_finished;
  if(!rst_n || clear)begin
   cycles=0;last_progress=0;checked=0;overlap_cycles=0;write_overlap_cycles=0;conv_seen=0;post_seen=0;early_layer=0;
   for(integer i=0;i<32;i++)begin starts[i]=0;first_conv[i]=0;last_post[i]=0;end
   slot_owner[0]=-1;slot_owner[1]=-1;
  end else if(enabled)begin
   cycles++;
   if(error || memory_fault)$fatal(1,"pipeline fault");
   if(compute_post_overlap)overlap_cycles++;
   if(compute_active && post_write_fire)write_overlap_cycles++;
   if(|(cnn_valid&cnn_ready) || post_done || conv_tile_done)last_progress=cycles;
   if(conv_start)begin
    j=conv_node;if((nodes[j*10]&post_seen)!=nodes[j*10])$fatal(1,"uncommitted halo dependency node %0d",j);
    if(conv_tag!=nodes[j*10+6])$fatal(1,"bad conv frame/layer tag");
    if(slot_owner[conv_slot]!=-1 && slot_owner[conv_slot]!=j)$fatal(1,"scratch reused before final post ack");
    slot_owner[conv_slot]=j;starts[j]++;if(starts[j]>2)$fatal(1,"duplicate conv");
    if(starts[j]==1)first_conv[j]=cycles;
    previous_layer_finished=1;
    for(integer n=0;n<meta[0];n++)if(nodes[n*10+6][23:16]==conv_frame && nodes[n*10+7]+1==conv_layer && !post_seen[n])previous_layer_finished=0;
    if(conv_layer>0 && !previous_layer_finished)early_layer=1;
    $fwrite(events,"%0d,conv_start,%0d,%0d,%0d\n",cycles,j,conv_tag,conv_slot);$fflush(events);
   end
   if(conv_tile_done)begin
    j=conv_node;if(conv_seen[j] || starts[j]!=2)$fatal(1,"invalid conv completion");
    a=32'h38000+conv_slot*8192;len=nodes[j*10+4]*4;
    for(integer b=0;b<len;b++)if(peek(a+b)!==golden[nodes[j*10+8]+b])$fatal(1,"raw node=%0d byte=%0d got=%h want=%h",j,b,peek(a+b),golden[nodes[j*10+8]+b]);
    checked=checked+len;conv_seen[j]=1;$fwrite(events,"%0d,conv_done,%0d,%0d,%0d\n",cycles,j,conv_tag,conv_slot);$fflush(events);
   end
   if(post_start)begin
    if(!conv_seen[post_node] || post_tag!=nodes[post_node*10+6])$fatal(1,"early post or tag mismatch");
    $fwrite(events,"%0d,post_start,%0d,%0d,%0d\n",cycles,post_node,post_tag,post_slot);$fflush(events);
   end
   if(post_done)begin
    j=post_node;if(post_seen[j] || slot_owner[post_slot]!=j)$fatal(1,"duplicate/misowned post");
    a=nodes[j*10+3];len=nodes[j*10+4];
    for(integer b=0;b<len;b++)if(peek(a+b)!==golden[a+b])$fatal(1,"post node=%0d byte=%0d got=%h want=%h",j,b,peek(a+b),golden[a+b]);
    checked=checked+len;post_seen[j]=1;last_post[j]=cycles;slot_owner[post_slot]=-1;
    $fwrite(events,"%0d,post_done,%0d,%0d,%0d\n",cycles,j,post_tag,post_slot);$fflush(events);
   end
   if(cycles-last_progress>12000 || cycles>600000)$fatal(1,"pipeline watchdog state=%d completed=%h",core_state,completed_mask);
  end
 end
endmodule
