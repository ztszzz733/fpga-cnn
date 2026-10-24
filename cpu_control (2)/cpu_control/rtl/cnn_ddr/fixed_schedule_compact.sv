// One 20-word template, four frame PCs, 16 physical leases. No expanded graph.
// A frame executes in template order; different frames use the shared operator
// pool independently. Terminal consumer IDs preserve residual-buffer lifetime.
module fixed_schedule_compact #(
 parameter integer STEPS=256,LW=$clog2(STEPS),IW=LW+2,
 parameter integer K3_UNITS=2,K1_UNITS=4,POST_UNITS=1,
 parameter integer UNITS=K3_UNITS+K1_UNITS+POST_UNITS+3
)(
 input logic clk,rst_n,clear,start,
 input logic [UNITS-1:0] unit_enable,
 input logic [2:0] image_count,
 input logic template_valid,input logic [LW-1:0] template_index,
 input logic [511:0] template_command,input logic [3:0] template_source_modes,
 input logic [1:0] template_dep_valid,input logic [LW-1:0] template_dep0,template_dep1,
 input logic [1:0] template_allocate_slot,template_consumer_count,
 input logic [LW-1:0] template_consumer0,template_consumer1,
 input logic [2:0] template_use_valid,input logic [5:0] template_use_slots,
 input logic [3*LW-1:0] template_use_owners,
 input logic template_result_valid,input logic [31:0] template_result_bytes,
 input logic address_valid,input logic [1:0] address_slot,
 input logic [31:0] image_base,workspace_base,address_frame,
 output wire configuration_ready,output logic [LW:0] loaded_steps,
 input logic frame_valid,input logic [1:0] frame_slot,input logic [31:0] frame_id,
 output wire frame_ready,output logic [3:0] frames_ready,
 input logic result_ready,
 output wire result_valid,outputs_pending,compute_done,busy,done,error,cancel,
 output logic result_accept,output logic [31:0] result_frame,result_addr,result_bytes,
 output wire [7:0] result_error,output logic [31:0] error_code,
 output logic [15:0] external_hold,buffer_live,buffer_release,buffer_allocate,
 output wire [16*IW-1:0] buffer_owners,
 output wire wait_buffer,wait_input,
 output wire [UNITS-1:0] mem_valid,mem_write,mem_byte,
 output wire [UNITS*32-1:0] mem_addr,mem_wdata,
 input logic [UNITS-1:0] mem_ready,mem_response,
 input logic [UNITS*32-1:0] mem_rdata,input logic memory_fault,
 output logic [UNITS-1:0] unit_start,unit_active,completion_pulse,
 output logic [UNITS-1:0][511:0] unit_command,
 output logic [UNITS-1:0][IW-1:0] unit_node,
 output wire [UNITS-1:0] operator_busy,operator_work,
 output logic [IW:0] completed_count,
 output wire [4*STEPS-1:0] completed_mask,
 output wire [K3_UNITS+K1_UNITS-1:0][31:0] conv_input_reads,conv_weight_reads,conv_mac_count
);
 localparam integer DW=K3_UNITS+K1_UNITS,POST=DW+1,ADD=POST+POST_UNITS,PAD=ADD+1;
 // The on-board format is fixed to 8-bit template IDs (up to 256 steps).
 localparam integer ROW_BITS=640;
 (* ram_style="block" *) logic [ROW_BITS-1:0] template_ram[STEPS];
 logic [ROW_BITS-1:0] row;
 logic [31:0] inputs[4],workspaces[4],tags[4];
 logic [LW:0] pc[4];
 logic [3:0] addresses_loaded,frame_active;
 logic [2:0] frames;
 logic running,finished,failed;
 logic [UNITS-1:0] enabled;
 logic [1:0] scan,selected_frame;
 logic [LW-1:0] selected_step;
 logic [1:0] fetch_phase;
 logic [LW-1:0] owner[16],consumer0[16],consumer1[16];
 logic [1:0] consumers[16];
 logic [31:0] output_addr[16],output_length[16];
 logic [UNITS-1:0][1:0] unit_frame;
 logic [UNITS-1:0][LW-1:0] unit_step;
 logic presenting;logic [3:0] result_slot,result_turn;
 logic [LW:0] max_consumer;
 logic [LW:0] result_entries;
 logic last_is_result;
 integer selected,pick,finishes,k3_turn,k1_turn,post_turn;
 logic lease_ready,valid_template,relocation_ok;
 logic [511:0] relocated;
 logic [ROW_BITS-1:0] input_row;
 wire [UNITS-1:0] ub,ud,ue;
 wire [UNITS-1:0][15:0][31:0] cmd=unit_command;
 wire [31:0] m0=row[512+:32],m1=row[544+:32],m2=row[576+:32];
 wire [3:0] allocation={selected_frame,m0[5:4]};
 wire [2:0] uses=m0[8:6];
 wire [5:0] use_slots=m0[14:9];
 wire [23:0] use_owners=m1[31:8];
 wire issue=running && fetch_phase==2 && !cancel && !frame_active[selected_frame] &&
  frames_ready[selected_frame] && lease_ready && selected>=0 && relocation_ok;
 assign configuration_ready=!running && !finished && !failed && !clear;
 assign frame_ready=running && !cancel && frame_slot<frames && !frames_ready[frame_slot];
 assign compute_done=finished;
 assign outputs_pending=|external_hold;
 assign busy=running || |unit_active || |buffer_live || |external_hold;
 assign done=finished && !busy && !cancel;
 assign error=failed;assign cancel=clear || failed || memory_fault;
 assign result_valid=presenting && !cancel;
 assign result_error=0;
 assign operator_busy=ub;
 assign wait_buffer=running && fetch_phase==2 && frames_ready[selected_frame] && !lease_ready;
 assign wait_input=running && fetch_phase==0 && scan<frames && !frames_ready[scan];
 for(genvar s=0;s<16;s++)assign buffer_owners[s*IW+:IW]=IW'(int'(owner[s])*int'(frames)+s/4);
 // Verification view derives completion from the four monotonic PCs; no bitmap
 // is stored, and unused debug outputs are removed in the board synthesis.
 for(genvar n=0;n<4*STEPS;n++)begin:completed_debug
  assign completed_mask[n]=frames!=0 && n<int'(loaded_steps)*int'(frames) &&
   pc[n%((frames==0)?1:frames)]>n/((frames==0)?1:frames);
 end
 always_comb begin
  input_row=0;input_row[0+:512]=template_command;
  input_row[512+:32]={6'b0,8'(template_dep0),template_dep_valid,template_result_valid,
   template_use_slots,template_use_valid,template_allocate_slot,template_source_modes};
  input_row[544+:32]={8'(template_use_owners[2*LW+:LW]),8'(template_use_owners[LW+:LW]),
   8'(template_use_owners[0+:LW]),8'(template_dep1)};
  input_row[576+:32]={14'b0,template_consumer_count,8'(template_consumer1),8'(template_consumer0)};
  input_row[608+:32]=template_result_bytes;
  valid_template=loaded_steps<STEPS && {1'b0,template_index}==loaded_steps && template_command[31:0]<=5 &&
   template_source_modes[1:0]!=3 && template_source_modes[3:2]!=3 && template_consumer_count<=2 &&
   (!template_dep_valid[0] || template_dep0<template_index) &&
   (!template_dep_valid[1] || template_dep1<template_index) &&
   (template_consumer_count==0 || template_consumer0>template_index) &&
   (template_consumer_count<2 || (template_consumer1>template_index && template_consumer0!=template_consumer1)) &&
   (!template_result_valid || template_result_bytes!=0);
  for(integer q=0;q<3;q++)if(template_use_valid[q] && template_use_owners[q*LW+:LW]>=template_index)valid_template=0;
 end
 // Synchronous template RAM; no array reset and no expanded per-frame copy.
 always_ff @(posedge clk)begin
  if(configuration_ready && template_valid && valid_template)template_ram[template_index]<=input_row;
  if(running && fetch_phase==1)row<=template_ram[selected_step];
  if(configuration_ready && address_valid)begin
   inputs[address_slot]<=image_base;workspaces[address_slot]<=workspace_base;tags[address_slot]<=address_frame;
  end
 end
 function automatic [32:0] relocate(input [31:0] offset,input [1:0] mode,input [1:0] f);
  case(mode)1:relocate={1'b0,inputs[f]}+{1'b0,offset};
   2:relocate={1'b0,workspaces[f]}+{1'b0,offset};default:relocate={1'b0,offset};endcase
 endfunction
 always_comb begin
  logic [32:0] a,b,o;
  a=relocate(row[32+:32],m0[1:0],selected_frame);
  b=relocate(row[64+:32],m0[3:2],selected_frame);
  o={1'b0,workspaces[selected_frame]}+{1'b0,row[96+:32]};
  relocated=row[0+:512];relocated[32+:32]=a[31:0];relocated[64+:32]=b[31:0];relocated[96+:32]=o[31:0];
  relocated[416+:32]=tags[selected_frame];relocated[448+:32]={30'b0,selected_frame};
  relocation_ok=!(a[32] || b[32] || o[32]) &&
   (!m0[15] || ({1'b0,o[31:0]}+{1'b0,row[608+:32]})<=33'h100000000);
  lease_ready=!buffer_live[allocation];
  for(integer q=0;q<3;q++)if(uses[q])begin
   if(!buffer_live[{selected_frame,use_slots[q*2+:2]}] ||
      owner[{selected_frame,use_slots[q*2+:2]}]!=use_owners[q*8+:8])lease_ready=0;
  end
  selected=-1;finishes=0;pick=-1;
  for(integer u=0;u<UNITS;u++)if(unit_active[u] && !unit_start[u] && ud[u])finishes++;
  case(row[31:0])
   0:for(integer q=0;q<K3_UNITS;q++)begin
    integer u;u=(k3_turn+q)%K3_UNITS;
    if(selected<0 && enabled[u] && !unit_active[u] && !ub[u])selected=u;
   end
   5:for(integer q=0;q<K1_UNITS;q++)begin
    integer u;u=K3_UNITS+(k1_turn+q)%K1_UNITS;
    if(selected<0 && enabled[u] && !unit_active[u] && !ub[u])selected=u;
   end
   1:for(integer q=0;q<POST_UNITS;q++)begin
    integer u;u=POST+(post_turn+q)%POST_UNITS;
    if(selected<0 && enabled[u] && !unit_active[u] && !ub[u])selected=u;
   end
   2:if(enabled[ADD] && !unit_active[ADD] && !ub[ADD])selected=ADD;
   3:if(enabled[DW] && !unit_active[DW] && !ub[DW])selected=DW;
   4:if(enabled[PAD] && !unit_active[PAD] && !ub[PAD])selected=PAD;
   default:;
  endcase
  for(integer q=0;q<16;q++)begin
   integer s;s=(int'(result_turn)+q)%16;
   if(pick<0 && external_hold[s] && pc[s/4]>{1'b0,owner[s]})pick=s;
  end
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   loaded_steps<=0;addresses_loaded<=0;frames_ready<=0;frames<=0;running<=0;finished<=0;failed<=0;error_code<=0;
   scan<=0;selected_frame<=0;selected_step<=0;fetch_phase<=0;frame_active<=0;
   unit_start<=0;unit_active<=0;completion_pulse<=0;unit_command<=0;unit_node<=0;unit_frame<=0;unit_step<=0;
   enabled<=0;completed_count<=0;buffer_live<=0;buffer_release<=0;buffer_allocate<=0;external_hold<=0;
   presenting<=0;result_slot<=0;result_turn<=0;result_accept<=0;result_frame<=0;result_addr<=0;result_bytes<=0;
   max_consumer<=0;result_entries<=0;last_is_result<=0;k3_turn<=0;k1_turn<=0;post_turn<=0;
   for(integer f=0;f<4;f++)pc[f]<=0;
   for(integer s=0;s<16;s++)begin owner[s]<=0;consumer0[s]<=0;consumer1[s]<=0;consumers[s]<=0;output_addr[s]<=0;output_length[s]<=0;end
  end else if(clear)begin
   loaded_steps<=0;addresses_loaded<=0;frames_ready<=0;frames<=0;running<=0;finished<=0;failed<=0;error_code<=0;
   scan<=0;fetch_phase<=0;frame_active<=0;unit_start<=0;unit_active<=0;completion_pulse<=0;
   completed_count<=0;buffer_live<=0;buffer_release<=0;buffer_allocate<=0;external_hold<=0;
   presenting<=0;result_turn<=0;result_accept<=0;max_consumer<=0;result_entries<=0;last_is_result<=0;
   k3_turn<=0;k1_turn<=0;post_turn<=0;
   for(integer f=0;f<4;f++)pc[f]<=0;
  end else begin
   unit_start<=0;completion_pulse<=0;buffer_allocate<=0;buffer_release<=0;result_accept<=0;
   if(memory_fault || |ue)begin
    failed<=1;error_code<=memory_fault?32'h100:32'h101;running<=0;unit_active<=0;frame_active<=0;
    buffer_live<=0;external_hold<=0;presenting<=0;
   end else if(failed)begin
    // Configuration/frame faults also cancel leases and dispatch bookkeeping;
    // otherwise software could see a permanently busy, already cancelled core.
    running<=0;unit_active<=0;frame_active<=0;buffer_live<=0;external_hold<=0;presenting<=0;
   end else begin
    if(configuration_ready)begin
     if(template_valid)begin
      if(!valid_template)begin failed<=1;error_code<=1;end
      else begin
       loaded_steps<=loaded_steps+1;last_is_result<=template_result_valid;
       if(template_result_valid)result_entries<=result_entries+1;
       if(template_consumer_count!=0 && {1'b0,template_consumer0}>max_consumer)max_consumer<={1'b0,template_consumer0};
       if(template_consumer_count==2 && {1'b0,template_consumer1}>max_consumer && template_consumer1>template_consumer0)max_consumer<={1'b0,template_consumer1};
      end
     end
     if(address_valid)begin
      if(addresses_loaded[address_slot] || workspace_base[1:0]!=0)begin failed<=1;error_code<=2;end
      else addresses_loaded[address_slot]<=1;
     end
     if(start)begin
      if(template_valid || address_valid || loaded_steps==0 || image_count==0 || image_count>4 ||
       (addresses_loaded & ((5'b1<<image_count)-1))!=((5'b1<<image_count)-1) ||
       max_consumer>=loaded_steps || result_entries!=1 || !last_is_result ||
       !(|unit_enable[0+:K3_UNITS]) || !(|unit_enable[K3_UNITS+:K1_UNITS]) ||
       !(|unit_enable[POST+:POST_UNITS]) || !unit_enable[DW] || !unit_enable[ADD] || !unit_enable[PAD])begin failed<=1;error_code<=3;end
      else begin running<=1;frames<=image_count;enabled<=unit_enable;end
     end
    end
    if(frame_valid && frame_ready)begin
     if(frame_id!=tags[frame_slot])begin failed<=1;error_code<=4;running<=0;end
     else frames_ready[frame_slot]<=1;
    end
    for(integer s=0;s<16;s++)if(buffer_live[s] && !external_hold[s] && pc[s/4]>{1'b0,owner[s]} &&
      (consumers[s]==0 || pc[s/4]>{1'b0,consumer0[s]}) &&
      (consumers[s]<2 || pc[s/4]>{1'b0,consumer1[s]}))begin buffer_live[s]<=0;buffer_release[s]<=1;end
    if(result_valid && result_ready)begin
     external_hold[result_slot]<=0;presenting<=0;result_accept<=1;result_turn<=result_slot+1;
    end else if(!presenting && pick>=0)begin
     result_slot<=4'(pick);presenting<=1;result_frame<=tags[pick/4];result_addr<=output_addr[pick];result_bytes<=output_length[pick];
    end
    if(running)begin
     if(completed_count==(IW+1)'(int'(loaded_steps)*int'(frames)))begin running<=0;finished<=1;end
     else begin
      completed_count<=completed_count+(IW+1)'(finishes);
      for(integer u=0;u<UNITS;u++)if(unit_active[u] && !unit_start[u] && ud[u])begin
       unit_active[u]<=0;completion_pulse[u]<=1;frame_active[unit_frame[u]]<=0;pc[unit_frame[u]]<=pc[unit_frame[u]]+1;
      end
      case(fetch_phase)
       0:begin
        scan<=scan+1;
        if(scan<frames && frames_ready[scan] && !frame_active[scan] && pc[scan]<loaded_steps)begin
         selected_frame<=scan;selected_step<=pc[scan][LW-1:0];fetch_phase<=1;
        end
       end
       1:fetch_phase<=2;
       2:begin
        fetch_phase<=0;
        if(!relocation_ok)begin failed<=1;error_code<=5;running<=0;end
        // A frame has at most one active job. By this second fetch cycle,
        // previous completions have advanced its PC and all releasable leases
        // have been retired. Other frames cannot change its four slots. Thus
        // an absent/wrong input owner or a still-live output slot is a broken
        // static lifetime plan, not a resource wait that can later resolve.
        else if(!lease_ready)begin failed<=1;error_code<=6;running<=0;end
        else if(issue)begin
         unit_start[selected]<=1;unit_active[selected]<=1;unit_command[selected]<=relocated;
         unit_node[selected]<=IW'(int'(selected_step)*int'(frames)+int'(selected_frame));
         unit_frame[selected]<=selected_frame;unit_step[selected]<=selected_step;frame_active[selected_frame]<=1;
         buffer_live[allocation]<=1;buffer_allocate[allocation]<=1;owner[allocation]<=selected_step;
         consumers[allocation]<=m2[17:16];consumer0[allocation]<=LW'(m2[7:0]);consumer1[allocation]<=LW'(m2[15:8]);
         if(m0[15])begin external_hold[allocation]<=1;output_addr[allocation]<=relocated[96+:32];output_length[allocation]<=row[608+:32];end
         if(selected<K3_UNITS)k3_turn<=(selected+1)%K3_UNITS;
         else if(selected<DW)k1_turn<=(selected-K3_UNITS+1)%K1_UNITS;
         else if(selected>=POST && selected<ADD)post_turn<=(selected-POST+1)%POST_UNITS;
        end
       end
       default:fetch_phase<=0;
      endcase
     end
    end
   end
  end
 end
 for(genvar e=0;e<DW;e++)begin:engines
  localparam integer KERNEL=e<K3_UNITS?3:1;
  self_conv_engine #(.MAX_CHANNELS(512),.MAX_KERNEL(KERNEL),.TILE(2)) convolution(
   .clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[e]),.depthwise(cmd[e][11][0]),
   .input_base(cmd[e][1]),.weight_base(cmd[e][2]),.output_base(cmd[e][3]),
   .width(cmd[e][7]),.height(cmd[e][8]),.in_channels(cmd[e][6]),.out_channels(cmd[e][9]),.kernel(32'(KERNEL)),.stride(cmd[e][10]),
   .busy(ub[e]),.done(ud[e]),.error(ue[e]),.valid(mem_valid[e]),.write(mem_write[e]),.byte_access(mem_byte[e]),
   .addr(mem_addr[e*32+:32]),.wdata(mem_wdata[e*32+:32]),.ready(mem_ready[e]),.response(mem_response[e]),.rdata(mem_rdata[e*32+:32]),
   .mac_fire(operator_work[e]),.phase(),.input_reads(conv_input_reads[e]),.weight_reads(conv_weight_reads[e]),.mac_count(conv_mac_count[e]));
 end
 dw7_bram_engine #(.MAX_WIDTH(7),.MAX_CHANNELS(512),.LANES(8)) dw7(
  .clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[DW]),.reuse_weights(1'b0),
  .input_base(cmd[DW][1]),.weight_base(cmd[DW][2]),.output_base(cmd[DW][3]),.width(cmd[DW][7]),.height(cmd[DW][8]),.channels(cmd[DW][6]),
  .busy(ub[DW]),.done(ud[DW]),.error(ue[DW]),.valid(mem_valid[DW]),.write(mem_write[DW]),.byte_access(mem_byte[DW]),.cancel(),
  .addr(mem_addr[DW*32+:32]),.wdata(mem_wdata[DW*32+:32]),.ready(mem_ready[DW]),.response(mem_response[DW]),.rdata(mem_rdata[DW*32+:32]),
  .phase(),.mac_fire(operator_work[DW]),.weights_cached(),.cache_hit());
 for(genvar e=POST;e<=ADD;e++)begin:postprocessing
  quant_post_bram_engine post(.clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[e]),.mode_add(e==ADD),
   .src_a(cmd[e][1]),.src_b(cmd[e][2]),.destination(cmd[e][3]),.parameter_base(cmd[e][4]),.count(cmd[e][5]),.channels(cmd[e][6]),
   .busy(ub[e]),.done(ud[e]),.error(ue[e]),.valid(mem_valid[e]),.write(mem_write[e]),.byte_access(mem_byte[e]),
   .addr(mem_addr[e*32+:32]),.wdata(mem_wdata[e*32+:32]),.ready(mem_ready[e]),.response(mem_response[e]),.rdata(mem_rdata[e*32+:32]));
  assign operator_work[e]=mem_valid[e] && mem_ready[e] && mem_write[e];
 end
 pad_hwc_engine padding(.clk(clk),.rst_n(rst_n),.clear(cancel),.start(unit_start[PAD]),
  .source(cmd[PAD][1]),.destination(cmd[PAD][3]),.width(cmd[PAD][7]),.height(cmd[PAD][8]),.channels(cmd[PAD][6]),.zero_point(cmd[PAD][9][7:0]),
  .busy(ub[PAD]),.done(ud[PAD]),.error(ue[PAD]),.valid(mem_valid[PAD]),.write(mem_write[PAD]),.byte_access(mem_byte[PAD]),
  .addr(mem_addr[PAD*32+:32]),.wdata(mem_wdata[PAD*32+:32]),.ready(mem_ready[PAD]),.response(mem_response[PAD]),.rdata(mem_rdata[PAD*32+:32]));
 assign operator_work[PAD]=mem_valid[PAD] && mem_ready[PAD] && mem_write[PAD];
endmodule
