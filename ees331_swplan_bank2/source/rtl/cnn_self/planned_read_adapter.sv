// Ordered, counted segments. No per-demand address/tag comparison or widening.
// clear is an epoch barrier: the fabric must cancel all client replies too.
// After clear, new work starts only after the enclosing fabric has quiesced.
module planned_read_adapter #(parameter integer DEPTH=4,MAX_BEATS=4608)(
 input logic clk,rst_n,clear,
 input wire c_valid,c_write,c_byte,
 input wire [31:0] c_addr,c_wdata,segment_beats,
 output wire c_ready,c_response,
 output wire [31:0] c_rdata,
 output wire m_valid,m_write,m_byte,
 output wire [31:0] m_addr,m_wdata,
 input wire m_ready,m_response,
 input wire [31:0] m_rdata,
 output wire idle,
 output logic fault
);
 localparam integer P=$clog2(DEPTH),C=$clog2(DEPTH+1),B=$clog2(MAX_BEATS+1);
 logic active,read_byte,write_queued,write_pending;
 logic [31:0] next_addr,write_addr,write_data;
 logic [B-1:0] issue_left,consume_left;
 logic write_byte;
 logic [P-1:0] head,tail,return_slot;
 logic [C-1:0] reserved,pending;
 logic [DEPTH-1:0] got;
 logic [31:0] data[DEPTH];
 logic reply_valid;
 logic [31:0] reply_data;
 wire read_offer=active && issue_left!=0 && reserved<DEPTH;
 assign m_valid=rst_n && !clear && !fault && (write_queued || read_offer);
 assign m_write=write_queued;
 assign m_addr=write_queued?write_addr:next_addr;
 assign m_wdata=write_data;
 assign m_byte=write_queued?write_byte:read_byte;
 wire issue=m_valid && m_ready && !m_write;
 wire write_take=m_valid && m_ready && m_write;
 wire read_return=m_response && !write_pending && !write_take;
 wire have_read=active && reserved!=0 && got[head];
 wire accept_write=c_valid && c_write && c_ready;
 wire consume=c_valid && !c_write && c_ready;
 assign c_ready=rst_n && !clear && !fault &&
  (c_write?(!active && reserved==0 && !write_queued && !write_pending && !reply_valid):have_read);
 assign c_response=reply_valid && !clear && !fault;
 assign c_rdata=reply_data;
 assign idle=!active && reserved==0 && !write_queued && !write_pending && !reply_valid;
 wire [32:0] segment_end={1'b0,c_addr}+({1'b0,segment_beats}<<(c_byte?0:2));
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   active<=0;read_byte<=0;write_queued<=0;write_pending<=0;
   next_addr<=0;issue_left<=0;consume_left<=0;write_addr<=0;write_data<=0;write_byte<=0;
   head<=0;tail<=0;return_slot<=0;reserved<=0;pending<=0;got<=0;
   reply_valid<=0;reply_data<=0;fault<=0;
  end else begin
   reply_valid<=0;
   // A demand starts a whole segment; the engine subsequently consumes the
   // FIFO in order. Segment metadata is latched before any bus request.
   if(c_valid && !c_write && idle && !fault)begin
    if(segment_beats==0 || segment_beats>MAX_BEATS || segment_end>33'h100000000 ||
       (!c_byte && c_addr[1:0]!=0))fault<=1;
    else begin
     active<=1;read_byte<=c_byte;next_addr<=c_addr;
     issue_left<=B'(segment_beats);consume_left<=B'(segment_beats);
     head<=0;tail<=0;return_slot<=0;got<=0;
    end
   end
   case({issue,consume})
    2'b10:reserved<=reserved+1'b1;
    2'b01:reserved<=reserved-1'b1;
    default:;
   endcase
   case({issue,read_return})
    2'b10:pending<=pending+1'b1;
    2'b01:pending<=pending-1'b1;
    default:;
   endcase
   if(consume)begin
    reply_data<=data[head];reply_valid<=1;
    got[head]<=0;head<=head+1'b1;consume_left<=consume_left-1'b1;
    if(consume_left==1)active<=0;
   end
   if(issue)begin
    got[tail]<=0;tail<=tail+1'b1;issue_left<=issue_left-1'b1;
    next_addr<=next_addr+(read_byte?32'd1:32'd4);
   end
   if(read_return)begin
    if(pending==0 && !issue)fault<=1;
    else begin data[return_slot]<=m_rdata;got[return_slot]<=1;return_slot<=return_slot+1'b1;end
   end
   if(accept_write)begin
    write_queued<=1;write_addr<=c_addr;write_data<=c_wdata;write_byte<=c_byte;
   end
   if(write_take)begin write_queued<=0;write_pending<=1;end
   // Includes zero-cycle bus completion for a newly accepted write.
   if(m_response && (write_pending || write_take))begin
    write_pending<=0;reply_valid<=1;reply_data<=m_rdata;
   end
  end
 end
`ifndef SYNTHESIS
 initial assert(DEPTH>=2 && (DEPTH&(DEPTH-1))==0);
 always_ff @(posedge clk)if(rst_n && !clear && !fault)begin
  assert(reserved<=DEPTH && pending<=reserved)else $fatal(1,"planned read credit overflow");
  if(consume && consume_left==1)
   assert(issue_left==0 && pending==0 && reserved==1)else $fatal(1,"segment ended before drain");
 end
`endif
endmodule
