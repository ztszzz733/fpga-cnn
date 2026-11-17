// Bit-exact affine/ residual post-processing. Parameter format matches
// quant_post_engine. Seven registered stages overlap successive input reads.
// Groups of four outputs use one aligned word write; heads/tails use bytes.
// Only one external request is outstanding. Done follows the final response.
// clear requires the fabric to cancel old requests and late responses too.
module quant_post_pipe_engine #(parameter MAX_CHANNELS=512, GROUP_BYTES=4, READ_WORD_BUFFER=1)(
 input logic clk,rst_n,clear,start,mode_add,
 input logic [31:0] src_a,src_b,destination,parameter_base,count,channels,
 output wire busy,done,error,
 output wire valid,write,byte_access,output logic [31:0] addr,wdata,
 input wire ready,response,input wire [31:0] rdata
);
 logic core_valid,core_write,core_byte,core_ready,core_response;
 logic [31:0] core_addr,core_wdata,core_rdata;
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
 wire [32:0] a_end={1'b0,pa}+({1'b0,n}<<(add?0:2));
 wire [32:0] b_end={1'b0,pb}+{1'b0,n};
 wire [32:0] out_end={1'b0,pout}+{1'b0,n};
 wire separate_output=(out_end<={1'b0,pa} || a_end<={1'b0,pout}) &&
                      (!add || out_end<={1'b0,pb} || b_end<={1'b0,pout});
 wire [GB-1:0] effective_group=(GROUP_BYTES==32 && !separate_output)?GB'(16):GB'(GROUP_BYTES);
 wire pr_response=core_response && (state==PW || (state==PR && core_ready));
 wire ar_response=core_response && (state==AW || (state==AR && core_ready));
 wire br_response=core_response && (state==BW || (state==BR && core_ready));
 wire wr_response=core_response && (state==WW || (state==WR && core_ready));
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
 assign core_valid=!clear && (state==PR || state==AR || state==BR || state==WR);
 assign core_write=state==WR;
 assign core_byte=(state==BR) || (state==AR && add) || (state==WR && group_len==1);
 always_comb begin
  core_addr=0;core_wdata=state==WR?(packed_word>>(store_offset*8)):32'd0;
  case(state)
   PR:core_addr=pp;
   AR:core_addr=pa+(add?index:(index<<2));
   BR:core_addr=pb+index;
   WR:core_addr=group_addr+store_offset;
   default:;
  endcase
 end
 // Independent synchronous parameter banks avoid five asynchronous RAM reads.
 always_ff @(posedge clk)begin
  if(!clear)begin
   if(pr_response)case(param_word)
    0:parameter_staging[0+:32]<=core_rdata;
    1:parameter_staging[32+:32]<=core_rdata;
    2:parameter_staging[64+:32]<=core_rdata;
    3:parameter_staging[96+:32]<=core_rdata;
    4:parameter_mem[param_ch]<={core_rdata[15:0],parameter_staging};
    default:;
   endcase
   if(issue)begin
    {high[0],low[0],cfg0,mb0,ma0,bias0}<=parameter_mem[ch];
    a0<=add?sample_a:$signed(core_rdata);b0<=add?$signed({24'd0,core_rdata[7:0]}):32'sd0;
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
     state<=(GROUP_BYTES!=4 && GROUP_BYTES!=16 && GROUP_BYTES!=32) || channels==0 || channels>MAX_CHANNELS || count==0 || parameter_base[1:0]!=0 ||
             (!mode_add && src_a[1:0]!=0) ? FAIL:PR;
    end
    PR,PW:begin
     if(state==PR && core_ready)state<=PW;
     if(pr_response)begin
      pp<=pp+4;
      if((param_word==3 && core_rdata[7:0]>63) || (param_word==4 && core_rdata[7:0]>core_rdata[15:8]))state<=FAIL;
      else if(param_word==4)begin
       param_word<=0;param_ch<=param_ch+1'b1;
       state<=param_ch+1'b1==nch?GROUP:PR;
      end else begin param_word<=param_word+1'b1;state<=PR;end
     end
    end
    GROUP:begin
     group_len<=group_addr[1:0]==0 && n-group_start>=4?((n-group_start>=effective_group)?effective_group:((n-group_start)>>2)<<2):1;
     loaded<=0;produced<=0;store_offset<=0;packed_word<=0;state<=AR;
    end
    AR,AW:begin
     if(state==AR && core_ready)state<=AW;
     if(ar_response)begin
      sample_a<=$signed({24'd0,core_rdata[7:0]});
      state<=add?BR:(loaded+1'b1==group_len?DRAIN:AR);
     end
    end
    BR,BW:begin
     if(state==BR && core_ready)state<=BW;
     if(br_response)state<=loaded+1'b1==group_len?DRAIN:AR;
    end
    WR,WW:begin
     if(state==WR && core_ready)state<=WW;
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

 generate if(READ_WORD_BUFFER)begin:add_word_buffers
  logic [1:0] cached_valid;
  logic [29:0] cached_tag[0:1];logic [31:0] cached_data[0:1];
  logic pending,pending_widen,pending_fill,pending_region;
  logic [1:0] pending_lane;logic [29:0] pending_tag;
  wire region=state==BR || state==BW;
  wire cacheable=add && separate_output && (state==AR || state==AW || state==BR || state==BW);
  wire [31:0] base=region?pb:pa;
  wire [32:0] limit=region?b_end:a_end;
  wire [31:0] aligned={core_addr[31:2],2'b00};
  wire hit=!pending && core_valid && !core_write && cacheable && cached_valid[region] && cached_tag[region]==core_addr[31:2];
  wire widen=core_valid && !core_write && core_byte && cacheable && aligned>=base && {1'b0,aligned}+33'd4<=limit;
  wire accepted=valid && ready;
  wire returned=response && (pending || accepted);
  wire fill=pending?pending_fill:(cacheable && !core_write && !byte_access);
  wire fill_region=pending?pending_region:region;
  wire [29:0] fill_tag=pending?pending_tag:core_addr[31:2];
  wire [1:0] byte_lane=pending?pending_lane:core_addr[1:0];
  assign valid=core_valid && !hit;assign write=core_write;assign byte_access=widen?1'b0:core_byte;
  assign addr=widen?aligned:core_addr;assign wdata=core_wdata;
  assign core_ready=!pending && (hit || ready);assign core_response=hit || returned;
  assign core_rdata=hit ? {24'd0,cached_data[region][core_addr[1:0]*8+:8]} :
                    ((pending?pending_widen:widen)?{24'd0,rdata[byte_lane*8+:8]}:rdata);
  always_ff @(posedge clk or negedge rst_n)begin
   if(!rst_n)begin cached_valid<=0;pending<=0;pending_widen<=0;pending_fill<=0;pending_region<=0;pending_lane<=0;pending_tag<=0;end
   else if(clear || (state==IDLE && start))begin cached_valid<=0;pending<=0;end
   else begin
    if(accepted)begin
     pending<=!response;pending_widen<=widen;pending_fill<=cacheable && !core_write && !byte_access;
     pending_region<=region;pending_lane<=core_addr[1:0];pending_tag<=core_addr[31:2];
     if(core_write)for(integer b=0;b<2;b++)if(cached_tag[b]==core_addr[31:2])cached_valid[b]<=0;
    end else if(returned)pending<=0;
    if(returned && fill)begin cached_valid[fill_region]<=1;cached_tag[fill_region]<=fill_tag;cached_data[fill_region]<=rdata;end
   end
  end
 end else begin:direct_memory
  assign valid=core_valid;assign write=core_write;assign byte_access=core_byte;assign addr=core_addr;assign wdata=core_wdata;
  assign core_ready=ready;assign core_response=response;assign core_rdata=rdata;
 end endgenerate
endmodule
