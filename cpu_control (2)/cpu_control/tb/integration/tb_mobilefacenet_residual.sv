`timescale 1ns/1ps
module tb_mobilefacenet_residual;
 localparam SIZE=524288;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0;
 logic [1:0] engine_enable=3,slot_limit=3;
 logic [5:0] task_count;
 logic program_valid=0;logic [4:0] program_index=0;
 logic [31:0] program_deps,program_config,program_params,program_dst,program_elements,program_channels,program_tag;
 logic [2:0] program_layer;
 logic program_add,program_keep;logic [31:0] program_src_a,program_src_b;
 wire post_add;wire [31:0] released_mask,release_pulse,live_mask;
 logic [31:0] release_seen=0,poison_pending=0;
 integer add_starts=0,add_overlap=0,skip_hold_cycles=0,join_wait_cycles=0,releases=0;
 bit poison=0;
 wire program_ready,busy,done,error,memory_fault,cnn_cancel;
 wire [20:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response,mem_ready;
 wire [671:0] cnn_addr,cnn_wdata,cnn_rdata;
 wire post_start,post_done;
 wire [1:0] post_slot;
 wire wait_slot,wait_dependency,wait_engine,wait_post;
 wire [1:0] conv_start,conv_tile_done,core_busy,engine_busy;
 wire [1:0][1:0] conv_slot;
 wire [1:0][4:0] conv_node;
 wire [1:0][31:0] conv_tag;
 wire [4:0] post_node;
 wire [31:0] post_tag,completed_mask;
 wire [8:0] slot_states;
 integer cycles=0,stall=0,last_progress=0,traffic_cycle=0;
 always @(posedge clk)begin
  if(!rst_n)traffic_cycle<=0;
  else begin traffic_cycle<=traffic_cycle+1;if(traffic_cycle>600000)$fatal(1,"warmup/run watchdog");end
 end
 // Stress engine 0 independently; return responses are never gated.
 wire [20:0] allow_request={1'b1,10'b1111111111,{10{stall==0 || traffic_cycle%7>=4}}};
 quant_residual_scheduler dut(.*);
 assign cnn_ready=mem_ready & allow_request;
 datasram_banked #(.SRAM_SIZE(SIZE),.BANKS(4),.CLIENTS(21)) mem(
  .clk(clk),.rst_n(rst_n),.cnn_cancel(cnn_cancel),.cnn_valid(cnn_valid & allow_request),.cnn_write(cnn_write),.cnn_byte(cnn_byte),
  .cnn_addr(cnn_addr),.cnn_wdata(cnn_wdata),.cnn_ready(mem_ready),.cnn_response(cnn_response),.cnn_rdata(cnn_rdata),.cnn_mem_fault(memory_fault),
  .dmem_addr(32'b0),.dmem_wdata(32'b0),.dmem_wstrb(4'b0),.dmem_re(1'b0),.dmem_we(1'b0),.dmem_rdata(),
  .io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'b0),.io_mem_wdata(32'b0),.io_mem_be(4'b0),.io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error());
 reg [31:0] meta[0:0],nodes[0:447];
 reg [7:0] initial_mem[0:SIZE-1],golden[0:SIZE-1];
 bit mutable_byte[0:SIZE-1];
 integer events,wave,metrics,checked=0,overlap_cycles=0,write_overlap_cycles=0;
 integer starts[32],slot_owner[3],first_conv[32],last_post[32],task_engine[32];
 integer engine_nodes[2],dual_compute_cycles=0,dual_memory_cycles=0,bank_wait_cycles=0;
 logic [1:0][1:0] engine_frames;
 logic [31:0] conv_seen=0,post_seen=0;
 logic enabled=0,early_layer=0;
 wire [1:0][5:0] core_state;
 assign core_state[0]=dut.engines[0].convolution.core.i_ctrl.i_ctrl_fsm.state_q;
 assign core_state[1]=dut.engines[1].convolution.core.i_ctrl.i_ctrl_fsm.state_q;
 wire [1:0] compute_active,conv_read_fire,conv_write_fire;
 wire post_busy=dut.pbusy;
 wire compute_post_overlap=(|compute_active) && post_busy;
 wire both_compute=&compute_active;
 wire triple_active=both_compute && post_busy;
 wire triple_write=triple_active && post_write_fire;
 wire mem_wait0=|(cnn_valid[9:0]&allow_request[9:0]&~cnn_ready[9:0]);
 wire mem_wait1=|(cnn_valid[19:10]&allow_request[19:10]&~cnn_ready[19:10]);
 wire mem_wait_post=cnn_valid[20]&allow_request[20]&~cnn_ready[20];
 wire [2:0] slot0_state=slot_states[2:0],slot1_state=slot_states[5:3],slot2_state=slot_states[8:6];
 integer triple_cycles=0,triple_writes=0,slot_use[3];
 integer wait_slot_cycles=0,wait_dependency_cycles=0,wait_engine_cycles=0,wait_post_cycles=0;
 integer mem_wait_cycles[3];
 wire post_read_fire=cnn_valid[20]&cnn_ready[20]&~cnn_write[20];
 wire post_write_fire=cnn_valid[20]&cnn_ready[20]&cnn_write[20];
 wire [31:0] post_address=cnn_addr[640+:32];
 wire [1:0][7:0] conv_frame,conv_layer,conv_stripe;
 for(genvar e=0;e<2;e++)begin
  assign compute_active[e]=core_busy[e] && core_state[e]==4;
  assign conv_read_fire[e]=|(cnn_valid[e*10+:9]&cnn_ready[e*10+:9]&~cnn_write[e*10+:9]);
  assign conv_write_fire[e]=|(cnn_valid[e*10+:9]&cnn_ready[e*10+:9]&cnn_write[e*10+:9]);
  assign conv_frame[e]=conv_tag[e][23:16];assign conv_layer[e]=conv_tag[e][15:8];assign conv_stripe[e]=conv_tag[e][7:0];
 end
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
   program_deps=nodes[j*14];program_config=nodes[j*14+1];program_params=nodes[j*14+2];program_dst=nodes[j*14+3];
   program_elements=nodes[j*14+4];program_channels=nodes[j*14+5];program_tag=nodes[j*14+6];program_layer=3'(nodes[j*14+7]);
   program_add=nodes[j*14+10][0];program_src_a=nodes[j*14+11];program_src_b=nodes[j*14+12];program_keep=nodes[j*14+13][0];
   if(!program_ready)$fatal(1,"program interface not ready");
  end
  @(negedge clk);program_valid=0;start=1;
  @(negedge clk);start=0;
 endtask
 initial begin:driver
  integer fd,n,out,first_f1,last_f0;
  if($test$plusargs("two_slots"))slot_limit=2;n=$value$plusargs("stall=%d",stall);poison=$test$plusargs("poison");
  $readmemh("meta.hex",meta);task_count=6'(meta[0]);$readmemh("nodes.hex",nodes,0,meta[0]*14-1);
  fd=$fopen("memory.bin","rb");n=$fread(initial_mem,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"bad memory");
  fd=$fopen("golden.bin","rb");n=$fread(golden,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"bad golden");
  #1;initialize_memory();
  for(integer j=0;j<meta[0];j++)for(integer b=0;b<nodes[j*14+4];b++)mutable_byte[nodes[j*14+3]+b]=1;
  for(integer s=0;s<slot_limit;s++)for(integer b=0;b<8192;b++)mutable_byte[32'h70000+s*8192+b]=1;
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,node,tag,slot,engine\n");
  repeat(6)@(negedge clk);rst_n=1;
  if($test$plusargs("restart"))begin
   program_all();wait(post_add && post_write_fire);repeat(9)@(negedge clk);clear=1;
   repeat(3)@(negedge clk);if(cnn_valid!=0 || busy || done || completed_mask!=0)$fatal(1,"clear failed");
   rst_n=0;clear=0;repeat(4)@(negedge clk);initialize_memory();rst_n=1;
  end
  enabled=1;program_all();wait(done);repeat(3)@(negedge clk);
  if(post_seen != ((32'd1<<meta[0])-1) || add_starts!=8)$fatal(1,"lost tasks");
  for(integer j=0;j<meta[0];j++)if(!nodes[j*14+10] && !conv_seen[j])$fatal(1,"missing convolution");
  if(releases!=20 || skip_hold_cycles==0 || join_wait_cycles==0 || add_overlap==0)$fatal(1,"missing lifetime/join/overlap evidence");
  if(overlap_cycles==0 || write_overlap_cycles==0)$fatal(1,"no useful post-write/compute overlap");
  if(!early_layer)$fatal(1,"no cross-layer stripe handoff before preceding full layer completed");
  if(engine_enable==3 && (dual_compute_cycles==0 || dual_memory_cycles==0 || engine_nodes[0]<2 || engine_nodes[1]<2))$fatal(1,"no dual useful execution");
  if(engine_enable==2 && (engine_nodes[0]!=0 || engine_nodes[1]!=20 || dual_compute_cycles!=0))$fatal(1,"disabled engine used");
  if(slot_limit==3 && (triple_cycles==0 || triple_writes==0 || slot_use[2]<2))$fatal(1,"third slot did not enable useful triple overlap/reuse");
  if(slot_limit==2 && (triple_cycles!=0 || slot_use[2]!=0))$fatal(1,"two-slot limit violated");
  first_f1=1000000;last_f0=0;
  for(integer j=0;j<meta[0];j++)begin
   if(!nodes[j*14+10] && nodes[j*14+6][23:16]==1 && first_conv[j]<first_f1)first_f1=first_conv[j];
   if(nodes[j*14+6][23:16]==0 && last_post[j]>last_f0)last_f0=last_post[j];
  end
  if(first_f1>=last_f0)$fatal(1,"frames did not interleave");
  for(integer i=0;i<SIZE;i++)if(!mutable_byte[i] && peek(i)!==initial_mem[i])$fatal(1,"immutable/guard changed %h",i);
  out=$fopen("outputs.bin","wb");
  for(integer j=0;j<meta[0];j++)if(nodes[j*14+13])for(integer b=0;b<nodes[j*14+4];b++)begin
   if(peek(nodes[j*14+3]+b)!==golden[nodes[j*14+3]+b])$fatal(1,"final output corrupted");
   $fwrite(out,"%c",peek(nodes[j*14+3]+b));
  end
  $fclose(out);
  metrics=$fopen("metrics.json","w");
  $fwrite(metrics,"{\"add_starts\":%0d,\"add_compute_overlap_cycles\":%0d,\"skip_hold_cycles\":%0d,\"join_wait_cycles\":%0d,\"releases\":%0d,",add_starts,add_overlap,skip_hold_cycles,join_wait_cycles,releases);
  $fwrite(metrics,"\"cycles\":%0d,\"nodes\":%0d,\"checked_bytes\":%0d,\"compute_post_overlap_cycles\":%0d,",cycles,meta[0],checked,overlap_cycles);
  $fwrite(metrics,"\"post_write_during_compute_cycles\":%0d,\"early_layer\":%0d,\"first_frame1_conv\":%0d,\"last_frame0_post\":%0d,",write_overlap_cycles,early_layer,first_f1,last_f0);
  $fwrite(metrics,"\"dual_compute_cycles\":%0d,\"dual_memory_cycles\":%0d,\"bank_wait_cycles\":%0d,\"engine_nodes\":[%0d,%0d],\"engine_frame_masks\":[%0d,%0d],",dual_compute_cycles,dual_memory_cycles,bank_wait_cycles,engine_nodes[0],engine_nodes[1],engine_frames[0],engine_frames[1]);
  $fwrite(metrics,"\"triple_cycles\":%0d,\"triple_write_cycles\":%0d,\"slot_use\":[%0d,%0d,%0d],",triple_cycles,triple_writes,slot_use[0],slot_use[1],slot_use[2]);
  $fwrite(metrics,"\"wait_slot_cycles\":%0d,\"wait_dependency_cycles\":%0d,\"wait_engine_cycles\":%0d,\"wait_post_cycles\":%0d,\"memory_wait_cycles\":[%0d,%0d,%0d]}\n",wait_slot_cycles,wait_dependency_cycles,wait_engine_cycles,wait_post_cycles,mem_wait_cycles[0],mem_wait_cycles[1],mem_wait_cycles[2]);
  $fclose(metrics);$fclose(events);$fclose(wave);
  $display("PASS tb_mobilefacenet_residual cycles=%0d overlap=%0d checked=%0d",cycles,overlap_cycles,checked);$finish;
 end
 `include "residual_monitor.svh"
 always @(posedge clk)begin:checks
  integer j,a,len;logic previous_layer_finished;logic [31:0] users;
  if(!rst_n || clear)begin
   cycles=0;last_progress=0;checked=0;release_seen=0;poison_pending=0;add_starts=0;add_overlap=0;skip_hold_cycles=0;join_wait_cycles=0;releases=0;overlap_cycles=0;write_overlap_cycles=0;conv_seen=0;post_seen=0;early_layer=0;
   for(integer i=0;i<32;i++)begin starts[i]=0;first_conv[i]=0;last_post[i]=0;end
   dual_compute_cycles=0;dual_memory_cycles=0;bank_wait_cycles=0;engine_nodes[0]=0;engine_nodes[1]=0;engine_frames=0;
   triple_cycles=0;triple_writes=0;wait_slot_cycles=0;wait_dependency_cycles=0;wait_engine_cycles=0;wait_post_cycles=0;
   for(integer k=0;k<3;k++)begin slot_owner[k]=-1;slot_use[k]=0;mem_wait_cycles[k]=0;end
  end else if(enabled)begin
   cycles++;
   if(error || memory_fault)$fatal(1,"pipeline fault");
   if(compute_post_overlap)overlap_cycles++;
   if(post_add && post_busy && (|compute_active))add_overlap++;
   for(integer n=0;n<meta[0];n++)begin
    if(nodes[n*14+10] && !post_seen[n] && (nodes[n*14]&post_seen)!=0 && (nodes[n*14]&post_seen)!=nodes[n*14])join_wait_cycles++;
    if(nodes[n*14+7]==0 && post_seen[n] && !released_mask[n])skip_hold_cycles++;
    if(release_pulse[n])begin
     users=0;for(integer c=0;c<meta[0];c++)if(nodes[c*14][n])users[c]=1;
     if(!post_seen[n] || release_seen[n] || nodes[n*14+13] || (users&post_seen)!=users)$fatal(1,"premature/duplicate release %0d",n);
     release_seen[n]=1;releases++;poison_pending[n]=1;
     $fwrite(events,"%0d,release,%0d,%0d,-1,-1\n",cycles,n,nodes[n*14+6]);
    end
   end
   if((|compute_active) && post_write_fire)write_overlap_cycles++;
   if(both_compute)dual_compute_cycles++;
   if(triple_active)triple_cycles++;
   if(triple_write)triple_writes++;
   if(wait_slot)wait_slot_cycles++;
   if(wait_dependency)wait_dependency_cycles++;
   if(wait_engine)wait_engine_cycles++;
   if(wait_post)wait_post_cycles++;
   if(mem_wait0)mem_wait_cycles[0]++;
   if(mem_wait1)mem_wait_cycles[1]++;
   if(mem_wait_post)mem_wait_cycles[2]++;
   if((|(cnn_valid[9:0]&cnn_ready[9:0])) && (|(cnn_valid[19:10]&cnn_ready[19:10])))dual_memory_cycles++;
   if(|(cnn_valid&allow_request&~cnn_ready))bank_wait_cycles++;
   if(engine_busy==3 && conv_slot[0]==conv_slot[1])$fatal(1,"engines share live scratch");
   if(post_busy && !post_add && ((engine_busy[0] && conv_slot[0]==post_slot) || (engine_busy[1] && conv_slot[1]==post_slot)))$fatal(1,"post/conv scratch collision");
   if(|(cnn_valid&cnn_ready) || post_done || (|conv_tile_done))last_progress=cycles;
   for(integer e=0;e<2;e++)begin
   if(conv_start[e])begin
    j=conv_node[e];if(nodes[j*14+10])$fatal(1,"Add dispatched to convolution");if((nodes[j*14]&released_mask)!=0)$fatal(1,"reading released feature");if(conv_slot[e]>=slot_limit)$fatal(1,"invalid slot");if((nodes[j*14]&post_seen)!=nodes[j*14])$fatal(1,"uncommitted halo dependency node %0d",j);
    if(conv_tag[e]!=nodes[j*14+6])$fatal(1,"bad conv frame/layer tag");
    if(slot_owner[conv_slot[e]]!=-1 && slot_owner[conv_slot[e]]!=j)$fatal(1,"scratch reused before final post ack");
    slot_owner[conv_slot[e]]=j;starts[j]++;if(starts[j]>nodes[j*14+5]/32)$fatal(1,"duplicate conv");
    if(starts[j]==1)begin slot_use[conv_slot[e]]++;first_conv[j]=cycles;task_engine[j]=e;engine_nodes[e]++;engine_frames[e][conv_frame[e]]=1;end
    else if(task_engine[j]!=e)$fatal(1,"channel group migrated between engines");
    previous_layer_finished=1;
    for(integer n=0;n<meta[0];n++)if(nodes[n*14+6][23:16]==conv_frame[e] && nodes[n*14+7]+1==conv_layer[e] && !post_seen[n])previous_layer_finished=0;
    if(conv_layer[e]>0 && !previous_layer_finished)early_layer=1;
    $fwrite(events,"%0d,conv_start,%0d,%0d,%0d,%0d\n",cycles,j,conv_tag[e],conv_slot[e],e);$fflush(events);
   end
   if(conv_tile_done[e])begin
    j=conv_node[e];if(nodes[j*14+10])$fatal(1,"Add dispatched to convolution");if((nodes[j*14]&released_mask)!=0)$fatal(1,"reading released feature");if(conv_slot[e]>=slot_limit)$fatal(1,"invalid slot");if(conv_seen[j] || starts[j]!=nodes[j*14+5]/32)$fatal(1,"invalid conv completion");
    a=32'h70000+conv_slot[e]*8192;len=nodes[j*14+4]*4;
    for(integer b=0;b<len;b++)if(peek(a+b)!==golden[nodes[j*14+8]+b])$fatal(1,"raw node=%0d byte=%0d got=%h want=%h",j,b,peek(a+b),golden[nodes[j*14+8]+b]);
    checked=checked+len;conv_seen[j]=1;$fwrite(events,"%0d,conv_done,%0d,%0d,%0d,%0d\n",cycles,j,conv_tag[e],conv_slot[e],e);$fflush(events);
   end
   end
   if(post_start)begin
    if(post_tag!=nodes[post_node*14+6])$fatal(1,"post tag mismatch");
    if(post_add)begin
     if((nodes[post_node*14]&post_seen)!=nodes[post_node*14] || (nodes[post_node*14]&released_mask)!=0)$fatal(1,"Add before both inputs committed or input released");
     add_starts++;
    end else if(!conv_seen[post_node])$fatal(1,"early convolution post");
    $fwrite(events,"%0d,post_start,%0d,%0d,%0d,-1\n",cycles,post_node,post_tag,post_slot);$fflush(events);
   end
   if(post_done)begin
    j=post_node;if(post_seen[j] || (!post_add && slot_owner[post_slot]!=j))$fatal(1,"duplicate/misowned post");
    a=nodes[j*14+3];len=nodes[j*14+4];
    for(integer b=0;b<len;b++)if(peek(a+b)!==golden[a+b])$fatal(1,"post node=%0d byte=%0d got=%h want=%h",j,b,peek(a+b),golden[a+b]);
    checked=checked+len;post_seen[j]=1;last_post[j]=cycles;if(!post_add)slot_owner[post_slot]=-1;
    $fwrite(events,"%0d,post_done,%0d,%0d,%0d,-1\n",cycles,j,post_tag,post_slot);$fflush(events);
   end
   if(cycles-last_progress>12000 || cycles>600000)$fatal(1,"pipeline watchdog state=%d completed=%h",core_state,completed_mask);
  end
 end
// Destructively recycle released feature storage, after all response handshakes.
 always @(negedge clk)if(enabled && poison)begin
  for(integer n=0;n<meta[0];n++)if(poison_pending[n])begin
   for(integer b=0;b<nodes[n*14+4];b++)begin
    integer a;a=nodes[n*14+3]+b;
    mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8]=8'hd7;
   end
  end
  poison_pending=0;
 end
endmodule
