// Four ordered reads, two posted writes, registered external request/data.
// Read-ahead is bounded by the engine's current contiguous span. A changed
// request drains and discards the unfinished span before crossing modes.
// Abort drains accepted reads and captured writes before releasing busy.
module simple_mem_bridge(
 input wire clk,rst_n,abort,
 input wire c_valid,c_write,c_byte,input wire [31:0] c_addr,c_wdata,
 input wire [12:0] c_read_beats,
 output wire c_ready,c_response,output wire [31:0] c_rdata,
 output wire m_valid,m_write,m_byte,output wire [31:0] m_addr,m_wdata,
 input wire m_ready,m_response,input wire [31:0] m_rdata,
 output wire busy,output wire [2:0] phase
);
 typedef enum logic [1:0] {IDLE,READS,WRITES} state_t;
 state_t state;
 logic offer_valid,offer_write,offer_byte,discard,delivery_valid;
 logic [31:0] delivery_data;
 logic [31:0] offer_addr,offer_data,next_addr,consume_addr;
 logic read_byte;
 logic [12:0] issue_left,consume_left;
 logic [1:0] read_head,read_tail,reply_tail;
 logic [2:0] reserved,read_pending,write_pending;
 logic [3:0] got;
 logic [31:0] data[4];
 logic [31:0] write_addr[2],write_data[2];
 logic write_byte[2];
 logic write_head,write_tail;
 logic [1:0] write_count;
 wire external_take=offer_valid && m_ready;
 wire read_take=external_take && !offer_write;
 wire write_take=external_take && offer_write;
 wire read_reply=state==READS && m_response && (read_pending!=0 || read_take);
 wire write_reply=state==WRITES && m_response && (write_pending!=0 || write_take);
 wire read_match=c_valid && !c_write && c_addr==consume_addr && c_byte==read_byte;
 wire consume=state==READS && delivery_valid && c_valid && !discard && !abort;
 wire push_write=c_valid && c_write && c_ready;
 // An offered transaction holds valid and payload through external stalls.
 wire load_read=state==READS && !discard && !abort && issue_left!=0 &&
                (!offer_valid || external_take) && reserved<(external_take?3:4);
 wire load_write=state==WRITES && (!offer_valid || external_take) && write_count!=0 && write_pending<3;
 assign c_ready=!abort && ((state==READS && delivery_valid && !discard) ||
                           (state!=READS && c_write && write_count<2));
 assign c_response=c_ready;
 assign c_rdata=delivery_data;
 assign m_valid=offer_valid;assign m_write=offer_write;assign m_byte=offer_byte;
 assign m_addr=offer_addr;assign m_wdata=offer_data;
 assign busy=state!=IDLE || offer_valid || write_count!=0 || write_pending!=0;
 assign phase={1'b0,state};
 always_ff @(posedge clk)begin
  if(!rst_n)begin
   state<=IDLE;offer_valid<=0;offer_write<=0;offer_byte<=0;offer_addr<=0;offer_data<=0;
   discard<=0;delivery_valid<=0;delivery_data<=0;
   read_byte<=0;next_addr<=0;consume_addr<=0;issue_left<=0;consume_left<=0;
   read_head<=0;read_tail<=0;reply_tail<=0;reserved<=0;read_pending<=0;write_pending<=0;got<=0;
   write_head<=0;write_tail<=0;write_count<=0;
  end else begin
   if(external_take)offer_valid<=0;
   if(push_write)begin
    write_addr[write_tail]<=c_addr;write_data[write_tail]<=c_wdata;write_byte[write_tail]<=c_byte;
    write_tail<=!write_tail;
   end
   if(load_write)begin
    offer_valid<=1;offer_write<=1;offer_byte<=write_byte[write_head];
    offer_addr<=write_addr[write_head];offer_data<=write_data[write_head];write_head<=!write_head;
   end
   case({push_write,load_write})
    2'b10:write_count<=write_count+1'b1;
    2'b01:write_count<=write_count-1'b1;
    default:;
   endcase
   case({write_take,write_reply})
    2'b10:write_pending<=write_pending+1'b1;
    2'b01:write_pending<=write_pending-1'b1;
    default:;
   endcase
   case(state)
    IDLE:begin
     discard<=0;delivery_valid<=0;
     if(write_count!=0)state<=WRITES;
     else if(c_valid && !c_write && !abort)begin
      state<=READS;read_byte<=c_byte;next_addr<=c_addr;consume_addr<=c_addr;
      issue_left<=c_read_beats==0?13'd1:c_read_beats;
      consume_left<=c_read_beats==0?13'd1:c_read_beats;
      read_head<=0;read_tail<=0;reply_tail<=0;reserved<=0;read_pending<=0;got<=0;
     end
    end
    READS:begin
     // Register address validation and data before completing the core demand.
     // The core holds this demand until c_ready, or abort cancels it.
     if(!delivery_valid && read_match && reserved!=0 && got[read_head] && !discard && !abort)begin
      delivery_valid<=1;delivery_data<=data[read_head];
     end
     if(load_read)begin
      offer_valid<=1;offer_write<=0;offer_byte<=read_byte;offer_addr<=next_addr;offer_data<=0;
      next_addr<=next_addr+(read_byte?32'd1:32'd4);issue_left<=issue_left-1'b1;
     end
     if(read_take)read_tail<=read_tail+1'b1;
     if(consume)begin
      delivery_valid<=0;
      got[read_head]<=0;read_head<=read_head+1'b1;
      consume_addr<=consume_addr+(read_byte?32'd1:32'd4);consume_left<=consume_left-1'b1;
      if(consume_left==1)state<=IDLE;
     end
     if(read_reply)begin
      data[reply_tail]<=m_rdata;got[reply_tail]<=1;reply_tail<=reply_tail+1'b1;
     end
     case({read_take,consume})
      2'b10:reserved<=reserved+1'b1;
      2'b01:reserved<=reserved-1'b1;
      default:;
     endcase
     case({read_take,read_reply})
      2'b10:read_pending<=read_pending+1'b1;
      2'b01:read_pending<=read_pending-1'b1;
      default:;
     endcase
     if(abort || (c_valid && !read_match))begin discard<=1;delivery_valid<=0;end
     if(discard && !offer_valid && read_pending==0)begin
      state<=IDLE;reserved<=0;got<=0;discard<=0;
     end
    end
    WRITES:if(write_count==0 && !offer_valid && write_pending==0)state<=IDLE;
    default:state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n)begin
  assert(reserved<=4 && read_pending<=4 && write_pending<=4 && write_count<=2)
   else $fatal(1,"stream bridge credit overflow");
  if(m_response)assert(read_reply || write_reply)else $fatal(1,"unsolicited stream reply");
  if(consume && consume_left==1)
   assert(reserved==1 && read_pending==0 && !offer_valid && issue_left==0)
    else $fatal(1,"segment completed with unread requests");
 end
`endif
endmodule
