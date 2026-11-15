// Static physical slot plan, runtime generation ownership and lifetime enforcement.
// The compiler declares ALL terminal consumers; their drained completions release
// a lease. Data addresses remain operator-native, no memory protocol substitution.
module self_buffer_leases #(
 parameter integer MAX_TASKS=64, IW=$clog2(MAX_TASKS)
)(
 input logic clk,rst_n,clear,cancel,
 input logic program_accept,input logic [IW-1:0] program_index,
 input logic program_allocate_valid,input logic [2:0] program_allocate_slot,
 input logic [MAX_TASKS-1:0] program_hold_mask,
 input logic [2:0] program_use_valid,input logic [8:0] program_use_slots,input logic [3*IW-1:0] program_use_owners,
 input logic [IW-1:0] candidate_node,input logic reserve_commit,
 input logic [MAX_TASKS-1:0] completed_mask,
 input logic [7:0] external_hold,
 output logic buffer_ready,
 output logic [7:0] buffer_live,
 output wire [7:0] buffer_release,
 output logic [7:0] buffer_allocate,
 output wire [8*IW-1:0] buffer_owners
);
 logic alloc[MAX_TASKS];logic [2:0] slot[MAX_TASKS],uses[MAX_TASKS];
 logic [8:0] use_slots[MAX_TASKS];logic [3*IW-1:0] use_owners[MAX_TASKS];
 logic [MAX_TASKS-1:0] hold[MAX_TASKS],pending[8];
 logic [IW-1:0] owner[8];logic [7:0] releasable;
 for(genvar i=0;i<8;i++)assign buffer_owners[i*IW+:IW]=owner[i];
 assign buffer_release=cancel ? 0:releasable;
 always_comb begin
  releasable=0;
  for(integer b=0;b<8;b++)
   if(buffer_live[b] && !external_hold[b] && (pending[b]&completed_mask)==pending[b])releasable[b]=1;
  buffer_ready=!cancel && (!alloc[candidate_node] || !buffer_live[slot[candidate_node]]);
  for(integer u=0;u<3;u++)if(uses[candidate_node][u])
   if(!buffer_live[use_slots[candidate_node][u*3+:3]] ||
      owner[use_slots[candidate_node][u*3+:3]]!=use_owners[candidate_node][u*IW+:IW])buffer_ready=0;
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   buffer_live<=0;buffer_allocate<=0;
   for(integer i=0;i<8;i++)begin owner[i]<=0;pending[i]<=0;end
  end else if(clear || cancel)begin buffer_live<=0;buffer_allocate<=0;end
  else begin
   buffer_allocate<=0;
   if(program_accept)begin
    alloc[program_index]<=program_allocate_valid;slot[program_index]<=program_allocate_slot;
    // Always retain the producer itself, even when there are no consumers.
    hold[program_index]<=program_hold_mask | (MAX_TASKS'(1)<<program_index);
    uses[program_index]<=program_use_valid;use_slots[program_index]<=program_use_slots;use_owners[program_index]<=program_use_owners;
   end
   for(integer i=0;i<8;i++)if(releasable[i])buffer_live[i]<=0;
   if(reserve_commit && alloc[candidate_node])begin
    buffer_live[slot[candidate_node]]<=1;buffer_allocate[slot[candidate_node]]<=1;
    owner[slot[candidate_node]]<=candidate_node;pending[slot[candidate_node]]<=hold[candidate_node];
   end
  end
 end
endmodule
