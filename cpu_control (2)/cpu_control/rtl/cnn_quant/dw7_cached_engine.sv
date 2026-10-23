// Independent depthwise 7x7, stride 1, valid convolution. UINT8 x INT8 -> INT32.
// Eight channel lanes; 32-bit packed loads. Weights persist across jobs, while
// a seven-row ring retains the current channel block's overlapping windows.
// No requantization/activation here: feed the existing quant_post_engine.
module dw7_cached_engine #(
 parameter integer MAX_WIDTH=112, MAX_CHANNELS=512, LANES=8
)(
 input logic clk,rst_n,clear,start,reuse_weights,
 input logic [31:0] input_base,weight_base,output_base,
 input logic [31:0] width,height,channels,
 output wire busy,done,error,valid,write,byte_access,cancel,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata,
 output wire [3:0] phase,
 output wire mac_fire,weights_cached,
 output logic cache_hit
);
 typedef enum logic [3:0] {IDLE,WREQ,WWAIT,IREQ,IWAIT,ZERO,MAC,OREQ,OWAIT,FINISH,FAIL} state_t;
 state_t state;
 logic signed [7:0] weight_mem[49][MAX_CHANNELS];
 logic [7:0] row_mem[7][MAX_WIDTH][LANES];
 logic signed [31:0] acc[LANES];
 logic [31:0] ib,wb,ob,w,h,c,ow,oh;
 integer wt,wc,block_c,load_y,load_x,load_lane,oy,ox,tap,out_lane;
 logic cache_valid;
 logic [31:0] cache_base,cache_channels;
 assign phase=state;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;
 assign cancel=clear;
 assign valid=!clear && (state==WREQ || state==IREQ || state==OREQ);
 assign write=state==OREQ;assign byte_access=0;
 assign mac_fire=state==MAC && !clear;assign weights_cached=cache_valid;
 always_comb begin
  addr=0;wdata=0;
  case(state)
   WREQ:addr=wb+32'(wt)*c+32'(wc);
   IREQ:addr=ib+(32'(load_y)*w+32'(load_x))*c+32'(block_c+load_lane);
   OREQ:begin addr=ob+((32'(oy)*ow+32'(ox))*c+32'(block_c+out_lane))*4;wdata=acc[out_lane];end
   default:;
  endcase
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;cache_valid<=0;cache_hit<=0;cache_base<=0;cache_channels<=0;
   ib<=0;wb<=0;ob<=0;w<=0;h<=0;c<=0;ow<=0;oh<=0;
   wt<=0;wc<=0;block_c<=0;load_y<=0;load_x<=0;load_lane<=0;oy<=0;ox<=0;tap<=0;out_lane<=0;
  end else if(clear)begin state<=IDLE;cache_valid<=0;cache_hit<=0;end
  else case(state)
   IDLE:if(start)begin
    ib<=input_base;wb<=weight_base;ob<=output_base;w<=width;h<=height;c<=channels;ow<=width-6;oh<=height-6;
    wt<=0;wc<=0;block_c<=0;load_y<=0;load_x<=0;load_lane<=0;oy<=0;ox<=0;tap<=0;out_lane<=0;cache_hit<=0;
    // Address extents/non-overlap remain a descriptor-builder responsibility.
    if(width<7 || width>MAX_WIDTH || height<7 || height>65535 || channels==0 || channels>MAX_CHANNELS ||
       channels%LANES!=0 || LANES%4!=0 || (input_base|weight_base|output_base)&3)state<=FAIL;
    else if(reuse_weights && cache_valid && cache_base==weight_base && cache_channels==channels)begin cache_hit<=1;state<=IREQ;end
    else begin cache_valid<=0;state<=WREQ;end
   end
   WREQ:if(ready)state<=WWAIT;
   WWAIT:if(response)begin
    for(integer b=0;b<4;b++)weight_mem[wt][wc+b]<=rdata[b*8+:8];
    if(wc+4==c)begin
     wc<=0;
     if(wt==48)begin cache_valid<=1;cache_base<=wb;cache_channels<=c;state<=IREQ;end
     else begin wt<=wt+1;state<=WREQ;end
    end else begin wc<=wc+4;state<=WREQ;end
   end
   IREQ:if(ready)state<=IWAIT;
   IWAIT:if(response)begin
    for(integer b=0;b<4;b++)row_mem[load_y%7][load_x][load_lane+b]<=rdata[b*8+:8];
    if(load_lane+4==LANES)begin
     load_lane<=0;
     if(load_x+1==w)begin
      load_x<=0;
      if(load_y==oy+6)state<=ZERO;
      else begin load_y<=load_y+1;state<=IREQ;end
     end else begin load_x<=load_x+1;state<=IREQ;end
    end else begin load_lane<=load_lane+4;state<=IREQ;end
   end
   ZERO:begin for(integer lane=0;lane<LANES;lane++)acc[lane]<=0;tap<=0;state<=MAC;end
   MAC:begin
    for(integer lane=0;lane<LANES;lane++)
     acc[lane]<=acc[lane]+32'($signed({1'b0,row_mem[(oy+tap/7)%7][ox+tap%7][lane]})*$signed(weight_mem[tap][block_c+lane]));
    if(tap==48)begin out_lane<=0;state<=OREQ;end else tap<=tap+1;
   end
   OREQ:if(ready)state<=OWAIT;
   OWAIT:if(response)begin
    if(out_lane+1<LANES)begin out_lane<=out_lane+1;state<=OREQ;end
    else if(ox+1<ow)begin ox<=ox+1;state<=ZERO;end
    else if(oy+1<oh)begin oy<=oy+1;ox<=0;load_y<=oy+7;load_x<=0;load_lane<=0;state<=IREQ;end
    else if(block_c+LANES<c)begin
     block_c<=block_c+LANES;oy<=0;ox<=0;load_y<=0;load_x<=0;load_lane<=0;state<=IREQ;
    end else state<=FINISH;
   end
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
  endcase
 end
endmodule
