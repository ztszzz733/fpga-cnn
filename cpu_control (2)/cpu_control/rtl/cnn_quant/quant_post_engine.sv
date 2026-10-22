// HWC affine requantization / residual addition, one outstanding SRAM command.
// Parameters per channel (five words): bias, multiplier A, multiplier B,
// {output_zero, input_B_zero, input_A_zero, shift}, {16'b0, clamp_hi, clamp_lo}.
// mode_add=0: int32 accumulator + bias -> uint8. mode_add=1: two uint8 inputs.
// Rounding is nearest with ties away from zero, once after the sum.
module quant_post_engine #(parameter MAX_CHANNELS=512)(
 input logic clk,rst_n,clear,start,mode_add,
 input logic [31:0] src_a,src_b,destination,parameter_base,count,channels,
 output wire busy,done,error,
 output wire valid,write,byte_access,output logic [31:0] addr,wdata,
 input wire ready,response,input wire [31:0] rdata
);
 typedef enum logic [3:0] {IDLE,PR,PW,AR,AW,BR,BW,CALC,WR,WW,FINISH,FAIL} state_t;
 state_t state;
 logic [31:0] pa,pb,pout,pp,n,nch,index,ch,pi;
 logic add;
 logic [31:0] params[0:MAX_CHANNELS*5-1];
 logic signed [31:0] a,b;
 logic [7:0] value;
 logic signed [95:0] ax,bx,product,rounded,half;
 logic [7:0] shift,za,zb,zo,lo,hi;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;
 assign error=state==FAIL;
 assign valid=(state==PR || state==AR || state==BR || state==WR) && !clear;
 assign write=state==WR;
 assign byte_access=state==WR || state==BR || (state==AR && add);
 always_comb begin
  addr=0;wdata={24'b0,value};
  case(state)
   PR:addr=pp+pi*4;
   AR:addr=pa+(add ? index:index*4);
   BR:addr=pb+index;
   WR:addr=pout+index;
   default:;
  endcase
  shift=params[ch*5+3][7:0];za=params[ch*5+3][15:8];
  zb=params[ch*5+3][23:16];zo=params[ch*5+3][31:24];
  lo=params[ch*5+4][7:0];hi=params[ch*5+4][15:8];
  ax=96'($signed(a));bx=96'($signed(b));
  if(add) begin ax=ax-96'({1'b0,za});bx=bx-96'({1'b0,zb});end
  else ax=ax+96'($signed(params[ch*5]));
  product=ax*96'($signed(params[ch*5+1]));
  if(add) product=product+bx*96'($signed(params[ch*5+2]));
  half=shift==0 ? 0:(96'sd1 << (shift-1));
  rounded=shift==0 ? product:(product<0 ? -(((-product)+half) >>> shift):((product+half) >>> shift));
  rounded=rounded+96'({1'b0,zo});
 end
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin state<=IDLE;pa<=0;pb<=0;pout<=0;pp<=0;n<=0;nch<=0;index<=0;ch<=0;pi<=0;add<=0;a<=0;b<=0;value<=0;end
  else if(clear) state<=IDLE;
  else case(state)
   IDLE:if(start) begin
    pa<=src_a;pb<=src_b;pout<=destination;pp<=parameter_base;n<=count;nch<=channels;
    index<=0;ch<=0;pi<=0;add<=mode_add;
    state<=channels==0 || channels>MAX_CHANNELS || count==0 || parameter_base[1:0]!=0 || (!mode_add && src_a[1:0]!=0) ? FAIL:PR;
   end
   PR:if(ready) state<=PW;
   PW:if(response) begin
    params[pi]<=rdata;
    if((pi%5==3 && rdata[7:0]>63) || (pi%5==4 && rdata[7:0]>rdata[15:8])) state<=FAIL;
    else if(pi+1==nch*5) state<=AR;
    else begin pi<=pi+1;state<=PR;end
   end
   AR:if(ready) state<=AW;
   AW:if(response) begin a<=add ? $signed({24'b0,rdata[7:0]}):$signed(rdata);state<=add ? BR:CALC;end
   BR:if(ready) state<=BW;
   BW:if(response) begin b<=$signed({24'b0,rdata[7:0]});state<=CALC;end
   CALC:begin
    value<=rounded<$signed({1'b0,lo}) ? lo:(rounded>$signed({1'b0,hi}) ? hi:rounded[7:0]);state<=WR;
   end
   WR:if(ready) state<=WW;
   WW:if(response) begin
    if(index+1==n) state<=FINISH;
    else begin index<=index+1;ch<=ch+1==nch ? 0:ch+1;state<=AR;end
   end
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
  endcase
 end
endmodule
