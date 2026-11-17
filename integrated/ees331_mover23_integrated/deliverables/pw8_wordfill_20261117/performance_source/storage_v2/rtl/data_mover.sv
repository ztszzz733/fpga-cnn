// One command outstanding. AXI3 INCR bursts plus aligned local word accesses.
// 64-bit AXI, 32-bit local word port; local byte starts may be unaligned.
// Tail accesses use exact 4/2/1-byte AXI transfers, never speculative overreads.
module data_mover #(
 parameter integer TIMEOUT_CYCLES=1024,
 parameter integer MAX_BURST_BEATS=16
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
 localparam integer BUF_AW=MAX_BURST_BEATS<=1?1:$clog2(MAX_BURST_BEATS);
 state_t state;
 logic dir,aw_done,w_done,timed_out;
 logic [31:0] ddr_ptr,loc_ptr,left_bytes,total_bytes,watchdog;
 // 128-byte staging at the default burst size; no additional block RAM.
 (* ram_style="distributed" *) logic [63:0] buffer[0:MAX_BURST_BEATS-1];
 logic [3:0] beat_bytes;
 logic [4:0] burst_beats,read_index,write_index;
 logic [7:0] burst_bytes,local_offset;
 logic [4:0] planned_beats;
 logic [2:0] size_q;
 wire [31:0] ddr_off=cmd_flags[0]?cmd_dst:cmd_src;
 wire [31:0] loc_off=cmd_flags[0]?cmd_src:cmd_dst;
 wire [32:0] phys={1'b0,cfg_ddr_base}+{1'b0,ddr_off};
 wire [33:0] phys_end={1'b0,phys}+{2'b0,cmd_bytes};
 wire [31:0] current_local=loc_ptr+{24'b0,local_offset};
 wire [BUF_AW-1:0] local_index=BUF_AW'(local_offset>>3);
 wire [2:0] lane=local_offset[2:0];
 wire [3:0] beat_left=beat_bytes-{1'b0,lane};
 wire [2:0] local_count=(current_local[1:0]==0 && beat_left>=4)?3'd4:
                      (!current_local[0] && beat_left>=2)?3'd2:3'd1;
 wire [31:0] local_input=local_rdata>>(current_local[1:0]*8);
 wire [7:0] following_offset=local_offset+8'(local_count);
 wire more_local={1'b0,local_offset}+9'(local_count)<{1'b0,burst_bytes};
 // Retire one response and issue the next word on the same edge. This uses
 // the local RAM's existing one-cycle port without a deeper request queue.
 wire lookahead=state==LWAIT && local_rsp_valid && !local_error && !timed_out && more_local;
 wire [7:0] offered_offset=lookahead?following_offset:local_offset;
 wire [31:0] offered_local=loc_ptr+{24'b0,offered_offset};
 wire [2:0] offered_lane=offered_offset[2:0];
 wire [3:0] offered_left=beat_bytes-{1'b0,offered_lane};
 wire [2:0] offered_count=(offered_local[1:0]==0 && offered_left>=4)?3'd4:
                         (!offered_local[0] && offered_left>=2)?3'd2:3'd1;
 wire expected_last=read_index+1'b1==burst_beats;
 wire bad_read=rresp!=0 || rid!=0 || rlast!=expected_last;
 wire [12:0] boundary_bytes=13'd4096-{1'b0,ddr_ptr[11:0]};
 always_comb begin
  planned_beats=1;
  if(left_bytes>=8)begin
   planned_beats=5'(MAX_BURST_BEATS);
   if((left_bytes>>3)<MAX_BURST_BEATS)planned_beats=5'(left_bytes>>3);
   if((boundary_bytes>>3)<13'(planned_beats))planned_beats=5'(boundary_bytes>>3);
  end
 end
 wire local_done=(state==LWAIT || (state==LREQ && local_ready)) && local_rsp_valid;
 wire progress=(arvalid&&arready)||(rready&&rvalid)||(awvalid&&awready)||(wvalid&&wready)||(bready&&bvalid)||(local_valid&&local_ready)||local_done;
 wire waiting=state==AR || state==RD || state==LREQ || state==LWAIT || state==WRITE || state==BRESP;
 assign cmd_ready=rst_n && enable && !fault_locked && state==IDLE;
 assign rsp_valid=state==RESPONSE;
 assign busy=state!=IDLE;
 assign drained=state==IDLE || state==RESPONSE;
 assign araddr=ddr_ptr;assign awaddr=ddr_ptr;
 assign arid=0;assign awid=0;assign wid=0;
 assign arlen=4'(burst_beats-1'b1);assign awlen=4'(burst_beats-1'b1);
 assign arburst=1;assign awburst=1;assign arlock=0;assign awlock=0;
 assign arcache=0;assign awcache=0;assign arqos=0;assign awqos=0;assign arprot=0;assign awprot=0;
 assign arsize=size_q;assign awsize=size_q;
 assign arvalid=state==AR;assign rready=state==RD;
 assign awvalid=state==WRITE && !aw_done;
 assign wvalid=state==WRITE && !w_done;
 assign wlast=write_index+1'b1==burst_beats;assign bready=state==BRESP;
 assign wdata=buffer[BUF_AW'(write_index)]<<(ddr_ptr[2:0]*8);
 assign wstrb=8'(((9'd1<<beat_bytes)-9'd1)<<ddr_ptr[2:0]);
 assign local_valid=state==LREQ || lookahead;
 assign local_write=!dir;
 assign local_addr={offered_local[31:2],2'b00};
 assign local_wstrb=dir?4'b0:(4'((5'd1<<offered_count)-1'b1)<<offered_local[1:0]);
 assign local_wdata=dir?32'b0:(32'(buffer[BUF_AW'(offered_offset>>3)]>>(offered_lane*8))<<(offered_local[1:0]*8));
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE;fault_locked<=0;timed_out<=0;rsp_status<=0;rsp_bytes_done<=0;
   ddr_ptr<=0;loc_ptr<=0;left_bytes<=0;total_bytes<=0;
   beat_bytes<=0;size_q<=0;watchdog<=0;dir<=0;aw_done<=0;w_done<=0;
   burst_beats<=1;burst_bytes<=0;local_offset<=0;read_index<=0;write_index<=0;
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
     local_offset<=0;read_index<=0;write_index<=0;aw_done<=0;w_done<=0;
     burst_beats<=planned_beats;
     if(left_bytes>=8) begin beat_bytes<=8;size_q<=3;burst_bytes<=8'(planned_beats)<<3;end
     else if(left_bytes>=4) begin beat_bytes<=4;size_q<=2;burst_bytes<=4;end
     else if(left_bytes>=2) begin beat_bytes<=2;size_q<=1;burst_bytes<=2;end
     else begin beat_bytes<=1;size_q<=0;burst_bytes<=1;end
     state<=dir?LREQ:AR;
    end
    AR: if(arready) state<=RD;
    RD: if(rvalid) begin
     if(bad_read) begin fault_locked<=1;if(!timed_out) rsp_status<=5;end
     if(read_index<burst_beats)begin
      buffer[BUF_AW'(read_index)]<=rdata>>(ddr_ptr[2:0]*8);
      read_index<=read_index+1'b1;
     end
     if(rlast) begin
      if(timed_out || rsp_status!=0 || bad_read) state<=RESPONSE;
      else state<=LREQ;
     end
    end
    LREQ,LWAIT: begin
     if(state==LREQ && local_ready) state<=LWAIT;
     if(local_done) begin
      if(local_error) begin fault_locked<=1;if(!timed_out) rsp_status<=10;end
      if(timed_out || local_error) state<=RESPONSE;
      else begin
       if(dir)for(integer b=0;b<4;b++)if(b<local_count)
        buffer[local_index][(int'(lane)+b)*8+:8]<=local_input[b*8+:8];
       if({1'b0,local_offset}+9'(local_count)=={1'b0,burst_bytes})state<=dir?WRITE:NEXT;
       else begin local_offset<=following_offset;state<=(lookahead&&local_ready)?LWAIT:LREQ;end
      end
     end
    end
    WRITE: begin
     if(awvalid && awready) aw_done<=1;
     if(wvalid && wready)begin
      if(wlast)w_done<=1;
      else write_index<=write_index+1'b1;
     end
     if((aw_done||awready)&&(w_done||(wvalid&&wready&&wlast))) state<=BRESP;
    end
    BRESP: if(bvalid) begin
     if(bresp!=0 || bid!=0) begin fault_locked<=1;if(!timed_out) rsp_status<=6;end
     if(timed_out || bresp!=0 || bid!=0) state<=RESPONSE;
     else state<=NEXT;
    end
    NEXT: begin
     if(timed_out) state<=RESPONSE;
     else if(left_bytes=={24'b0,burst_bytes}) begin rsp_bytes_done<=total_bytes;state<=RESPONSE;end
     else begin ddr_ptr<=ddr_ptr+{24'b0,burst_bytes};loc_ptr<=loc_ptr+{24'b0,burst_bytes};left_bytes<=left_bytes-{24'b0,burst_bytes};state<=PREP;end
    end
    RESPONSE: if(rsp_ready) state<=IDLE;
    default: state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 initial assert(TIMEOUT_CYCLES>=2) else $fatal(1,"timeout parameter");
 initial assert(MAX_BURST_BEATS>=1 && MAX_BURST_BEATS<=16) else $fatal(1,"AXI3 burst limit");
`endif
endmodule
