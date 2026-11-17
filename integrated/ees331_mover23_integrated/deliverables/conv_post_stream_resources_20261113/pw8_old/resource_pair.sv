module resource_pair(input wire clk,rst_n,clear,start,request_stream,depthwise,post_add,
 input wire [1:0] consumer_count,
 input wire [31:0] input_base,weight_base,raw_base,output_base,parameter_base,src_b,
 input wire [31:0] width,height,in_channels,out_channels,stride,post_count,post_channels,
 output wire busy,done,error,stream_active,output wire [3:0] decision_reason,
 output wire [1:0] mem_valid,mem_write,mem_byte,output wire [63:0] mem_addr,mem_wdata,
 input wire [1:0] mem_ready,mem_response,input wire [63:0] mem_rdata);
 localparam integer KERNEL=1;
 typedef enum logic [2:0] {IDLE,CRUN,PSTART,PRUN,FINISH,FAIL} state_t;
 state_t state;
 logic cs,ps,ce,pe,cd,pd,cb,pbusy;
 logic [31:0] ib,wb,rb,ob,pb,sb,w,h,ci,co,st,n,nch;logic dw,add;
 wire kill=clear || state==FAIL || ce || pe;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;assign stream_active=0;assign decision_reason=1;
 self_pw8_engine #(.MAX_CHANNELS(512)) conv(.clk(clk),.rst_n(rst_n),.clear(kill),.start(cs),.depthwise(dw),
  .input_base(ib),.weight_base(wb),.output_base(rb),.width(w),.height(h),.in_channels(ci),.out_channels(co),.kernel(32'(KERNEL)),.stride(st),
  .busy(cb),.done(cd),.error(ce),.valid(mem_valid[0]),.write(mem_write[0]),.byte_access(mem_byte[0]),.addr(mem_addr[31:0]),.wdata(mem_wdata[31:0]),
  .ready(mem_ready[0]),.response(mem_response[0]),.rdata(mem_rdata[31:0]),.mac_fire(),.phase(),.input_reads(),.weight_reads(),.mac_count());
 quant_post_pipe_engine #(.MAX_CHANNELS(512),.GROUP_BYTES(16)) post(.clk(clk),.rst_n(rst_n),.clear(kill),.start(ps),.mode_add(add),
  .src_a(rb),.src_b(sb),.destination(ob),.parameter_base(pb),.count(n),.channels(nch),.busy(pbusy),.done(pd),.error(pe),
  .valid(mem_valid[1]),.write(mem_write[1]),.byte_access(mem_byte[1]),.addr(mem_addr[63:32]),.wdata(mem_wdata[63:32]),
  .ready(mem_ready[1]),.response(mem_response[1]),.rdata(mem_rdata[63:32]));
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;cs<=0;ps<=0;end
  else if(clear)begin state<=IDLE;cs<=0;ps<=0;end
  else begin
   cs<=0;ps<=0;
   if(ce||pe)state<=FAIL;
   else case(state)
    IDLE:if(start)begin
     ib<=input_base;wb<=weight_base;rb<=raw_base;ob<=output_base;pb<=parameter_base;sb<=src_b;
     w<=width;h<=height;ci<=in_channels;co<=out_channels;st<=stride;n<=post_count;nch<=post_channels;dw<=depthwise;add<=post_add;
     cs<=1;state<=CRUN;
    end
    CRUN:if(cd)state<=PSTART;
    PSTART:begin ps<=1;state<=PRUN;end
    PRUN:if(pd)state<=FINISH;
    FINISH,FAIL:state<=IDLE;
    default:state<=FAIL;
   endcase
  end
 end
endmodule
