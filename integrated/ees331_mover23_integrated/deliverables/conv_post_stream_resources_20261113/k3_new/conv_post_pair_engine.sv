// Trial pair endpoint. Reserves one convolution and one existing post engine.
// Not wired into fixed_schedule_compact. Port0 serves convolution traffic;
// port1 serves post parameters/final writes. Direct raw results never hit RAM.
module conv_post_pair_engine #(
 parameter integer KERNEL=1,MAX_CHANNELS=512,FIFO_DEPTH=8,
 parameter integer F_BITS=$clog2(FIFO_DEPTH),C_BITS=$clog2(MAX_CHANNELS+1)
)(
 input logic clk,rst_n,clear,start,request_stream,depthwise,post_add,
 input logic [1:0] consumer_count,
 input logic [31:0] input_base,weight_base,raw_base,output_base,parameter_base,src_b,
 input logic [31:0] width,height,in_channels,out_channels,stride,post_count,post_channels,
 output wire busy,done,error,stream_active,
 output logic [3:0] decision_reason,
 output wire [1:0] mem_valid,mem_write,mem_byte,
 output wire [63:0] mem_addr,mem_wdata,
 input logic [1:0] mem_ready,mem_response,input logic [63:0] mem_rdata,
 output wire conv_work,post_work,raw_push,raw_pop,conv_finished,
 output wire [F_BITS:0] fifo_level,
 output logic [31:0] forwarded_count,
 output wire [31:0] conv_input_reads,conv_weight_reads,conv_mac_count
);
 typedef enum logic [3:0] {IDLE,SIZE,RUN,POST_START,POST_WAIT,FINISH,FAIL} state_t;
 state_t state;
 logic active,cs,ps,conv_seen,post_seen;
 logic cv,cw,cb,cr,cp,cd,ce,pd,pe,pbusy,cbusy,pready;
 logic [31:0] ca,cdata,cchannel;
 logic [31:0] ib,wb,rb,ob,pb,sb,w,h,ci,co,st,n,nch;
 logic dw,add,requested;logic [1:0] consumers;
 logic [2:0] step;logic [5:0] bit_index;
 logic [63:0] lhs,acc,input_bytes,expected_elements;
 logic [31:0] rhs,ow,oh;
 wire [63:0] mul_value=acc+(rhs[0]?lhs:64'd0);
 wire [63:0] output_end={32'd0,ob}+{32'd0,n};
 wire [63:0] input_end={32'd0,ib}+input_bytes;
 wire [63:0] weight_bytes=KERNEL==1?mul_value:mul_value*64'd9;
 wire [63:0] weight_end={32'd0,wb}+weight_bytes;
 wire [63:0] param_end={32'd0,pb}+({32'd0,nch}<<4)+({32'd0,nch}<<2);
 wire [63:0] raw_end={32'd0,rb}+(expected_elements<<2);
 wire overlap_input=({32'd0,ob}<input_end && {32'd0,ib}<output_end);
 wire overlap_weight=({32'd0,ob}<weight_end && {32'd0,wb}<output_end);
 wire overlap_param=({32'd0,ob}<param_end && {32'd0,pb}<output_end);
 wire eligible=requested && consumers==1 && !add && nch==co && {32'd0,n}==expected_elements &&
  !overlap_input && !overlap_weight && !overlap_param && output_end<=64'h100000000;
 wire kill=clear || state==FAIL || ce || pe;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;
 assign stream_active=active && busy;
 assign conv_finished=conv_seen;

 // Shallow register FIFO: raw INT32, final element index, and channel tag.
 (* ram_style="registers" *) logic [31:0] q_data[0:FIFO_DEPTH-1],q_index[0:FIFO_DEPTH-1];
 (* ram_style="registers" *) logic [C_BITS-1:0] q_channel[0:FIFO_DEPTH-1];
 logic [F_BITS-1:0] wp,rp;logic [F_BITS:0] used;
 assign fifo_level=used;
 assign raw_push=active && cv && cw && used<FIFO_DEPTH && !kill;
 assign raw_pop=active && used!=0 && pready && !kill;
 assign mem_valid[0]=cv && !(active && cw) && !kill;
 assign mem_write[0]=cw;assign mem_byte[0]=cb;
 assign mem_addr[31:0]=ca;assign mem_wdata[31:0]=cdata;
 assign cr=(active && cw)?(used<FIFO_DEPTH && !kill):mem_ready[0];
 assign cp=(active && cw)?raw_push:mem_response[0];
 always_ff @(posedge clk)if(raw_push)begin
  q_data[wp]<=cdata;q_index[wp]<=(ca-rb)>>2;q_channel[wp]<=C_BITS'(cchannel);
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin wp<=0;rp<=0;used<=0;forwarded_count<=0;end
  else if(kill || (state==IDLE && start))begin wp<=0;rp<=0;used<=0;forwarded_count<=0;end
  else begin
   if(raw_push)begin wp<=wp+1'b1;forwarded_count<=forwarded_count+1;end
   if(raw_pop)rp<=rp+1'b1;
   case({raw_push,raw_pop})2'b10:used<=used+1'b1;2'b01:used<=used-1'b1;default:;endcase
  end
 end
 generate if(KERNEL==1)begin:k1
  self_pw8_engine #(.MAX_CHANNELS(MAX_CHANNELS)) conv(
   .clk(clk),.rst_n(rst_n),.clear(kill),.start(cs),.depthwise(dw),
   .input_base(ib),.weight_base(wb),.output_base(rb),.width(w),.height(h),
   .in_channels(ci),.out_channels(co),.kernel(32'd1),.stride(st),
   .busy(cbusy),.done(cd),.error(ce),.valid(cv),.write(cw),.byte_access(cb),.addr(ca),.wdata(cdata),
   .ready(cr),.response(cp),.rdata(mem_rdata[31:0]),.mac_fire(conv_work),.phase(),
   .input_reads(conv_input_reads),.weight_reads(conv_weight_reads),.mac_count(conv_mac_count),.result_channel(cchannel));
 end else begin:k3
  self_conv_spatial4_engine #(.MAX_CHANNELS(MAX_CHANNELS),.MAX_KERNEL(3),.TILE(2)) conv(
   .clk(clk),.rst_n(rst_n),.clear(kill),.start(cs),.depthwise(dw),
   .input_base(ib),.weight_base(wb),.output_base(rb),.width(w),.height(h),
   .in_channels(ci),.out_channels(co),.kernel(32'd3),.stride(st),
   .busy(cbusy),.done(cd),.error(ce),.valid(cv),.write(cw),.byte_access(cb),.addr(ca),.wdata(cdata),
   .ready(cr),.response(cp),.rdata(mem_rdata[31:0]),.mac_fire(conv_work),.phase(),
   .input_reads(conv_input_reads),.weight_reads(conv_weight_reads),.mac_count(conv_mac_count),.result_channel(cchannel));
 end endgenerate
 quant_post_pipe_engine #(.MAX_CHANNELS(MAX_CHANNELS),.GROUP_BYTES(16),.STREAM_SUPPORT(1)) post(
  .clk(clk),.rst_n(rst_n),.clear(kill),.start(ps),.mode_add(add),.src_a(rb),.src_b(sb),
  .destination(ob),.parameter_base(pb),.count(n),.channels(nch),
  .busy(pbusy),.done(pd),.error(pe),.valid(mem_valid[1]),.write(mem_write[1]),.byte_access(mem_byte[1]),
  .addr(mem_addr[63:32]),.wdata(mem_wdata[63:32]),.ready(mem_ready[1]),.response(mem_response[1]),.rdata(mem_rdata[63:32]),
  .stream_mode(active),.s_valid(active && used!=0),.s_data(q_data[rp]),.s_index(q_index[rp]),
  .s_channel(32'(q_channel[rp])),.s_ready(pready),.stream_work(post_work));

 // Serial size calculations avoid introducing runtime division/multipliers.
 // Both modes pay identical admission cost. Only the direct mode overlaps
 // the two engines; fallback leaves old intermediate memory traffic intact.
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;cs<=0;ps<=0;active<=0;conv_seen<=0;post_seen<=0;decision_reason<=0;end
  else if(clear)begin state<=IDLE;cs<=0;ps<=0;active<=0;conv_seen<=0;post_seen<=0;decision_reason<=0;end
  else begin
   cs<=0;ps<=0;
   if(ce || pe)state<=FAIL;
   else case(state)
    IDLE:if(start)begin
     ib<=input_base;wb<=weight_base;rb<=raw_base;ob<=output_base;pb<=parameter_base;sb<=src_b;
     w<=width;h<=height;ci<=in_channels;co<=out_channels;st<=stride;
     n<=post_count;nch<=post_channels;dw<=depthwise;add<=post_add;requested<=request_stream;consumers<=consumer_count;
     active<=0;conv_seen<=0;post_seen<=0;decision_reason<=0;
     ow<=((width-KERNEL)>>(stride==2))+1;oh<=((height-KERNEL)>>(stride==2))+1;
     lhs<={32'd0,width};rhs<=height;acc<=0;step<=0;bit_index<=0;
     state<=(width<KERNEL || height<KERNEL || width>65535 || height>65535 || in_channels==0 || in_channels>MAX_CHANNELS ||
      out_channels==0 || out_channels>MAX_CHANNELS || (stride!=1 && stride!=2) || (depthwise && out_channels!=in_channels) ||
      post_count==0 || post_channels==0 || post_channels>MAX_CHANNELS || consumer_count==0 || raw_base[1:0]!=0 || parameter_base[1:0]!=0 ||
      (KERNEL!=1 && KERNEL!=3) || (FIFO_DEPTH<2) || ((FIFO_DEPTH&(FIFO_DEPTH-1))!=0))?FAIL:SIZE;
    end
    SIZE:begin
     lhs<=lhs<<1;rhs<=rhs>>1;acc<=mul_value;bit_index<=bit_index+1;
     if(bit_index==31)begin
      acc<=0;bit_index<=0;step<=step+1;
      case(step)
       0:begin lhs<=mul_value;rhs<=ci;end
       1:begin input_bytes<=mul_value;lhs<={32'd0,ow};rhs<=oh;end
       2:begin lhs<=mul_value;rhs<=co;end
       3:begin expected_elements<=mul_value;lhs<={32'd0,co};rhs<=dw?32'd1:ci;end
       4:begin
        if(input_end>64'h100000000 || weight_end>64'h100000000 || raw_end>64'h100000000 || param_end>64'h100000000 || output_end>64'h100000000)state<=FAIL;
        else begin
         active<=eligible;cs<=1;ps<=eligible;state<=RUN;
         decision_reason<=!requested?1:(consumers!=1?2:(add?3:((nch!=co || {32'd0,n}!=expected_elements)?4:
          ((overlap_input || overlap_weight || overlap_param)?5:0))));
        end
       end
       default:state<=FAIL;
      endcase
     end
    end
    RUN:begin
     if(cd)begin
      conv_seen<=1;
      if(active)begin if(forwarded_count!=n)state<=FAIL;end
      else state<=POST_START;
     end
     if(pd)post_seen<=1;
     if(active && (conv_seen || cd) && (post_seen || pd) && used==0)state<=FINISH;
    end
    POST_START:begin ps<=1;state<=POST_WAIT;end
    POST_WAIT:if(pd)begin post_seen<=1;state<=FINISH;end
    FINISH,FAIL:state<=IDLE;
    default:state<=FAIL;
   endcase
  end
 end
endmodule
