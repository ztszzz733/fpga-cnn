// Executes one 24-word official NEureka register image fetched from SRAM.
`include "hci_helpers.svh"
module neureka_conv_engine import hci_package::*; (
 input logic clk,rst_n,clear,start,input logic [31:0] config_address,
 output logic busy,done,error,
 output logic cfg_valid,output logic [31:0] cfg_addr,
 input logic cfg_ready,cfg_response,input logic [31:0] cfg_rdata,
 output wire [8:0] valid,write,byte_access,output wire [287:0] addr,wdata,
 input wire [8:0] ready,response,input wire [287:0] rdata,
 output wire core_busy,output wire memory_idle
);
 localparam hci_size_parameter_t `HCI_SIZE_PARAM(tcdm) = '{DW:288,AW:32,BW:8,UW:0,IW:0,EW:0,EHW:0};
 hci_core_intf #(.DW(288),.UW(0),.IW(0),.EW(0),.EHW(0)) tcdm(.clk(clk));
 hwpe_ctrl_intf_periph #(.ID_WIDTH(16)) periph(.clk(clk));
 wire [8:0][1:0] evt;
 neureka_top #(.PE_H(4),.PE_W(4),.N_CORES(9),.ID(16),.`HCI_SIZE_PARAM(tcdm)(`HCI_SIZE_PARAM(tcdm))) core(
  .clk_i(clk),.rst_ni(rst_n && !clear),.test_mode_i(1'b0),.evt_o(evt),.busy_o(core_busy),.tcdm(tcdm),.periph(periph));
 neureka_banked_bridge bridge(clk,rst_n,clear,tcdm,valid,write,byte_access,addr,wdata,ready,response,rdata,memory_idle);
 typedef enum logic [3:0] {IDLE,ACQUIRE,ACQUIRE_WAIT,FETCH,FETCH_WAIT,CONFIGURE,CONFIG_WAIT,TRIGGER,TRIGGER_WAIT,RUN,DRAIN,SOFT_CLEAR,CLEAR_WAIT,SETTLE} state_t;
 state_t state;
 logic [31:0] pointer,word_q;
 logic [4:0] index;
 logic seen_busy;
 logic [3:0] settle_count;
 assign busy=state!=IDLE;
 assign cfg_valid=state==FETCH && !clear;
 assign cfg_addr=pointer+index*4;
 always_comb begin
  periph.req=0;periph.add=0;periph.wen=0;periph.be=15;periph.data=0;periph.id=0;
  if(state==ACQUIRE) begin periph.req=1;periph.add=4;periph.wen=1;end
  if(state==CONFIGURE) begin periph.req=1;periph.add=32'h20+index*4;periph.data=word_q;end
  if(state==TRIGGER) begin periph.req=1;periph.add=0;end
  if(state==SOFT_CLEAR) begin periph.req=1;periph.add=32'h14;end
  if(clear) periph.req=0;
 end
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin state<=IDLE;done<=0;error<=0;pointer<=0;word_q<=0;index<=0;seen_busy<=0;settle_count<=0;end
  else if(clear) begin state<=IDLE;done<=0;error<=0;seen_busy<=0;end
  else begin
   done<=0;error<=0;
   case(state)
    // Sequential adapter: soft-clear each job as in the upstream standalone
    // driver, after the previous job and all bank responses have drained.
    IDLE:if(start) begin pointer<=config_address;index<=0;seen_busy<=0;state<=SOFT_CLEAR;end
    SOFT_CLEAR:if(periph.gnt) state<=CLEAR_WAIT;
    CLEAR_WAIT:if(periph.r_valid) begin settle_count<=12;state<=SETTLE;end
    SETTLE:if(settle_count==0) state<=ACQUIRE;else settle_count<=settle_count-1;
    ACQUIRE:if(periph.gnt) state<=ACQUIRE_WAIT;
    ACQUIRE_WAIT:if(periph.r_valid) begin
     if(periph.r_data[31]) begin error<=1;state<=IDLE;end else state<=FETCH;
    end
    FETCH:if(cfg_ready) state<=FETCH_WAIT;
    FETCH_WAIT:if(cfg_response) begin word_q<=cfg_rdata;state<=CONFIGURE;end
    CONFIGURE:if(periph.gnt) state<=CONFIG_WAIT;
    CONFIG_WAIT:if(periph.r_valid) begin
     if(index==23) state<=TRIGGER;else begin index<=index+1;state<=FETCH;end
    end
    TRIGGER:if(periph.gnt) state<=TRIGGER_WAIT;
    TRIGGER_WAIT:if(periph.r_valid) state<=RUN;
    RUN:begin
     if(core_busy) seen_busy<=1;
     if((|evt) || (seen_busy && !core_busy)) state<=DRAIN;
    end
    // An idle bridge can be accepting a newly asserted final HCI request on
    // this edge. Do not publish the output buffer before that write drains.
    DRAIN:if(memory_idle && !core_busy && !tcdm.req) begin done<=1;state<=IDLE;end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
