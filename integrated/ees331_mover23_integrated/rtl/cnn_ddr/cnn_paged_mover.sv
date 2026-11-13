// CNN memory backed by the storage_v2 DATA MOVER and tile BRAM.
// Parameterized local RAM is divided into fully associative 1 KiB pages. Exactly one
// CNN request or DDR page transfer is active; this correctness-first policy
// preserves the existing CNN ready/response protocol without task rewrites.
module cnn_paged_mover #(
 parameter integer CLIENTS=23,
 parameter integer LOCAL_BYTES=32768,
 parameter integer PAGE_BYTES=1024,
 parameter logic [31:0] LOGICAL_BYTES=32'h04000000,
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
 localparam integer SLOTS=LOCAL_BYTES/PAGE_BYTES;
 localparam integer PB=$clog2(PAGE_BYTES), SB=$clog2(SLOTS);
 localparam integer CW=(CLIENTS<=1)?1:$clog2(CLIENTS);
 typedef enum logic [2:0] {IDLE,ACCESS,REPLY,WB_REQ,WB_WAIT,FILL_REQ,FILL_WAIT,SCAN} state_t;
 state_t state;
 logic [SLOTS-1:0] valid_page,dirty_page;
 logic [31:PB] page_number[0:SLOTS-1];
 logic [SB:0] scan_idx;
 logic [SB-1:0] wb_slot;
 logic wb_for_scan,scan_invalidate,drop_response,csr_error,pend_valid,pend_invalidate;
 logic [31:0] pend_start,pend_end,scan_start,scan_end;
 logic [31:0] range_start,range_bytes,readonly_end;
 logic protect_enable;
 logic [31:0] hits,misses,writebacks,fills,ddr_read_bytes,ddr_write_bytes,wait_cycles;
 logic [CW-1:0] round_robin,request_owner;
 logic [SB-1:0] request_slot,victim_turn;
 logic [31:0] request_addr,request_wdata;
 logic request_write,request_byte;
 logic [CLIENTS-1:0] response_q;
 logic [CLIENTS*32-1:0] rdata_q;
 wire [31:0] request_page={request_addr[31:PB],{PB{1'b0}}};
 wire [31:0] old_page={page_number[wb_slot],{PB{1'b0}}};
 wire [31:0] wb_local=32'(wb_slot)*PAGE_BYTES;
 wire [31:0] request_local=32'(request_slot)*PAGE_BYTES+(request_addr & 32'(PAGE_BYTES-1));
 wire [31:0] scan_page={page_number[scan_idx[SB-1:0]],{PB{1'b0}}};
 wire scan_match=valid_page[scan_idx[SB-1:0]] && scan_page<scan_end &&
                 {1'b0,scan_page}+33'(PAGE_BYTES)>{1'b0,scan_start};

 integer selected,index;
 logic selected_valid,selected_bad;
 logic [31:0] selected_addr;
 logic page_hit,free_found;
 logic [SB-1:0] hit_slot,free_slot;
 always_comb begin
  selected=0;selected_valid=0;cnn_ready='0;
  for(integer n=0;n<CLIENTS;n++)begin
   index=integer'(round_robin)+n;
   if(index>=CLIENTS)index=index-CLIENTS;
   if(!selected_valid && cnn_valid[index])begin selected=index;selected_valid=1;end
  end
  selected_addr=cnn_addr[selected*32+:32];
  selected_bad=selected_addr>=LOGICAL_BYTES ||
    (!cnn_byte[selected] && (selected_addr[1:0]!=0 ||
      {1'b0,selected_addr}+33'd4>{1'b0,LOGICAL_BYTES})) ||
    (cnn_write[selected] && protect_enable && selected_addr<readonly_end);
  page_hit=0;free_found=0;hit_slot=0;free_slot=0;
  for(integer s=0;s<SLOTS;s++)begin
   if(!page_hit && valid_page[s] && page_number[s]==selected_addr[31:PB])begin
    page_hit=1;hit_slot=SB'(s);
   end
   if(!free_found && !valid_page[s])begin free_found=1;free_slot=SB'(s);end
  end
  if(state==IDLE && !pend_valid && !cnn_mem_fault && !mover_fault_locked &&
     !cnn_cancel && !cache_csr_we && selected_valid)cnn_ready[selected]=1;
 end
 assign cnn_response=(cnn_cancel || cnn_mem_fault) ? '0 : response_q;
 assign cnn_rdata=rdata_q;
 assign cache_csr_ready=1'b1;

 // Only the selected, aligned word is presented to the compute port.
 wire comp_req=state==ACCESS && !drop_response && !cnn_cancel;
 wire comp_we=request_write;
 wire [31:0] comp_addr={request_local[31:2],2'b00};
 wire [31:0] comp_wdata=request_byte ?
    ({24'b0,request_wdata[7:0]} << (request_addr[1:0]*8)) : request_wdata;
 wire [3:0] comp_wstrb=request_byte ? (4'b1 << request_addr[1:0]) : 4'hf;
 wire [31:0] comp_rdata;
 wire comp_error;
 wire [7:0] read_byte=comp_rdata[request_addr[1:0]*8+:8];

 wire mover_cmd_valid=state==WB_REQ || state==FILL_REQ;
 wire mover_cmd_ready,mover_rsp_valid,mover_fault_locked,mover_drained,mover_busy;
 wire [31:0] mover_rsp_status,mover_rsp_bytes;
 wire [31:0] mover_cmd_src=state==WB_REQ ? wb_local : request_page;
 wire [31:0] mover_cmd_dst=state==WB_REQ ? old_page : 32'(request_slot)*PAGE_BYTES;
 wire [31:0] mover_cmd_flags=state==WB_REQ ? 32'd1 : 32'd0;
 wire mover_recover=cache_csr_we && cache_csr_addr[7:0]==8'h04 &&
                    cache_csr_wdata==3 && state==IDLE && !pend_valid;
 wire local_valid,local_write,local_ready,local_rsp_valid,local_error;
 wire [31:0] local_addr,local_wdata,local_rdata;
 wire [3:0] local_wstrb;
 tile_local_ram #(.BYTES(LOCAL_BYTES)) local_ram(
  .clk,.rst_n,.comp_req,.comp_we,.comp_addr,.comp_wdata,.comp_wstrb,
  .comp_rdata,.comp_error,.dma_valid(local_valid),.dma_write(local_write),
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
     (cnn_mem_fault || mover_fault_locked),csr_error,(state!=IDLE || pend_valid),1'b1};
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

 always_ff @(posedge clk) begin
  if(!rst_n)begin
   state<=IDLE;valid_page<='0;dirty_page<='0;scan_idx<=0;wb_slot<=0;
   wb_for_scan<=0;scan_invalidate<=0;drop_response<=0;csr_error<=0;
   pend_valid<=0;pend_invalidate<=0;pend_start<=0;pend_end<=0;
   scan_start<=0;scan_end<=0;range_start<=0;range_bytes<=LOGICAL_BYTES;
   readonly_end<=0;protect_enable<=0;cnn_mem_fault<=0;
   hits<=0;misses<=0;writebacks<=0;fills<=0;
   ddr_read_bytes<=0;ddr_write_bytes<=0;wait_cycles<=0;
   round_robin<=0;request_owner<=0;request_slot<=0;victim_turn<=0;
   request_addr<=0;request_wdata<=0;
   request_write<=0;request_byte<=0;response_q<='0;rdata_q<='0;
   for(integer k=0;k<SLOTS;k++)page_number[k]<='0;
  end else begin
   response_q<='0;
   if(cnn_cancel && state!=IDLE)drop_response<=1;
   if(state==WB_WAIT || state==FILL_WAIT)wait_cycles<=wait_cycles+1;
   if(cache_csr_we)begin
    if(cache_csr_addr[1:0]!=0)csr_error<=1;
    else case(cache_csr_addr[7:0])
     8'h08:range_start<=cache_csr_wdata;
     8'h0c:range_bytes<=cache_csr_wdata;
     8'h10:if(state==IDLE && !pend_valid && cache_csr_wdata<=LOGICAL_BYTES)
       readonly_end<=cache_csr_wdata;else csr_error<=1;
     8'h14:if(state==IDLE && !pend_valid)
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
    IDLE:if(pend_valid)begin
     pend_valid<=0;scan_start<=pend_start;scan_end<=pend_end;
     scan_invalidate<=pend_invalidate;scan_idx<=0;state<=SCAN;
     drop_response<=0;
    end else if(|cnn_ready)begin
     round_robin<=selected==CLIENTS-1 ? '0 : CW'(selected+1);
     drop_response<=0;
     if(selected_bad)cnn_mem_fault<=1;
     else begin
      request_owner<=CW'(selected);request_addr<=selected_addr;
      request_wdata<=cnn_wdata[selected*32+:32];
      request_write<=cnn_write[selected];request_byte<=cnn_byte[selected];
      if(page_hit)begin
       hits<=hits+1;request_slot<=hit_slot;state<=ACCESS;
      end else begin
       misses<=misses+1;
       request_slot<=free_found ? free_slot : victim_turn;
       wb_slot<=free_found ? free_slot : victim_turn;
       victim_turn<=victim_turn==SB'(SLOTS-1)?'0:victim_turn+1'b1;
       wb_for_scan<=0;
       state<=!free_found && dirty_page[victim_turn] ? WB_REQ : FILL_REQ;
      end
     end
    end
    ACCESS:begin
     if(comp_req && request_write)dirty_page[request_slot]<=1;
     state<=REPLY;
    end
    REPLY:begin
     if(comp_error)cnn_mem_fault<=1;
     else if(!drop_response && !cnn_cancel)begin
      response_q[request_owner]<=1;
      rdata_q[request_owner*32+:32]<=request_write ? 0 :
       request_byte ? {{24{read_byte[7]}},read_byte} : comp_rdata;
     end
     state<=IDLE;
    end
    WB_REQ:if(mover_cmd_ready)state<=WB_WAIT;
    WB_WAIT:if(mover_rsp_valid)begin
     if(mover_rsp_status!=0 || mover_rsp_bytes!=PAGE_BYTES)begin
      cnn_mem_fault<=1;csr_error<=1;state<=IDLE;
     end else begin
      dirty_page[wb_slot]<=0;writebacks<=writebacks+1;
      ddr_write_bytes<=ddr_write_bytes+PAGE_BYTES;
      if(wb_for_scan)begin
       if(scan_invalidate)valid_page[wb_slot]<=0;
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
      page_number[request_slot]<=request_addr[31:PB];
      fills<=fills+1;ddr_read_bytes<=ddr_read_bytes+PAGE_BYTES;
      state<=drop_response || cnn_cancel ? IDLE : ACCESS;
     end
    end
    SCAN:if(scan_idx==SLOTS)state<=IDLE;
     else if(scan_match && dirty_page[scan_idx[SB-1:0]])begin
      wb_slot<=scan_idx[SB-1:0];wb_for_scan<=1;state<=WB_REQ;
     end else begin
      if(scan_match && scan_invalidate)valid_page[scan_idx[SB-1:0]]<=0;
      scan_idx<=scan_idx+1'b1;
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
  assert(LOGICAL_BYTES[PB-1:0]==0 && DDR_BASE[2:0]==0 &&
    {1'b0,DDR_BASE}+{1'b0,LOGICAL_BYTES}<=33'h100000000)
   else $fatal(1,"DDR aperture");
 end
`endif
endmodule
