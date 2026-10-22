// Experimental dependency-driven three-layer stripe executor, inside CNN.
// A node owns one of two INT32 scratch slots through its final post write ack.
// Each node has two 32-output-channel NEureka configurations per scratch slot:
// cfg_base + slot*192 + channel_group*96. Input/output feature planes remain
// separately allocated; dependency bits publish committed UINT8 stripes.
module quant_stripe_scheduler #(
 parameter MAX_TASKS=32,
 parameter logic [31:0] SCRATCH0=32'h38000, SCRATCH1=32'h3a000
)(
 input logic clk,rst_n,clear,start,overlap_enable,
 input logic [5:0] task_count,
 input logic program_valid,input logic [4:0] program_index,
 input logic [31:0] program_deps,program_config,program_params,program_dst,
 input logic [31:0] program_elements,program_channels,program_tag,
 input logic [1:0] program_layer,
 output wire program_ready,busy,done,error,
 input wire memory_fault,
 output wire [10:0] cnn_valid,cnn_write,cnn_byte,
 output wire [351:0] cnn_addr,cnn_wdata,
 input wire [10:0] cnn_ready,cnn_response,input wire [351:0] cnn_rdata,
 output wire cnn_cancel,conv_start,post_start,conv_tile_done,post_done,core_busy,
 output wire [4:0] conv_node,post_node,
 output wire [31:0] conv_tag,post_tag,completed_mask,
 output wire [5:0] slot_states,
 output wire conv_slot,post_slot
);
 typedef enum logic [2:0] {FREE,READY,CONV,POST_READY,POST} slot_t;
 slot_t slots[2];
 logic [4:0] owner[2];
 logic [31:0] deps[MAX_TASKS],cfg[MAX_TASKS],param[MAX_TASKS],dest[MAX_TASKS];
 logic [31:0] elements[MAX_TASKS],channels[MAX_TASKS],tag[MAX_TASKS];
 logic [1:0] layer[MAX_TASKS];
 logic [31:0] programmed,issued,completed;
 logic [5:0] total;
 logic running,finished,failed,overlap;
 logic cactive,pactive,cslot,pslot,cpart;
 logic free_found,free_pick,eligible,cfound,cpick,pfound,ppick;
 logic [4:0] pick;
 wire cbusy,cdone,cerror,pbusy,pdone,perror,mem_idle;
 wire abort_jobs=clear || failed || memory_fault;
 wire [31:0] mask=total==32 ? 32'hffffffff:((32'd1<<total)-1);
 assign program_ready=!running && !finished && !failed && !clear;
 assign busy=running;
 assign done=finished;
 assign error=failed;
 assign cnn_cancel=abort_jobs;
 assign completed_mask=completed;
 assign slot_states={slots[1],slots[0]};
 assign conv_node=owner[cactive ? cslot:cpick];
 assign post_node=owner[pactive ? pslot:ppick];
 assign conv_tag=tag[conv_node];assign post_tag=tag[post_node];
 assign conv_slot=cactive ? cslot:cpick;
 assign post_slot=pactive ? pslot:ppick;
 always_comb begin
  free_found=0;free_pick=0;eligible=0;pick=0;
  cfound=0;cpick=0;pfound=0;ppick=0;
  for(integer s=0;s<2;s++) begin
   if(slots[s]==FREE && !free_found) begin free_found=1;free_pick=1'(s);end
   if(slots[s]==READY && (!cfound || layer[owner[s]]>layer[owner[cpick]])) begin cfound=1;cpick=1'(s);end
   if(slots[s]==POST_READY && !pfound) begin pfound=1;ppick=1'(s);end
  end
  // Prefer a downstream layer as soon as its halo-producing stripes commit.
  // Equal-layer ties use submission index; bounded DAGs do not starve tasks.
  for(integer j=0;j<MAX_TASKS;j++) begin
   if(j<total && !issued[j] && ((deps[j]&completed)==deps[j]) &&
      (!eligible || layer[j]>layer[pick])) begin eligible=1;pick=5'(j);end
  end
 end
 wire launch_new=cfound && !cactive;
 wire launch_second=cactive && cpart && slots[cslot]==READY;
 assign conv_start=running && !abort_jobs && !cbusy && !cdone && (launch_new || launch_second) &&
                   (overlap || (!pactive && !pfound));
 assign post_start=running && !abort_jobs && pfound && !pactive && !pbusy && !pdone &&
                   (overlap || (!cactive && !cbusy));
 assign conv_tile_done=cdone && cactive && cpart && !abort_jobs;
 assign post_done=pdone && pactive && !abort_jobs;
 neureka_conv_engine convolution(
  .clk(clk),.rst_n(rst_n),.clear(abort_jobs),.start(conv_start),
  .config_address(cfg[conv_node]+(conv_slot ? 192:0)+(launch_second ? 96:0)),
  .busy(cbusy),.done(cdone),.error(cerror),
  .cfg_valid(cnn_valid[9]),.cfg_addr(cnn_addr[288+:32]),.cfg_ready(cnn_ready[9]),
  .cfg_response(cnn_response[9]),.cfg_rdata(cnn_rdata[288+:32]),
  .valid(cnn_valid[8:0]),.write(cnn_write[8:0]),.byte_access(cnn_byte[8:0]),
  .addr(cnn_addr[0+:288]),.wdata(cnn_wdata[0+:288]),.ready(cnn_ready[8:0]),
  .response(cnn_response[8:0]),.rdata(cnn_rdata[0+:288]),.core_busy(core_busy),.memory_idle(mem_idle));
 assign cnn_write[9]=0;assign cnn_byte[9]=0;assign cnn_wdata[288+:32]=0;
 quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(abort_jobs),.start(post_start),.mode_add(1'b0),
  .src_a(post_slot ? SCRATCH1:SCRATCH0),.src_b(32'b0),.destination(dest[post_node]),
  .parameter_base(param[post_node]),.count(elements[post_node]),.channels(channels[post_node]),
  .busy(pbusy),.done(pdone),.error(perror),.valid(cnn_valid[10]),.write(cnn_write[10]),.byte_access(cnn_byte[10]),
  .addr(cnn_addr[320+:32]),.wdata(cnn_wdata[320+:32]),.ready(cnn_ready[10]),.response(cnn_response[10]),.rdata(cnn_rdata[320+:32]));
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   programmed<=0;issued<=0;completed<=0;total<=0;running<=0;finished<=0;failed<=0;overlap<=0;
   cactive<=0;pactive<=0;cslot<=0;pslot<=0;cpart<=0;
   for(integer s=0;s<2;s++)begin slots[s]<=FREE;owner[s]<=0;end
  end else if(clear) begin
   programmed<=0;issued<=0;completed<=0;running<=0;finished<=0;failed<=0;cactive<=0;pactive<=0;cpart<=0;
   for(integer s=0;s<2;s++)slots[s]<=FREE;
  end else if(memory_fault || cerror || perror) begin failed<=1;running<=0;cactive<=0;pactive<=0;end
  else if(!failed) begin
   if(program_valid && program_ready) begin
    deps[program_index]<=program_deps;cfg[program_index]<=program_config;param[program_index]<=program_params;
    dest[program_index]<=program_dst;elements[program_index]<=program_elements;channels[program_index]<=program_channels;
    tag[program_index]<=program_tag;layer[program_index]<=program_layer;programmed[program_index]<=1;
   end
   if(start && program_ready) begin
    if(task_count==0 || task_count>MAX_TASKS ||
       (programmed & (task_count==32 ? 32'hffffffff:((32'd1<<task_count)-1))) !=
                    (task_count==32 ? 32'hffffffff:((32'd1<<task_count)-1))) failed<=1;
    else begin total<=task_count;overlap<=overlap_enable;running<=1;end
   end
   if(running) begin
    if(free_found && eligible) begin slots[free_pick]<=READY;owner[free_pick]<=pick;issued[pick]<=1;end
    if(conv_start) begin
     cactive<=1;cslot<=conv_slot;slots[conv_slot]<=CONV;
     if(!launch_second)cpart<=0;
    end
    if(cdone && cactive) begin
     if(!cpart)begin cpart<=1;slots[cslot]<=READY;end
     else begin cactive<=0;cpart<=0;slots[cslot]<=POST_READY;end
    end
    if(post_start)begin pactive<=1;pslot<=post_slot;slots[post_slot]<=POST;end
    if(post_done)begin pactive<=0;slots[pslot]<=FREE;completed[post_node]<=1;end
    if((completed&mask)==mask)begin running<=0;finished<=1;end
   end
  end
 end
endmodule
