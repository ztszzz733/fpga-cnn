// Mixed automatic DDR paging and explicit LOCAL access over one physical RAM.
// The first CACHE_BYTES are reserved for automatic paging; the remaining
// bytes form a software-owned local window. One DATA MOVER serves both paths.
module cnn_plan_storage #(
 parameter integer CLIENTS=23,
 parameter integer LOCAL_BYTES=401408,
 parameter integer CACHE_BYTES=65536,
 parameter integer PAGE_BYTES=1024,
 parameter integer MOVER_TIMEOUT_CYCLES=100000,
 parameter bit ENABLE_FAST_HIT=1'b1,
 parameter logic [31:0] LOGICAL_BYTES=32'h04000000,
 parameter logic [31:0] DDR_BYTES=32'h01000000,
 parameter logic [31:0] LOCAL_BASE=32'h04000000,
 parameter logic [31:0] DDR_BASE=32'h10000000
)(
 input logic clk,rst_n,
 input wire [CLIENTS-1:0] cnn_valid,cnn_write,cnn_byte,
 input wire [CLIENTS*32-1:0] cnn_addr,cnn_wdata,
 output logic [CLIENTS-1:0] cnn_ready,
 output wire [CLIENTS-1:0] cnn_response,
 output wire [CLIENTS*32-1:0] cnn_rdata,
 input wire cnn_cancel,
 output logic cnn_mem_fault,
 input logic [31:0] cache_csr_addr,cache_csr_wdata,
 input logic cache_csr_re,cache_csr_we,
 output logic [31:0] cache_csr_rdata,
 output wire cache_csr_ready,
 input logic plan_cmd_valid,
 output wire plan_cmd_ready,
 input logic [31:0] plan_cmd_epoch,plan_cmd_frame_id,plan_cmd_id,
 input logic plan_cmd_direction,
 input logic [31:0] plan_cmd_ddr_offset,plan_cmd_local_offset,plan_cmd_bytes,
 output wire plan_rsp_valid,
 input logic plan_rsp_ready,
 output wire [31:0] plan_rsp_epoch,plan_rsp_frame_id,plan_rsp_id,
 output wire [31:0] plan_rsp_kind,plan_rsp_status,
 input logic plan_recover,
 output wire plan_busy,plan_drained,plan_fault,
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
  localparam integer EXPLICIT_BYTES=LOCAL_BYTES-CACHE_BYTES;
  localparam integer SLOTS=CACHE_BYTES/PAGE_BYTES;
 localparam integer PB=$clog2(PAGE_BYTES), SB=$clog2(SLOTS);
 localparam integer CW=(CLIENTS<=1)?1:$clog2(CLIENTS);
 localparam integer LOOKUP_LEAVES=2**$clog2(SLOTS);
 localparam integer GRANT_LEAVES=2**$clog2(CLIENTS);
 function automatic logic [1:0] bank_of_slot(input logic [SB-1:0] slot);
  if(LOCAL_BYTES==401408 && PAGE_BYTES==1024)
   bank_of_slot=int'(slot)<96?2'd0:int'(slot)<192?2'd1:
                int'(slot)<292?2'd2:2'd3;
  else bank_of_slot=2'd0;
 endfunction
 // Interleave the replacement walk across banks, including their unequal
 // four-page tails, so the first four filled pages occupy four banks.
 function automatic logic [SB-1:0] slot_from_turn(input logic [SB-1:0] turn);
   if(CACHE_BYTES==401408 && PAGE_BYTES==1024)begin
   if(int'(turn)<384)begin
    case(turn[1:0])
     2'd0:slot_from_turn=SB'(turn>>2);
     2'd1:slot_from_turn=SB'(96+(int'(turn)>>2));
     2'd2:slot_from_turn=SB'(192+(int'(turn)>>2));
     default:slot_from_turn=SB'(292+(int'(turn)>>2));
    endcase
   end else slot_from_turn=turn[0] ?
    SB'(388+((int'(turn)-384)>>1)) : SB'(288+((int'(turn)-384)>>1));
  end else slot_from_turn=turn;
 endfunction
 typedef enum logic [2:0] {IDLE,ACCESS,DRAIN,WB_REQ,WB_WAIT,FILL_REQ,FILL_WAIT,SCAN} state_t;
 state_t state;
  typedef enum logic [2:0] {SYNC_IDLE,SYNC_QUIESCE,SYNC_SCAN,
                            SYNC_PERMIT,SYNC_TRANSFER} sync_t;
  sync_t plan_sync;
  logic [31:0] plan_sync_start,plan_sync_end;
  // Quiesce before the alias scan. Once the explicit transfer owns MOVER,
  // resident DDR cache hits may use compute ports; misses wait for MOVER.
  wire plan_hold_ddr=plan_sync!=SYNC_IDLE && plan_sync!=SYNC_TRANSFER;
 logic [SLOTS-1:0] valid_page,dirty_page;
 logic [31:PB] page_number[0:SLOTS-1];
 logic [SB:0] scan_idx;
 logic [SB-1:0] wb_slot;
 logic wb_for_scan,scan_invalidate,drop_response,csr_error,pend_valid,pend_invalidate;
 logic [31:0] pend_start,pend_end,scan_start,scan_end;
 logic [31:0] range_start,range_bytes,readonly_end;
 logic protect_enable;
 logic [31:0] hits,misses,writebacks,fills,ddr_read_bytes,ddr_write_bytes,wait_cycles;
 logic [31:0] local_dma_overlap_cycles,local_dma_accesses;
 logic [31:0] axi_read_bytes,axi_write_bytes;
 logic [31:0] plan_axi_read_bytes,plan_axi_write_bytes;
 logic [31:0] local_wait_cycles,plan_dma_cycles;
 logic [CW-1:0] round_robin,request_owner;
 logic [CW-1:0] bank_round_robin[4];
 logic [CLIENTS-1:0] hint_valid;
 logic [SB-1:0] hint_slot[CLIENTS];
 logic [31:PB] hint_page[CLIENTS];
 logic [SB-1:0] request_slot,victim_turn;
 logic [31:0] request_addr,request_wdata;
 logic request_write,request_byte;
  logic [3:0] issue_valid,reply_valid,reply_is_local;
 logic [3:0][CW-1:0] issue_owner,reply_owner;
 logic [3:0][SB-1:0] issue_slot;
 logic [3:0][31:0] issue_addr,issue_wdata;
 logic [3:0] issue_write,issue_byte,reply_write,reply_byte;
 logic [3:0][1:0] reply_byte_offset;
 logic [CLIENTS-1:0] response_q;
 logic [CLIENTS*32-1:0] rdata_q;
 wire [31:0] request_page={request_addr[31:PB],{PB{1'b0}}};
 wire [31:0] old_page={page_number[wb_slot],{PB{1'b0}}};
 wire [31:0] wb_local=32'(wb_slot)*PAGE_BYTES;
 wire [31:0] scan_page={page_number[scan_idx[SB-1:0]],{PB{1'b0}}};
 wire scan_match=valid_page[scan_idx[SB-1:0]] && scan_page<scan_end &&
                 {1'b0,scan_page}+33'(PAGE_BYTES)>{1'b0,scan_start};

 integer selected,index;
 logic selected_valid,selected_bad;
 logic [31:0] selected_addr;
 logic page_hit,free_found;
 logic [SB-1:0] hit_slot,free_slot;
 wire [2*LOOKUP_LEAVES-1:1] hit_tree,free_tree;
 wire [SB-1:0] hit_slot_tree[1:2*LOOKUP_LEAVES-1];
 wire [SB-1:0] free_slot_tree[1:2*LOOKUP_LEAVES-1];
 // A balanced lookup avoids a 392-entry serial priority path from the
 // requester through page selection into the miss engine.
 for(genvar s=0;s<LOOKUP_LEAVES;s++)begin:lookup_leaf
  if(s<SLOTS)begin:present
   assign hit_tree[LOOKUP_LEAVES+s]=valid_page[s] &&
    page_number[s]==selected_addr[31:PB];
   assign free_tree[LOOKUP_LEAVES+s]=!valid_page[s];
  end else begin:absent
   assign hit_tree[LOOKUP_LEAVES+s]=0;
   assign free_tree[LOOKUP_LEAVES+s]=0;
  end
  assign hit_slot_tree[LOOKUP_LEAVES+s]=SB'(s);
  assign free_slot_tree[LOOKUP_LEAVES+s]=SB'(s);
 end
 for(genvar n=1;n<LOOKUP_LEAVES;n++)begin:lookup_branch
  assign hit_tree[n]=hit_tree[2*n] || hit_tree[2*n+1];
  assign free_tree[n]=free_tree[2*n] || free_tree[2*n+1];
  assign hit_slot_tree[n]=hit_tree[2*n] ?
   hit_slot_tree[2*n] : hit_slot_tree[2*n+1];
  assign free_slot_tree[n]=free_tree[2*n] ?
   free_slot_tree[2*n] : free_slot_tree[2*n+1];
 end
 assign page_hit=hit_tree[1];
 assign free_found=free_tree[1];
 assign hit_slot=hit_slot_tree[1];
 assign free_slot=free_slot_tree[1];
 wire [SB-1:0] turn_slot=slot_from_turn(victim_turn);
 wire [SB-1:0] alloc_slot=!valid_page[turn_slot] ? turn_slot :
                           (free_found ? free_slot : turn_slot);
  function automatic logic [1:0] bank_of_physical(input logic [31:0] addr);
   bank_of_physical=addr<32'd98304 ? 2'd0 :
                    addr<32'd196608 ? 2'd1 :
                    addr<32'd299008 ? 2'd2 : 2'd3;
  endfunction
  logic [CLIENTS-1:0] bad_client,fast_hint,local_client,direct_good;
  logic [31:0] physical_local_addr[CLIENTS];
 wire [3:0] fast_grant;
 wire [3:0][CW-1:0] fast_owner;
 wire [CLIENTS-1:0] bank_eligible[4],bank_after[4],bank_candidates[4];
 wire [3:0][2*GRANT_LEAVES-1:1] grant_tree;
 wire [3:0][2*GRANT_LEAVES-1:1][CW-1:0] grant_index_tree;
 logic slow_take;
 logic [2:0] hit_incr;
 wire miss_serving=(state==WB_REQ || state==WB_WAIT ||
                    state==FILL_REQ || state==FILL_WAIT) && !wb_for_scan;
 wire can_accept=!pend_valid && !cnn_mem_fault && !mover_fault_locked &&
                 !cnn_cancel && !cache_csr_we;
 always_comb begin
  for(integer c=0;c<CLIENTS;c++)begin
    local_client[c]=cnn_addr[c*32+:32]>=LOCAL_BASE &&
     {1'b0,cnn_addr[c*32+:32]}<{1'b0,LOCAL_BASE}+33'(EXPLICIT_BYTES);
    physical_local_addr[c]=32'(CACHE_BYTES)+
     (cnn_addr[c*32+:32]-LOCAL_BASE);
    bad_client[c]=local_client[c] ?
     (!cnn_byte[c] && (cnn_addr[c*32+:2]!=0 ||
       {1'b0,cnn_addr[c*32+:32]}+33'd4>
        {1'b0,LOCAL_BASE}+33'(EXPLICIT_BYTES))) :
     (cnn_addr[c*32+:32]>=DDR_BYTES ||
      (!cnn_byte[c] && (cnn_addr[c*32+:2]!=0 ||
        {1'b0,cnn_addr[c*32+:32]}+33'd4>{1'b0,DDR_BYTES})) ||
      (cnn_write[c] && protect_enable && cnn_addr[c*32+:32]<readonly_end));
    direct_good[c]=cnn_valid[c] && local_client[c] && !bad_client[c];
    fast_hint[c]=ENABLE_FAST_HIT && cnn_valid[c] && !local_client[c] &&
     !bad_client[c] &&
    hint_valid[c] && hint_page[c]==cnn_addr[c*32+PB+:32-PB];
  end
 end
 for(genvar b=0;b<4;b++)begin:grant_bank
  for(genvar c=0;c<CLIENTS;c++)begin:grant_client
    assign bank_eligible[b][c]=can_accept && !issue_valid[b] &&
     ((direct_good[c] && state!=DRAIN &&
       bank_of_physical(physical_local_addr[c])==2'(b)) ||
      ((state==IDLE || miss_serving) && !plan_hold_ddr && fast_hint[c] &&
       bank_of_slot(hint_slot[c])==2'(b) &&
       (!miss_serving || hint_slot[c]!=request_slot)));
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
 always_comb begin
  selected=0;selected_valid=0;index=0;
  for(integer n=0;n<CLIENTS;n++)begin
   index=integer'(round_robin)+n;
   if(index>=CLIENTS)index=index-CLIENTS;
    if(!selected_valid && cnn_valid[index] &&
       !fast_hint[index] && !direct_good[index])begin
    selected=index;selected_valid=1;
   end
  end
  selected_addr=cnn_addr[selected*32+:32];
  selected_bad=bad_client[selected];
 end
 always_comb begin
  cnn_ready='0;slow_take=0;
  for(integer b=0;b<4;b++)if(fast_grant[b])cnn_ready[fast_owner[b]]=1;
   if(can_accept && !plan_hold_ddr && selected_valid &&
    (state==IDLE || (miss_serving && !selected_bad && page_hit &&
                     hit_slot!=request_slot)))begin
   cnn_ready[selected]=1;slow_take=1;
  end
 end
 always_comb begin
  hit_incr=0;
  for(integer b=0;b<4;b++)if(fast_grant[b])hit_incr=hit_incr+3'd1;
  if(slow_take && !selected_bad && page_hit)hit_incr=hit_incr+3'd1;
 end
 assign cnn_response=(cnn_cancel || cnn_mem_fault || mover_fault_locked) ? '0 : response_q;
 assign cnn_rdata=rdata_q;
 assign cache_csr_ready=1'b1;

  logic [3:0] comp_req,comp_we,comp_byte,comp_is_local;
 logic [3:0][CW-1:0] comp_owner;
 logic [3:0][SB-1:0] comp_slot;
 logic [3:0][31:0] comp_logical_addr,comp_addr,comp_wdata;
 logic [3:0][3:0] comp_wstrb;
 wire [3:0][31:0] comp_rdata;
 wire [3:0] comp_error;
 wire [3:0][7:0] read_byte;
 for(genvar b=0;b<4;b++)assign read_byte[b]=
    comp_rdata[b][reply_byte_offset[b]*8+:8];
 always_comb begin
  for(integer b=0;b<4;b++)begin
   logic [31:0] source_wdata,local_addr;
   comp_req[b]=(issue_valid[b] || fast_grant[b]) && !cnn_cancel &&
     !cnn_mem_fault && !mover_fault_locked;
   comp_owner[b]=issue_valid[b] ? issue_owner[b] : fast_owner[b];
    comp_is_local[b]=!issue_valid[b] && direct_good[fast_owner[b]];
    comp_slot[b]=issue_valid[b] ? issue_slot[b] : hint_slot[fast_owner[b]];
   comp_logical_addr[b]=issue_valid[b] ? issue_addr[b] :
     cnn_addr[fast_owner[b]*32+:32];
   source_wdata=issue_valid[b] ? issue_wdata[b] :
     cnn_wdata[fast_owner[b]*32+:32];
   comp_we[b]=issue_valid[b] ? issue_write[b] : cnn_write[fast_owner[b]];
   comp_byte[b]=issue_valid[b] ? issue_byte[b] : cnn_byte[fast_owner[b]];
    local_addr=comp_is_local[b] ?
      32'(CACHE_BYTES)+(comp_logical_addr[b]-LOCAL_BASE) :
      32'(comp_slot[b])*PAGE_BYTES+
       (comp_logical_addr[b] & 32'(PAGE_BYTES-1));
   comp_addr[b]={local_addr[31:2],2'b00};
   comp_wdata[b]=comp_byte[b] ?
     ({24'b0,source_wdata[7:0]} << (comp_logical_addr[b][1:0]*8)) : source_wdata;
   comp_wstrb[b]=comp_byte[b] ? (4'b1 << comp_logical_addr[b][1:0]) : 4'hf;
  end
 end

  wire page_cmd_valid=state==WB_REQ || state==FILL_REQ;
  wire mover_cmd_ready,mover_rsp_valid,mover_fault_locked,mover_drained,mover_busy;
 wire [31:0] mover_rsp_status,mover_rsp_bytes;
  wire [31:0] page_cmd_src=state==WB_REQ ? wb_local : request_page;
  wire [31:0] page_cmd_dst=state==WB_REQ ? old_page : 32'(request_slot)*PAGE_BYTES;
  wire [31:0] page_cmd_flags=state==WB_REQ ? 32'd1 : 32'd0;
  wire plan_mover_cmd_valid,plan_mover_cmd_ready,plan_mover_rsp_valid;
  wire plan_mover_rsp_ready;
  wire [31:0] plan_mover_cmd_src,plan_mover_cmd_dst;
  wire [31:0] plan_mover_cmd_bytes,plan_mover_cmd_flags;
  wire [31:0] plan_accepted_count,plan_completed_count,plan_queue_wait_cycles;
  wire plan_pending_valid;
  wire [31:0] plan_pending_ddr_offset,plan_pending_bytes;
  logic mover_owner_plan,mover_turn_plan;
  wire grant_plan=plan_mover_cmd_valid &&
                  (!page_cmd_valid || mover_turn_plan);
  wire grant_page=page_cmd_valid && !grant_plan;
  wire mover_cmd_valid=grant_page || grant_plan;
  wire page_cmd_ready=mover_cmd_ready && grant_page;
  assign plan_mover_cmd_ready=mover_cmd_ready && grant_plan;
  wire page_mover_rsp_valid=mover_rsp_valid && !mover_owner_plan;
  assign plan_mover_rsp_valid=mover_rsp_valid && mover_owner_plan;
  wire [31:0] mover_cmd_src=grant_plan ? plan_mover_cmd_src : page_cmd_src;
  wire [31:0] mover_cmd_dst=grant_plan ? plan_mover_cmd_dst : page_cmd_dst;
  wire [31:0] mover_cmd_bytes=grant_plan ? plan_mover_cmd_bytes : 32'(PAGE_BYTES);
  wire [31:0] mover_cmd_flags=grant_plan ? plan_mover_cmd_flags : page_cmd_flags;
  wire pager_recover=cache_csr_we && cache_csr_addr[7:0]==8'h04 &&
                     cache_csr_wdata==3 && state==IDLE && !pend_valid &&
                     !(|issue_valid) && !(|reply_valid);
  wire mover_recover=pager_recover ||
                     (plan_recover && plan_drained && state==IDLE);
  always_ff @(posedge clk)begin
   if(!rst_n)begin mover_owner_plan<=0;mover_turn_plan<=0;end
   else if(mover_cmd_valid && mover_cmd_ready)begin
    mover_owner_plan<=grant_plan;
    mover_turn_plan<=!grant_plan;
   end
  end
  storage_plan_queue #(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES),
   .LOCAL_PHYS_BASE(32'(CACHE_BYTES)),.LOCAL_BYTES(32'(EXPLICIT_BYTES)),
   .RAM_BYTES(32'(LOCAL_BYTES))) plan_queue(
   .clk,.rst_n,.recover(plan_recover),
   .ddr_readonly_end(protect_enable ? readonly_end : 32'b0),
   .cmd_valid(plan_cmd_valid),.cmd_ready(plan_cmd_ready),
   .cmd_epoch(plan_cmd_epoch),.cmd_frame_id(plan_cmd_frame_id),
   .cmd_id(plan_cmd_id),.cmd_direction(plan_cmd_direction),
   .cmd_ddr_offset(plan_cmd_ddr_offset),.cmd_local_offset(plan_cmd_local_offset),
   .cmd_bytes(plan_cmd_bytes),.rsp_valid(plan_rsp_valid),
   .rsp_ready(plan_rsp_ready),.rsp_epoch(plan_rsp_epoch),
   .rsp_frame_id(plan_rsp_frame_id),.rsp_id(plan_rsp_id),
   .rsp_kind(plan_rsp_kind),.rsp_status(plan_rsp_status),
   .busy(plan_busy),.drained(plan_drained),.fault(plan_fault),
   .accepted_count(plan_accepted_count),.completed_count(plan_completed_count),
   .queue_wait_cycles(plan_queue_wait_cycles),
   .pending_valid(plan_pending_valid),
   .pending_ddr_offset(plan_pending_ddr_offset),
   .pending_bytes(plan_pending_bytes),
   .mover_issue_permit(plan_sync==SYNC_PERMIT),
   .mover_cmd_valid(plan_mover_cmd_valid),
   .mover_cmd_ready(plan_mover_cmd_ready),
   .mover_cmd_src(plan_mover_cmd_src),.mover_cmd_dst(plan_mover_cmd_dst),
   .mover_cmd_bytes(plan_mover_cmd_bytes),.mover_cmd_flags(plan_mover_cmd_flags),
   .mover_rsp_valid(plan_mover_rsp_valid),
   .mover_rsp_ready(plan_mover_rsp_ready),
   .mover_rsp_status(mover_rsp_status),.mover_rsp_bytes_done(mover_rsp_bytes),
   .mover_fault_locked,.mover_drained,.mover_busy
  );
 wire local_valid,local_write,local_ready,local_rsp_valid,local_error;
 wire [31:0] local_addr,local_wdata,local_rdata;
 wire [3:0] local_wstrb;
 tile_local_ram_bank4 #(.BYTES(LOCAL_BYTES)) local_ram(
  .clk,.rst_n,.comp_req,.comp_we,.comp_addr,.comp_wdata,.comp_wstrb,
  .comp_rdata,.comp_error,.dma_valid(local_valid),.dma_write(local_write),
  .dma_ready(local_ready),.dma_addr(local_addr),.dma_wdata(local_wdata),
  .dma_wstrb(local_wstrb),.dma_rsp_valid(local_rsp_valid),.dma_error(local_error),
  .dma_rdata(local_rdata)
 );
 data_mover #(.TIMEOUT_CYCLES(MOVER_TIMEOUT_CYCLES)) mover(
  .clk,.rst_n,.enable(1'b1),.recover(mover_recover),
  .cfg_ddr_base(DDR_BASE),.cfg_ddr_bytes(DDR_BYTES),.cfg_local_bytes(32'(LOCAL_BYTES)),
  .cmd_valid(mover_cmd_valid),.cmd_ready(mover_cmd_ready),
   .cmd_src(mover_cmd_src),.cmd_dst(mover_cmd_dst),.cmd_bytes(mover_cmd_bytes),
   .cmd_flags(mover_cmd_flags),.rsp_valid(mover_rsp_valid),
   .rsp_ready(mover_owner_plan ? plan_mover_rsp_ready : 1'b1),
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
     (state!=IDLE || pend_valid || (|issue_valid) || (|reply_valid)),1'b1};
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
    8'h3c:cache_csr_rdata=EXPLICIT_BYTES;
    8'h40:cache_csr_rdata=LOCAL_BASE;
    8'h44:cache_csr_rdata=CACHE_BYTES;
    8'h48:cache_csr_rdata=plan_accepted_count;
    8'h4c:cache_csr_rdata=plan_completed_count;
    8'h50:cache_csr_rdata=plan_queue_wait_cycles;
    8'h54:cache_csr_rdata=32'd1;
    8'h58:cache_csr_rdata=DDR_BYTES;
    8'h5c:cache_csr_rdata=32'd8;
    8'h60:cache_csr_rdata=32'd4;
    8'h64:cache_csr_rdata={8'd1,8'd4,8'd32,8'd32};
    8'h68:cache_csr_rdata=32'h00000003;
    8'h6c:cache_csr_rdata=local_dma_overlap_cycles;
    8'h70:cache_csr_rdata=local_dma_accesses;
    8'h74:cache_csr_rdata={27'b0,plan_rsp_valid,plan_cmd_ready,
                           plan_fault,plan_drained,plan_busy};
    8'h80:cache_csr_rdata=axi_read_bytes;
    8'h84:cache_csr_rdata=axi_write_bytes;
    8'h88:cache_csr_rdata=plan_axi_read_bytes;
    8'h8c:cache_csr_rdata=plan_axi_write_bytes;
    8'h90:cache_csr_rdata=local_wait_cycles;
    8'h94:cache_csr_rdata=plan_dma_cycles;
   default:;
  endcase
 end

 always_ff @(posedge clk) begin
  if(!rst_n)begin
    state<=IDLE;plan_sync<=SYNC_IDLE;plan_sync_start<=0;plan_sync_end<=0;
    valid_page<='0;dirty_page<='0;scan_idx<=0;wb_slot<=0;
   wb_for_scan<=0;scan_invalidate<=0;drop_response<=0;csr_error<=0;
   pend_valid<=0;pend_invalidate<=0;pend_start<=0;pend_end<=0;
   scan_start<=0;scan_end<=0;range_start<=0;range_bytes<=DDR_BYTES;
   readonly_end<=0;protect_enable<=0;cnn_mem_fault<=0;
   hits<=0;misses<=0;writebacks<=0;fills<=0;
   ddr_read_bytes<=0;ddr_write_bytes<=0;wait_cycles<=0;
   local_dma_overlap_cycles<=0;local_dma_accesses<=0;
   axi_read_bytes<=0;axi_write_bytes<=0;
   plan_axi_read_bytes<=0;plan_axi_write_bytes<=0;
   local_wait_cycles<=0;plan_dma_cycles<=0;
   round_robin<=0;request_owner<=0;request_slot<=0;victim_turn<=0;
   hint_valid<='0;
   for(integer c=0;c<CLIENTS;c++)begin hint_slot[c]<=0;hint_page[c]<=0;end
   for(integer b=0;b<4;b++)bank_round_robin[b]<=0;
   request_addr<=0;request_wdata<=0;
   request_write<=0;request_byte<=0;response_q<='0;rdata_q<='0;
    issue_valid<=0;reply_valid<=0;reply_is_local<=0;
    issue_owner<=0;reply_owner<=0;
   issue_slot<=0;issue_addr<=0;issue_wdata<=0;
   issue_write<=0;issue_byte<=0;reply_write<=0;reply_byte<=0;
   reply_byte_offset<=0;
   for(integer k=0;k<SLOTS;k++)page_number[k]<='0;
  end else begin
   response_q<='0;
   issue_valid<=0;
   reply_valid<=comp_req;
    reply_is_local<=comp_is_local;
   hits<=hits+32'(hit_incr);
   if(S_AXI_HP0_RVALID && S_AXI_HP0_RREADY)begin
    axi_read_bytes<=axi_read_bytes+(32'd1<<S_AXI_HP0_ARSIZE);
    if(mover_owner_plan)
     plan_axi_read_bytes<=plan_axi_read_bytes+
                          (32'd1<<S_AXI_HP0_ARSIZE);
   end
   if(S_AXI_HP0_WVALID && S_AXI_HP0_WREADY)begin
    axi_write_bytes<=axi_write_bytes+32'($countones(S_AXI_HP0_WSTRB));
    if(mover_owner_plan)
     plan_axi_write_bytes<=plan_axi_write_bytes+
                           32'($countones(S_AXI_HP0_WSTRB));
   end
   if(|(cnn_valid & local_client & ~cnn_ready))
    local_wait_cycles<=local_wait_cycles+1'b1;
   if(plan_sync==SYNC_TRANSFER && mover_busy)
    plan_dma_cycles<=plan_dma_cycles+1'b1;
   if(plan_sync==SYNC_TRANSFER && mover_busy &&
      (|(fast_grant & comp_is_local)))begin
    local_dma_overlap_cycles<=local_dma_overlap_cycles+1'b1;
    local_dma_accesses<=local_dma_accesses+
     32'($countones(fast_grant & comp_is_local));
   end
   for(integer b=0;b<4;b++)begin
    if(comp_req[b])begin
     reply_owner[b]<=comp_owner[b];
     reply_write[b]<=comp_we[b];
     reply_byte[b]<=comp_byte[b];
     reply_byte_offset[b]<=comp_logical_addr[b][1:0];
      if(comp_we[b] && !comp_is_local[b])dirty_page[comp_slot[b]]<=1;
    end
    if(reply_valid[b] && !cnn_cancel && !cnn_mem_fault && !mover_fault_locked)begin
     if(comp_error[b])cnn_mem_fault<=1;
     else begin
      response_q[reply_owner[b]]<=1;
      rdata_q[reply_owner[b]*32+:32]<=reply_write[b] ? 0 :
       reply_byte[b] ? {{24{read_byte[b][7]}},read_byte[b]} : comp_rdata[b];
     end
    end
    if(fast_grant[b])begin
     bank_round_robin[b]<=fast_owner[b]==CW'(CLIENTS-1) ?
      '0 : fast_owner[b]+1'b1;
    end
   end
   if(cnn_cancel)begin issue_valid<=0;reply_valid<=0;end
   if(slow_take)begin
    round_robin<=selected==CLIENTS-1 ? '0 : CW'(selected+1);
    if(!selected_bad && page_hit)begin
      hint_valid[selected]<=1;hint_slot[selected]<=hit_slot;
      hint_page[selected]<=selected_addr[31:PB];
      issue_valid[bank_of_slot(hit_slot)]<=1;
      issue_owner[bank_of_slot(hit_slot)]<=CW'(selected);
      issue_slot[bank_of_slot(hit_slot)]<=hit_slot;
      issue_addr[bank_of_slot(hit_slot)]<=selected_addr;
      issue_wdata[bank_of_slot(hit_slot)]<=cnn_wdata[selected*32+:32];
      issue_write[bank_of_slot(hit_slot)]<=cnn_write[selected];
      issue_byte[bank_of_slot(hit_slot)]<=cnn_byte[selected];
    end
    end else if(selected_valid && !pend_valid && !plan_hold_ddr && !cnn_cancel &&
               !cnn_mem_fault && !mover_fault_locked &&
               miss_serving)begin
    // A second miss can hold valid high throughout a transfer. Rotate the
    // lookup owner so resident requests behind it still get a turn.
    round_robin<=selected==CLIENTS-1 ? '0 : CW'(selected+1);
   end
   if(cnn_cancel && state!=IDLE)drop_response<=1;
   if(state==WB_WAIT || state==FILL_WAIT)wait_cycles<=wait_cycles+1;
    if(cache_csr_we && plan_sync!=SYNC_IDLE)csr_error<=1;
    else if(cache_csr_we)begin
    if(cache_csr_addr[1:0]!=0)csr_error<=1;
    else case(cache_csr_addr[7:0])
     8'h08:range_start<=cache_csr_wdata;
     8'h0c:range_bytes<=cache_csr_wdata;
     8'h10:if(state==IDLE && !pend_valid && cache_csr_wdata<=DDR_BYTES)
       readonly_end<=cache_csr_wdata;else csr_error<=1;
     8'h14:if(state==IDLE && !pend_valid)
       protect_enable<=cache_csr_wdata[0];else csr_error<=1;
     8'h04:case(cache_csr_wdata)
      1,2:if(!pend_valid && range_start<=DDR_BYTES &&
             {1'b0,range_start}+{1'b0,range_bytes}<={1'b0,DDR_BYTES})begin
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
    case(plan_sync)
     SYNC_IDLE:if(plan_pending_valid)begin
      plan_sync_start<=plan_pending_ddr_offset;
      plan_sync_end<=plan_pending_ddr_offset+plan_pending_bytes;
      plan_sync<=SYNC_QUIESCE;
     end
     SYNC_QUIESCE:if(state==IDLE && !pend_valid && !(|issue_valid) &&
       !(|(reply_valid & ~reply_is_local)) && !mover_busy)begin
      pend_valid<=1;pend_start<=plan_sync_start;
      pend_end<=plan_sync_end;pend_invalidate<=1;
      plan_sync<=SYNC_SCAN;
     end
     SYNC_SCAN:if(state==IDLE && !pend_valid && !mover_busy)
      plan_sync<=plan_pending_valid ? SYNC_PERMIT : SYNC_IDLE;
     SYNC_PERMIT:begin
      if(grant_plan && mover_cmd_ready)plan_sync<=SYNC_TRANSFER;
      else if(!plan_pending_valid)plan_sync<=SYNC_IDLE;
     end
     SYNC_TRANSFER:if(plan_mover_rsp_valid && plan_mover_rsp_ready)
      plan_sync<=SYNC_IDLE;
     default:plan_sync<=SYNC_IDLE;
    endcase
    case(state)
     IDLE:if(pend_valid)begin
      if (!(|issue_valid) && !(|reply_valid))begin
      pend_valid<=0;scan_start<=pend_start;scan_end<=pend_end;
      scan_invalidate<=pend_invalidate;scan_idx<=0;state<=SCAN;
      drop_response<=0;
     end
    end else if(slow_take)begin
     drop_response<=0;
     if(selected_bad)cnn_mem_fault<=1;
     else if(!page_hit)begin
      request_owner<=CW'(selected);request_addr<=selected_addr;
      request_wdata<=cnn_wdata[selected*32+:32];
      request_write<=cnn_write[selected];request_byte<=cnn_byte[selected];
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
      issue_wdata[bank_of_slot(request_slot)]<=request_wdata;
      issue_write[bank_of_slot(request_slot)]<=request_write;
      issue_byte[bank_of_slot(request_slot)]<=request_byte;
      hint_valid[request_owner]<=1;hint_slot[request_owner]<=request_slot;
      hint_page[request_owner]<=request_addr[31:PB];
     end
     state<=IDLE;
    end
    DRAIN:if (!(|issue_valid) && !(|reply_valid))
     state<=valid_page[request_slot] && dirty_page[request_slot] ? WB_REQ : FILL_REQ;
    WB_REQ:if(page_cmd_ready)state<=WB_WAIT;
    WB_WAIT:if(page_mover_rsp_valid)begin
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
    FILL_REQ:if(page_cmd_ready)state<=FILL_WAIT;
    FILL_WAIT:if(page_mover_rsp_valid)begin
     if(mover_rsp_status!=0 || mover_rsp_bytes!=PAGE_BYTES)begin
      cnn_mem_fault<=1;state<=IDLE;
     end else begin
      valid_page[request_slot]<=1;dirty_page[request_slot]<=0;
      page_number[request_slot]<=request_addr[31:PB];
      fills<=fills+1;ddr_read_bytes<=ddr_read_bytes+PAGE_BYTES;
      state<=drop_response || cnn_cancel ? IDLE : ACCESS;
     end
    end
    SCAN:if(scan_idx==(SB+1)'(SLOTS))state<=IDLE;
     else if(scan_match && dirty_page[scan_idx[SB-1:0]])begin
      wb_slot<=scan_idx[SB-1:0];wb_for_scan<=1;state<=WB_REQ;
     end else begin
      if(scan_match && scan_invalidate)begin
       valid_page[scan_idx[SB-1:0]]<=0;
       for(integer c=0;c<CLIENTS;c++)
        if(hint_slot[c]==scan_idx[SB-1:0])hint_valid[c]<=0;
      end
      scan_idx<=scan_idx+1'b1;
     end
    default:state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 initial begin
  assert(CLIENTS>=1)else $fatal(1,"at least one CNN client required");
   assert(CACHE_BYTES>=PAGE_BYTES*2 && CACHE_BYTES<LOCAL_BYTES &&
     CACHE_BYTES%PAGE_BYTES==0 && PAGE_BYTES>=4 &&
     (PAGE_BYTES&(PAGE_BYTES-1))==0)
   else $fatal(1,"paged mover geometry");
  assert(LOCAL_BYTES!=401408 || PAGE_BYTES==1024)
   else $fatal(1,"four-bank geometry requires 1 KiB pages");
  assert(DDR_BYTES>0 && DDR_BYTES<=LOGICAL_BYTES &&
    DDR_BYTES[PB-1:0]==0 && DDR_BASE[2:0]==0 &&
    {1'b0,DDR_BASE}+{1'b0,DDR_BYTES}<=33'h100000000)
   else $fatal(1,"DDR aperture");
   assert(LOCAL_BASE>=LOGICAL_BYTES &&
     {1'b0,LOCAL_BASE}+33'(EXPLICIT_BYTES)<=33'h100000000)
    else $fatal(1,"local aperture");
 end
`endif
endmodule
