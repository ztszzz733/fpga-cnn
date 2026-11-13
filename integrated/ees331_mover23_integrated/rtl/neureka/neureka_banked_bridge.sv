// One outstanding HCI transaction; parallel word lanes share the existing banks.
// NEureka's r_id_filter requires response exactly one cycle after grant.
// Capture the held request BEFORE grant, collect SRAM data, THEN grant it.
// Partial stores are decomposed into byte stores (no read/modify/write).
`include "hci_helpers.svh"
module neureka_banked_bridge import hci_package::*; (
 input logic clk,rst_n,clear,
 hci_core_intf.target hci,
 output logic [8:0] valid,write,byte_access,
 output logic [287:0] addr,wdata,
 input logic [8:0] ready,response,input logic [287:0] rdata,
 output logic idle
);
 logic active,returning,wen;
 logic [31:0] base;
 logic [287:0] data_q,read_q;
 logic [35:0] remaining;
 logic [8:0] pending;
 logic [8:0][3:0] issued_be;
 logic [8:0][3:0] selected_be;
 assign idle=!active && !returning;
 assign hci.gnt=active && remaining==0 && pending==0 && !clear && rst_n;
 assign hci.r_valid=returning && !clear;
 assign hci.r_data=read_q;
 assign hci.r_id='0;
 assign hci.r_opc='0;
 assign hci.r_user='0;
 assign hci.r_ecc='0;
 assign hci.egnt='1;
 assign hci.r_evalid='0;
 always_comb begin
  valid='0;write='0;byte_access='0;addr='0;wdata='0;selected_be='0;
  for(int i=0;i<9;i++) begin
   addr[i*32+:32]=base+4*i;wdata[i*32+:32]=data_q[i*32+:32];
   write[i]=!wen;
   if(active && !pending[i] && remaining[i*4+:4]!=0 && !clear) begin
    valid[i]=1;
    if(wen || remaining[i*4+:4]==15) selected_be[i]=remaining[i*4+:4];
    else begin
     byte_access[i]=1;
     for(int b=3;b>=0;b--) if(remaining[i*4+b]) begin
      selected_be[i]=4'b1<<b;
      addr[i*32+:32]=base+4*i+b;
      wdata[i*32+:32]={24'b0,data_q[(i*4+b)*8+:8]};
     end
    end
   end
  end
 end
 always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin active<=0;returning<=0;pending<=0;remaining<=0;read_q<=0;wen<=0;base<=0;data_q<=0;issued_be<=0;end
  else if(clear) begin active<=0;returning<=0;pending<=0;remaining<=0;end
  else begin
   if(hci.req && idle) begin
    active<=1;wen<=hci.wen;base<={hci.add[31:2],2'b0};data_q<=hci.data;
    remaining<=hci.wen ? {36{1'b1}} : hci.be;read_q<=0;
   end
   for(int i=0;i<9;i++) begin
    if(valid[i] && ready[i]) begin pending[i]<=1;issued_be[i]<=selected_be[i];end
    if(pending[i] && response[i]) begin
     pending[i]<=0;remaining[i*4+:4]<=remaining[i*4+:4] & ~issued_be[i];
     read_q[i*32+:32]<=rdata[i*32+:32];
    end
   end
   if(hci.req && hci.gnt) begin active<=0;returning<=1;end
   if(returning && hci.r_ready) returning<=0;
  end
 end
endmodule
