// EES331 six-module control bridge. GP0 is AXI3, CPU accesses remain zero wait.
// PS can only publish mailbox requests; only the CPU drives CNN/cache registers.
module image_control_bridge #(
 parameter logic [31:0] BASE_ADDR=32'h4000_0000
)(
 input logic clk,rst_n,
 input logic [31:0] mmio_addr,mmio_wdata,
 input logic mmio_re,mmio_we,
 output logic [31:0] mmio_rdata,output wire mmio_ready,
 output logic [31:0] cnn_mmio_addr,cnn_mmio_wdata,
 output logic cnn_mmio_re,cnn_mmio_we,
 input logic [31:0] cnn_mmio_rdata,input logic cnn_mmio_ready,
 output logic [31:0] cache_csr_addr,cache_csr_wdata,
 output logic cache_csr_re,cache_csr_we,
 input logic [31:0] cache_csr_rdata,input logic cache_csr_ready,
 input logic [31:0] M_AXI_GP0_AWADDR,M_AXI_GP0_ARADDR,
 input logic [11:0] M_AXI_GP0_AWID,M_AXI_GP0_ARID,M_AXI_GP0_WID,
 input logic [3:0] M_AXI_GP0_AWLEN,M_AXI_GP0_ARLEN,
 input logic [2:0] M_AXI_GP0_AWSIZE,M_AXI_GP0_ARSIZE,
 input logic [1:0] M_AXI_GP0_AWBURST,M_AXI_GP0_ARBURST,
 input logic [1:0] M_AXI_GP0_AWLOCK,M_AXI_GP0_ARLOCK,
 input logic [3:0] M_AXI_GP0_AWCACHE,M_AXI_GP0_ARCACHE,
 input logic [2:0] M_AXI_GP0_AWPROT,M_AXI_GP0_ARPROT,
 input logic [3:0] M_AXI_GP0_AWQOS,M_AXI_GP0_ARQOS,
 input logic [31:0] M_AXI_GP0_WDATA,
 input logic [3:0] M_AXI_GP0_WSTRB,
 input logic M_AXI_GP0_AWVALID,M_AXI_GP0_WVALID,M_AXI_GP0_WLAST,
 input logic M_AXI_GP0_BREADY,M_AXI_GP0_ARVALID,M_AXI_GP0_RREADY,
 output wire M_AXI_GP0_AWREADY,M_AXI_GP0_WREADY,M_AXI_GP0_ARREADY,
 output logic [11:0] M_AXI_GP0_BID,M_AXI_GP0_RID,
 output logic [1:0] M_AXI_GP0_BRESP,M_AXI_GP0_RRESP,
 output logic [31:0] M_AXI_GP0_RDATA,
 output logic M_AXI_GP0_BVALID,M_AXI_GP0_RVALID,M_AXI_GP0_RLAST
);
 localparam logic [31:0] IDENT=32'h45455332;
 logic [31:0] index_reg,request_seq,ack_seq,command;
 logic [31:0] argument[0:14];
 logic [31:0] response_status,response_data[0:3],cpu_ready;
 logic bridge_error;
 wire pending=request_seq!=ack_seq;
 wire cpu_sel=mmio_addr>=BASE_ADDR && mmio_addr<BASE_ADDR+32'h24;
 wire [5:0] cpu_off=mmio_addr[5:0];
 wire [31:0] local_index=index_reg;
 logic aw_active,aw_bad;
 logic [31:0] aw_addr;
 logic [11:0] aw_id;
 logic [3:0] aw_length,write_beat;
 logic read_active,read_bad;
 logic [31:0] read_addr;
 logic [11:0] read_id;
 logic [3:0] read_length,read_beat;
 integer j;
 assign mmio_ready=1'b1;
 assign M_AXI_GP0_AWREADY=!aw_active && !M_AXI_GP0_BVALID;
 // AXI permits waiting for AW before accepting W. This avoids write-data IDs
 // being associated with the wrong address and supports WVALID arriving first.
 assign M_AXI_GP0_WREADY=aw_active && !M_AXI_GP0_BVALID;
 assign M_AXI_GP0_ARREADY=!read_active && !M_AXI_GP0_RVALID;

 function automatic logic valid_mailbox_addr(input logic [31:0] a);
  return a>=BASE_ADDR && a<BASE_ADDR+32'h68 && a[1:0]==0;
 endfunction
 function automatic logic [31:0] mailbox_read(input logic [31:0] off);
  case(off)
   0:mailbox_read=IDENT;
   4:mailbox_read={30'b0,bridge_error,pending};
   8:mailbox_read=request_seq;
   12:mailbox_read=ack_seq;
   16:mailbox_read=command;
   80:mailbox_read=response_status;
   84:mailbox_read=response_data[0];
   88:mailbox_read=response_data[1];
   92:mailbox_read=response_data[2];
   96:mailbox_read=response_data[3];
   100:mailbox_read=cpu_ready;
   default:begin
    mailbox_read=0;
    if(off>=20 && off<=76 && off[1:0]==0)
     mailbox_read=argument[(off-20)>>2];
   end
  endcase
 endfunction
 function automatic logic ps_writable(input logic [31:0] a,input logic [31:0] d);
  logic [31:0] off;
  begin
   off=a-BASE_ADDR;
   // Repeating the published sequence is idempotent, including after ACK.
   ps_writable=valid_mailbox_addr(a) &&
    ((off==8 && (d==request_seq || (!pending && d!=ack_seq))) ||
     (!pending && off>=16 && off<=76));
  end
 endfunction

 always_comb begin
  cnn_mmio_addr=index_reg-32'h1000;cnn_mmio_wdata=mmio_wdata;
  cache_csr_addr=index_reg-32'h2000;cache_csr_wdata=mmio_wdata;
  cnn_mmio_re=0;cnn_mmio_we=0;cache_csr_re=0;cache_csr_we=0;
  mmio_rdata=0;
  if(cpu_sel)begin
   case(cpu_off)
    0:mmio_rdata=IDENT;
    4:mmio_rdata={30'b0,bridge_error,pending};
    8:mmio_rdata=index_reg;
    12:begin
     if(local_index<32'h68)mmio_rdata=mailbox_read(local_index);
     else if(local_index>=32'h1000 && local_index<32'h2000)begin
      mmio_rdata=cnn_mmio_rdata;cnn_mmio_re=mmio_re;cnn_mmio_we=mmio_we;
     end else if(local_index>=32'h2000 && local_index<32'h2100)begin
      mmio_rdata=cache_csr_rdata;cache_csr_re=mmio_re;cache_csr_we=mmio_we;
     end
    end
    16:mmio_rdata=request_seq;
    20:mmio_rdata=ack_seq;
    24:mmio_rdata=response_status;
    28:mmio_rdata=response_data[0];
    32:mmio_rdata={31'b0,bridge_error};
    default:mmio_rdata=0;
   endcase
  end
 end

 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   index_reg<=0;request_seq<=0;ack_seq<=0;command<=0;
   response_status<=0;cpu_ready<=0;bridge_error<=0;
   for(j=0;j<15;j=j+1)argument[j]<=0;
   for(j=0;j<4;j=j+1)response_data[j]<=0;
   aw_active<=0;aw_bad<=0;aw_addr<=0;aw_id<=0;aw_length<=0;write_beat<=0;
   read_active<=0;read_bad<=0;read_addr<=0;read_id<=0;read_length<=0;read_beat<=0;
   M_AXI_GP0_BID<=0;M_AXI_GP0_BRESP<=0;M_AXI_GP0_BVALID<=0;
   M_AXI_GP0_RID<=0;M_AXI_GP0_RRESP<=0;M_AXI_GP0_RDATA<=0;
   M_AXI_GP0_RVALID<=0;M_AXI_GP0_RLAST<=0;
  end else begin
   if(M_AXI_GP0_BVALID && M_AXI_GP0_BREADY)M_AXI_GP0_BVALID<=0;
   if(M_AXI_GP0_AWVALID && M_AXI_GP0_AWREADY)begin
    aw_active<=1;aw_addr<=M_AXI_GP0_AWADDR;aw_id<=M_AXI_GP0_AWID;
    aw_length<=M_AXI_GP0_AWLEN;write_beat<=0;
    aw_bad<=M_AXI_GP0_AWLEN!=0 || M_AXI_GP0_AWSIZE!=2 ||
      M_AXI_GP0_AWBURST>1 || M_AXI_GP0_AWLOCK!=0 || !valid_mailbox_addr(M_AXI_GP0_AWADDR);
   end
   if(M_AXI_GP0_WVALID && M_AXI_GP0_WREADY)begin
    // Unsupported bursts are fully drained and answered SLVERR; no side effects.
    if(write_beat==aw_length)begin
     aw_active<=0;M_AXI_GP0_BVALID<=1;M_AXI_GP0_BID<=aw_id;
     if(aw_bad || M_AXI_GP0_WID!=aw_id || !M_AXI_GP0_WLAST ||
        M_AXI_GP0_WSTRB!=4'hf || !ps_writable(aw_addr,M_AXI_GP0_WDATA))begin
      M_AXI_GP0_BRESP<=2'b10;
     end else begin
      M_AXI_GP0_BRESP<=0;
      case(aw_addr-BASE_ADDR)
       8:request_seq<=M_AXI_GP0_WDATA;
       16:command<=M_AXI_GP0_WDATA;
       default:argument[(aw_addr-BASE_ADDR-20)>>2]<=M_AXI_GP0_WDATA;
      endcase
     end
    end else begin
     write_beat<=write_beat+1'b1;
     if(M_AXI_GP0_WLAST || M_AXI_GP0_WID!=aw_id)aw_bad<=1;
    end
   end
   if(M_AXI_GP0_ARVALID && M_AXI_GP0_ARREADY)begin
    read_active<=1;read_addr<=M_AXI_GP0_ARADDR;read_id<=M_AXI_GP0_ARID;
    read_length<=M_AXI_GP0_ARLEN;read_beat<=0;
    read_bad<=M_AXI_GP0_ARLEN!=0 || M_AXI_GP0_ARSIZE!=2 ||
      M_AXI_GP0_ARBURST>1 || M_AXI_GP0_ARLOCK!=0 || !valid_mailbox_addr(M_AXI_GP0_ARADDR);
   end
   if(M_AXI_GP0_RVALID && M_AXI_GP0_RREADY)begin
    M_AXI_GP0_RVALID<=0;
    if(M_AXI_GP0_RLAST)read_active<=0;
    else read_beat<=read_beat+1'b1;
   end
   if(read_active && !M_AXI_GP0_RVALID)begin
    M_AXI_GP0_RVALID<=1;M_AXI_GP0_RID<=read_id;
    M_AXI_GP0_RLAST<=read_beat==read_length;
    M_AXI_GP0_RRESP<=read_bad?2'b10:2'b00;
    M_AXI_GP0_RDATA<=read_bad?32'b0:mailbox_read(read_addr-BASE_ADDR);
   end
   if(cpu_sel && mmio_we)begin
    case(cpu_off)
     8:index_reg<=mmio_wdata;
     12:begin
      case(index_reg)
       12:begin
        if(mmio_wdata==request_seq)ack_seq<=mmio_wdata;
        else bridge_error<=1;
       end
       80:response_status<=mmio_wdata;
       84:response_data[0]<=mmio_wdata;
       88:response_data[1]<=mmio_wdata;
       92:response_data[2]<=mmio_wdata;
       96:response_data[3]<=mmio_wdata;
       100:cpu_ready<=mmio_wdata;
       default:begin
        if(index_reg<32'h1000 || index_reg>=32'h2100 || index_reg[1:0]!=0)bridge_error<=1;
       end
      endcase
     end
     20:begin
      if(mmio_wdata==request_seq)ack_seq<=mmio_wdata;
      else bridge_error<=1;
     end
     24:response_status<=mmio_wdata;
     28:response_data[0]<=mmio_wdata;
     32:if(mmio_wdata[0])bridge_error<=0;
     default:bridge_error<=1;
    endcase
   end
   if((cnn_mmio_re || cnn_mmio_we) && !cnn_mmio_ready)bridge_error<=1;
   if((cache_csr_re || cache_csr_we) && !cache_csr_ready)bridge_error<=1;
  end
 end
endmodule
