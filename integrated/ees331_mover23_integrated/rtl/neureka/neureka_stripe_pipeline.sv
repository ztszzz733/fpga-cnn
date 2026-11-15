// Experimental CNN subsystem: two scratch slots, one real NEureka and one
// existing ReLU engine. A producer submits only after the input stripe + halo
// has committed to SRAM. Config/weights stay immutable until the job completes.
// Raw output slots are caller-provided, disjoint, and selected by tile_slot.
// ReLU is flat elementwise here: HWC needs no CHW conversion (no per-channel params).
module neureka_stripe_pipeline (
 input wire clk,rst_n,clear,overlap_enable,
 input wire tile_valid, tile_slot, tile_last,
 input wire [31:0] tile_config,
 input wire [255:0] tile_relu_descriptor,
 output wire tile_ready,
 output wire busy,done,error,
 input wire memory_fault,
 output wire [10:0] cnn_valid,cnn_write,cnn_byte,
 output wire [351:0] cnn_addr,cnn_wdata,
 input wire [10:0] cnn_ready,cnn_response,
 input wire [351:0] cnn_rdata,
 output wire cnn_cancel,
 output wire conv_start,post_start,conv_done,post_done,core_busy,
 output wire [31:0] conv_tile,post_tile,accepted_tiles,completed_tiles,
 output wire [5:0] slot_states
);
 typedef enum logic [2:0] {FREE,READY,CONV,POST_READY,POST} slot_state_t;
 slot_state_t slot_state[2];
 logic [31:0] config_addr[2],job_id[2];
 logic [255:0] post_desc[2];
 logic [31:0] accepted,completed;
 logic conv_active,post_active,conv_slot,post_slot,closed,failed;
 logic conv_found,post_found,conv_pick,post_pick;
 wire cbusy,cdone,cerror,pbusy,pdone,perror,mem_idle;
 wire abort_jobs=clear || failed || memory_fault;
 assign cnn_cancel=abort_jobs;
 assign error=failed;
 assign tile_ready=!abort_jobs && !closed && slot_state[tile_slot]==FREE;
 assign accepted_tiles=accepted;
 assign completed_tiles=completed;
 assign busy=accepted!=completed && !failed;
 assign done=closed && accepted==completed && !failed;
 assign conv_tile=job_id[conv_active ? conv_slot:conv_pick];
 assign post_tile=job_id[post_active ? post_slot:post_pick];
 assign slot_states={slot_state[1],slot_state[0]};
 assign conv_done=cdone && conv_active && !abort_jobs;
 assign post_done=pdone && post_active && !abort_jobs;
 always_comb begin
  conv_found=0;post_found=0;conv_pick=0;post_pick=0;
  for(integer s=0;s<2;s=s+1) begin
   if(slot_state[s]==READY && (!conv_found || job_id[s]<job_id[conv_pick])) begin
    conv_found=1;conv_pick=1'(s);
   end
   if(slot_state[s]==POST_READY && (!post_found || job_id[s]<job_id[post_pick])) begin
    post_found=1;post_pick=1'(s);
   end
  end
 end
 assign conv_start=conv_found && !conv_active && !cbusy && !cdone && !abort_jobs &&
                    (overlap_enable || (!post_active && !post_found));
 assign post_start=post_found && !post_active && !pbusy && !pdone && !abort_jobs;
 neureka_conv_engine convolution(
  .clk(clk),.rst_n(rst_n),.clear(abort_jobs),.start(conv_start),.config_address(config_addr[conv_pick]),
  .busy(cbusy),.done(cdone),.error(cerror),
  .cfg_valid(cnn_valid[9]),.cfg_addr(cnn_addr[288+:32]),.cfg_ready(cnn_ready[9]),
  .cfg_response(cnn_response[9]),.cfg_rdata(cnn_rdata[288+:32]),
  .valid(cnn_valid[8:0]),.write(cnn_write[8:0]),.byte_access(cnn_byte[8:0]),
  .addr(cnn_addr[0+:288]),.wdata(cnn_wdata[0+:288]),.ready(cnn_ready[8:0]),
  .response(cnn_response[8:0]),.rdata(cnn_rdata[0+:288]),.core_busy(core_busy),.memory_idle(mem_idle));
 assign cnn_write[9]=0;assign cnn_byte[9]=0;assign cnn_wdata[288+:32]=0;
 tensor_operator_engine #(.OPCODE(6)) activation(
  .clk(clk),.rst_n(rst_n),.clear(abort_jobs),.start(post_start),.descriptor(post_desc[post_pick]),
  .busy(pbusy),.done(pdone),.error(perror),
  .cmd_valid(cnn_valid[10]),.cmd_ready(cnn_ready[10]),.cmd_write(cnn_write[10]),
  .cmd_byte(cnn_byte[10]),.cmd_addr(cnn_addr[320+:32]),.cmd_wdata(cnn_wdata[320+:32]),
  .rsp_valid(cnn_response[10]),.rsp_data(cnn_rdata[320+:32]));
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   accepted<=0;completed<=0;closed<=0;failed<=0;
   conv_active<=0;post_active<=0;conv_slot<=0;post_slot<=0;
   for(integer s=0;s<2;s=s+1) begin slot_state[s]<=FREE;config_addr[s]<=0;post_desc[s]<=0;job_id[s]<=0;end
  end else if(clear) begin
   accepted<=0;completed<=0;closed<=0;failed<=0;conv_active<=0;post_active<=0;
   for(integer s=0;s<2;s=s+1) slot_state[s]<=FREE;
  end else if(memory_fault || cerror || perror) begin
   failed<=1;conv_active<=0;post_active<=0;
  end else if(!failed) begin
   if(tile_valid && tile_ready) begin
    config_addr[tile_slot]<=tile_config;post_desc[tile_slot]<=tile_relu_descriptor;
    job_id[tile_slot]<=accepted;slot_state[tile_slot]<=READY;
    accepted<=accepted+1;closed<=tile_last;
   end
   if(conv_start) begin conv_slot<=conv_pick;conv_active<=1;slot_state[conv_pick]<=CONV;end
   // cdone is emitted only after NEureka's bridge has drained all writes.
   if(conv_done) begin conv_active<=0;slot_state[conv_slot]<=POST_READY;end
   if(post_start) begin post_slot<=post_pick;post_active<=1;slot_state[post_pick]<=POST;end
   // Reuse is permitted only after the final activation write response.
   if(post_done) begin post_active<=0;slot_state[post_slot]<=FREE;completed<=completed+1;end
  end
 end
endmodule
