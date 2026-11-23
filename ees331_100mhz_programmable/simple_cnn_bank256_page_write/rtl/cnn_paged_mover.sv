// CNN memory backed by the storage_v2 DATA MOVER and tile BRAM.
// Parameterized local RAM is divided into fully associative 1 KiB pages.
// Two independent compute banks serve resident pages while one linear DMA
// port transfers a page. A miss locks only its selected physical page slot.
module cnn_paged_mover #(
 parameter bit READ64=1, parameter bit PACKED_WRITE=1,
 parameter integer WRITE_BITS=256,
 parameter integer CLIENTS=23,
 parameter integer LOCAL_BYTES=32768,
 parameter integer PAGE_BYTES=1024,
 parameter bit ENABLE_FAST_HIT=1'b1,
 parameter logic [31:0] LOGICAL_BYTES=32'h04000000,
 parameter logic [31:0] DDR_BASE=32'h10000000
)(
 input logic clk,rst_n,
 input wire [CLIENTS-1:0] cnn_valid,cnn_write,cnn_byte,cnn_double,cnn_wide,
 // Nonzero length is carried only on the first accepted write beat.
 input wire [CLIENTS*6-1:0] cnn_burst_len,
 input wire [CLIENTS*32-1:0] cnn_addr,
 input wire [CLIENTS*WRITE_BITS-1:0] cnn_wdata,
 output logic [CLIENTS-1:0] cnn_ready,
 output wire [CLIENTS-1:0] cnn_response,
 output wire [CLIENTS*64-1:0] cnn_rdata,
 input wire cnn_cancel,
 output logic cnn_mem_fault,
 input logic [31:0] cache_csr_addr,cache_csr_wdata,
 input logic cache_csr_re,cache_csr_we,
 output logic [31:0] cache_csr_rdata,
 output wire cache_csr_ready,
 output wire [31:0] S_AXI_HP0_AWADDR,S_AXI_HP0_ARADDR,
 output wire [63:0] S_AXI_HP0_WDATA,
 input wire [63:0] S_AXI_HP0_RDATA,
 output wire [5:0] S_AXI_HP0_AWID,S_AXI_HP0_ARID,S_AXI_HP0_WID,
 input wire [5:0] S_AXI_HP0_BID,S_AXI_HP0_RID,
 output wire [3:0] S_AXI_HP0_AWLEN,S_AXI_HP0_ARLEN,
 output wire [2:0] S_AXI_HP0_AWSIZE,S_AXI_HP0_ARSIZE,
 output wire [1:0] S_AXI_HP0_AWBURST,S_AXI_HP0_ARBURST,
 output wire [1:0] S_AXI_HP0_AWLOCK,S_AXI_HP0_ARLOCK,
 output wire [3:0] S_AXI_HP0_AWCACHE,S_AXI_HP0_ARCACHE,
 output wire [2:0] S_AXI_HP0_AWPROT,S_AXI_HP0_ARPROT,
 output wire [3:0] S_AXI_HP0_AWQOS,S_AXI_HP0_ARQOS,
 output wire [7:0] S_AXI_HP0_WSTRB,
 output wire S_AXI_HP0_AWVALID,S_AXI_HP0_WVALID,S_AXI_HP0_WLAST,
 output wire S_AXI_HP0_BREADY,S_AXI_HP0_ARVALID,S_AXI_HP0_RREADY,
 input wire S_AXI_HP0_AWREADY,S_AXI_HP0_WREADY,S_AXI_HP0_BVALID,
 input wire S_AXI_HP0_ARREADY,S_AXI_HP0_RVALID,S_AXI_HP0_RLAST,
 input wire [1:0] S_AXI_HP0_BRESP,S_AXI_HP0_RRESP
);
 localparam integer WRITE_BYTES=WRITE_BITS/8;
 localparam integer WRITE_ALIGNMENT=$clog2(WRITE_BYTES);
 // Four request entries per client. Upstream ready depends only on a
 // registered occupancy, never on its current address or bank grant. There is
 // no fall-through path on a full FIFO. Cache replies retain client order.
 wire [CLIENTS-1:0] queued_double,queued_wide;
 wire [CLIENTS-1:0] queued_valid,queued_write,queued_byte,queued_bad,queued_page_match;
 wire [CLIENTS-1:0] queued_head,queued_body,queued_notify,burst_receiving;
 logic [CLIENTS-1:0] burst_live;
 wire burst_open=(|burst_receiving) || (|burst_live);
 wire [CLIENTS*32-1:0] queued_addr;
 wire [CLIENTS*WRITE_BITS-1:0] committed_wdata;
 logic [CLIENTS-1:0] queued_ready;
 wire queue_empty=!(|queued_valid);
 for(genvar c=0;c<CLIENTS;c++)begin:request_queue
  logic [1:0] head,tail;
  logic [2:0] count;
  (* ram_style="distributed" *) logic [39:0] entries[4];
  (* ram_style="distributed" *) logic [WRITE_BITS-1:0] payload[4];
  logic [39:0] front;
  logic [1:0] popped_index;
  logic page_match;
  wire [1:0] next_head=head+2'd1;
  wire [39:0] next_entry=entries[next_head];
  logic [5:0] recv_left;
  logic [31:0] next_write_addr;
  wire [31:0] write_addr=cnn_addr[c*32+:32];
  wire [5:0] write_len=cnn_burst_len[c*6+:6];
  wire burst_body=recv_left!=0;
  wire burst_head=!burst_body && write_len!=0;
  wire notify=!burst_head && (!burst_body || recv_left==1);
  assign burst_receiving[c]=burst_body;
  wire [39:0] input_entry={burst_head,burst_body,notify,input_bad,PACKED_WRITE && cnn_wide[c],READ64 && cnn_double[c],cnn_write[c],cnn_byte[c],cnn_addr[c*32+:32]};
  assign queued_page_match[c]=page_match;
  assign queued_valid[c]=count!=0;
  assign {queued_head[c],queued_body[c],queued_notify[c],queued_bad[c],queued_wide[c],queued_double[c],queued_write[c],queued_byte[c],queued_addr[c*32+:32]}=front;
  assign committed_wdata[c*WRITE_BITS+:WRITE_BITS]=payload[popped_index];
  assign cnn_ready[c]=rst_n && count<4 && !cnn_cancel && !cnn_mem_fault &&
    !mover_fault_locked && (!pend_valid || burst_body) && !cache_csr_we;
  // Protection configuration is writable only when queues and pending
  // requests are empty. Record classification at ingress, outside arbitration.
  wire burst_write=WRITE_BITS==256 && PACKED_WRITE && cnn_wide[c] && cnn_write[c];
  wire [31:0] burst_bytes={21'd0,write_len,5'd0};
  wire bad_header=burst_head && (!burst_write || write_len<2 || write_len>32 ||
    (write_addr & 32'(PAGE_BYTES-1))+burst_bytes>PAGE_BYTES ||
    write_addr>=LOGICAL_BYTES || burst_bytes>LOGICAL_BYTES-write_addr);
  wire bad_body=burst_body && (!burst_write || write_len!=0 || write_addr!=next_write_addr);
  wire input_bad=bad_header || bad_body || cnn_addr[c*32+:32]>=LOGICAL_BYTES ||
    (!cnn_byte[c] && cnn_addr[c*32+:2]!=0) ||
    (READ64 && cnn_double[c] && (cnn_byte[c] || cnn_write[c] || cnn_addr[c*32+:3]!=0 || LOGICAL_BYTES-cnn_addr[c*32+:32]<8)) ||
    (PACKED_WRITE && cnn_wide[c] && (!cnn_write[c] || cnn_double[c] || cnn_byte[c] || cnn_addr[c*32+:WRITE_ALIGNMENT]!=0 || cnn_addr[c*32+:32]>32'(LOGICAL_BYTES-WRITE_BYTES))) ||
    (cnn_write[c] && protect_enable && cnn_addr[c*32+:32]<readonly_end);
  wire push=cnn_valid[c] && cnn_ready[c];
  wire pop=queued_valid[c] && queued_ready[c];
  always_ff @(posedge clk)begin
   if(push)entries[tail]<=input_entry;
   if(push && cnn_write[c])payload[tail]<=cnn_wdata[c*WRITE_BITS+:WRITE_BITS];
   // Capture only the selected slot on the grant edge. If it gets reused,
   // the payload stage samples the old word before that edge's RAM write.
   if(pop)popped_index<=head;
   // Show-ahead register: a simultaneous push replacing the only entry
   // bypasses the RAM read/write collision. No combinational fall-through.
   if(push && (count==0 || (pop && count==1)))begin
    front<=input_entry;
    page_match<=hint_page[c]==cnn_addr[c*32+PB+:TAG_BITS];
   end else if(pop && count>1)begin
    front<=next_entry;
    page_match<=hint_page[c]==next_entry[PB+:TAG_BITS];
   end else page_match<=hint_page[c]==front[PB+:TAG_BITS];
   if(!rst_n || cnn_cancel || cnn_mem_fault || mover_fault_locked)begin
    head<=0;tail<=0;count<=0;recv_left<=0;next_write_addr<=0;
   end else begin
    if(push)begin
     tail<=tail+1'b1;
     if(burst_head && !input_bad)recv_left<=write_len-1'b1;
     if(burst_body)recv_left<=recv_left-1'b1;
     if(burst_head || burst_body)next_write_addr<=write_addr+32'd32;
    end
    if(pop)head<=head+1'b1;
    case({push,pop})
     2'b10:count<=count+1'b1;
     2'b01:count<=count-1'b1;
     default:;
    endcase
   end
  end
`ifndef SYNTHESIS
  always_ff @(posedge clk)if(rst_n && !cnn_cancel && !cnn_mem_fault && !mover_fault_locked)begin
   assert(count<=4)else $fatal(1,"request FIFO overflow");
   if(pop)assert(count!=0)else $fatal(1,"request FIFO underflow");
  end
`endif
 end
 localparam integer SLOTS=LOCAL_BYTES/PAGE_BYTES;
 localparam integer SLOTS_PER_BANK=SLOTS/2;
 // Both the current 192 KiB layout and the original 392 KiB layout use
 // two compute banks. Preserve the scalar-bank mapping of legacy sizes.
 localparam bit TWO_BANKS=LOCAL_BYTES==192*1024 || LOCAL_BYTES==392*1024;
 localparam integer PB=$clog2(PAGE_BYTES), SB=$clog2(SLOTS);
 localparam integer CW=(CLIENTS<=1)?1:$clog2(CLIENTS);
 localparam integer LOOKUP_LEAVES=2**$clog2(SLOTS);
 localparam integer LOOKUP_GROUPS=LOOKUP_LEAVES>8 ? LOOKUP_LEAVES/8 : 1;
 localparam integer TAG_BITS=LOGICAL_BYTES>PAGE_BYTES ? $clog2(LOGICAL_BYTES/PAGE_BYTES) : 1;
 localparam integer GRANT_LEAVES=2**$clog2(CLIENTS);
 // Slot addresses are contiguous within each bank; allocation alternates banks.
 function automatic logic [1:0] bank_of_slot(input logic [SB-1:0] slot);
  if(TWO_BANKS)bank_of_slot=slot>=SB'(SLOTS_PER_BANK)?2'd1:2'd0;
  else bank_of_slot=2'd0;
 endfunction
 function automatic logic [SB-1:0] slot_from_turn(input logic [SB-1:0] turn);
  if(TWO_BANKS)
   slot_from_turn=turn[0]?(SB'(SLOTS_PER_BANK)+(turn>>1)):(turn>>1);
  else slot_from_turn=turn;
 endfunction
 typedef enum logic [2:0] {IDLE,ACCESS,DRAIN,WB_REQ,WB_WAIT,FILL_REQ,FILL_WAIT,SCAN} state_t;
 state_t state;
 logic [SLOTS-1:0] valid_page,dirty_page;
 logic [TAG_BITS-1:0] page_number[0:SLOTS-1];
 logic [SB:0] scan_idx;
 logic [SB-1:0] wb_slot;
 logic wb_for_scan,scan_invalidate,drop_response,csr_error,pend_valid,pend_invalidate;
 logic [31:0] pend_start,pend_end,scan_start,scan_end;
 logic [31:0] range_start,range_bytes,readonly_end;
 logic protect_enable;
 logic [31:0] hits,misses,writebacks,fills,ddr_read_bytes,ddr_write_bytes,wait_cycles;
 logic [CW-1:0] round_robin,request_owner;
 logic [CW-1:0] bank_round_robin[2];
 logic [CLIENTS-1:0] hint_valid;
 logic [SB-1:0] hint_slot[CLIENTS];
 logic [1:0] hint_bank[CLIENTS];
 logic [TAG_BITS-1:0] hint_page[CLIENTS];
 logic [SB-1:0] request_slot,victim_turn;
 logic [31:0] request_addr;
 logic [WRITE_BITS-1:0] request_wdata;
 logic request_payload_pending;
 logic request_write,request_byte,request_double,request_wide;
 logic [1:0] issue_valid,reply_valid;
 // Per beat: {releases the burst's slot, returns a client completion}.
 logic [1:0][1:0] issue_mark,bank_mark,reply_mark,bank_reply_mark;
 logic selected_burst,selected_notify,request_burst,request_notify;
 logic [CLIENTS-1:0] beat_return;
 logic [1:0][CW-1:0] issue_owner,reply_owner;
 logic [1:0][SB-1:0] issue_slot;
 logic [1:0][31:0] issue_addr;
 logic [1:0] issue_replay;
 logic [1:0] bank_valid,bank_write,bank_byte,bank_double,bank_wide;
 logic [1:0][CW-1:0] bank_owner;
 logic [1:0][SB-1:0] bank_slot;
 logic [1:0][31:0] bank_addr;
 logic [1:0][WRITE_BITS-1:0] bank_wdata;
 logic [1:0] issue_write,issue_byte,reply_write,reply_byte,issue_double,issue_wide;
 logic [1:0][1:0] reply_byte_offset;
 logic [CLIENTS-1:0] response_q;
 logic [CLIENTS*64-1:0] rdata_q;
 wire [31:0] request_page={request_addr[31:PB],{PB{1'b0}}};
 wire [31:0] old_page=32'(page_number[wb_slot])<<PB;
 wire [31:0] wb_local=32'(wb_slot)*PAGE_BYTES;
 logic scan_phase,scan_valid_q,scan_dirty_q;
 logic [TAG_BITS-1:0] scan_tag_q;
 logic [SB-1:0] scan_slot_q;
 wire [31:0] scan_page=32'(scan_tag_q)<<PB;
 wire scan_match=scan_valid_q && scan_page<scan_end &&
                 scan_page[31:PB]>=scan_start[31:PB];

 logic [CW-1:0] selected,next_owner;
 logic lookup_pending,lookup_result_pending,selected_valid,selected_bad,selected_double,selected_wide;
 logic [31:0] selected_addr;
 logic selected_write,selected_byte;
 logic page_hit,free_found;
 logic [SB-1:0] hit_slot,free_slot;
 wire [2*LOOKUP_LEAVES-1:1] hit_tree,free_tree;
 wire [SB-1:0] hit_slot_tree[1:2*LOOKUP_LEAVES-1];
 wire [SB-1:0] free_slot_tree[1:2*LOOKUP_LEAVES-1];
 wire [2*LOOKUP_GROUPS-1:1] group_hit;
 wire [SB-1:0] group_slot[1:2*LOOKUP_GROUPS-1];
 // A balanced lookup avoids a 392-entry serial priority path from the
 // requester through page selection into the miss engine.
 for(genvar s=0;s<LOOKUP_LEAVES;s++)begin:lookup_leaf
  if(s<SLOTS)begin:present
   assign hit_tree[LOOKUP_LEAVES+s]=valid_page[s] &&
    page_number[s]==selected_addr[PB+:TAG_BITS];
   assign free_tree[LOOKUP_LEAVES+s]=!valid_page[s];
  end else begin:absent
   assign hit_tree[LOOKUP_LEAVES+s]=0;
   assign free_tree[LOOKUP_LEAVES+s]=0;
  end
  assign hit_slot_tree[LOOKUP_LEAVES+s]=SB'(s);
  assign free_slot_tree[LOOKUP_LEAVES+s]=SB'(s);
 end
 for(genvar n=1;n<LOOKUP_LEAVES;n++)begin:lookup_branch
  if(n>=LOOKUP_GROUPS)begin:page_hits
   assign hit_tree[n]=hit_tree[2*n] || hit_tree[2*n+1];
   assign hit_slot_tree[n]=hit_tree[2*n] ?
    hit_slot_tree[2*n] : hit_slot_tree[2*n+1];
  end
  assign free_tree[n]=free_tree[2*n] || free_tree[2*n+1];
  assign free_slot_tree[n]=free_tree[2*n] ?
   free_slot_tree[2*n] : free_slot_tree[2*n+1];
 end
 for(genvar n=LOOKUP_GROUPS;n<2*LOOKUP_GROUPS;n++)begin:lookup_group
  logic hit_q;
  logic [SB-1:0] slot_q;
  always_ff @(posedge clk)begin
   hit_q<=hit_tree[n];
   slot_q<=hit_slot_tree[n];
  end
  assign group_hit[n]=hit_q;
  assign group_slot[n]=slot_q;
 end
 for(genvar n=1;n<LOOKUP_GROUPS;n++)begin:lookup_merge
  assign group_hit[n]=group_hit[2*n] || group_hit[2*n+1];
  assign group_slot[n]=group_hit[2*n] ? group_slot[2*n] : group_slot[2*n+1];
 end
 // Separate the final 64-group priority merge from bank arbitration.
 always_ff @(posedge clk)begin
  page_hit<=group_hit[1];
  hit_slot<=group_slot[1];
 end
 assign free_found=free_tree[1];
 assign free_slot=free_slot_tree[1];
 wire [SB-1:0] turn_slot=slot_from_turn(victim_turn);
 wire [SB-1:0] alloc_slot=!valid_page[turn_slot] ? turn_slot :
                           (free_found ? free_slot : turn_slot);
 logic [CLIENTS-1:0] bad_client,fast_hint;
 wire [1:0] fast_grant;
 wire [1:0][CW-1:0] fast_owner;
 wire [CLIENTS-1:0] bank_eligible[2],bank_after[2],bank_candidates[2];
 wire [1:0][2*GRANT_LEAVES-1:1] grant_tree;
 wire [1:0][2*GRANT_LEAVES-1:1][CW-1:0] grant_index_tree;
 // Multi-outstanding clients must not cross slow/fast paths or banks
 // before all earlier replies drain: no IDs exist on the client interface.
 logic [CLIENTS-1:0][2:0] client_pending;
 logic [CLIENTS-1:0] client_slow;
 logic [CLIENTS-1:0][1:0] client_bank;
 logic slow_take;
 logic [2:0] hit_incr,hit_incr_q;
 wire miss_serving=(state==WB_REQ || state==WB_WAIT ||
                    state==FILL_REQ || state==FILL_WAIT) && !wb_for_scan;
 wire can_accept=!(pend_valid && queue_empty && !burst_open) && !cnn_mem_fault && !mover_fault_locked &&
                 !cnn_cancel;
 logic alloc_locked;
 always_comb begin
  alloc_locked=0;
  for(integer c=0;c<CLIENTS;c++)
   if(burst_live[c] && hint_slot[c]==alloc_slot)alloc_locked=1;
 end
 wire selected_miss=can_accept && state==IDLE && selected_valid && !selected_bad && !page_hit;
 wire will_allocate=selected_miss && !alloc_locked;
 always_comb begin
  for(integer c=0;c<CLIENTS;c++)begin
   // A four-byte aligned access below the page-aligned limit fits in range.
   bad_client[c]=queued_bad[c];
   fast_hint[c]=queued_valid[c] && !bad_client[c] && hint_valid[c] &&
    (queued_body[c] ? burst_live[c] : ENABLE_FAST_HIT && queued_page_match[c]);
  end
 end
 for(genvar b=0;b<2;b++)begin:grant_bank
  for(genvar c=0;c<CLIENTS;c++)begin:grant_client
   assign bank_eligible[b][c]=can_accept && (state==IDLE || miss_serving) &&
    !(selected_valid && page_hit && !selected_bad && bank_of_slot(hit_slot)==2'(b)) && fast_hint[c] &&
    client_pending[c]<(burst_live[c] ? 3'd7 : 3'd4) &&
    !(queued_head[c] && will_allocate && hint_slot[c]==alloc_slot) &&
    (client_pending[c]==0 || (!client_slow[c] && client_bank[c]==2'(b))) &&
    hint_bank[c]==2'(b) &&
    (!miss_serving || hint_slot[c]!=request_slot);
   assign bank_after[b][c]=bank_eligible[b][c] &&
    c>=int'(bank_round_robin[b]);
  end
  assign bank_candidates[b]= (|bank_after[b]) ? bank_after[b] : bank_eligible[b];
  for(genvar c=0;c<GRANT_LEAVES;c++)begin:grant_leaf
   if(c<CLIENTS)assign grant_tree[b][GRANT_LEAVES+c]=bank_candidates[b][c];
   else assign grant_tree[b][GRANT_LEAVES+c]=0;
   assign grant_index_tree[b][GRANT_LEAVES+c]=CW'(c);
  end
  for(genvar n=1;n<GRANT_LEAVES;n++)begin:grant_branch
   assign grant_tree[b][n]=grant_tree[b][2*n] || grant_tree[b][2*n+1];
   assign grant_index_tree[b][n]=grant_tree[b][2*n] ?
    grant_index_tree[b][2*n] : grant_index_tree[b][2*n+1];
  end
  assign fast_grant[b]=grant_tree[b][1];
  assign fast_owner[b]=grant_index_tree[b][1];
 end
 wire [CLIENTS-1:0] slow_eligible,slow_after;
 for(genvar c=0;c<CLIENTS;c++)begin:slow_candidates
  assign slow_eligible[c]=queued_valid[c] && (!queued_body[c] || bad_client[c]) && !fast_hint[c] && client_pending[c]==0;
  assign slow_after[c]=slow_eligible[c] && CW'(c)>=round_robin;
 end
 wire [CLIENTS-1:0] slow_priority=(|slow_after)?slow_after:slow_eligible;
 always_comb begin
  next_owner='0;
  for(integer c=CLIENTS-1;c>=0;c--)
   if(slow_priority[c])next_owner=CW'(c);
 end
 // Register the requester, then the local lookup group, before accepting
 // a slow request. Discard the lookup when a refill reaches ACCESS.
 always_ff @(posedge clk)begin
  if(!rst_n || !can_accept || !(state==IDLE || miss_serving))begin
   lookup_pending<=0;lookup_result_pending<=0;
   selected_valid<=0;
  end else begin
   selected_valid<=lookup_result_pending;
   lookup_result_pending<=lookup_pending;
   lookup_pending<=0;
   if(!selected_valid && !lookup_pending && !lookup_result_pending && (|slow_priority))begin
    lookup_pending<=1;
    selected<=next_owner;
    selected_addr<=queued_addr[next_owner*32+:32];
    selected_write<=queued_write[next_owner];
    selected_byte<=queued_byte[next_owner];
    selected_double<=queued_double[next_owner];
    selected_wide<=queued_wide[next_owner];
    selected_bad<=bad_client[next_owner];
    selected_burst<=queued_head[next_owner];
    selected_notify<=queued_notify[next_owner];
   end
  end
 end
 always_comb begin
  queued_ready='0;slow_take=0;
  for(integer b=0;b<2;b++)if(fast_grant[b])queued_ready[fast_owner[b]]=1;
  if(can_accept && selected_valid &&
    ((state==IDLE && (selected_bad || page_hit || !alloc_locked)) || (miss_serving && !selected_bad && page_hit &&
                     hit_slot!=request_slot)))begin
   queued_ready[selected]=1;slow_take=1;
  end
 end
 always_comb begin
  hit_incr=0;
  for(integer b=0;b<2;b++)if(fast_grant[b])hit_incr=hit_incr+3'd1;
  if(slow_take && !selected_bad && page_hit)hit_incr=hit_incr+3'd1;
 end
 // Counter carry propagation must not share a cycle with arbitration.
 // Maintenance becomes idle only after the longer response pipeline drains,
 // so software observes the complete count after waiting for quiescence.
 always_ff @(posedge clk)if(!rst_n)hit_incr_q<=0;else hit_incr_q<=hit_incr;
 assign cnn_response=(cnn_cancel || cnn_mem_fault || mover_fault_locked) ? '0 : response_q;
 assign cnn_rdata=rdata_q;
 assign cache_csr_ready=1'b1;

 logic [1:0] comp_req,comp_we,comp_byte;
 logic [1:0][CW-1:0] comp_owner;
 logic [1:0][SB-1:0] comp_slot;
 logic [1:0][31:0] comp_logical_addr,comp_addr;
 logic [1:0][WRITE_BITS-1:0] comp_wdata;
 logic [1:0][3:0] comp_wstrb;
 wire [1:0][63:0] comp_rdata;
 wire [1:0] comp_error;
 logic [1:0] bank_reply_valid,bank_reply_error;
 logic [1:0][CW-1:0] bank_reply_owner;
 logic [1:0][63:0] bank_reply_data;
 wire [1:0][7:0] read_byte;
 for(genvar b=0;b<2;b++)assign read_byte[b]=
    comp_rdata[b][reply_byte_offset[b]*8+:8];
 always_comb begin
  for(integer b=0;b<2;b++)begin
   logic [31:0] local_addr;
   logic [WRITE_BITS-1:0] source_wdata;
   // Use only the paired control and data at the registered bank stage.
   comp_req[b]=bank_valid[b] && !cnn_cancel && !cnn_mem_fault && !mover_fault_locked;
   comp_owner[b]=bank_owner[b];
   comp_slot[b]=bank_slot[b];
   comp_logical_addr[b]=bank_addr[b];
   source_wdata=bank_wdata[b];
   comp_we[b]=bank_write[b];
   comp_byte[b]=bank_byte[b];
   local_addr=32'(comp_slot[b])*PAGE_BYTES+
     (comp_logical_addr[b] & 32'(PAGE_BYTES-1));
   comp_addr[b]={local_addr[31:2],2'b00};
   comp_wdata[b]=comp_byte[b] ?
     ({{(WRITE_BITS-8){1'b0}},source_wdata[7:0]} << (comp_logical_addr[b][1:0]*8)) : source_wdata;
   comp_wstrb[b]=comp_byte[b] ? (4'b1 << comp_logical_addr[b][1:0]) : 4'hf;
  end
 end

 // Payload stage follows the registered grant. No grant or FIFO pop
 // signal drives write enables on these wide data registers.
 for(genvar b=0;b<2;b++)begin:bank_payload_stage
  always_ff @(posedge clk)begin
   if(!rst_n || cnn_cancel || cnn_mem_fault || mover_fault_locked)bank_valid[b]<=0;
   else bank_valid[b]<=issue_valid[b];
   bank_wdata[b]<=issue_replay[b]?request_wdata:committed_wdata[issue_owner[b]*WRITE_BITS+:WRITE_BITS];
   if(issue_valid[b])begin
    bank_owner[b]<=issue_owner[b];
    bank_slot[b]<=issue_slot[b];
    bank_addr[b]<=issue_addr[b];
    bank_write[b]<=issue_write[b];
    bank_byte[b]<=issue_byte[b];
    bank_double[b]<=issue_double[b];
    bank_wide[b]<=issue_wide[b];
    bank_mark[b]<=issue_mark[b];
   end
  end
 end

 // Capture BRAM output formatting locally before the per-client return mux.
 always_ff @(posedge clk)begin
  if(!rst_n || cnn_cancel || cnn_mem_fault || mover_fault_locked)bank_reply_valid<=0;
  else bank_reply_valid<=reply_valid;
  for(integer b=0;b<2;b++)if(reply_valid[b])begin
   bank_reply_owner[b]<=reply_owner[b];bank_reply_error[b]<=comp_error[b];
   bank_reply_mark[b]<=reply_mark[b];
   bank_reply_data[b]<=reply_write[b] ? 0 :
    reply_byte[b] ? {32'd0,{24{read_byte[b][7]}},read_byte[b]} : comp_rdata[b];
  end
 end
 wire mover_cmd_valid=state==WB_REQ || state==FILL_REQ;
 wire mover_cmd_ready,mover_rsp_valid,mover_fault_locked,mover_drained,mover_busy;
 wire [31:0] mover_rsp_status,mover_rsp_bytes;
 wire [31:0] mover_cmd_src=state==WB_REQ ? wb_local : request_page;
 wire [31:0] mover_cmd_dst=state==WB_REQ ? old_page : 32'(request_slot)*PAGE_BYTES;
 wire [31:0] mover_cmd_flags=state==WB_REQ ? 32'd1 : 32'd0;
 wire mover_recover=cache_csr_we && cache_csr_addr[7:0]==8'h04 &&
                    cache_csr_wdata==3 && state==IDLE && !pend_valid &&
                     !(|issue_valid) && !(|bank_valid) && !(|reply_valid) && !(|bank_reply_valid);
 wire local_valid,local_write,local_ready,local_rsp_valid,local_error;
 wire [31:0] local_addr,local_wdata,local_rdata;
 wire [3:0] local_wstrb;
 tile_local_ram_bank2 #(.READ64(READ64),.PACKED_WRITE(PACKED_WRITE),.WRITE_BITS(WRITE_BITS),.BYTES(LOCAL_BYTES),.TWO_BANKS(TWO_BANKS),.DISJOINT_PORTS(1)) local_ram(
  .clk,.rst_n,.comp_req,.comp_we,.comp_addr,.comp_wdata,.comp_wstrb,
  .comp_rdata,.comp_double(bank_double),.comp_wide(bank_wide),.comp_error,.dma_valid(local_valid),.dma_write(local_write),
  .dma_ready(local_ready),.dma_addr(local_addr),.dma_wdata(local_wdata),
  .dma_wstrb(local_wstrb),.dma_rsp_valid(local_rsp_valid),.dma_error(local_error),
  .dma_rdata(local_rdata)
 );
 data_mover #(.TIMEOUT_CYCLES(100000)) mover(
  .clk,.rst_n,.enable(1'b1),.recover(mover_recover),
  .cfg_ddr_base(DDR_BASE),.cfg_ddr_bytes(LOGICAL_BYTES),.cfg_local_bytes(32'(LOCAL_BYTES)),
  .cmd_valid(mover_cmd_valid),.cmd_ready(mover_cmd_ready),
  .cmd_src(mover_cmd_src),.cmd_dst(mover_cmd_dst),.cmd_bytes(32'(PAGE_BYTES)),
  .cmd_flags(mover_cmd_flags),.rsp_valid(mover_rsp_valid),.rsp_ready(1'b1),
  .rsp_status(mover_rsp_status),.rsp_bytes_done(mover_rsp_bytes),
  .fault_locked(mover_fault_locked),.drained(mover_drained),.busy(mover_busy),
  .local_valid,.local_write,.local_ready,.local_addr,.local_wdata,
  .local_wstrb,.local_rsp_valid,.local_error,.local_rdata,
  .araddr(S_AXI_HP0_ARADDR),.awaddr(S_AXI_HP0_AWADDR),
  .arid(S_AXI_HP0_ARID),.awid(S_AXI_HP0_AWID),.wid(S_AXI_HP0_WID),
  .arlen(S_AXI_HP0_ARLEN),.awlen(S_AXI_HP0_AWLEN),
  .arsize(S_AXI_HP0_ARSIZE),.awsize(S_AXI_HP0_AWSIZE),
  .arburst(S_AXI_HP0_ARBURST),.awburst(S_AXI_HP0_AWBURST),
  .arlock(S_AXI_HP0_ARLOCK),.awlock(S_AXI_HP0_AWLOCK),
  .arcache(S_AXI_HP0_ARCACHE),.awcache(S_AXI_HP0_AWCACHE),
  .arqos(S_AXI_HP0_ARQOS),.awqos(S_AXI_HP0_AWQOS),
  .arprot(S_AXI_HP0_ARPROT),.awprot(S_AXI_HP0_AWPROT),
  .arvalid(S_AXI_HP0_ARVALID),.awvalid(S_AXI_HP0_AWVALID),
  .wvalid(S_AXI_HP0_WVALID),.wlast(S_AXI_HP0_WLAST),
  .rready(S_AXI_HP0_RREADY),.bready(S_AXI_HP0_BREADY),
  .arready(S_AXI_HP0_ARREADY),.awready(S_AXI_HP0_AWREADY),
  .wready(S_AXI_HP0_WREADY),.rvalid(S_AXI_HP0_RVALID),
  .rlast(S_AXI_HP0_RLAST),.bvalid(S_AXI_HP0_BVALID),
  .rdata(S_AXI_HP0_RDATA),.rid(S_AXI_HP0_RID),.bid(S_AXI_HP0_BID),
  .rresp(S_AXI_HP0_RRESP),.bresp(S_AXI_HP0_BRESP),
  .wdata(S_AXI_HP0_WDATA),.wstrb(S_AXI_HP0_WSTRB)
 );

 always_comb begin
  cache_csr_rdata=0;
  case(cache_csr_addr[7:0])
   8'h00:cache_csr_rdata={27'b0,(drop_response && state!=IDLE),
     (cnn_mem_fault || mover_fault_locked),csr_error,
     (state!=IDLE || pend_valid || !queue_empty || burst_open || (|issue_valid) || (|bank_valid) || (|reply_valid) || (|bank_reply_valid)),1'b1};
   8'h08:cache_csr_rdata=range_start;
   8'h0c:cache_csr_rdata=range_bytes;
   8'h10:cache_csr_rdata=readonly_end;
   8'h14:cache_csr_rdata={31'b0,protect_enable};
   8'h20:cache_csr_rdata=hits;
   8'h24:cache_csr_rdata=misses;
   8'h28:cache_csr_rdata=writebacks;
   8'h2c:cache_csr_rdata=fills;
   8'h30:cache_csr_rdata=ddr_read_bytes;
   8'h34:cache_csr_rdata=ddr_write_bytes;
   8'h38:cache_csr_rdata=wait_cycles;
   8'h3c:cache_csr_rdata=LOCAL_BYTES;
   default:;
  endcase
 end

 // One ordered response per client per cycle. Up to four accepted requests
 // may use a same-bank fixed-latency fast stream; slow requests are isolated.
 always_ff @(posedge clk)begin
  // A failed transaction produces no client reply. Drop all accepted
  // credits on a fabric fault before recovery reopens the request path.
  if(!rst_n || cnn_cancel || cnn_mem_fault || mover_fault_locked)begin client_pending<=0;client_slow<=0;client_bank<=0;end
  else for(integer c=0;c<CLIENTS;c++)begin
   case({(queued_valid[c] && queued_ready[c]),beat_return[c]})
    2'b10:client_pending[c]<=client_pending[c]+1'b1;
    2'b01:client_pending[c]<=client_pending[c]-1'b1;
    default:;
   endcase
   if(beat_return[c] && client_pending[c]==1)client_slow[c]<=0;
   if(slow_take && selected==c)client_slow[c]<=1;
   for(integer b=0;b<2;b++)if(fast_grant[b] && fast_owner[b]==c)begin
    client_bank[c]<=2'(b);client_slow[c]<=0;
   end
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n && !cnn_cancel && !cnn_mem_fault)begin
  for(integer c=0;c<CLIENTS;c++)begin
   if(!burst_live[c] && !beat_return[c])
    assert(client_pending[c]<=4) else $fatal(1,"client read credits exceeded");
   if(beat_return[c])assert(client_pending[c]!=0) else $fatal(1,"reply without accepted request");
   if(slow_take && selected==c)assert(client_pending[c]==0) else $fatal(1,"slow path overtakes outstanding read");
  end
  for(integer a=0;a<2;a++)for(integer b=a+1;b<2;b++)
   if(reply_valid[a] && reply_valid[b])assert(reply_owner[a]!=reply_owner[b]) else $fatal(1,"same-client response collision");
  for(integer b=0;b<2;b++)if(fast_grant[b])begin
   assert(hint_valid[fast_owner[b]] &&
     hint_page[fast_owner[b]]==queued_addr[fast_owner[b]*32+PB+:TAG_BITS])
     else $fatal(1,"registered FIFO page classification became stale");
  end
 end
`endif
 always_ff @(posedge clk) begin
  if(!rst_n)begin
   state<=IDLE;valid_page<='0;dirty_page<='0;scan_idx<=0;wb_slot<=0;scan_phase<=0;
   wb_for_scan<=0;scan_invalidate<=0;drop_response<=0;csr_error<=0;
   pend_valid<=0;pend_invalidate<=0;pend_start<=0;pend_end<=0;
   scan_start<=0;scan_end<=0;range_start<=0;range_bytes<=LOGICAL_BYTES;
   readonly_end<=0;protect_enable<=0;cnn_mem_fault<=0;
   hits<=0;misses<=0;writebacks<=0;fills<=0;
   ddr_read_bytes<=0;ddr_write_bytes<=0;wait_cycles<=0;
   round_robin<=0;request_owner<=0;request_slot<=0;victim_turn<=0;
   hint_valid<='0;burst_live<='0;beat_return<='0;
   issue_mark<=0;reply_mark<=0;request_burst<=0;request_notify<=0;
   for(integer c=0;c<CLIENTS;c++)begin hint_slot[c]<=0;hint_page[c]<=0;hint_bank[c]<=0;end
   for(integer b=0;b<2;b++)bank_round_robin[b]<=0;
   request_addr<=0;request_wdata<=0;request_payload_pending<=0;
   request_write<=0;request_byte<=0;request_double<=0;request_wide<=0;response_q<='0;rdata_q<='0;
   issue_valid<=0;reply_valid<=0;issue_owner<=0;reply_owner<=0;
   issue_slot<=0;issue_addr<=0;issue_replay<=0;
   issue_write<=0;issue_byte<=0;issue_double<=0;issue_wide<=0;reply_write<=0;reply_byte<=0;
   reply_byte_offset<=0;
  end else begin
   response_q<='0;
   beat_return<='0;
   issue_valid<=0;
   issue_replay<=0;
   if(request_payload_pending)begin
    request_payload_pending<=0;
    request_wdata<=committed_wdata[request_owner*WRITE_BITS+:WRITE_BITS];
   end
   reply_valid<=comp_req;
   hits<=hits+32'(hit_incr_q);
   for(integer b=0;b<2;b++)begin
    if(comp_req[b])begin
     reply_owner[b]<=comp_owner[b];
     reply_mark[b]<=bank_mark[b];
     reply_write[b]<=comp_we[b];
     reply_byte[b]<=comp_byte[b];
     reply_byte_offset[b]<=comp_logical_addr[b][1:0];
     if(comp_we[b])dirty_page[comp_slot[b]]<=1;
    end
    if(bank_reply_valid[b] && !cnn_cancel && !cnn_mem_fault && !mover_fault_locked)begin
     if(bank_reply_error[b])cnn_mem_fault<=1;
     else begin
      beat_return[bank_reply_owner[b]]<=1;
      if(bank_reply_mark[b][0])begin
       response_q[bank_reply_owner[b]]<=1;
       rdata_q[bank_reply_owner[b]*64+:64]<=bank_reply_data[b];
      end
      if(bank_reply_mark[b][1])burst_live[bank_reply_owner[b]]<=0;
     end
    end
    if(fast_grant[b])begin
     issue_valid[b]<=1;
     issue_owner[b]<=fast_owner[b];
     issue_slot[b]<=hint_slot[fast_owner[b]];
     issue_addr[b]<=queued_addr[fast_owner[b]*32+:32];
     issue_write[b]<=queued_write[fast_owner[b]];
     issue_byte[b]<=queued_byte[fast_owner[b]];
     issue_double[b]<=queued_double[fast_owner[b]];
     issue_wide[b]<=queued_wide[fast_owner[b]];
     issue_mark[b]<={queued_body[fast_owner[b]] && queued_notify[fast_owner[b]],queued_notify[fast_owner[b]]};
     if(queued_head[fast_owner[b]])burst_live[fast_owner[b]]<=1;
     bank_round_robin[b]<=fast_owner[b]==CW'(CLIENTS-1) ?
      '0 : fast_owner[b]+1'b1;
    end
   end
   if(cnn_cancel || cnn_mem_fault || mover_fault_locked)begin
    issue_valid<=0;reply_valid<=0;burst_live<=0;
   end
   // A page used by an in-flight write may not be evicted until the last
   // physical beat commits. Try the next victim if the current one is busy.
   if(selected_miss && alloc_locked)
    victim_turn<=victim_turn==SB'(SLOTS-1)?'0:victim_turn+1'b1;
   if(slow_take)begin
    round_robin<=selected==CW'(CLIENTS-1) ? '0 : selected+1'b1;
    if(!selected_bad && page_hit)begin
      hint_valid[selected]<=1;hint_slot[selected]<=hit_slot;
      hint_page[selected]<=selected_addr[PB+:TAG_BITS];
      hint_bank[selected]<=bank_of_slot(hit_slot);
      issue_valid[bank_of_slot(hit_slot)]<=1;
      issue_owner[bank_of_slot(hit_slot)]<=CW'(selected);
      issue_slot[bank_of_slot(hit_slot)]<=hit_slot;
      issue_addr[bank_of_slot(hit_slot)]<=selected_addr;
      issue_write[bank_of_slot(hit_slot)]<=selected_write;
      issue_byte[bank_of_slot(hit_slot)]<=selected_byte;
      issue_double[bank_of_slot(hit_slot)]<=selected_double;
      issue_wide[bank_of_slot(hit_slot)]<=selected_wide;
      issue_mark[bank_of_slot(hit_slot)]<={1'b0,selected_notify};
      if(selected_burst)burst_live[selected]<=1;
    end
   end else if(selected_valid && !pend_valid && !cnn_cancel &&
               !cnn_mem_fault && !mover_fault_locked &&
               miss_serving)begin
    // A second miss can hold valid high throughout a transfer. Rotate the
    // lookup owner so resident requests behind it still get a turn.
    round_robin<=selected==CW'(CLIENTS-1) ? '0 : selected+1'b1;
   end
   if(cnn_cancel && state!=IDLE)drop_response<=1;
   if(state==WB_WAIT || state==FILL_WAIT)wait_cycles<=wait_cycles+1;
   if(cache_csr_we)begin
    if(cache_csr_addr[1:0]!=0)csr_error<=1;
    else case(cache_csr_addr[7:0])
     8'h08:range_start<=cache_csr_wdata;
     8'h0c:range_bytes<=cache_csr_wdata;
     8'h10:if(state==IDLE && !pend_valid && queue_empty && !burst_open && !(|client_pending) && cache_csr_wdata<=LOGICAL_BYTES)
       readonly_end<=cache_csr_wdata;else csr_error<=1;
     8'h14:if(state==IDLE && !pend_valid && queue_empty && !burst_open && !(|client_pending))
       protect_enable<=cache_csr_wdata[0];else csr_error<=1;
     8'h04:case(cache_csr_wdata)
      1,2:if(!pend_valid && range_start<=LOGICAL_BYTES &&
             {1'b0,range_start}+{1'b0,range_bytes}<={1'b0,LOGICAL_BYTES})begin
       pend_start<=range_start;pend_end<=range_start+range_bytes;
       pend_valid<=1;pend_invalidate<=cache_csr_wdata==2;
      end else csr_error<=1;
      3:if(state==IDLE && !pend_valid)begin
       csr_error<=0;cnn_mem_fault<=0;
      end else csr_error<=1;
      default:csr_error<=1;
     endcase
     default:csr_error<=1;
    endcase
   end
   case(state)
     IDLE:if(pend_valid && queue_empty && !burst_open)begin
      if (!(|issue_valid) && !(|bank_valid) && !(|reply_valid) && !(|bank_reply_valid))begin
      pend_valid<=0;scan_start<=pend_start;scan_end<=pend_end;
      scan_invalidate<=pend_invalidate;scan_idx<=0;scan_phase<=0;state<=SCAN;
      drop_response<=0;
     end
    end else if(slow_take)begin
     drop_response<=0;
     if(selected_bad)cnn_mem_fault<=1;
     else if(!page_hit)begin
      request_owner<=CW'(selected);request_addr<=selected_addr;
      request_payload_pending<=1;
      request_write<=selected_write;request_byte<=selected_byte;
      request_double<=selected_double;
      request_wide<=selected_wide;
      request_burst<=selected_burst;request_notify<=selected_notify;
      misses<=misses+1;
      request_slot<=alloc_slot;
      wb_slot<=alloc_slot;
      for(integer c=0;c<CLIENTS;c++)
       if(hint_slot[c]==alloc_slot)hint_valid[c]<=0;
      victim_turn<=victim_turn==SB'(SLOTS-1)?'0:victim_turn+1'b1;
      wb_for_scan<=0;
      state<=DRAIN;
     end
    end
    ACCESS:begin
     if(!drop_response && !cnn_cancel && !cnn_mem_fault)begin
      issue_valid[bank_of_slot(request_slot)]<=1;
      issue_owner[bank_of_slot(request_slot)]<=request_owner;
      issue_slot[bank_of_slot(request_slot)]<=request_slot;
      issue_addr[bank_of_slot(request_slot)]<=request_addr;
      issue_replay[bank_of_slot(request_slot)]<=1;
      issue_write[bank_of_slot(request_slot)]<=request_write;
      issue_byte[bank_of_slot(request_slot)]<=request_byte;
      issue_double[bank_of_slot(request_slot)]<=request_double;
      issue_wide[bank_of_slot(request_slot)]<=request_wide;
      issue_mark[bank_of_slot(request_slot)]<={1'b0,request_notify};
      if(request_burst)burst_live[request_owner]<=1;
      hint_valid[request_owner]<=1;hint_slot[request_owner]<=request_slot;
      hint_page[request_owner]<=request_addr[PB+:TAG_BITS];
      hint_bank[request_owner]<=bank_of_slot(request_slot);
     end
     state<=IDLE;
    end
    DRAIN:if (!(|issue_valid) && !(|bank_valid) && !(|reply_valid) && !(|bank_reply_valid))
     state<=valid_page[request_slot] && dirty_page[request_slot] ? WB_REQ : FILL_REQ;
    WB_REQ:if(mover_cmd_ready)state<=WB_WAIT;
    WB_WAIT:if(mover_rsp_valid)begin
     if(mover_rsp_status!=0 || mover_rsp_bytes!=PAGE_BYTES)begin
      cnn_mem_fault<=1;csr_error<=1;state<=IDLE;
     end else begin
      dirty_page[wb_slot]<=0;writebacks<=writebacks+1;
      ddr_write_bytes<=ddr_write_bytes+PAGE_BYTES;
      if(wb_for_scan)begin
       if(scan_invalidate)begin
        valid_page[wb_slot]<=0;
        for(integer c=0;c<CLIENTS;c++)
         if(hint_slot[c]==wb_slot)hint_valid[c]<=0;
       end
       scan_idx<=scan_idx+1'b1;state<=SCAN;
      end else if(drop_response || cnn_cancel)state<=IDLE;
      else state<=FILL_REQ;
     end
    end
    FILL_REQ:if(mover_cmd_ready)state<=FILL_WAIT;
    FILL_WAIT:if(mover_rsp_valid)begin
     if(mover_rsp_status!=0 || mover_rsp_bytes!=PAGE_BYTES)begin
      cnn_mem_fault<=1;state<=IDLE;
     end else begin
      valid_page[request_slot]<=1;dirty_page[request_slot]<=0;
      page_number[request_slot]<=request_addr[PB+:TAG_BITS];
      fills<=fills+1;ddr_read_bytes<=ddr_read_bytes+PAGE_BYTES;
      state<=drop_response || cnn_cancel ? IDLE : ACCESS;
     end
    end
    SCAN:if(scan_idx==(SB+1)'(SLOTS))begin state<=IDLE;scan_phase<=0;end
     else if(!scan_phase)begin
      scan_tag_q<=page_number[scan_idx[SB-1:0]];
      scan_valid_q<=valid_page[scan_idx[SB-1:0]];
      scan_dirty_q<=dirty_page[scan_idx[SB-1:0]];
      scan_slot_q<=scan_idx[SB-1:0];scan_phase<=1;
     end else begin
      scan_phase<=0;
      if(scan_match && scan_dirty_q)begin
       wb_slot<=scan_slot_q;wb_for_scan<=1;state<=WB_REQ;
      end else begin
       if(scan_match && scan_invalidate)begin
        valid_page[scan_slot_q]<=0;
        for(integer c=0;c<CLIENTS;c++)
         if(hint_slot[c]==scan_slot_q)hint_valid[c]<=0;
       end
       scan_idx<=scan_idx+1'b1;
      end
     end
    default:state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 initial begin
  assert(CLIENTS>=1)else $fatal(1,"at least one CNN client required");
  assert(LOCAL_BYTES>=PAGE_BYTES*2 && LOCAL_BYTES%PAGE_BYTES==0 && PAGE_BYTES>=4 && (PAGE_BYTES&(PAGE_BYTES-1))==0)
   else $fatal(1,"paged mover geometry");
  assert(!TWO_BANKS || (PAGE_BYTES==1024 && SLOTS%2==0))
   else $fatal(1,"two-bank geometry requires paired 1 KiB pages");
  assert(LOGICAL_BYTES[PB-1:0]==0 && DDR_BASE[2:0]==0 &&
    {1'b0,DDR_BASE}+{1'b0,LOGICAL_BYTES}<=33'h100000000)
   else $fatal(1,"DDR aperture");
 end
`endif
endmodule

