// Storage C1 v0.2 implementation. One command and one AXI3 beat outstanding.
// 64-bit AXI, 32-bit local word port; local byte starts may be unaligned.
// Tail accesses use exact 4/2/1-byte AXI transfers, never speculative overreads.
module data_mover #(
 parameter integer TIMEOUT_CYCLES=1024
)(
 input logic clk,rst_n,enable,recover,
 input logic [31:0] cfg_ddr_base,cfg_ddr_bytes,cfg_local_bytes,
 input logic cmd_valid,
 output wire cmd_ready,
 input logic [31:0] cmd_src,cmd_dst,cmd_bytes,cmd_flags,
 output wire rsp_valid,
 input logic rsp_ready,
 output logic [31:0] rsp_status,rsp_bytes_done,
 output logic fault_locked,
 output wire drained,busy,
 output wire local_valid,local_write,
 input logic local_ready,
 output wire [31:0] local_addr,local_wdata,
 output wire [3:0] local_wstrb,
 input logic local_rsp_valid,local_error,
 input logic [31:0] local_rdata,
 output wire [31:0] araddr,awaddr,
 output wire [5:0] arid,awid,wid,
 output wire [3:0] arlen,awlen,
 output logic [2:0] arsize,awsize,
 output wire [1:0] arburst,awburst,arlock,awlock,
 output wire [3:0] arcache,awcache,arqos,awqos,
 output wire [2:0] arprot,awprot,
 output wire arvalid,awvalid,wvalid,wlast,rready,bready,
 input logic arready,awready,wready,rvalid,rlast,bvalid,
 input logic [63:0] rdata,
 input logic [5:0] rid,bid,
 input logic [1:0] rresp,bresp,
 output wire [63:0] wdata,
 output wire [7:0] wstrb
);
 typedef enum logic [3:0] {IDLE,PREP,AR,RD,LREQ,LWAIT,WRITE,BRESP,NEXT,RESPONSE} state_t;
 state_t state;
 logic dir,aw_done,w_done,timed_out;
 logic [31:0] ddr_ptr,loc_ptr,left_bytes,total_bytes,watchdog;
 logic [63:0] buffer;
 logic [3:0] beat_bytes,lane;
 logic [2:0] size_q;
 wire [31:0] ddr_off=cmd_flags[0]?cmd_dst:cmd_src;
 wire [31:0] loc_off=cmd_flags[0]?cmd_src:cmd_dst;
 wire [32:0] phys={1'b0,cfg_ddr_base}+{1'b0,ddr_off};
 wire [33:0] phys_end={1'b0,phys}+{2'b0,cmd_bytes};
 wire [31:0] current_local=loc_ptr+{28'b0,lane};
 wire local_done=(state==LWAIT || (state==LREQ && local_ready)) && local_rsp_valid;
 wire progress=(arvalid&&arready)||(rready&&rvalid)||(awvalid&&awready)||(wvalid&&wready)||(bready&&bvalid)||(local_valid&&local_ready)||local_done;
 wire waiting=state==AR || state==RD || state==LREQ || state==LWAIT || state==WRITE || state==BRESP;
 assign cmd_ready=rst_n && enable && !fault_locked && state==IDLE;
 assign rsp_valid=state==RESPONSE;
 assign busy=state!=IDLE;
 assign drained=state==IDLE || state==RESPONSE;
 assign araddr=ddr_ptr;assign awaddr=ddr_ptr;
 assign arid=0;assign awid=0;assign wid=0;
 assign arlen=0;assign awlen=0;
 assign arburst=1;assign awburst=1;assign arlock=0;assign awlock=0;
 assign arcache=0;assign awcache=0;assign arqos=0;assign awqos=0;assign arprot=0;assign awprot=0;
 assign arsize=size_q;assign awsize=size_q;
 assign arvalid=state==AR;assign rready=state==RD;
 assign awvalid=state==WRITE && !aw_done;
 assign wvalid=state==WRITE && !w_done;
 assign wlast=1;assign bready=state==BRESP;
 assign wdata=buffer<<(ddr_ptr[2:0]*8);
 assign wstrb=8'(((9'd1<<beat_bytes)-9'd1)<<ddr_ptr[2:0]);
 assign local_valid=state==LREQ;
 assign local_write=!dir;
 assign local_addr={current_local[31:2],2'b00};
 assign local_wstrb=4'b0001<<current_local[1:0];
 assign local_wdata={24'b0,buffer[lane*8+:8]}<<(current_local[1:0]*8);
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE;fault_locked<=0;timed_out<=0;rsp_status<=0;rsp_bytes_done<=0;
   ddr_ptr<=0;loc_ptr<=0;left_bytes<=0;total_bytes<=0;buffer<=0;
   beat_bytes<=0;lane<=0;size_q<=0;watchdog<=0;dir<=0;aw_done<=0;w_done<=0;
  end else begin
   if(recover && state==IDLE) fault_locked<=0;
   if(!waiting || progress) watchdog<=0;
   else if(watchdog<TIMEOUT_CYCLES-1) watchdog<=watchdog+1;
   else if(!timed_out) begin
    timed_out<=1;fault_locked<=1;rsp_status<=7;
   end
   case(state)
    IDLE: if(cmd_valid && cmd_ready) begin
     state<=RESPONSE;rsp_status<=0;rsp_bytes_done<=0;timed_out<=0;
     if(cmd_flags[31:1]!=0) rsp_status<=1;
     else if(cmd_bytes==0) rsp_status<=2;
     else if({1'b0,ddr_off}+{1'b0,cmd_bytes}>{1'b0,cfg_ddr_bytes} ||
             {1'b0,loc_off}+{1'b0,cmd_bytes}>{1'b0,cfg_local_bytes} ||
             phys[32] || phys_end>34'h100000000) rsp_status<=3;
     else if(phys[2:0]!=0) rsp_status<=4;
     else begin
      state<=PREP;dir<=cmd_flags[0];ddr_ptr<=phys[31:0];loc_ptr<=loc_off;
      left_bytes<=cmd_bytes;total_bytes<=cmd_bytes;
     end
    end
    PREP: begin
     lane<=0;buffer<=0;aw_done<=0;w_done<=0;
     if(left_bytes>=8) begin beat_bytes<=8;size_q<=3;end
     else if(left_bytes>=4) begin beat_bytes<=4;size_q<=2;end
     else if(left_bytes>=2) begin beat_bytes<=2;size_q<=1;end
     else begin beat_bytes<=1;size_q<=0;end
     state<=dir?LREQ:AR;
    end
    AR: if(arready) state<=RD;
    RD: if(rvalid) begin
     if(rresp!=0 || rid!=0 || !rlast) begin fault_locked<=1;if(!timed_out) rsp_status<=5;end
     if(rlast) begin
      if(timed_out || rsp_status!=0 || rresp!=0 || rid!=0) state<=RESPONSE;
      else begin buffer<=rdata>>(ddr_ptr[2:0]*8);state<=LREQ;end
     end
    end
    LREQ,LWAIT: begin
     if(state==LREQ && local_ready) state<=LWAIT;
     if(local_done) begin
      if(local_error) begin fault_locked<=1;if(!timed_out) rsp_status<=10;end
      if(timed_out || local_error) state<=RESPONSE;
      else begin
        if(dir) buffer[lane*8+:8]<=local_rdata[current_local[1:0]*8+:8];
       if(lane+1==beat_bytes) state<=dir?WRITE:NEXT;
       else begin lane<=lane+1;state<=LREQ;end
      end
     end
    end
    WRITE: begin
     if(awvalid && awready) aw_done<=1;
     if(wvalid && wready) w_done<=1;
     if((aw_done||awready)&&(w_done||wready)) state<=BRESP;
    end
    BRESP: if(bvalid) begin
     if(bresp!=0 || bid!=0) begin fault_locked<=1;if(!timed_out) rsp_status<=6;end
     if(timed_out || bresp!=0 || bid!=0) state<=RESPONSE;
     else state<=NEXT;
    end
    NEXT: begin
     if(timed_out) state<=RESPONSE;
     else if(left_bytes=={28'b0,beat_bytes}) begin rsp_bytes_done<=total_bytes;state<=RESPONSE;end
     else begin ddr_ptr<=ddr_ptr+{28'b0,beat_bytes};loc_ptr<=loc_ptr+{28'b0,beat_bytes};left_bytes<=left_bytes-{28'b0,beat_bytes};state<=PREP;end
    end
    RESPONSE: if(rsp_ready) state<=IDLE;
    default: state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 initial assert(TIMEOUT_CYCLES>=2) else $fatal(1,"timeout parameter");
`endif
endmodule
