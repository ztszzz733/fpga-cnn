// Adapt the convolution core's existing per-element interface to one bank
// command per span. A returned packed word can satisfy four byte requests.
module conv_span_port(
 input wire clk,rst_n,abort,c_valid,c_byte,
 input wire [31:0] c_addr,input wire [12:0] c_span,
 output wire c_ready,c_response,output wire [31:0] c_rdata,
 output wire busy,read_lock,output wire [2:0] phase,
 output wire cmd_valid,input wire cmd_ready,
 output wire [31:0] cmd_addr,output wire [12:0] cmd_bytes,
 input wire reader_busy,data_valid,data_word,data_last,input wire [31:0] data,
 output wire data_ready
);
 typedef enum logic [1:0] {IDLE,COMMAND,STREAM} state_t;
 state_t state;
 logic [31:0] base;
 logic [12:0] length;
 logic [1:0] lane;
 assign cmd_valid=state==COMMAND && !abort;
 assign cmd_addr=base;
 assign cmd_bytes=length;
 assign busy=state!=IDLE || reader_busy;
 assign read_lock=state!=IDLE;
 assign phase={1'b0,state};
 assign c_ready=state==STREAM && data_valid && c_valid && !abort;
 assign c_response=c_ready;
 assign c_rdata=c_byte ? {24'd0,data[lane*8+:8]} : data;
 wire end_of_word=!data_word || !c_byte || lane==3;
 assign data_ready=c_ready && end_of_word;
 always_ff @(posedge clk)begin
  if(!rst_n || abort)begin state<=IDLE;lane<=0;end
  else case(state)
   IDLE:if(c_valid && !reader_busy)begin
    base<=c_addr;
    length<=c_span;
    lane<=0;state<=COMMAND;
   end
   COMMAND:if(cmd_ready)state<=STREAM;
   STREAM:if(c_ready)begin
    if(end_of_word)begin lane<=0;if(data_last)state<=IDLE;end
    else lane<=lane+1'b1;
   end
   default:state<=IDLE;
  endcase
 end
`ifndef SYNTHESIS
 logic [31:0] expected;
 always_ff @(posedge clk)begin
  if(cmd_valid && cmd_ready)expected<=base;
  if(c_ready)begin
   assert(c_addr==expected) else $fatal(1,"span discontinuity %x expected %x",c_addr,expected);
   if(!c_byte)assert(data_word && lane==0);
   expected<=expected+(c_byte?1:4);
  end
 end
`endif
endmodule
