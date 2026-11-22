// Adapt the convolution core's existing per-element interface to one bank
// command per span. A beat can satisfy one or more core requests.
module conv_span_port #(
 parameter integer DATA_BITS=64,
 localparam integer LANE_BITS=$clog2(DATA_BITS/8),
 localparam integer BYTE_BITS=LANE_BITS+1
)(
 input wire clk,rst_n,abort,c_valid,c_byte,c_double,
 input wire [31:0] c_addr,input wire [12:0] c_span,
 output wire c_ready,c_response,output wire [63:0] c_rdata,
 output wire busy,read_lock,output wire [2:0] phase,
 output wire cmd_valid,input wire cmd_ready,
 output wire [31:0] cmd_addr,output wire [12:0] cmd_bytes,
 input wire reader_busy,data_valid,data_last,input wire [BYTE_BITS-1:0] data_bytes,input wire [DATA_BITS-1:0] data,
 output wire data_ready
);
 typedef enum logic [1:0] {IDLE,COMMAND,STREAM} state_t;
 state_t state;
 logic [31:0] base;
 logic [12:0] length;
 logic [LANE_BITS-1:0] lane;
 assign cmd_valid=state==COMMAND && !abort;
 assign cmd_addr=base;
 assign cmd_bytes=length;
 assign busy=state!=IDLE || reader_busy;
 assign read_lock=state!=IDLE;
 assign phase={1'b0,state};
 assign c_ready=state==STREAM && data_valid && c_valid && !abort;
 assign c_response=c_ready;
 wire [63:0] double_word=data[(int'(lane)>>3)*64+:64];
 wire [31:0] word=data[(int'(lane)>>2)*32+:32];
 assign c_rdata=c_double ? double_word : (c_byte ? {56'd0,data[lane*8+:8]} : {32'd0,word});
 wire [BYTE_BITS-1:0] take_bytes=c_double?BYTE_BITS'(8):(c_byte?BYTE_BITS'(1):BYTE_BITS'(4));
 wire [BYTE_BITS-1:0] next_lane={1'b0,lane}+take_bytes;
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
    else lane<=next_lane[LANE_BITS-1:0];
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
   if(c_double)assert(lane[2:0]==0);
   expected<=expected+32'(take_bytes);
  end
 end
`endif
endmodule
