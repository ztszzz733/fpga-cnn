// One 64-byte transaction on the Zynq-7000 AXI3 HP interface.
// AW and W advance independently. Completion of writes means B was accepted.
// cmd_addr is an already validated, physical, 64-byte aligned address.
module cnn_ddr_bridge (
 input logic clk, rst_n,
 input logic cmd_valid, cmd_write,
 input logic [31:0] cmd_addr,
 input logic [511:0] cmd_wline,
 output wire cmd_ready,
 output logic done, error,
 output logic [511:0] rline,
 output wire busy,
 output wire [31:0] S_AXI_HP0_AWADDR, S_AXI_HP0_ARADDR,
 output wire [63:0] S_AXI_HP0_WDATA,
 input wire [63:0] S_AXI_HP0_RDATA,
 output wire [5:0] S_AXI_HP0_AWID, S_AXI_HP0_ARID, S_AXI_HP0_WID,
 input wire [5:0] S_AXI_HP0_BID, S_AXI_HP0_RID,
 output wire [3:0] S_AXI_HP0_AWLEN, S_AXI_HP0_ARLEN,
 output wire [2:0] S_AXI_HP0_AWSIZE, S_AXI_HP0_ARSIZE,
 output wire [1:0] S_AXI_HP0_AWBURST, S_AXI_HP0_ARBURST,
 output wire [1:0] S_AXI_HP0_AWLOCK, S_AXI_HP0_ARLOCK,
 output wire [3:0] S_AXI_HP0_AWCACHE, S_AXI_HP0_ARCACHE,
 output wire [2:0] S_AXI_HP0_AWPROT, S_AXI_HP0_ARPROT,
 output wire [3:0] S_AXI_HP0_AWQOS, S_AXI_HP0_ARQOS,
 output wire [7:0] S_AXI_HP0_WSTRB,
 output wire S_AXI_HP0_AWVALID, S_AXI_HP0_WVALID, S_AXI_HP0_WLAST,
 output wire S_AXI_HP0_BREADY, S_AXI_HP0_ARVALID, S_AXI_HP0_RREADY,
 input wire S_AXI_HP0_AWREADY, S_AXI_HP0_WREADY, S_AXI_HP0_BVALID,
 input wire S_AXI_HP0_ARREADY, S_AXI_HP0_RVALID, S_AXI_HP0_RLAST,
 input wire [1:0] S_AXI_HP0_BRESP, S_AXI_HP0_RRESP
);
 typedef enum logic [1:0] {IDLE, WR, RD_ADDR, RD_DATA} state_t;
 state_t state;
 logic [31:0] address_q;
 logic [511:0] line_q;
 logic [3:0] beat;
 logic aw_done, w_done, transfer_error;
 assign busy = state != IDLE;
 assign cmd_ready = state == IDLE;
 assign S_AXI_HP0_AWADDR = address_q;
 assign S_AXI_HP0_ARADDR = address_q;
 assign S_AXI_HP0_WDATA = line_q[beat[2:0]*64 +: 64];
 assign S_AXI_HP0_AWID=0, S_AXI_HP0_ARID=0, S_AXI_HP0_WID=0;
 assign S_AXI_HP0_AWLEN=7, S_AXI_HP0_ARLEN=7;
 assign S_AXI_HP0_AWSIZE=3, S_AXI_HP0_ARSIZE=3;
 assign S_AXI_HP0_AWBURST=1, S_AXI_HP0_ARBURST=1;
 assign S_AXI_HP0_AWLOCK=0, S_AXI_HP0_ARLOCK=0;
 // Non-cacheable/non-bufferable attributes; this does not provide PS coherency.
 assign S_AXI_HP0_AWCACHE=0, S_AXI_HP0_ARCACHE=0;
 assign S_AXI_HP0_AWPROT=0, S_AXI_HP0_ARPROT=0;
 assign S_AXI_HP0_AWQOS=0, S_AXI_HP0_ARQOS=0;
 assign S_AXI_HP0_WSTRB=8'hff;
 assign S_AXI_HP0_AWVALID = state==WR && !aw_done;
 assign S_AXI_HP0_WVALID = state==WR && !w_done;
 assign S_AXI_HP0_WLAST = beat==7;
 assign S_AXI_HP0_BREADY = state==WR && aw_done && w_done;
 assign S_AXI_HP0_ARVALID = state==RD_ADDR;
 assign S_AXI_HP0_RREADY = state==RD_DATA;
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE; address_q<=0; line_q<=0; rline<=0; beat<=0;
   aw_done<=0; w_done<=0; transfer_error<=0; done<=0; error<=0;
  end else begin
   done<=0;
   case(state)
    IDLE: if(cmd_valid) begin
     address_q<=cmd_addr; line_q<=cmd_wline; beat<=0;
     aw_done<=0; w_done<=0; transfer_error<=0; error<=0;
     state<=cmd_write ? WR : RD_ADDR;
    end
    WR: begin
     if(S_AXI_HP0_AWVALID && S_AXI_HP0_AWREADY) aw_done<=1;
     if(S_AXI_HP0_WVALID && S_AXI_HP0_WREADY) begin
      if(beat==7) w_done<=1;
      else beat<=beat+1'b1;
     end
     if(S_AXI_HP0_BREADY && S_AXI_HP0_BVALID) begin
      error<=S_AXI_HP0_BRESP!=0 || S_AXI_HP0_BID!=0;
      done<=1; state<=IDLE;
     end
    end
    RD_ADDR: if(S_AXI_HP0_ARREADY) state<=RD_DATA;
    RD_DATA: if(S_AXI_HP0_RVALID) begin
     if(beat<8) rline[beat[2:0]*64 +: 64]<=S_AXI_HP0_RDATA;
     if(S_AXI_HP0_RRESP!=0 || S_AXI_HP0_RID!=0 || beat>=8) transfer_error<=1;
     if(S_AXI_HP0_RLAST) begin
      error<=transfer_error || S_AXI_HP0_RRESP!=0 || S_AXI_HP0_RID!=0 || beat!=7;
      done<=1; state<=IDLE;
     end else begin
      if(beat<8) beat<=beat+1'b1;
      if(beat>=7) transfer_error<=1;
     end
    end
    default: state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk) if(rst_n && cmd_valid && cmd_ready)
  assert(cmd_addr[5:0]==0) else $fatal(1,"unaligned 64B DDR command");
`endif
endmodule
