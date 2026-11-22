// Stage a complete page-local run before claiming the shared client port.
// After a header is offered it must drain, even if its operator is aborted.
module page_write_bridge(
 input wire clk,rst_n,abort,fault,launch,
 input wire c_valid,c_wide,
 input wire [31:0] c_addr,
 input wire [255:0] c_data,
 input wire [5:0] c_beats,
 output wire c_take,pending,owns_port,busy,
 output wire [2:0] phase,
 output wire m_valid,m_wide,
 output wire [31:0] m_addr,
 output wire [255:0] m_data,
 output wire [5:0] m_beats,
 input wire m_ready,m_response
);
 typedef enum logic [2:0] {IDLE,COLLECT,READY,STREAM,WAIT_REPLY} state_t;
 state_t state;
 logic [31:0] base;
 logic wide;
 logic [5:0] length;
 logic [4:0] index;
 (* ram_style="distributed" *) logic [255:0] payload[32];

 assign c_take=c_valid && !abort && !fault && (state==IDLE || state==COLLECT);
 assign pending=state==READY && !abort && !fault;
 assign owns_port=state==STREAM || state==WAIT_REPLY;
 assign busy=state!=IDLE;
 assign phase=state;
 assign m_valid=state==STREAM && !fault;
 assign m_wide=wide;
 assign m_addr={base[31:10],base[9:0]+{index,5'b0}};
 assign m_data=payload[index];
 assign m_beats=(m_valid && index==0 && length>1) ? length : 6'd0;

 always_ff @(posedge clk)begin
  if(c_take)payload[index]<=c_data;
  if(!rst_n || fault)begin
   state<=IDLE;index<=0;base<=0;wide<=0;length<=0;
  end else case(state)
   IDLE:if(c_take)begin
    base<=c_addr;length<=c_beats;wide<=c_wide;
    if(c_beats==1)state<=READY;
    else begin index<=1;state<=COLLECT;end
   end
   COLLECT:if(abort)begin state<=IDLE;index<=0;end
    else if(c_take)begin
     if({1'b0,index}+6'd1==length)begin state<=READY;index<=0;end
     else index<=index+1'b1;
    end
   READY:if(abort)state<=IDLE;
    else if(launch)state<=STREAM;
   STREAM:if(m_ready)begin
    if({1'b0,index}+6'd1==length)begin state<=WAIT_REPLY;index<=0;end
    else index<=index+1'b1;
   end
   WAIT_REPLY:if(m_response)state<=IDLE;
   default:begin state<=IDLE;index<=0;end
  endcase
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n && !fault)begin
  if(c_take && state==IDLE)assert(c_beats>=1 && c_beats<=32 &&
    (c_beats==1 || (c_wide && ({1'b0,c_addr[9:0]}+{c_beats,5'b0})<=1024)))
   else $fatal(1,"invalid page write run");
  if(c_take && state==COLLECT)assert(c_wide && c_addr==m_addr)
   else $fatal(1,"non-contiguous staged page write");
  if(m_response)assert(state==WAIT_REPLY)else $fatal(1,"unexpected page write reply");
 end
`endif
endmodule
