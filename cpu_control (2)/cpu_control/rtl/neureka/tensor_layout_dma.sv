// Byte transpose CHW <-> HWC. Layout conversions are real SRAM transactions.
// lp[0]=0: CHW -> HWC; lp[0]=1: HWC -> CHW. Non-overlapping buffers required.
module tensor_layout_dma(
 input logic clk,rst_n,clear,start,input logic [255:0] descriptor,
 output wire busy,done,error,output wire valid,input wire ready,
 output wire write,byte_access,output wire [31:0] addr,wdata,
 input wire response,input wire [31:0] rdata
);
 typedef enum logic [2:0] {IDLE,READ_REQ,READ_WAIT,WRITE_REQ,WRITE_WAIT,DONE,ERROR} state_t;
 state_t state;
 logic [31:0] ia,oa,plane,channels,pixel,channel;
 logic direction;logic [7:0] value;
 wire [31:0] chw=channel*plane+pixel,hwc=pixel*channels+channel;
 assign busy=state!=IDLE && state!=DONE && state!=ERROR;
 assign done=state==DONE;assign error=state==ERROR;
 assign valid=(state==READ_REQ || state==WRITE_REQ) && !clear;
 assign write=state==WRITE_REQ;assign byte_access=1;
 assign addr=write ? oa+(direction ? chw:hwc) : ia+(direction ? hwc:chw);
 assign wdata={24'b0,value};
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin state<=IDLE;ia<=0;oa<=0;plane<=0;channels<=0;pixel<=0;channel<=0;direction<=0;value<=0;end
  else if(clear) state<=IDLE;
  else case(state)
   IDLE:if(start) begin
    ia<=descriptor[63:32];oa<=descriptor[95:64];
    plane<=32'(descriptor[191:176])*32'(descriptor[175:160]);channels<={16'b0,descriptor[207:192]};
    pixel<=0;channel<=0;direction<=descriptor[224];
    state<=descriptor[191:176]==0 || descriptor[175:160]==0 || descriptor[207:192]==0 ? ERROR:READ_REQ;
   end
   READ_REQ:if(ready) state<=READ_WAIT;
   READ_WAIT:if(response) begin value<=rdata[7:0];state<=WRITE_REQ;end
   WRITE_REQ:if(ready) state<=WRITE_WAIT;
   WRITE_WAIT:if(response) begin
    if(channel+1<channels) begin channel<=channel+1;state<=READ_REQ;end
    else if(pixel+1<plane) begin channel<=0;pixel<=pixel+1;state<=READ_REQ;end
    else state<=DONE;
   end
   DONE,ERROR:state<=IDLE;
   default:state<=IDLE;
  endcase
 end
endmodule
