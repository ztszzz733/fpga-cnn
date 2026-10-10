// Six-module SoC compatible CNN replacement. Same CPU queue MMIO and 11 SRAM clients.
// New descriptor op=11: IA points to 24 official NEureka configuration words.
// New descriptor op=12: tensor_layout_dma. Scalar ops 2,3,6,7,8,10 unchanged.
// Tasks execute in order; no hidden host copies or behavioral convolution model.
module mobilefacenet_neureka_top #(
 parameter [31:0] BASE_ADDR=32'h40000000,parameter ENABLE_OVERLAP=1
)(
 input wire clk,rst_n,input wire [31:0] mmio_addr,mmio_wdata,
 input wire mmio_we,mmio_re,output wire [31:0] mmio_rdata,output wire mmio_ready,
 output logic [10:0] cnn_valid,cnn_write,cnn_byte,
 output logic [351:0] cnn_addr,cnn_wdata,
 input wire [10:0] cnn_ready,cnn_response,input wire [351:0] cnn_rdata,
 output wire cnn_cancel,output wire status_busy,status_done,status_error
);
 wire start,clear;wire [3:0] opcode;wire [31:0] queue_base,count,unused_oa,unused_wa,unused_ba,unused_ch,unused_lp;
 logic done,error;logic [31:0] completed,pointer;
 typedef enum logic [2:0] {IDLE,FETCH_START,FETCH_WAIT,ISSUE,EXECUTE,ADVANCE} state_t;
 state_t state;
 wire [255:0] fetched;logic [255:0] descriptor;
 wire fetch_valid,fetch_ready,fetch_response,descriptor_valid,reader_idle;wire [31:0] fetch_addr;
 wire [3:0] task_op=descriptor[3:0];
 wire scalar_valid;wire [511:0] unused_spans;
 wire [63:0] queue_end={32'b0,queue_base}+{32'b0,count}*32;
 task_descriptor_info scalar_check(descriptor,queue_base,queue_end,scalar_valid,unused_spans);
 wire [63:0] tensor_bytes={48'b0,descriptor[191:176]}*{48'b0,descriptor[175:160]}*{48'b0,descriptor[207:192]};
 wire [63:0] input_end={32'b0,descriptor[63:32]}+tensor_bytes;
 wire [63:0] output_end={32'b0,descriptor[95:64]}+tensor_bytes;
 wire dma_valid=tensor_bytes!=0 && input_end<=64'h100000000 && output_end<=64'h100000000 &&
  (input_end<={32'b0,descriptor[95:64]} || output_end<={32'b0,descriptor[63:32]}) &&
  (output_end<={32'b0,queue_base} || {32'b0,descriptor[95:64]}>=queue_end) && descriptor[255:225]==0;
 wire command_valid=descriptor[31:8]==24'd1 && (task_op==11 ?
  (descriptor[33:32]==0 && {32'b0,descriptor[63:32]}+96<=64'h100000000):
  task_op==12 ? dma_valid:scalar_valid);
 wire launch=state==ISSUE && command_valid;
 wire fetch_launch=state==FETCH_START;
 assign status_busy=state!=IDLE;assign status_done=done;assign status_error=error;assign cnn_cancel=clear;
 accelerator_regs #(.BASE_ADDR(BASE_ADDR)) regs(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
  mmio_rdata,mmio_ready,start,clear,opcode,status_busy,done,error,queue_base,unused_oa,unused_wa,unused_ba,count,unused_ch,unused_lp);
 task_descriptor_reader reader(clk,rst_n,clear,fetch_launch,pointer,reader_idle,
  fetch_valid,fetch_ready,fetch_addr,fetch_response,cnn_rdata[9*32+:32],descriptor_valid,state==FETCH_WAIT,fetched);
 wire [8:0] nv,nw,nb;wire [287:0] na,nd;
 wire cv,cbusy,cdone,cerror,core_busy,memory_idle;wire [31:0] ca;
 neureka_conv_engine convolution(clk,rst_n,clear,launch && task_op==11,descriptor[63:32],
  cbusy,cdone,cerror,cv,ca,cnn_ready[9],cnn_response[9],cnn_rdata[9*32+:32],
  nv,nw,nb,na,nd,cnn_ready[8:0],cnn_response[8:0],cnn_rdata[0+:288],core_busy,memory_idle);
 wire lv,lw,lb,lbusy,ldone,lerror;wire [31:0] la,ld;
 tensor_layout_dma layout(clk,rst_n,clear,launch && task_op==12,descriptor,lbusy,ldone,lerror,
  lv,cnn_ready[9],lw,lb,la,ld,cnn_response[9],cnn_rdata[9*32+:32]);
 wire [5:0] sv,sw,sb,sbusy,sdone,serror;wire [191:0] sa,sd;
 for(genvar u=0;u<6;u++) begin:operators
  localparam CODE=u==0 ? 2:u==1 ? 3:u==2 ? 6:u==3 ? 7:u==4 ? 8:10;
  tensor_operator_engine #(.OPCODE(CODE)) engine(clk,rst_n,clear,launch && task_op==CODE,descriptor,
   sbusy[u],sdone[u],serror[u],sv[u],cnn_ready[10],sw[u],sb[u],sa[u*32+:32],sd[u*32+:32],cnn_response[10],cnn_rdata[320+:32]);
 end
 assign fetch_ready=cnn_ready[9];assign fetch_response=cnn_response[9];
 always_comb begin
  cnn_valid=0;cnn_write=0;cnn_byte=0;cnn_addr=0;cnn_wdata=0;
  cnn_valid[8:0]=nv;cnn_write[8:0]=nw;cnn_byte[8:0]=nb;cnn_addr[0+:288]=na;cnn_wdata[0+:288]=nd;
  cnn_valid[9]=fetch_valid || cv || lv;cnn_addr[288+:32]=fetch_valid ? fetch_addr:cv ? ca:la;
  cnn_write[9]=lw && lv;cnn_byte[9]=lb && lv;cnn_wdata[288+:32]=ld;
  for(int u=0;u<6;u++) if(sv[u]) begin
   cnn_valid[10]=1;cnn_write[10]=sw[u];cnn_byte[10]=sb[u];cnn_addr[320+:32]=sa[u*32+:32];cnn_wdata[320+:32]=sd[u*32+:32];
  end
  if(clear) cnn_valid=0;
 end
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin state<=IDLE;done<=0;error<=0;completed<=0;pointer<=0;descriptor<=0;end
  else if(clear) begin state<=IDLE;done<=0;error<=0;completed<=0;end
  else begin
   done<=0;error<=0;
   case(state)
    IDLE:if(start) begin
     completed<=0;pointer<=queue_base;
     if(count==0 || queue_base[1:0]!=0 || opcode!=15 || queue_end>64'h100000000) error<=1;else state<=FETCH_START;
    end
    FETCH_START:state<=FETCH_WAIT;
    FETCH_WAIT:if(descriptor_valid) begin descriptor<=fetched;state<=ISSUE;end
    ISSUE:begin
     if(command_valid && (task_op==11 || task_op==12 || task_op==2 || task_op==3 || task_op==6 || task_op==7 || task_op==8 || task_op==10)) state<=EXECUTE;
     else begin error<=1;state<=IDLE;end
    end
    EXECUTE:begin
     if(cerror || lerror || |serror) begin error<=1;state<=IDLE;end
     else if(cdone || ldone || |sdone) begin completed<=completed+1;state<=ADVANCE;end
    end
    ADVANCE:if(completed==count) begin done<=1;state<=IDLE;end
     else begin pointer<=pointer+32;state<=FETCH_START;end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
