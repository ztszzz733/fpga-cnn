// Isolated full-network correctness entry: SRAM command list, sequential dispatch.
// One actual NEureka + DW7 + existing quant/Add + hardware padding. This does not
// replace the two-engine residual scheduler and makes no concurrency claim.
module quant_network_sequential(
 input logic clk,rst_n,clear,start,
 input logic [31:0] descriptor_base,command_count,
 input logic memory_fault,
 output wire busy,done,error,cancel,
 output wire [13:0] mem_valid,mem_write,mem_byte,
 output wire [447:0] mem_addr,mem_wdata,
 input wire [13:0] mem_ready,mem_response,input wire [447:0] mem_rdata,
 output logic [31:0] command_index,
 output wire [31:0] command_kind,layer_index,
 output wire command_done,operator_start,conv_busy,post_busy,dw7_busy,pad_busy,
 output wire [3:0] phase,
 output wire dw7_mac
);
 typedef enum logic [3:0] {IDLE,FETCH,FWAIT,LAUNCH,WAIT_OP,REPORT,NEXT,FINISH,FAIL} state_t;
 state_t state;
 logic [31:0] base,total,cmd[16];logic [3:0] word_index;
 wire cb,cd,ce,pd,pe,dd,de,bd,be,core_busy,mem_idle;
 wire abort_ops=clear || state==FAIL || memory_fault;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;assign cancel=abort_ops;
 assign phase=state;assign command_kind=cmd[0];assign layer_index=cmd[12];
 assign operator_start=state==LAUNCH && !abort_ops;assign command_done=state==REPORT;
 // A negedge latch keeps this gate stable throughout the high clock phase.
 // Sequential mode only: the convolution clock is off during post/pad/DW7.
 logic conv_enable;
 always_ff @(negedge clk or negedge rst_n)
  if(!rst_n)conv_enable<=1;else conv_enable<=clear || memory_fault || state==FAIL || (cmd[0]==0 && state!=FINISH);
 wire conv_clk=clk && conv_enable;
 neureka_conv_engine convolution(.clk(conv_clk),.rst_n(rst_n),.clear(abort_ops),.start(operator_start && cmd[0]==0),
  .config_address(cmd[1]),.busy(cb),.done(cd),.error(ce),
  .cfg_valid(mem_valid[9]),.cfg_addr(mem_addr[288+:32]),.cfg_ready(mem_ready[9]),.cfg_response(mem_response[9]),.cfg_rdata(mem_rdata[288+:32]),
  .valid(mem_valid[8:0]),.write(mem_write[8:0]),.byte_access(mem_byte[8:0]),.addr(mem_addr[0+:288]),.wdata(mem_wdata[0+:288]),
  .ready(mem_ready[8:0]),.response(mem_response[8:0]),.rdata(mem_rdata[0+:288]),.core_busy(core_busy),.memory_idle(mem_idle));
 assign conv_busy=cb;assign mem_write[9]=0;assign mem_byte[9]=0;assign mem_wdata[288+:32]=0;
 quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(operator_start && (cmd[0]==1 || cmd[0]==2)),
  .mode_add(cmd[0]==2),.src_a(cmd[1]),.src_b(cmd[2]),.destination(cmd[3]),.parameter_base(cmd[4]),.count(cmd[5]),.channels(cmd[6]),
  .busy(post_busy),.done(pd),.error(pe),.valid(mem_valid[10]),.write(mem_write[10]),.byte_access(mem_byte[10]),
  .addr(mem_addr[320+:32]),.wdata(mem_wdata[320+:32]),.ready(mem_ready[10]),.response(mem_response[10]),.rdata(mem_rdata[320+:32]));
 dw7_cached_engine #(.MAX_WIDTH(7)) dw7(.clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(operator_start && cmd[0]==3),.reuse_weights(1'b0),
  .input_base(cmd[1]),.weight_base(cmd[2]),.output_base(cmd[3]),.width(cmd[7]),.height(cmd[8]),.channels(cmd[6]),
  .busy(dw7_busy),.done(dd),.error(de),.valid(mem_valid[11]),.write(mem_write[11]),.byte_access(mem_byte[11]),.cancel(),
  .addr(mem_addr[352+:32]),.wdata(mem_wdata[352+:32]),.ready(mem_ready[11]),.response(mem_response[11]),.rdata(mem_rdata[352+:32]),
  .phase(),.mac_fire(dw7_mac),.weights_cached(),.cache_hit());
 pad_hwc_engine padding(.clk(clk),.rst_n(rst_n),.clear(abort_ops),.start(operator_start && cmd[0]==4),
  .source(cmd[1]),.destination(cmd[3]),.width(cmd[7]),.height(cmd[8]),.channels(cmd[6]),.zero_point(cmd[9][7:0]),
  .busy(pad_busy),.done(bd),.error(be),.valid(mem_valid[12]),.write(mem_write[12]),.byte_access(mem_byte[12]),
  .addr(mem_addr[384+:32]),.wdata(mem_wdata[384+:32]),.ready(mem_ready[12]),.response(mem_response[12]),.rdata(mem_rdata[384+:32]));
 assign mem_valid[13]=state==FETCH && !abort_ops;
 assign mem_write[13]=0;assign mem_byte[13]=0;assign mem_addr[416+:32]=base+command_index*64+32'(word_index)*4;assign mem_wdata[416+:32]=0;
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;base<=0;total<=0;word_index<=0;command_index<=0;for(integer i=0;i<16;i++)cmd[i]<=0;end
  else if(clear)begin state<=IDLE;command_index<=0;word_index<=0;end
  else if(memory_fault || ce || pe || de || be)state<=FAIL;
  else case(state)
   IDLE:if(start)begin base<=descriptor_base;total<=command_count;command_index<=0;word_index<=0;
    state<=descriptor_base[1:0]!=0 || command_count==0 || command_count>65535 ? FAIL:FETCH;end
   FETCH:if(mem_ready[13])state<=FWAIT;
   FWAIT:if(mem_response[13])begin cmd[word_index]<=mem_rdata[416+:32];
    if(word_index==15)state<=LAUNCH;else begin word_index<=word_index+1;state<=FETCH;end end
   LAUNCH:state<=cmd[0]>4 ? FAIL:WAIT_OP;
   WAIT_OP:if((cmd[0]==0 && cd && mem_idle && !core_busy) || ((cmd[0]==1 || cmd[0]==2) && pd) ||
              (cmd[0]==3 && dd) || (cmd[0]==4 && bd))state<=REPORT;
   REPORT:state<=NEXT;
   NEXT:if(command_index+1==total)state<=FINISH;else begin command_index<=command_index+1;word_index<=0;state<=FETCH;end
   FINISH,FAIL:;
   default:state<=FAIL;
  endcase
 end
endmodule
