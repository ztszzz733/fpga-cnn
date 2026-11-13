// Materialize a one-pixel zero-point border around an HWC tensor.
// Packed word transfers when channels are a multiple of four, byte otherwise.
module pad_hwc_engine(
 input logic clk,rst_n,clear,start,
 input logic [31:0] source,destination,width,height,channels,
 input logic [7:0] zero_point,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
 typedef enum logic [3:0] {IDLE,SELECT,RREQ,RWAIT,WREQ,WWAIT,FINISH,FAIL} state_t;
 state_t state;
 logic [31:0] src,dst,w,h,c,x,y,ch,value,step;
 logic [7:0] fill;
 wire border=x==0 || y==0 || x==w+1 || y==h+1;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;
 assign valid=!clear && (state==RREQ || state==WREQ);
 assign write=state==WREQ;assign byte_access=step==1;
 always_comb begin
  addr=state==RREQ ? src+((y-1)*w+x-1)*c+ch : dst+(y*(w+2)+x)*c+ch;
  wdata=value;
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;src<=0;dst<=0;w<=0;h<=0;c<=0;x<=0;y<=0;ch<=0;value<=0;step<=1;fill<=0;end
  else if(clear)state<=IDLE;
  else case(state)
   IDLE:if(start)begin
    src<=source;dst<=destination;w<=width;h<=height;c<=channels;fill<=zero_point;x<=0;y<=0;ch<=0;
    step<=channels%4==0 ? 4:1;
    state<=width==0 || height==0 || channels==0 || width>112 || height>112 || channels>512 ||
           (channels%4==0 && ((source|destination)&3)!=0) ? FAIL:SELECT;
   end
   SELECT:if(border)begin value<={4{fill}};state<=WREQ;end else state<=RREQ;
   RREQ:if(ready)state<=RWAIT;
   RWAIT:if(response)begin value<=rdata;state<=WREQ;end
   WREQ:if(ready)state<=WWAIT;
   WWAIT:if(response)begin
    state<=SELECT;
    if(ch+step<c)ch<=ch+step;
    else begin ch<=0;if(x<w+1)x<=x+1;else begin x<=0;if(y<h+1)y<=y+1;else state<=FINISH;end end
   end
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
  endcase
 end
endmodule
