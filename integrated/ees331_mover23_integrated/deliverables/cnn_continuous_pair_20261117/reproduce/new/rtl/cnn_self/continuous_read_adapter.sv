// Ordered, bounded read-ahead for immutable inputs/weights. Four reserved
// response slots; bank responses have no backpressure and must remain ordered.
// read_end is exclusive, valid at the first demand of each contiguous run.
// clear MUST cancel both this adapter and the bank/interconnect in-flight work.
module continuous_read_adapter #(parameter DEPTH=4)(
 input logic clk,rst_n,clear,
 input wire c_valid,c_write,c_byte,input wire [31:0] c_addr,c_wdata,read_end,
 output wire c_ready,c_response,output wire [31:0] c_rdata,
 output wire m_valid,m_write,m_byte,output wire [31:0] m_addr,m_wdata,
 input wire m_ready,m_response,input wire [31:0] m_rdata,
 output wire idle,output wire [3:0] read_pending,
 output logic fault
);
 localparam P=$clog2(DEPTH),C=$clog2(DEPTH+1);
 logic [P-1:0] head,tail,returned;
 logic [C-1:0] count,pending;
 logic [DEPTH-1:0] got;
 logic [31:0] tags[DEPTH],data[DEPTH];
 logic stream,stream_byte,write_pending,read_hold,direct_is_read;
 logic [31:0] next_addr,end_addr;
 wire matched=count!=0 && tags[head]==c_addr;
 wire consume=c_valid && !c_write && matched && got[head] && !write_pending && !clear;
 wire direct_offer=c_valid && !c_write && (c_byte || read_end-c_addr<8) && count==0 && pending==0 && !write_pending && !read_hold;
 wire restart_stream=c_valid && !c_write && !direct_offer && !write_pending && pending==0 &&
  ((count==0 && (!stream || next_addr>=end_addr)) || (count!=0 && !matched)) && !read_hold && !clear;
 wire want_write=c_valid && c_write;
 wire can_write=(want_write || direct_offer) && pending==0 && !write_pending && !read_hold;
 wire want_read=stream && next_addr<end_addr && (count<DEPTH || consume) && (!want_write || read_hold) && !direct_offer && !write_pending;
 assign m_valid=rst_n && !clear && !fault && (can_write || want_read);
 assign m_write=can_write && c_write;
 assign m_byte=can_write?c_byte:stream_byte;
 assign m_addr=can_write?c_addr:next_addr;
 assign m_wdata=can_write?c_wdata:32'd0;
 wire take=m_valid && m_ready;
 wire issue=take && !can_write;
 wire take_write=take && can_write;
 wire read_return=m_response && !write_pending;
 assign c_ready=rst_n && !clear && !fault && ((c_write || direct_offer)?can_write && m_ready:consume);
 assign c_response=rst_n && !clear && !fault && (consume || (m_response && write_pending));
 assign c_rdata=consume?data[head]:m_rdata;
 assign read_pending=4'(pending)+(write_pending && direct_is_read?4'd1:4'd0);
 assign idle=pending==0 && !write_pending;
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   head<=0;tail<=0;returned<=0;count<=0;pending<=0;got<=0;
   stream<=0;stream_byte<=0;write_pending<=0;read_hold<=0;direct_is_read<=0;next_addr<=0;end_addr<=0;fault<=0;
  end else begin
   if(m_valid && !can_write)read_hold<=!m_ready;
   if(restart_stream)begin
    head<=0;tail<=0;returned<=0;count<=0;got<=0;
    stream<=1;stream_byte<=c_byte;next_addr<=c_addr;
    end_addr<=c_byte?c_addr+1:read_end;
   end else begin
    case({issue,consume})
     2'b10:count<=count+1'b1;
     2'b01:count<=count-1'b1;
     default:;
    endcase
    if(consume)begin got[head]<=0;head<=head+1'b1;end
    if(issue)begin tags[tail]<=next_addr;got[tail]<=0;tail<=tail+1'b1;next_addr<=next_addr+(stream_byte?1:4);end
    if(read_return)begin data[returned]<=m_rdata;got[returned]<=1;returned<=returned+1'b1;end
   end
   case({issue,read_return})
    2'b10:pending<=pending+1'b1;
    2'b01:pending<=pending-1'b1;
    default:;
   endcase
   if(take_write)begin write_pending<=1;direct_is_read<=!c_write;end
   if(m_response && write_pending)write_pending<=0;
   if(read_return && pending==0)fault<=1;
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n && !clear)begin
  assert(count<=DEPTH && pending<=count) else $fatal(1,"prefetch credit overflow");
  assert(!(restart_stream && (issue || read_return))) else $fatal(1,"restart collision");
  if(issue)assert({1'b0,next_addr}+(stream_byte?33'd1:33'd4)<={1'b0,end_addr}) else $fatal(1,"read beyond bounded run");
  if(read_return)assert(pending!=0) else $fatal(1,"unexpected ordered read response");
 end
 initial assert(DEPTH>=2 && (DEPTH&(DEPTH-1))==0);
`endif
endmodule
