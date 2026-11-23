// Adapt the convolution core's existing per-element interface to one bank
// command per span. A beat can satisfy one or more core requests.
module conv_span_port(
 input wire clk,rst_n,abort,c_valid,c_byte,c_double,
 input wire [31:0] c_addr,input wire [12:0] c_span,
 output wire c_ready,c_response,output wire [63:0] c_rdata,
 output wire busy,read_lock,output wire [2:0] phase,
 output wire cmd_valid,input wire cmd_ready,
 output wire [31:0] cmd_addr,output wire [12:0] cmd_bytes,
 input wire reader_busy,data_valid,data_last,input wire [3:0] data_bytes,input wire [63:0] data,
 output wire data_ready
);
 typedef enum logic [1:0] {IDLE,COMMAND,STREAM} state_t;
 state_t state;
 logic [31:0] base;
 logic [12:0] length;
 logic [2:0] lane;
 assign cmd_valid=state==COMMAND && !abort;
 assign cmd_addr=base;
 assign cmd_bytes=length;
 assign busy=state!=IDLE || reader_busy;
 assign read_lock=state!=IDLE;
 assign phase={1'b0,state};
 assign c_ready=state==STREAM && data_valid && c_valid && !abort;
 assign c_response=c_ready;
 assign c_rdata=c_double ? data : (c_byte ? {56'd0,data[lane*8+:8]} : {32'd0,lane[2]?data[63:32]:data[31:0]});
 wire [3:0] take_bytes=c_double?4'd8:(c_byte?4'd1:4'd4);
 wire [3:0] next_lane={1'b0,lane}+take_bytes;
 wire end_of_word=next_lane==data_bytes;
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
    else lane<=next_lane[2:0];
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
   assert(next_lane<=data_bytes);
   if(!c_byte)assert(lane[1:0]==0);
   expected<=expected+32'(take_bytes);
  end
 end
`endif
endmodule
