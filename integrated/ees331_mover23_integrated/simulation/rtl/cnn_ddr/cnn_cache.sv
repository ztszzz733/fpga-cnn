// Correctness-first, blocking, write-back/write-allocate CNN cache.
// Data is physically four synchronous 32-bit banks. One accepted CNN request
// (including one miss) is outstanding globally. This is not four-MSHR cache.
// Byte reads sign-extend, matching bai datasram_banked; words must be aligned.
module cnn_cache #(
 parameter integer CLIENTS=10,
 parameter integer CACHE_BYTES=131072,
 parameter logic [31:0] LOGICAL_BYTES=32'h01000000,
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
 output wire cmd_valid,cmd_write,
 output wire [31:0] cmd_addr,
 output wire [511:0] cmd_wline,
 input wire cmd_ready,ddr_done,ddr_error,
 input wire [511:0] ddr_rline
);
 localparam integer SETS=CACHE_BYTES/128, SW=$clog2(SETS);
 localparam integer LINES=SETS*2, LW=$clog2(LINES), ROWS=LINES*4, RW=$clog2(ROWS);
 localparam integer TW=32-6-SW, MW=TW+2, CW=(CLIENTS<=1)?1:$clog2(CLIENTS);
 typedef enum logic [4:0] {
  INIT,IDLE,LOOKUP,CHECK,HIT_REPLY,
  WB_READ,WB_CAPTURE,WB_SEND,WB_WAIT,FILL_SEND,FILL_WAIT,FILL_WRITE,
  SCAN_LOOKUP,SCAN_CHECK
 } state_t;
 state_t state;
 logic initialized,csr_error,drop_response,maintenance,invalidate;
 logic maintenance_pending,pending_invalidate;
 logic [31:0] pending_start,pending_end;
 logic [SW-1:0] init_set,scan_set;
 logic scan_way;
 logic [31:0] range_start,range_bytes,readonly_end,scan_start,scan_end;
 logic protect_enable;
 logic [31:0] hits,misses,writebacks,fills,ddr_read_bytes,ddr_write_bytes,wait_cycles;
 logic [CW-1:0] round_robin,request_owner;
 logic [31:0] request_addr,request_wdata;
 logic request_write,request_byte,request_missed;
 wire [SW-1:0] request_set=request_addr[6 +: SW];
 wire [TW-1:0] request_tag=request_addr[6+SW +: TW];
 logic [LW-1:0] victim_line;
 logic [TW-1:0] victim_tag;
 logic [31:0] victim_logical;
 logic [1:0] chunk;
 logic [511:0] writeback_line;
 logic [CLIENTS-1:0] response_q;
 logic [CLIENTS*32-1:0] rdata_q;

 // Each metadata RAM is a way; lookup is synchronous. No array reset.
 (* ram_style="block" *) logic [MW-1:0] metadata0[0:SETS-1];
 (* ram_style="block" *) logic [MW-1:0] metadata1[0:SETS-1];
 (* ram_style="distributed" *) logic lru[0:SETS-1];
 logic [MW-1:0] meta_q0,meta_q1,meta_d0,meta_d1;
 logic [SW-1:0] meta_index;
 logic meta_en,meta_we0,meta_we1,lru_we,lru_d,lru_q;
 always_ff @(posedge clk) begin
  if(meta_en) begin
   meta_q0<=metadata0[meta_index]; meta_q1<=metadata1[meta_index]; lru_q<=lru[meta_index];
  end
  if(meta_we0) metadata0[meta_index]<=meta_d0;
  if(meta_we1) metadata1[meta_index]<=meta_d1;
  if(lru_we) lru[meta_index]<=lru_d;
 end
 wire hit0=meta_q0[MW-1] && meta_q0[TW-1:0]==request_tag;
 wire hit1=meta_q1[MW-1] && meta_q1[TW-1:0]==request_tag;
 wire hit=hit0 || hit1;
 wire hit_way=!hit0;
 wire chosen_way=!meta_q0[MW-1] ? 1'b0 : !meta_q1[MW-1] ? 1'b1 : lru_q;
 wire [MW-1:0] chosen_meta=chosen_way ? meta_q1 : meta_q0;
 wire [MW-1:0] scan_meta=scan_way ? meta_q1 : meta_q0;
 wire [31:0] scan_line_addr={scan_meta[TW-1:0],scan_set,6'b0};
 wire scan_matches=scan_start<scan_end && scan_meta[MW-1] && scan_line_addr<scan_end &&
                        ({1'b0,scan_line_addr}+33'd64)>{1'b0,scan_start};
 wire [31:0] hit_word;
 wire [7:0] hit_byte=hit_word[request_addr[1:0]*8 +: 8];

 logic [3:0] bank_en;
 logic [RW-1:0] bank_addr[0:3];
 logic [31:0] bank_wdata[0:3],bank_rdata[0:3];
 logic [3:0] bank_be[0:3];
 for(genvar b=0;b<4;b++) begin: data_banks
  (* ram_style="block" *) logic [31:0] mem[0:ROWS-1];
  always_ff @(posedge clk) if(bank_en[b]) begin
   bank_rdata[b]<=mem[bank_addr[b]];
   for(integer lane=0;lane<4;lane++)
    if(bank_be[b][lane]) mem[bank_addr[b]][lane*8 +: 8]<=bank_wdata[b][lane*8 +: 8];
  end
 end
 assign hit_word=bank_rdata[request_addr[3:2]];
 assign cnn_response=(cnn_cancel || cnn_mem_fault) ? '0 : response_q;
 assign cnn_rdata=rdata_q;
 assign cache_csr_ready=1'b1;
 assign cmd_valid=state==WB_SEND || state==FILL_SEND;
 assign cmd_write=state==WB_SEND;
 assign cmd_addr=DDR_BASE + (state==WB_SEND ? victim_logical : {request_addr[31:6],6'b0});
 assign cmd_wline=writeback_line;

 integer selected,index;
 logic selected_valid;
 logic [31:0] selected_addr;
 logic selected_bad;
 always_comb begin
  selected=0; selected_valid=0; cnn_ready='0;
  for(integer n=0;n<CLIENTS;n++) begin
   index=integer'(round_robin)+n;
   if(index>=CLIENTS) index=index-CLIENTS;
   if(!selected_valid && cnn_valid[index]) begin selected=index; selected_valid=1; end
  end
  selected_addr=cnn_addr[selected*32 +: 32];
  selected_bad=selected_addr>=LOGICAL_BYTES ||
    (!cnn_byte[selected] && (selected_addr[1:0]!=0 || {1'b0,selected_addr}+33'd4>{1'b0,LOGICAL_BYTES})) ||
    (cnn_write[selected] && protect_enable && selected_addr<readonly_end);
  if(state==IDLE && !maintenance_pending && !cnn_mem_fault && !cnn_cancel && !cache_csr_we && selected_valid)
   cnn_ready[selected]=1;
 end

 always_comb begin
  meta_en=0; meta_we0=0; meta_we1=0; lru_we=0; lru_d=0;
  meta_index=request_set; meta_d0=meta_q0; meta_d1=meta_q1;
  bank_en=0;
  for(integer b=0;b<4;b++) begin bank_addr[b]='0; bank_wdata[b]=0; bank_be[b]=0; end
  case(state)
   INIT: begin
    meta_index=init_set; meta_we0=1;meta_we1=1;meta_d0=0;meta_d1=0;lru_we=1;
   end
   LOOKUP: meta_en=1;
   CHECK: if(hit) begin
    bank_en[request_addr[3:2]]=1;
    bank_addr[request_addr[3:2]]={hit_way,request_set,request_addr[5:4]};
    bank_wdata[request_addr[3:2]]=request_byte ? {4{request_wdata[7:0]}} : request_wdata;
    if(request_write && !drop_response && !cnn_cancel) begin
     bank_be[request_addr[3:2]]=request_byte ? (4'b1<<request_addr[1:0]) : 4'hf;
     if(hit_way) begin meta_we1=1;meta_d1[TW]=1;end
     else begin meta_we0=1;meta_d0[TW]=1;end
    end
    lru_we=1;lru_d=!hit_way;
   end
   WB_READ: for(integer b=0;b<4;b++) begin
    bank_en[b]=1; bank_addr[b]={victim_line,chunk};
   end
   WB_WAIT: if(ddr_done && !ddr_error) begin
    meta_index=victim_line[SW-1:0];
    if(victim_line[LW-1]) begin
     meta_we1=1;meta_d1={!(maintenance && invalidate),1'b0,victim_tag};
    end else begin
     meta_we0=1;meta_d0={!(maintenance && invalidate),1'b0,victim_tag};
    end
   end
   FILL_WRITE: begin
    for(integer b=0;b<4;b++) begin
     bank_en[b]=1;bank_addr[b]={victim_line,chunk};bank_be[b]=4'hf;
     bank_wdata[b]=ddr_rline[(integer'(chunk)*4+b)*32 +: 32];
    end
    if(chunk==3) begin
     if(victim_line[LW-1]) begin meta_we1=1;meta_d1={2'b10,request_tag};end
     else begin meta_we0=1;meta_d0={2'b10,request_tag};end
     lru_we=1;lru_d=!victim_line[LW-1];
    end
   end
   SCAN_LOOKUP: begin meta_index=scan_set;meta_en=1;end
   SCAN_CHECK: begin
    meta_index=scan_set;
    if(scan_matches && !scan_meta[TW] && invalidate) begin
     if(scan_way) begin meta_we1=1;meta_d1=0;end
     else begin meta_we0=1;meta_d0=0;end
    end
   end
   default: ;
  endcase
 end

 task automatic advance_scan;
  if(scan_way) begin
   scan_way<=0;
   if(scan_set==SW'(SETS-1)) begin maintenance<=0;state<=IDLE;end
   else begin scan_set<=scan_set+1'b1;state<=SCAN_LOOKUP;end
  end else begin scan_way<=1;state<=SCAN_LOOKUP;end
 endtask

 always_comb begin
  cache_csr_rdata=0;
  case(cache_csr_addr[7:0])
   8'h00: cache_csr_rdata={27'b0,((cnn_cancel || drop_response) && state!=IDLE),cnn_mem_fault,csr_error,(state!=IDLE || maintenance_pending),initialized};
   8'h08: cache_csr_rdata=range_start;
   8'h0c: cache_csr_rdata=range_bytes;
   8'h10: cache_csr_rdata=readonly_end;
   8'h14: cache_csr_rdata={31'b0,protect_enable};
   8'h20: cache_csr_rdata=hits;
   8'h24: cache_csr_rdata=misses;
   8'h28: cache_csr_rdata=writebacks;
   8'h2c: cache_csr_rdata=fills;
   8'h30: cache_csr_rdata=ddr_read_bytes;
   8'h34: cache_csr_rdata=ddr_write_bytes;
   8'h38: cache_csr_rdata=wait_cycles;
   8'h3c: cache_csr_rdata=CACHE_BYTES;
   default: ;
  endcase
 end

 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=INIT;initialized<=0;init_set<=0;scan_set<=0;scan_way<=0;
   cnn_mem_fault<=0;csr_error<=0;drop_response<=0;maintenance<=0;invalidate<=0;
   maintenance_pending<=0;pending_invalidate<=0;pending_start<=0;pending_end<=0;
   range_start<=0;range_bytes<=LOGICAL_BYTES;readonly_end<=0;protect_enable<=0;
   scan_start<=0;scan_end<=0;round_robin<=0;request_owner<=0;
   request_addr<=0;request_wdata<=0;request_write<=0;request_byte<=0;request_missed<=0;
   victim_line<=0;victim_tag<=0;victim_logical<=0;chunk<=0;writeback_line<=0;
   response_q<='0;rdata_q<='0;hits<=0;misses<=0;writebacks<=0;fills<=0;
   ddr_read_bytes<=0;ddr_write_bytes<=0;wait_cycles<=0;
  end else begin
   response_q<='0;
   if(cnn_cancel && state!=IDLE) drop_response<=1;
   if((state==WB_WAIT || state==FILL_WAIT) && !ddr_done) wait_cycles<=wait_cycles+1;
   // Range registers are staging registers. A command snapshots them into a
   // one-entry queue, so firmware may fence a completed frame while other CNN
   // clients are running. New CNN accepts stop until the queued command runs.
   if(cache_csr_we) begin
    if(cache_csr_addr[1:0]!=0 || !initialized) csr_error<=1;
    else case(cache_csr_addr[7:0])
     8'h08: range_start<=cache_csr_wdata;
     8'h0c: range_bytes<=cache_csr_wdata;
     8'h10: if(state==IDLE && !maintenance_pending && cache_csr_wdata<=LOGICAL_BYTES)
       readonly_end<=cache_csr_wdata; else csr_error<=1;
     8'h14: if(state==IDLE && !maintenance_pending) protect_enable<=cache_csr_wdata[0]; else csr_error<=1;
     8'h04: begin
      case(cache_csr_wdata)
       1,2: if(!maintenance_pending && range_start<=LOGICAL_BYTES &&
                  {1'b0,range_start}+{1'b0,range_bytes}<={1'b0,LOGICAL_BYTES}) begin
        pending_start<=range_start;pending_end<=range_start+range_bytes;
        maintenance_pending<=1;pending_invalidate<=cache_csr_wdata==2;
       end else csr_error<=1;
       3: if(state==IDLE && !maintenance_pending) begin csr_error<=0;cnn_mem_fault<=0;end else csr_error<=1;
       default: csr_error<=1;
      endcase
     end
     default: csr_error<=1;
    endcase
   end
   case(state)
    INIT: if(init_set==SW'(SETS-1)) begin initialized<=1;state<=IDLE;end else init_set<=init_set+1'b1;
    IDLE: if(maintenance_pending) begin
     maintenance_pending<=0;scan_start<=pending_start;scan_end<=pending_end;
     scan_set<=0;scan_way<=0;maintenance<=1;invalidate<=pending_invalidate;
     state<=SCAN_LOOKUP;drop_response<=0;
    end else if(|cnn_ready) begin
     drop_response<=0;
     round_robin<=selected==CLIENTS-1 ? '0 : CW'(selected+1);
     if(selected_bad) cnn_mem_fault<=1;
     else begin
      request_owner<=CW'(selected);request_addr<=selected_addr;
      request_wdata<=cnn_wdata[selected*32 +: 32];request_write<=cnn_write[selected];
      request_byte<=cnn_byte[selected];request_missed<=0;state<=LOOKUP;
     end
    end
    LOOKUP: state<=CHECK;
    CHECK: if(drop_response || cnn_cancel) state<=IDLE;
     else if(hit) begin
      if(!request_missed) hits<=hits+1;
      state<=HIT_REPLY;
     end else begin
      misses<=misses+1;request_missed<=1;
      victim_line<={chosen_way,request_set};victim_tag<=chosen_meta[TW-1:0];
      victim_logical<={chosen_meta[TW-1:0],request_set,6'b0};chunk<=0;
      state<=chosen_meta[MW-1] && chosen_meta[TW] ? WB_READ : FILL_SEND;
     end
    HIT_REPLY: begin
     if(!drop_response && !cnn_cancel) begin
      response_q[request_owner]<=1;
      rdata_q[request_owner*32 +: 32]<=request_write ? 0 :
        request_byte ? {{24{hit_byte[7]}},hit_byte} : hit_word;
     end
     state<=IDLE;
    end
    WB_READ: state<=WB_CAPTURE;
    WB_CAPTURE: begin
     for(integer b=0;b<4;b++) writeback_line[(integer'(chunk)*4+b)*32 +: 32]<=bank_rdata[b];
     if(chunk==3) state<=WB_SEND;
     else begin chunk<=chunk+1'b1;state<=WB_READ;end
    end
    WB_SEND: if(cmd_ready) state<=WB_WAIT;
    WB_WAIT: if(ddr_done) begin
     if(ddr_error) begin cnn_mem_fault<=1;csr_error<=1;maintenance<=0;state<=IDLE;end
     else begin
      writebacks<=writebacks+1;ddr_write_bytes<=ddr_write_bytes+64;
      if(maintenance) advance_scan();
      else if(drop_response || cnn_cancel) state<=IDLE;
      else state<=FILL_SEND;
     end
    end
    FILL_SEND: if(cmd_ready) state<=FILL_WAIT;
    FILL_WAIT: if(ddr_done) begin
     if(ddr_error) begin cnn_mem_fault<=1;state<=IDLE;end
     else begin fills<=fills+1;ddr_read_bytes<=ddr_read_bytes+64;chunk<=0;state<=FILL_WRITE;end
    end
    FILL_WRITE: if(chunk==3) begin
     if(drop_response || cnn_cancel) state<=IDLE;else state<=LOOKUP;
    end else chunk<=chunk+1'b1;
    SCAN_LOOKUP: state<=SCAN_CHECK;
    SCAN_CHECK: if(scan_matches && scan_meta[TW]) begin
     victim_line<={scan_way,scan_set};victim_tag<=scan_meta[TW-1:0];
     victim_logical<=scan_line_addr;chunk<=0;state<=WB_READ;
    end else advance_scan();
    default: state<=INIT;
   endcase
  end
 end
`ifndef SYNTHESIS
 initial begin
  assert(CLIENTS>0 && SETS>=2 && (SETS & (SETS-1))==0) else $fatal(1,"cache geometry");
  assert(LOGICAL_BYTES[5:0]==0 && DDR_BASE[5:0]==0 &&
         {1'b0,DDR_BASE}+{1'b0,LOGICAL_BYTES}<=33'h100000000) else $fatal(1,"DDR aperture");
 end
`endif
endmodule
