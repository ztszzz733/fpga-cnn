// Bounded command DAG. One candidate inspected per cycle; up to five jobs active.
// Each command has at most two earlier dependencies, explicit frame tag in word13.
// Completion is the operator's drained-write completion, never its launch.
module network_dispatch #(
 parameter integer MAX_TASKS=1024, IW=$clog2(MAX_TASKS)
)(
 input logic clk,rst_n,clear,start,memory_fault,
 input logic [1:0] engine_enable,
 input logic program_valid, input logic [IW-1:0] program_index,
 input logic [511:0] program_command,
 input logic [1:0] program_dep_valid,
 input logic [IW-1:0] program_dep0,program_dep1,
 input logic [IW:0] task_count,
 output wire program_ready,busy,done,error,cancel,
 input logic [4:0] unit_busy,unit_done,unit_error,
 output logic [4:0] unit_start,unit_active,completion_pulse,
 output logic [4:0][511:0] unit_command,
 output logic [4:0][IW-1:0] unit_node,
 output logic [MAX_TASKS-1:0] completed_mask,
 output logic [IW:0] completed_count
);
 logic [511:0] commands[MAX_TASKS];
 logic [1:0] dv[MAX_TASKS];
 logic [IW-1:0] d0[MAX_TASKS],d1[MAX_TASKS],scan;
 logic [MAX_TASKS-1:0] issued;
 logic [IW:0] loaded,total;
 logic running,finished,failed,turn;
 logic [1:0] enabled;
 integer selected,finishes;
 wire dependencies=(!dv[scan][0] || completed_mask[d0[scan]]) &&
                   (!dv[scan][1] || completed_mask[d1[scan]]);
 assign program_ready=!running && !finished && !failed && !clear;
 assign busy=running;assign done=finished;assign error=failed;
 assign cancel=clear || failed || memory_fault;
 always_comb begin
  selected=-1;finishes=0;
  for(integer u=0;u<5;u++)if(unit_active[u] && !unit_start[u] && unit_done[u])finishes++;
  case(commands[scan][31:0])
   0:begin
    if(enabled[turn] && !unit_active[turn] && !unit_busy[turn])selected=int'(turn);
    else if(enabled[!turn] && !unit_active[!turn] && !unit_busy[!turn])selected=int'(!turn);
   end
   1,2:if(!unit_active[2] && !unit_busy[2])selected=2;
   3:if(!unit_active[3] && !unit_busy[3])selected=3;
   4:if(!unit_active[4] && !unit_busy[4])selected=4;
   default:;
  endcase
 end
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n)begin
   loaded<=0;total<=0;scan<=0;issued<=0;completed_mask<=0;completed_count<=0;
   running<=0;finished<=0;failed<=0;turn<=0;enabled<=0;
   unit_start<=0;unit_active<=0;completion_pulse<=0;unit_command<=0;unit_node<=0;
  end else if(clear)begin
   loaded<=0;total<=0;scan<=0;issued<=0;completed_mask<=0;completed_count<=0;
   running<=0;finished<=0;failed<=0;turn<=0;
   unit_start<=0;unit_active<=0;completion_pulse<=0;
  end else begin
   unit_start<=0;completion_pulse<=0;
   if(memory_fault || |unit_error)begin failed<=1;running<=0;unit_active<=0;end
   else if(!failed)begin
    if(program_valid && program_ready)begin
     if(loaded>=MAX_TASKS || {1'b0,program_index}!=loaded || program_command[31:0]>4 ||
        (program_dep_valid[0] && program_dep0>=program_index) ||
        (program_dep_valid[1] && program_dep1>=program_index))failed<=1;
     else begin
      commands[program_index]<=program_command;dv[program_index]<=program_dep_valid;
      d0[program_index]<=program_dep0;d1[program_index]<=program_dep1;loaded<=loaded+1;
     end
    end
    if(start && program_ready)begin
     if(program_valid || task_count==0 || task_count!=loaded || engine_enable==0)failed<=1;
     else begin running<=1;total<=task_count;enabled<=engine_enable;end
    end
    if(running)begin
     if(completed_count==total)begin running<=0;finished<=1;end
     else begin
      scan<=({1'b0,scan}+1>=total) ? '0:scan+1'b1;
      if(!issued[scan] && dependencies && selected>=0)begin
       issued[scan]<=1;unit_start[selected]<=1;unit_active[selected]<=1;
       unit_command[selected]<=commands[scan];unit_node[selected]<=scan;
       if(selected<2)turn<=!selected[0];
      end
      completed_count<=completed_count+(IW+1)'(finishes);
      for(integer u=0;u<5;u++)if(unit_active[u] && !unit_start[u] && unit_done[u])begin
       completed_mask[unit_node[u]]<=1;unit_active[u]<=0;completion_pulse[u]<=1;
      end
     end
    end
   end
  end
 end
endmodule
