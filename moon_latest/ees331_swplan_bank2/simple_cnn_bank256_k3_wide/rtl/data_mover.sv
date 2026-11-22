// 1 KiB aligned pages on the EES331 cache path. Each command transfers
// eight 128-byte AXI3 bursts. Ordered local requests stream with four credits.
// Synchronous staging separates the AXI and
// local BRAM timing paths. No byte shifter or arbitrary-length burst planner.
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
 output wire [2:0] arsize,awsize,
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
 typedef enum logic [3:0] {
  IDLE, VALIDATE, ADDRESS, AR, AXI_READ, LOCAL_PREFETCH, LOCAL_STREAM,
  LOCAL_DRAIN, AW, WRITE_PREFETCH, WRITE_SEND, B, NEXT, RESPONSE
 } state_t;
 localparam integer WD_BITS=$clog2(TIMEOUT_CYCLES);
 state_t state;
 logic writeback, flags_ok, length_ok, timed_out;
 logic [31:0] ddr_offset,local_offset;
 logic [32:0] physical_addr;
 logic [21:0] ddr_page,local_page;
 logic [2:0] burst;
 logic [4:0] rx_beat,local_word;
 logic [3:0] tx_beat;
 logic [WD_BITS-1:0] watchdog;
 (* ram_style="distributed" *) logic [31:0] low_words[16],high_words[16];
 logic [31:0] read_low,read_high,returned_word;
 logic [5:0] local_sent,local_received;
 logic [2:0] local_pending;
 logic local_failed,returned_valid;
 logic [4:0] returned_index;
 wire [5:0] next_local=local_sent+6'd1;
 wire local_take=local_valid && local_ready;

 assign cmd_ready=rst_n && enable && !fault_locked && state==IDLE;
 assign rsp_valid=state==RESPONSE;
 assign busy=state!=IDLE;
 assign drained=state==IDLE || state==RESPONSE;
 assign araddr={ddr_page,burst,7'b0};
 assign awaddr=araddr;
 assign arid=0;assign awid=0;assign wid=0;
 assign arlen=15;assign awlen=15;
 assign arsize=3;assign awsize=3;
 assign arburst=1;assign awburst=1;assign arlock=0;assign awlock=0;
 assign arcache=0;assign awcache=0;assign arqos=0;assign awqos=0;
 assign arprot=0;assign awprot=0;
 assign arvalid=state==AR;assign rready=state==AXI_READ;
 assign awvalid=state==AW;
 assign wvalid=state==WRITE_SEND;assign wlast=tx_beat==15;
 assign wdata={read_high,read_low};
 assign wstrb=8'hff;
 assign bready=state==B;
 assign local_valid=state==LOCAL_STREAM && local_sent<32 && local_pending<4 && !timed_out && !local_failed;
 assign local_write=!writeback;
 assign local_addr={local_page,burst,local_sent[4:0],2'b00};
 assign local_wstrb=!writeback?4'hf:4'b0;
 assign local_wdata=local_sent[0]?read_high:read_low;

 wire local_done=(state==LOCAL_STREAM || state==LOCAL_DRAIN) && local_rsp_valid && (local_pending!=0 || local_take);
 wire progress=(arvalid && arready) || (rready && rvalid) ||
               (awvalid && awready) || (wvalid && wready) || (bready && bvalid) ||
               (local_valid && local_ready) || local_done;
 wire waiting=state==AR || state==AXI_READ || state==LOCAL_STREAM || (state==LOCAL_DRAIN && local_pending!=0) ||
              state==AW || state==WRITE_SEND || state==B;
 wire expire=waiting && !progress && watchdog==WD_BITS'(TIMEOUT_CYCLES-1);
 wire read_bad=rresp!=0 || rid!=0 || (rlast!=(rx_beat==15));
 wire accept_beat=state==AXI_READ && rvalid && rx_beat<16;
 wire publish_word=returned_valid;
 wire [3:0] staging_read_index=(state==WRITE_PREFETCH)?tx_beat:((state==WRITE_SEND)?(tx_beat+4'd1):(state==LOCAL_PREFETCH?4'd0:next_local[4:1]));
 wire [3:0] staging_write_index=accept_beat?rx_beat[3:0]:returned_index[4:1];
 wire [31:0] low_in=accept_beat?rdata[31:0]:returned_word;
 wire [31:0] high_in=accept_beat?rdata[63:32]:returned_word;
 always_ff @(posedge clk)begin
  if(accept_beat || (publish_word && !returned_index[0]))
   low_words[staging_write_index]<=low_in;
  if(accept_beat || (publish_word && returned_index[0]))
   high_words[staging_write_index]<=high_in;
  if(state==LOCAL_PREFETCH || state==WRITE_PREFETCH || (state==WRITE_SEND && wready && !wlast) || (local_take && !writeback && local_sent<31))begin
   read_low<=low_words[staging_read_index];
   read_high<=high_words[staging_read_index];
  end
  if(!rst_n)begin
   local_sent<=0;local_received<=0;local_pending<=0;local_failed<=0;
   returned_valid<=0;returned_index<=0;returned_word<=0;
  end else begin
   returned_valid<=0;
   if(state==LOCAL_PREFETCH)begin
    local_sent<=0;local_received<=0;local_pending<=0;local_failed<=0;
   end else begin
    if(local_take)local_sent<=local_sent+1'b1;
    if(local_done)begin
     local_received<=local_received+1'b1;
     if(local_error)local_failed<=1;
     if(writeback && !local_error && !timed_out && !local_failed)begin
      returned_word<=local_rdata;returned_index<=local_received[4:0];returned_valid<=1;
     end
    end
    case({local_take,local_done})
     2'b10:local_pending<=local_pending+1'b1;
     2'b01:local_pending<=local_pending-1'b1;
     default:;
    endcase
   end
  end
 end

 always_ff @(posedge clk)begin
  if(!rst_n)begin
   state<=IDLE;fault_locked<=0;timed_out<=0;rsp_status<=0;rsp_bytes_done<=0;
   writeback<=0;flags_ok<=0;length_ok<=0;ddr_offset<=0;local_offset<=0;
   physical_addr<=0;ddr_page<=0;local_page<=0;watchdog<=0;
   burst<=0;rx_beat<=0;local_word<=0;tx_beat<=0;
  end else begin
   if(recover && state==IDLE)fault_locked<=0;
   if(!waiting || progress)watchdog<=0;
   else if(!expire)watchdog<=watchdog+1'b1;
   if(expire && !timed_out)begin
    timed_out<=1;fault_locked<=1;rsp_status<=7;
   end
   case(state)
    IDLE:if(cmd_valid && cmd_ready)begin
     state<=VALIDATE;writeback<=cmd_flags[0];flags_ok<=cmd_flags[31:1]==0;
     length_ok<=cmd_bytes==1024;rsp_status<=0;rsp_bytes_done<=0;timed_out<=0;
     ddr_offset<=cmd_flags[0]?cmd_dst:cmd_src;
     local_offset<=cmd_flags[0]?cmd_src:cmd_dst;
    end
    VALIDATE:begin
     physical_addr<={1'b0,cfg_ddr_base}+{1'b0,ddr_offset};
     local_page<=local_offset[31:10];
     if(!flags_ok)begin rsp_status<=1;state<=RESPONSE;end
     else if(!length_ok)begin rsp_status<=2;state<=RESPONSE;end
     else if(ddr_offset[31:10]>=cfg_ddr_bytes[31:10] || local_offset[31:10]>=cfg_local_bytes[31:10])
      begin rsp_status<=3;state<=RESPONSE;end
     else if(ddr_offset[9:0]!=0 || local_offset[9:0]!=0 || cfg_ddr_base[9:0]!=0)
      begin rsp_status<=4;state<=RESPONSE;end
     else state<=ADDRESS;
    end
    ADDRESS:if(physical_addr[32])begin rsp_status<=3;state<=RESPONSE;end
     else begin
      ddr_page<=physical_addr[31:10];burst<=0;rx_beat<=0;local_word<=0;tx_beat<=0;
      state<=writeback?LOCAL_PREFETCH:AR;
     end
    AR:if(arready)state<=AXI_READ;
    AXI_READ:if(rvalid)begin
     if(read_bad)begin fault_locked<=1;if(!timed_out)rsp_status<=5;end
     if(rx_beat<16)rx_beat<=rx_beat+1'b1;
     if(rlast)state<=timed_out || rsp_status!=0 || read_bad ? RESPONSE : LOCAL_PREFETCH;
    end
    LOCAL_PREFETCH:state<=LOCAL_STREAM;
    LOCAL_STREAM:begin
     if(local_done && local_error)begin
      fault_locked<=1;if(!timed_out)rsp_status<=10;
     end
     if((local_take && local_sent==31) || (local_done && local_error) || timed_out)
      state<=LOCAL_DRAIN;
    end
    LOCAL_DRAIN:begin
     if(local_done && local_error)begin
      fault_locked<=1;if(!timed_out)rsp_status<=10;
     end
     if(local_pending==0 && !returned_valid)
      state<=(timed_out || local_failed)?RESPONSE:(writeback?AW:NEXT);
    end
    AW:if(awready)state<=WRITE_PREFETCH;
    WRITE_PREFETCH:state<=WRITE_SEND;
    WRITE_SEND:if(wready)begin
     if(wlast)state<=B;
     else tx_beat<=tx_beat+1'b1; // Synchronous staging prepares the next beat on this edge.
    end
    B:if(bvalid)begin
     if(bresp!=0 || bid!=0)begin fault_locked<=1;if(!timed_out)rsp_status<=6;end
     state<=timed_out || bresp!=0 || bid!=0 ? RESPONSE : NEXT;
    end
    NEXT:if(burst==7)begin rsp_bytes_done<=1024;state<=RESPONSE;end
     else begin
      burst<=burst+1'b1;rx_beat<=0;local_word<=0;tx_beat<=0;
      state<=writeback?LOCAL_PREFETCH:AR;
     end
    RESPONSE:if(rsp_ready)state<=IDLE;
    default:state<=IDLE;
   endcase
  end
 end

`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n)begin
  assert(local_pending<=4)else $fatal(1,"local credit overflow");
  if(local_rsp_valid)assert(local_pending!=0 || local_take)else $fatal(1,"unsolicited local response");
  if(state==RESPONSE)assert(local_pending==0 && !returned_valid)else $fatal(1,"response before local drain");
 end
 initial assert(TIMEOUT_CYCLES>=2 && MAX_BURST_BEATS==16)
  else $fatal(1,"aligned page mover geometry");
`endif
endmodule
