// One buffered request, one outstanding external transaction, registered reply.
// c_ready and c_response are returned together only after external completion.
// Abort drains a buffered/accepted request before becoming idle; no late reply
// can be reassigned to a later job. It may finish an already buffered write.
module simple_mem_bridge #(parameter integer DATA_BITS=32)(
 input wire clk,rst_n,abort,
 input wire c_valid,c_write,c_byte,c_quad,input wire [31:0] c_addr,
 input wire [DATA_BITS-1:0] c_wdata,
 output wire c_ready,c_response,output wire [31:0] c_rdata,
 output wire m_valid,m_write,m_byte,m_quad,output wire [31:0] m_addr,
 output wire [DATA_BITS-1:0] m_wdata,
 input wire m_ready,m_response,input wire [31:0] m_rdata,
 output wire busy,output wire [2:0] phase
);
 typedef enum logic [2:0] {IDLE,OFFER,WAIT_REPLY,RETURN,QUIET} state_t;
 state_t state;
 logic write_q,byte_q,quad_q,discard;
 logic [31:0] addr_q,rdata_q;
 logic [DATA_BITS-1:0] wdata_q;
 assign m_valid=state==OFFER;
 assign m_write=write_q;assign m_byte=byte_q;
 assign m_quad=quad_q;assign m_addr=addr_q;assign m_wdata=wdata_q;
 assign c_ready=state==RETURN && !abort && !discard;
 assign c_response=c_ready;assign c_rdata=rdata_q;
 assign busy=state!=IDLE;assign phase=state;
 always_ff @(posedge clk)begin
  if(!rst_n)begin
   state<=IDLE;write_q<=0;byte_q<=0;quad_q<=0;addr_q<=0;wdata_q<=0;rdata_q<=0;discard<=0;
  end else begin
   if(abort)discard<=1;
   case(state)
    IDLE:begin
     discard<=abort;
     if(c_valid && !abort)begin
      write_q<=c_write;byte_q<=c_byte;quad_q<=c_quad;addr_q<=c_addr;wdata_q<=c_wdata;
      state<=OFFER;discard<=0;
     end
    end
    OFFER:if(m_ready)begin
     if(m_response)begin rdata_q<=m_rdata;state<=(abort || discard)?QUIET:RETURN;end
     else state<=WAIT_REPLY;
    end
    WAIT_REPLY:if(m_response)begin rdata_q<=m_rdata;state<=(abort || discard)?QUIET:RETURN;end
    RETURN:state<=QUIET;
    QUIET:state<=IDLE;
    default:state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n)begin
  assert(!(m_response && state!=WAIT_REPLY && !(state==OFFER && m_ready))) else $fatal(1,"unsolicited memory reply");
 end
`endif
endmodule
