// One outstanding descriptor; ready means ALL external SRAM reads have drained.
// Slot reservations protect results even before their producer has completed.
module self_result_handoff #(
 parameter integer MAX_TASKS=64, IW=$clog2(MAX_TASKS)
)(
 input logic clk,rst_n,clear,cancel,
 input logic program_accept,input logic [IW-1:0] program_index,
 input logic program_result_valid,program_allocate_valid,
 input logic [2:0] program_allocate_slot,
 input logic [31:0] program_result_frame,program_result_addr,program_result_bytes,
 input logic [IW-1:0] candidate_node,input logic reserve_commit,
 input logic [MAX_TASKS-1:0] completed_mask,
 input logic result_ready,
 output wire result_valid,
 output logic [31:0] result_frame,result_addr,result_bytes,
 output wire [7:0] result_error,
 output logic result_accept,
 output logic [7:0] external_hold,
 output wire outputs_pending,
 output logic configuration_error
);
 logic is_result[MAX_TASKS];logic [2:0] slots[MAX_TASKS];
 logic [31:0] frames[MAX_TASKS],addresses[MAX_TASKS],lengths[MAX_TASKS];
 logic [IW-1:0] owners[8];
 logic [31:0] slot_frame[8],slot_addr[8],slot_bytes[8];
 logic presenting;logic [2:0] selected,turn;integer pick;
 assign result_valid=presenting && !clear && !cancel && !configuration_error;
 assign result_error=0; // Only successful, drained results are published.
 assign outputs_pending=|external_hold;
 always_comb begin
  pick=-1;
  for(integer k=0;k<8;k++)
   if(pick<0 && external_hold[(int'(turn)+k)%8] && completed_mask[owners[(int'(turn)+k)%8]])
    pick=(int'(turn)+k)%8;
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   presenting<=0;selected<=0;turn<=0;external_hold<=0;result_accept<=0;
   result_frame<=0;result_addr<=0;result_bytes<=0;configuration_error<=0;
   for(integer i=0;i<8;i++)begin owners[i]<=0;slot_frame[i]<=0;slot_addr[i]<=0;slot_bytes[i]<=0;end
  end else if(clear || cancel)begin
   presenting<=0;external_hold<=0;result_accept<=0;turn<=0;
   if(clear)configuration_error<=0;
  end else begin
   result_accept<=0;
   if(program_accept)begin
    is_result[program_index]<=program_result_valid;slots[program_index]<=program_allocate_slot;
    frames[program_index]<=program_result_frame;addresses[program_index]<=program_result_addr;lengths[program_index]<=program_result_bytes;
    if(program_result_valid && (!program_allocate_valid || program_result_bytes==0 ||
       ({1'b0,program_result_addr}+{1'b0,program_result_bytes})>33'h100000000))configuration_error<=1;
   end
   if(reserve_commit && is_result[candidate_node])begin
    external_hold[slots[candidate_node]]<=1;owners[slots[candidate_node]]<=candidate_node;
    slot_frame[slots[candidate_node]]<=frames[candidate_node];
    slot_addr[slots[candidate_node]]<=addresses[candidate_node];slot_bytes[slots[candidate_node]]<=lengths[candidate_node];
   end
   if(result_valid && result_ready)begin
    external_hold[selected]<=0;presenting<=0;result_accept<=1;turn<=selected+3'd1;
   end else if(!presenting && pick>=0)begin
    selected<=3'(pick);presenting<=1;
    result_frame<=slot_frame[pick];result_addr<=slot_addr[pick];result_bytes<=slot_bytes[pick];
   end
  end
 end
endmodule
