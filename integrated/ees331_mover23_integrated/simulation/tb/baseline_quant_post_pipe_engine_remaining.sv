// Bit-exact affine/ residual post-processing. Parameter format matches
// quant_post_engine. Seven registered stages overlap successive input reads.
// Groups of four outputs use one aligned word write; heads/tails use bytes.
// Only one external request is outstanding. Done follows the final response.
// clear requires the fabric to cancel old requests and late responses too.
module baseline_quant_post_pipe_engine_remaining #(parameter MAX_CHANNELS=512, GROUP_BYTES=4)(
 input logic clk,rst_n,clear,start,mode_add,
 input logic [31:0] src_a,src_b,destination,parameter_base,count,channels,
 output wire busy,done,error,
 output wire valid,write,byte_access,output logic [31:0] addr,wdata,
 input wire ready,response,input wire [31:0] rdata
);
 localparam CB=$clog2(MAX_CHANNELS+1);
 localparam GB=$clog2(GROUP_BYTES+1);
 localparam LB=$clog2(GROUP_BYTES);
 typedef enum logic [3:0] {IDLE,PR,PW,GROUP,AR,AW,BR,BW,DRAIN,WR,WW,FINISH,FAIL} state_t;
 state_t state;
 logic [31:0] pa,pb,pout,pp,n,index,group_start;
 logic [CB-1:0] nch,ch,param_ch;
 logic [2:0] param_word;
 logic [GB-1:0] group_len,loaded,produced,store_offset;
 logic add;
 logic signed [31:0] sample_a;
 logic [8*GROUP_BYTES-1:0] packed_word;
 (* ram_style="block" *) logic [143:0] parameter_mem[0:MAX_CHANNELS-1];
 logic [127:0] parameter_staging;
 logic signed [31:0] bias0,ma0,mb0,a0,b0,ma1,mb1;
 logic [31:0] cfg0;
 logic [6:0] pv;
 logic [5:0] sh[0:6];
 logic [7:0] zero[0:6],low[0:6],high[0:6];
 logic [LB-1:0] lane[0:6];
 logic signed [32:0] ax1,bx1;
 logic signed [64:0] prod_a2,prod_b2;
 logic signed [65:0] sum3,rounded5,value6;
 logic [65:0] magnitude4;
 logic negative4;
 wire pr_response=response && (state==PW || (state==PR && ready));
 wire ar_response=response && (state==AW || (state==AR && ready));
 wire br_response=response && (state==BW || (state==BR && ready));
 wire wr_response=response && (state==WW || (state==WR && ready));
 wire issue=!clear && ((!add && ar_response) || (add && br_response));
 wire [31:0] group_addr=pout+group_start;
 wire [2:0] store_bytes=group_len==1?1:4;
 wire [65:0] absolute3=sum3[65] ? $unsigned(-sum3):$unsigned(sum3);
 wire [65:0] half3=sh[3]==0 ? 66'd0:(66'd1<<(sh[3]-1'b1));
 wire [65:0] shifted4=magnitude4>>sh[4];
 wire [7:0] clipped6=value6<$signed({1'b0,low[6]}) ? low[6] :
                            (value6>$signed({1'b0,high[6]}) ? high[6]:value6[7:0]);
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;
 assign error=state==FAIL;
 assign valid=!clear && (state==PR || state==AR || state==BR || state==WR);
 assign write=state==WR;
 assign byte_access=(state==BR) || (state==AR && add) || (state==WR && group_len==1);
 always_comb begin
  addr=0;wdata=state==WR?(packed_word>>(store_offset*8)):32'd0;
  case(state)
   PR:addr=pp;
   AR:addr=pa+(add?index:(index<<2));
   BR:addr=pb+index;
   WR:addr=group_addr+store_offset;
   default:;
  endcase
 end
 // Independent synchronous parameter banks avoid five asynchronous RAM reads.
 always_ff @(posedge clk)begin
  if(!clear)begin
   if(pr_response)case(param_word)
    0:parameter_staging[0+:32]<=rdata;
    1:parameter_staging[32+:32]<=rdata;
    2:parameter_staging[64+:32]<=rdata;
    3:parameter_staging[96+:32]<=rdata;
    4:parameter_mem[param_ch]<={rdata[15:0],parameter_staging};
    default:;
   endcase
   if(issue)begin
    {high[0],low[0],cfg0,mb0,ma0,bias0}<=parameter_mem[ch];
    a0<=add?sample_a:$signed(rdata);b0<=add?$signed({24'd0,rdata[7:0]}):32'sd0;
    lane[0]<=loaded[LB-1:0];
   end
   if(pv[0])begin
    ax1<=add ? ($signed({a0[31],a0})-$signed({25'd0,cfg0[15:8]})) :
               ($signed({a0[31],a0})+$signed({bias0[31],bias0}));
    bx1<=add ? ($signed({b0[31],b0})-$signed({25'd0,cfg0[23:16]})):33'sd0;
    ma1<=ma0;mb1<=mb0;sh[1]<=cfg0[5:0];zero[1]<=cfg0[31:24];
   end
   if(pv[1])begin prod_a2<=ax1*ma1;prod_b2<=bx1*mb1;end
   if(pv[2])sum3<=$signed({prod_a2[64],prod_a2})+$signed({prod_b2[64],prod_b2});
   if(pv[3])begin magnitude4<=absolute3+half3;negative4<=sum3[65];end
   if(pv[4])rounded5<=negative4 ? -$signed(shifted4):$signed(shifted4);
   if(pv[5])value6<=rounded5+$signed({1'b0,zero[5]});
   for(integer i=1;i<7;i=i+1)begin
    if(pv[i-1])begin
     lane[i]<=lane[i-1];low[i]<=low[i-1];high[i]<=high[i-1];
     if(i>1)begin sh[i]<=sh[i-1];zero[i]<=zero[i-1];end
    end
   end
  end
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)pv<=0;
  else if(clear || state==IDLE || state==FAIL)pv<=0;
  else pv<={pv[5:0],issue};
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)state<=IDLE;
  else if(clear)state<=IDLE;
  else begin
   if(pv[6])begin
    packed_word[lane[6]*8+:8]<=clipped6;produced<=produced+1'b1;
    if(produced+1'b1==group_len)state<=WR;
   end
   if(issue)begin
    loaded<=loaded+1'b1;index<=index+1'b1;ch<=ch+1'b1==nch?0:ch+1'b1;
   end
   case(state)
    IDLE:if(start)begin
     pa<=src_a;pb<=src_b;pout<=destination;pp<=parameter_base;n<=count;
     nch<=channels;add<=mode_add;ch<=0;param_ch<=0;param_word<=0;index<=0;group_start<=0;
     state<=(GROUP_BYTES!=4 && GROUP_BYTES!=16) || channels==0 || channels>MAX_CHANNELS || count==0 || parameter_base[1:0]!=0 ||
             (!mode_add && src_a[1:0]!=0) ? FAIL:PR;
    end
    PR,PW:begin
     if(state==PR && ready)state<=PW;
     if(pr_response)begin
      pp<=pp+4;
      if((param_word==3 && rdata[7:0]>63) || (param_word==4 && rdata[7:0]>rdata[15:8]))state<=FAIL;
      else if(param_word==4)begin
       param_word<=0;param_ch<=param_ch+1'b1;
       state<=param_ch+1'b1==nch?GROUP:PR;
      end else begin param_word<=param_word+1'b1;state<=PR;end
     end
    end
    GROUP:begin
     group_len<=group_addr[1:0]==0 && n-group_start>=4?((n-group_start>=GROUP_BYTES)?GROUP_BYTES:((n-group_start)>>2)<<2):1;
     loaded<=0;produced<=0;store_offset<=0;packed_word<=0;state<=AR;
    end
    AR,AW:begin
     if(state==AR && ready)state<=AW;
     if(ar_response)begin
      sample_a<=$signed({24'd0,rdata[7:0]});
      state<=add?BR:(loaded+1'b1==group_len?DRAIN:AR);
     end
    end
    BR,BW:begin
     if(state==BR && ready)state<=BW;
     if(br_response)state<=loaded+1'b1==group_len?DRAIN:AR;
    end
    WR,WW:begin
     if(state==WR && ready)state<=WW;
     if(wr_response)begin
      if(store_offset+store_bytes<group_len)begin
       store_offset<=store_offset+store_bytes;state<=WR;
      end else begin
       group_start<=group_start+group_len;
       state<=index==n?FINISH:GROUP;
      end
     end
    end
    DRAIN:;
    FINISH,FAIL:state<=IDLE;
    default:state<=FAIL;
   endcase
  end
 end
endmodule
