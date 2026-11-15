// One fixed graph template, reused for 1..4 address descriptors. This is CNN
// hardware: the host never expands per-image commands or assigns an operator.
// Source relocation: 0=shared absolute, 1=image base, 2=workspace base.
module stream_fixed_programmer #(
 parameter FRAME_CONTEXTS=4,FW=$clog2(FRAME_CONTEXTS),SW=FW+2,
 parameter MAX_TASKS=64,IW=$clog2(MAX_TASKS),STEPS=MAX_TASKS/4,LW=$clog2(STEPS)
)(
 input logic clk,rst_n,clear,start,
 input logic [FW:0] image_count,
 input logic template_valid,input logic [LW-1:0] template_index,
 input logic [511:0] template_command,input logic [3:0] template_source_modes,
 input logic [1:0] template_dep_valid,
 input logic [LW-1:0] template_dep0,template_dep1,
 input logic [1:0] template_allocate_slot,
 input logic [STEPS-1:0] template_hold_mask,
 input logic [2:0] template_use_valid,input logic [5:0] template_use_slots,
 input logic [3*LW-1:0] template_use_owners,
 input logic template_result_valid,input logic [31:0] template_result_bytes,
 input logic address_valid,input logic [FW-1:0] address_slot,
 input logic [31:0] image_base,workspace_base,address_frame,
 output wire configuration_ready,output logic configuration_error,output wire expanding,
 input logic program_ready,
 output wire program_valid,output logic [IW-1:0] program_index,
 output logic [511:0] program_command,output logic [1:0] program_dep_valid,
 output logic [IW-1:0] program_dep0,program_dep1,output logic [IW:0] task_count,
 output wire program_allocate_valid,output logic [SW-1:0] program_allocate_slot,
 output logic [MAX_TASKS-1:0] program_hold_mask,
 output logic [2:0] program_use_valid,output logic [3*SW-1:0] program_use_slots,
 output logic [3*IW-1:0] program_use_owners,
 output logic program_result_valid,output logic [31:0] program_result_frame,program_result_addr,program_result_bytes,
 output wire core_start
);
 localparam CONFIG=0,EXPAND=1,LAUNCH=2,EXECUTE=3;
 logic [1:0] state;
 logic [LW:0] loaded;
 logic [LW-1:0] step;
 logic [FW-1:0] frame;
 logic [FW:0] frames;
 logic [FRAME_CONTEXTS-1:0] addresses_loaded;
 logic [31:0] inputs[FRAME_CONTEXTS],workspaces[FRAME_CONTEXTS],tags[FRAME_CONTEXTS];
 logic [511:0] cmds[STEPS];logic [3:0] modes[STEPS];logic [1:0] dv[STEPS],slots[STEPS];
 logic [LW-1:0] d0[STEPS],d1[STEPS];logic [STEPS-1:0] holds[STEPS];
 logic [2:0] uv[STEPS];logic [5:0] us[STEPS];logic [3*LW-1:0] uo[STEPS];
 logic rv[STEPS];logic [31:0] lengths[STEPS];
 wire valid_template=loaded<STEPS && {1'b0,template_index}==loaded && template_command[31:0]<=5 &&
  template_source_modes[1:0]!=3 && template_source_modes[3:2]!=3 &&
  (!template_dep_valid[0] || template_dep0<template_index) && (!template_dep_valid[1] || template_dep1<template_index);
 assign configuration_ready=state==CONFIG && !configuration_error && !clear;
 assign expanding=state==EXPAND || state==LAUNCH;
 assign program_valid=state==EXPAND && !configuration_error && !clear;
 assign core_start=state==LAUNCH && !configuration_error && !clear;
 assign program_allocate_valid=1;
 function automatic [31:0] relocate(input [31:0] offset,input [1:0] mode,input [FW-1:0] f);
  case(mode)1:relocate=inputs[f]+offset;2:relocate=workspaces[f]+offset;default:relocate=offset;endcase
 endfunction
 // Configuration RAMs intentionally have no reset; loaded entries are valid.
 always_ff @(posedge clk)if(configuration_ready)begin
  if(template_valid && valid_template)begin
   cmds[template_index]<=template_command;modes[template_index]<=template_source_modes;
   dv[template_index]<=template_dep_valid;d0[template_index]<=template_dep0;d1[template_index]<=template_dep1;
   slots[template_index]<=template_allocate_slot;holds[template_index]<=template_hold_mask;
   uv[template_index]<=template_use_valid;us[template_index]<=template_use_slots;uo[template_index]<=template_use_owners;
   rv[template_index]<=template_result_valid;lengths[template_index]<=template_result_bytes;
  end
  if(address_valid && address_slot<FRAME_CONTEXTS)begin inputs[address_slot]<=image_base;workspaces[address_slot]<=workspace_base;tags[address_slot]<=address_frame;end
 end
 always_comb begin
  program_index=IW'(int'(step)*int'(frames)+int'(frame));
  program_command=cmds[step];
  program_command[32+:32]=relocate(cmds[step][32+:32],modes[step][1:0],frame);
  program_command[64+:32]=relocate(cmds[step][64+:32],modes[step][3:2],frame);
  program_command[96+:32]=workspaces[frame]+cmds[step][96+:32];
  program_command[416+:32]=tags[frame];program_command[448+:32]=32'(frame);
  program_dep_valid=dv[step];program_dep0=IW'(int'(d0[step])*int'(frames)+int'(frame));program_dep1=IW'(int'(d1[step])*int'(frames)+int'(frame));
  program_allocate_slot={frame,slots[step]};program_hold_mask=0;
  for(integer s=0;s<STEPS;s++)if(s<loaded && holds[step][s])program_hold_mask[s*int'(frames)+int'(frame)]=1;
  program_use_valid=uv[step];program_use_slots=0;program_use_owners=0;
  for(integer u=0;u<3;u++)begin
   program_use_slots[u*SW+:SW]={frame,us[step][u*2+:2]};
   program_use_owners[u*IW+:IW]=IW'(int'(uo[step][u*LW+:LW])*int'(frames)+int'(frame));
  end
  program_result_valid=rv[step];program_result_frame=tags[frame];program_result_addr=program_command[96+:32];program_result_bytes=lengths[step];
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=CONFIG;loaded<=0;step<=0;frame<=0;frames<=0;addresses_loaded<=0;configuration_error<=0;task_count<=0;end
  else if(clear)begin state<=CONFIG;loaded<=0;step<=0;frame<=0;frames<=0;addresses_loaded<=0;configuration_error<=0;task_count<=0;end
  else begin
   if(configuration_ready)begin
    if(template_valid)begin if(valid_template)loaded<=loaded+1;else configuration_error<=1;end
    if(address_valid)begin
     if(address_slot>=FRAME_CONTEXTS || addresses_loaded[address_slot] || workspace_base[1:0]!=0)configuration_error<=1;
     else addresses_loaded[address_slot]<=1;
    end
    if(start)begin
     if(template_valid || address_valid || loaded==0 || image_count==0 || image_count>FRAME_CONTEXTS || int'(loaded)*int'(image_count)>MAX_TASKS ||
        (addresses_loaded & (((FRAME_CONTEXTS+1)'(1)<<image_count)-1))!=(((FRAME_CONTEXTS+1)'(1)<<image_count)-1))configuration_error<=1;
     else begin frames<=image_count;task_count<=(IW+1)'(int'(loaded)*int'(image_count));state<=EXPAND;end
    end
   end
   if(program_valid && program_ready)begin
    if(int'(frame)+1==frames)begin
     frame<=0;if({1'b0,step}+1==loaded)state<=LAUNCH;else step<=step+1;
    end else frame<=frame+1;
   end
   if(core_start)state<=EXECUTE;
  end
 end
endmodule
