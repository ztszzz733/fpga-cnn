// Four finite in-flight frame contexts. A whole-frame commit follows the final
// input SRAM write; no task reads an uncommitted image. No frame/engine binding.
module stream_dispatch #(
 parameter MAX_TASKS=64,IW=$clog2(MAX_TASKS),K3_UNITS=3,K1_UNITS=1,POST_UNITS=1,
 parameter UNITS=K3_UNITS+K1_UNITS+POST_UNITS+3
)(
 input logic clk,rst_n,clear,start,memory_fault,
 input logic [UNITS-1:0] unit_enable,
 input logic frame_valid, input logic [1:0] frame_slot,
 input logic [31:0] frame_id,output wire frame_ready,
 output logic [3:0] frames_ready,
 input logic buffer_ready,output wire [IW-1:0] candidate_node,
 output wire reserve_commit,wait_buffer,wait_input,
 input logic program_valid,input logic [IW-1:0] program_index,
 input logic [511:0] program_command,input logic [1:0] program_dep_valid,
 input logic [IW-1:0] program_dep0,program_dep1,input logic [IW:0] task_count,
 output wire program_ready,busy,done,error,cancel,
 input logic [UNITS-1:0] unit_busy,unit_done,unit_error,
 output logic [UNITS-1:0] unit_start,unit_active,completion_pulse,
 output logic [UNITS-1:0][511:0] unit_command,
 output logic [UNITS-1:0][IW-1:0] unit_node,
 output logic [MAX_TASKS-1:0] completed_mask,
 output logic [IW:0] completed_count
);
 localparam DW=K3_UNITS+K1_UNITS,POST=DW+1,ADD=POST+POST_UNITS,PAD=ADD+1;
 logic [511:0] commands[MAX_TASKS];
 logic [1:0] dv[MAX_TASKS];logic [IW-1:0] d0[MAX_TASKS],d1[MAX_TASKS],scan;
 logic [MAX_TASKS-1:0] issued;
 logic [IW:0] loaded,total;
 logic running,finished,failed;
 logic [UNITS-1:0] enabled;
 logic [31:0] frame_tags[4];
 integer k3_turn,k1_turn,post_turn,selected,finishes;
 wire dependencies=(!dv[scan][0] || completed_mask[d0[scan]]) && (!dv[scan][1] || completed_mask[d1[scan]]);
 wire input_ok=frames_ready[commands[scan][449:448]] && frame_tags[commands[scan][449:448]]==commands[scan][416+:32];
 wire valid_program=loaded<MAX_TASKS && program_index<MAX_TASKS && {1'b0,program_index}==loaded && program_command[31:0]<=5 &&
  program_command[448+:32]<4 && (!program_dep_valid[0] || program_dep0<program_index) && (!program_dep_valid[1] || program_dep1<program_index);
 assign candidate_node=scan;
 assign reserve_commit=running && !cancel && !issued[scan] && dependencies && input_ok && selected>=0 && buffer_ready;
 assign wait_buffer=running && !cancel && !issued[scan] && dependencies && input_ok && !buffer_ready;
 assign wait_input=running && !cancel && !issued[scan] && dependencies && !input_ok;
 assign program_ready=!running && !finished && !failed && !clear;
 assign frame_ready=running && !cancel && !frames_ready[frame_slot];
 assign busy=running;assign done=finished;assign error=failed;
 assign cancel=clear || failed || memory_fault;
 // Programming RAMs have no reset. Valid entries are delimited by loaded.
 always_ff @(posedge clk)if(program_valid && program_ready && valid_program)begin
  commands[program_index]<=program_command;dv[program_index]<=program_dep_valid;
  d0[program_index]<=program_dep0;d1[program_index]<=program_dep1;
 end
 always_comb begin
  selected=-1;finishes=0;
  for(integer u=0;u<UNITS;u++)if(unit_active[u] && !unit_start[u] && unit_done[u])finishes++;
  case(commands[scan][31:0])
   0:for(integer q=0;q<K3_UNITS;q++)begin
    integer u;u=(k3_turn+q)%K3_UNITS;
    if(selected<0 && enabled[u] && !unit_active[u] && !unit_busy[u])selected=u;
   end
   5:for(integer q=0;q<K1_UNITS;q++)begin
    integer u;u=K3_UNITS+(k1_turn+q)%K1_UNITS;
    if(selected<0 && enabled[u] && !unit_active[u] && !unit_busy[u])selected=u;
   end
   1:for(integer q=0;q<POST_UNITS;q++)begin
    integer u;u=POST+(post_turn+q)%POST_UNITS;
    if(selected<0 && enabled[u] && !unit_active[u] && !unit_busy[u])selected=u;
   end
   2:if(enabled[ADD] && !unit_active[ADD] && !unit_busy[ADD])selected=ADD;
   3:if(enabled[DW] && !unit_active[DW] && !unit_busy[DW])selected=DW;
   4:if(enabled[PAD] && !unit_active[PAD] && !unit_busy[PAD])selected=PAD;
   default:;
  endcase
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   loaded<=0;total<=0;scan<=0;issued<=0;completed_mask<=0;completed_count<=0;
   running<=0;finished<=0;failed<=0;enabled<=0;k3_turn<=0;k1_turn<=0;post_turn<=0;
   unit_start<=0;unit_active<=0;completion_pulse<=0;unit_command<=0;unit_node<=0;frames_ready<=0;
  end else if(clear)begin
   loaded<=0;total<=0;scan<=0;issued<=0;completed_mask<=0;completed_count<=0;
   running<=0;finished<=0;failed<=0;k3_turn<=0;k1_turn<=0;post_turn<=0;
   unit_start<=0;unit_active<=0;completion_pulse<=0;frames_ready<=0;
  end else begin
   unit_start<=0;completion_pulse<=0;
   if(memory_fault || |unit_error)begin failed<=1;running<=0;unit_active<=0;frames_ready<=0;end
   else if(!failed)begin
    if(program_valid && program_ready)begin if(!valid_program)failed<=1;else loaded<=loaded+1;end
    if(start && program_ready)begin
     if(program_valid || task_count==0 || task_count!=loaded || !(|unit_enable[0+:K3_UNITS]) ||
       !(|unit_enable[K3_UNITS+:K1_UNITS]) || !(|unit_enable[POST+:POST_UNITS]) || !unit_enable[DW] || !unit_enable[ADD] || !unit_enable[PAD])failed<=1;
     else begin running<=1;total<=task_count;enabled<=unit_enable;end
    end
    if(frame_valid && frame_ready)begin frames_ready[frame_slot]<=1;frame_tags[frame_slot]<=frame_id;end
    if(running)begin
     if(completed_count==total)begin running<=0;finished<=1;end
     else begin
      scan<=({1'b0,scan}+1>=total)?'0:scan+1'b1;
      if(reserve_commit)begin
       issued[scan]<=1;unit_start[selected]<=1;unit_active[selected]<=1;
       unit_command[selected]<=commands[scan];unit_node[selected]<=scan;
       if(selected<K3_UNITS)k3_turn<=(selected+1)%K3_UNITS;
       else if(selected<DW)k1_turn<=(selected-K3_UNITS+1)%K1_UNITS;
       else if(selected>=POST && selected<ADD)post_turn<=(selected-POST+1)%POST_UNITS;
      end
      completed_count<=completed_count+(IW+1)'(finishes);
      for(integer u=0;u<UNITS;u++)if(unit_active[u] && !unit_start[u] && unit_done[u])begin
       completed_mask[unit_node[u]]<=1;unit_active[u]<=0;completion_pulse[u]<=1;
      end
     end
    end
   end
  end
 end
endmodule
