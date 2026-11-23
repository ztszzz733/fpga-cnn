// One contiguous byte-range command, ordered 8B/4B/1B pager accesses and elastic
// returns. Byte accesses at each end keep every physical read inside the range.
module bank_span_reader #(parameter bit READ64=1)(
 input wire clk,rst_n,abort,
 input wire cmd_valid,
 input wire [31:0] cmd_addr,input wire [12:0] cmd_bytes,
 output wire cmd_ready,busy,
 output wire data_valid,data_last,output wire [3:0] data_bytes,output wire [63:0] data,
 input wire data_ready,
 output wire m_valid,m_byte,m_double,output wire [31:0] m_addr,
 input wire m_ready,m_response,input wire [63:0] m_rdata
);
 localparam integer DEPTH=4;
 logic active,discard,stalled;
 logic [12:0] remaining;
 logic [31:0] address;
 logic [2:0] issued,returned,consumed;
 logic [63:0] payload[DEPTH];
 logic [3:0] beat_bytes[DEPTH];
 logic last_beat[DEPTH];
 wire [2:0] reserved=issued-consumed;
 wire has_data=returned!=consumed;
 wire wide=address[1:0]==0 && remaining>=4;
 assign m_double=READ64 && address[2:0]==0 && remaining>=8;
 wire [12:0] step=m_double?13'd8:(wide?13'd4:13'd1);
 wire last_issue=remaining==step;
 assign busy=active;
 assign cmd_ready=!active && !abort;
 // Once offered, even an aborted request keeps stable pins until acceptance.
 assign m_valid=active && remaining!=0 && reserved<DEPTH &&
                ((!abort && !discard) || stalled);
 assign m_byte=!wide;
 assign m_addr=address;
 wire issue=m_valid && m_ready;
 assign data_valid=active && has_data && !abort && !discard;
 assign data=payload[consumed[1:0]];
 assign data_bytes=beat_bytes[consumed[1:0]];
 assign data_last=last_beat[consumed[1:0]];
 always_ff @(posedge clk)begin
  if(!rst_n)begin
   active<=0;discard<=0;stalled<=0;remaining<=0;
   issued<=0;returned<=0;consumed<=0;
  end else if(cmd_valid && cmd_ready)begin
   active<=1;discard<=0;stalled<=0;
   address<=cmd_addr;
   remaining<=cmd_bytes;issued<=0;returned<=0;consumed<=0;
  end else if(active)begin
   stalled<=m_valid && !m_ready;
   if(issue)begin
    beat_bytes[issued[1:0]]<=step[3:0];last_beat[issued[1:0]]<=last_issue;
    issued<=issued+1'b1;remaining<=remaining-step;address<=address+32'(step);
   end
   if(m_response)begin payload[returned[1:0]]<=m_rdata;returned<=returned+1'b1;end
   if(data_valid && data_ready)begin
    consumed<=consumed+1'b1;
    if(data_last)active<=0;
   end
   if(abort || discard)begin
    discard<=1;
    if(!m_valid && issued==returned)active<=0;
   end
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n)begin
  if(cmd_ready && cmd_valid)assert(cmd_bytes!=0);
  if(m_response)assert(active && (issued!=returned || issue));
  if(active)assert(reserved<=DEPTH);
 end
`endif
endmodule
