// Two genuine NEureka engines share a dependency table and up to three scratch slots.
// No frame/layer-to-engine affinity: select an idle enabled engine round-robin.
// Generalized 32-channel groups; Add joins bypass and main branch without a scratch slot.
// Intermediate feature release waits for every declared consumer to finish its writes.
module quant_residual_scheduler #(
 parameter MAX_TASKS=32,
 parameter logic [31:0] SCRATCH0=32'h70000, SCRATCH1=32'h72000, SCRATCH2=32'h74000
)(
 input logic clk,rst_n,clear,start,
 input logic [1:0] engine_enable,slot_limit,
 input logic [5:0] task_count,
 input logic program_valid,input logic [4:0] program_index,
 input logic [31:0] program_deps,program_config,program_params,program_dst,
 input logic [31:0] program_elements,program_channels,program_tag,
 input logic [2:0] program_layer,
 input logic program_add,program_keep,
 input logic [31:0] program_src_a,program_src_b,
 output wire post_add,
 output wire [31:0] released_mask,release_pulse,live_mask,
 output wire program_ready,busy,done,error,
 input wire memory_fault,
 output wire [20:0] cnn_valid,cnn_write,cnn_byte,
 output wire [671:0] cnn_addr,cnn_wdata,
 input wire [20:0] cnn_ready,cnn_response,input wire [671:0] cnn_rdata,
 output wire cnn_cancel,post_start,post_done,
 output wire [1:0] conv_start,conv_tile_done,core_busy,engine_busy,
 output wire [1:0][1:0] conv_slot,
 output wire [1:0][4:0] conv_node,
 output wire [1:0][31:0] conv_tag,
 output wire [4:0] post_node,
 output wire [31:0] post_tag,completed_mask,
 output wire [8:0] slot_states,
 output wire [1:0] post_slot,
 output wire wait_slot,wait_dependency,wait_engine,wait_post
);
 typedef enum logic [2:0] {FREE,READY,CONV,POST_READY,POST} slot_t;
 slot_t slots[3];
 logic [4:0] owner[3];
 logic [31:0] deps[MAX_TASKS],cfg[MAX_TASKS],param[MAX_TASKS],dest[MAX_TASKS];
 logic [31:0] elements[MAX_TASKS],channels[MAX_TASKS],tag[MAX_TASKS];
 logic [2:0] layer[MAX_TASKS];
 logic kind[MAX_TASKS],keep[MAX_TASKS];
 logic [31:0] src_a[MAX_TASKS],src_b[MAX_TASKS],released,releasable,consumers[MAX_TASKS];
 logic [1:0][2:0] cgroup;
 logic [4:0] pnode,apick;
 logic afound;
 logic [31:0] programmed,issued,completed;
 logic [5:0] total;
 logic running,finished,failed;
 logic [1:0] enabled,cactive,limit;
 logic [1:0][1:0] cslot;
 logic pactive,next_engine;
 logic [1:0] pslot,free_pick,cpick,ppick;
 logic free_found,eligible,cfound,pfound,efound,epick,unissued;
 logic [4:0] pick;
 wire [1:0] cbusy,cdone,cerror,mem_idle,launch_second;
 wire pbusy,pdone,perror;
 wire abort_jobs=clear || failed || memory_fault;
 wire [31:0] mask=total==32 ? 32'hffffffff:((32'd1<<total)-1);
 assign program_ready=!running && !finished && !failed && !clear;
 assign busy=running;assign done=finished;assign error=failed;
 assign cnn_cancel=abort_jobs;assign completed_mask=completed;
 assign slot_states={slots[2],slots[1],slots[0]};assign engine_busy=cactive;
 assign wait_slot=running && eligible && !free_found;
 assign wait_dependency=running && unissued && !eligible && !afound;
 assign wait_engine=running && cfound && !efound;
 assign wait_post=running && (pfound || afound) && (pactive || pbusy || pdone);
 function automatic [31:0] scratch_address(input logic [1:0] slot);
  case(slot) 0:return SCRATCH0;1:return SCRATCH1;2:return SCRATCH2;default:return 32'hffffffff;endcase
 endfunction
 assign post_node=pactive ? pnode:(afound ? apick:owner[ppick]);
 assign post_add=kind[post_node];
 assign released_mask=released;assign release_pulse=running && !abort_jobs ? releasable:0;
 assign live_mask=completed & ~released;
 always_comb begin
  releasable=0;
  for(integer i=0;i<MAX_TASKS;i++)begin
   consumers[i]=0;
   for(integer j=0;j<MAX_TASKS;j++)if(j<total && deps[j][i])consumers[i][j]=1;
   if(i<total && completed[i] && !released[i] && !keep[i] && (consumers[i]&completed)==consumers[i])releasable[i]=1;
  end
 end
 assign post_tag=tag[post_node];assign post_slot=pactive ? pslot:(afound ? 2'd3:ppick);
 always_comb begin
  free_found=0;free_pick=0;eligible=0;pick=0;unissued=0;afound=0;apick=0;
  cfound=0;cpick=0;pfound=0;ppick=0;efound=0;epick=0;
  for(integer s=0;s<3;s++) begin
   if(s<limit && slots[s]==FREE && !free_found) begin free_found=1;free_pick=2'(s);end
   // READY between channel groups is reserved to its current engine.
   if(slots[s]==READY && !(cactive[0] && cslot[0]==2'(s)) && !(cactive[1] && cslot[1]==2'(s)) &&
      (!cfound || layer[owner[s]]>layer[owner[cpick]])) begin cfound=1;cpick=2'(s);end
   if(slots[s]==POST_READY && !pfound) begin pfound=1;ppick=2'(s);end
  end
  for(integer e=0;e<2;e++) begin
   if(enabled[1'(e)^next_engine] && !cactive[1'(e)^next_engine] &&
      !cbusy[1'(e)^next_engine] && !cdone[1'(e)^next_engine] && !efound) begin
    efound=1;epick=1'(e)^next_engine;
   end
  end
  for(integer j=0;j<MAX_TASKS;j++) begin
   if(j<total && !issued[j])unissued=1;
   if(j<total && kind[j] && !issued[j] && ((deps[j]&completed)==deps[j]) && !afound)begin afound=1;apick=5'(j);end
   if(j<total && !kind[j] && !issued[j] && ((deps[j]&completed)==deps[j]) &&
      (!eligible || layer[j]>layer[pick])) begin eligible=1;pick=5'(j);end
  end
 end
 for(genvar e=0;e<2;e++) begin:engines
  assign conv_slot[e]=cactive[e] ? cslot[e]:cpick;
  assign conv_node[e]=owner[conv_slot[e]];
  assign conv_tag[e]=tag[conv_node[e]];
  assign launch_second[e]=cactive[e] && cgroup[e]!=0 && slots[cslot[e]]==READY;
  assign conv_start[e]=running && !abort_jobs && enabled[e] && !cbusy[e] && !cdone[e] &&
                       (launch_second[e] || (cfound && efound && epick==1'(e) && !cactive[e]));
  assign conv_tile_done[e]=cdone[e] && cactive[e] && cgroup[e]+1==channels[conv_node[e]]/32 && !abort_jobs;
  neureka_conv_engine convolution(
   .clk(clk),.rst_n(rst_n),.clear(abort_jobs),.start(conv_start[e]),
   .config_address(cfg[conv_node[e]]+(32'(conv_slot[e])*(channels[conv_node[e]]/32)*96)+(launch_second[e] ? 32'(cgroup[e])*96:0)),
   .busy(cbusy[e]),.done(cdone[e]),.error(cerror[e]),
   .cfg_valid(cnn_valid[e*10+9]),.cfg_addr(cnn_addr[(e*10+9)*32+:32]),.cfg_ready(cnn_ready[e*10+9]),
   .cfg_response(cnn_response[e*10+9]),.cfg_rdata(cnn_rdata[(e*10+9)*32+:32]),
   .valid(cnn_valid[e*10+:9]),.write(cnn_write[e*10+:9]),.byte_access(cnn_byte[e*10+:9]),
   .addr(cnn_addr[e*320+:288]),.wdata(cnn_wdata[e*320+:288]),.ready(cnn_ready[e*10+:9]),
   .response(cnn_response[e*10+:9]),.rdata(cnn_rdata[e*320+:288]),.core_busy(core_busy[e]),.memory_idle(mem_idle[e]));
  assign cnn_write[e*10+9]=0;assign cnn_byte[e*10+9]=0;assign cnn_wdata[(e*10+9)*32+:32]=0;
 end
 assign post_start=running && !abort_jobs && (pfound || afound) && !pactive && !pbusy && !pdone;
 assign post_done=pdone && pactive && !abort_jobs;
 quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(abort_jobs),.start(post_start),.mode_add(post_add),
  .src_a(post_add ? src_a[post_node]:scratch_address(post_slot)),.src_b(src_b[post_node]),.destination(dest[post_node]),
  .parameter_base(param[post_node]),.count(elements[post_node]),.channels(channels[post_node]),
  .busy(pbusy),.done(pdone),.error(perror),.valid(cnn_valid[20]),.write(cnn_write[20]),.byte_access(cnn_byte[20]),
  .addr(cnn_addr[640+:32]),.wdata(cnn_wdata[640+:32]),.ready(cnn_ready[20]),.response(cnn_response[20]),.rdata(cnn_rdata[640+:32]));
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   programmed<=0;issued<=0;completed<=0;released<=0;total<=0;running<=0;finished<=0;failed<=0;enabled<=0;limit<=0;
   cactive<=0;pactive<=0;cslot<=0;pslot<=0;cgroup<=0;next_engine<=0;
   for(integer s=0;s<3;s++)begin slots[s]<=FREE;owner[s]<=0;end
  end else if(clear) begin
   programmed<=0;issued<=0;completed<=0;released<=0;running<=0;finished<=0;failed<=0;cactive<=0;pactive<=0;cgroup<=0;next_engine<=0;
   for(integer s=0;s<3;s++)slots[s]<=FREE;
  end else if(memory_fault || (|cerror) || perror) begin failed<=1;running<=0;cactive<=0;pactive<=0;end
  else if(!failed) begin
   if(program_valid && program_ready && program_index<MAX_TASKS) begin
    deps[program_index]<=program_deps;cfg[program_index]<=program_config;param[program_index]<=program_params;
    dest[program_index]<=program_dst;elements[program_index]<=program_elements;channels[program_index]<=program_channels;
    tag[program_index]<=program_tag;layer[program_index]<=program_layer;programmed[program_index]<=1;
    kind[program_index]<=program_add;keep[program_index]<=program_keep;src_a[program_index]<=program_src_a;src_b[program_index]<=program_src_b;
    if(program_elements==0 || program_channels==0 || program_channels>128 || program_elements%program_channels!=0 ||
       (!program_add && (program_channels%32!=0 || program_elements>2048)))failed<=1;
   end
   if(start && program_ready) begin
    if(task_count==0 || task_count>MAX_TASKS || engine_enable==0 || (slot_limit!=2 && slot_limit!=3) ||
       (programmed & (task_count==32 ? 32'hffffffff:((32'd1<<task_count)-1))) !=
                    (task_count==32 ? 32'hffffffff:((32'd1<<task_count)-1))) failed<=1;
    else begin total<=task_count;enabled<=engine_enable;limit<=slot_limit;running<=1;end
   end
   if(running) begin
    released<=released | releasable;
    if(free_found && eligible) begin slots[free_pick]<=READY;owner[free_pick]<=pick;issued[pick]<=1;end
    for(integer e=0;e<2;e++) begin
     if(conv_start[e]) begin
      cactive[e]<=1;cslot[e]<=conv_slot[e];slots[conv_slot[e]]<=CONV;
      if(!launch_second[e])begin cgroup[e]<=0;next_engine<=!1'(e);end
     end
     if(cdone[e] && cactive[e]) begin
      if(cgroup[e]+1<channels[conv_node[e]]/32)begin cgroup[e]<=cgroup[e]+1;slots[cslot[e]]<=READY;end
      else begin cactive[e]<=0;cgroup[e]<=0;slots[cslot[e]]<=POST_READY;end
     end
    end
    if(post_start)begin
     pactive<=1;pslot<=post_slot;pnode<=post_node;
     if(post_add)issued[post_node]<=1;else slots[post_slot]<=POST;
    end
    if(post_done)begin pactive<=0;if(!post_add)slots[pslot]<=FREE;completed[post_node]<=1;end
    if((completed&mask)==mask)begin running<=0;finished<=1;end
   end
  end
 end
endmodule
