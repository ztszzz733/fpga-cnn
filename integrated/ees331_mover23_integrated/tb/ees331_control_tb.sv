`timescale 1ns/1ps
// Real unchanged CPU + generated firmware + GP0 bridge; register-level CNN/cache
// responders here test control only. Arithmetic/cache are tested independently.
module ees331_control_tb;
 logic clk=0,rst_n=0;always #5 clk=~clk;
 logic [31:0] mmio_addr,mmio_wdata,mmio_rdata;
 logic mmio_re,mmio_we,mmio_ready;
 logic [31:0] cnn_mmio_addr,cnn_mmio_wdata,cnn_mmio_rdata;
 logic cnn_mmio_re,cnn_mmio_we,cnn_mmio_ready=1;
 logic [31:0] cache_csr_addr,cache_csr_wdata,cache_csr_rdata;
 logic cache_csr_re,cache_csr_we,cache_csr_ready=1;
 logic [31:0] M_AXI_GP0_AWADDR=0,M_AXI_GP0_ARADDR=0;
 logic [11:0] M_AXI_GP0_AWID=12'h123,M_AXI_GP0_ARID=12'h456,M_AXI_GP0_WID=12'h123;
 logic [3:0] M_AXI_GP0_AWLEN=0,M_AXI_GP0_ARLEN=0;
 logic [2:0] M_AXI_GP0_AWSIZE=2,M_AXI_GP0_ARSIZE=2;
 logic [1:0] M_AXI_GP0_AWBURST=1,M_AXI_GP0_ARBURST=1;
 logic [1:0] M_AXI_GP0_AWLOCK=0,M_AXI_GP0_ARLOCK=0;
 logic [3:0] M_AXI_GP0_AWCACHE=0,M_AXI_GP0_ARCACHE=0;
 logic [2:0] M_AXI_GP0_AWPROT=0,M_AXI_GP0_ARPROT=0;
 logic [3:0] M_AXI_GP0_AWQOS=0,M_AXI_GP0_ARQOS=0;
 logic [31:0] M_AXI_GP0_WDATA=0,M_AXI_GP0_RDATA;
 logic [3:0] M_AXI_GP0_WSTRB=15;
 logic M_AXI_GP0_AWVALID=0,M_AXI_GP0_WVALID=0,M_AXI_GP0_WLAST=1;
 logic M_AXI_GP0_BREADY=0,M_AXI_GP0_ARVALID=0,M_AXI_GP0_RREADY=0;
 logic M_AXI_GP0_AWREADY,M_AXI_GP0_WREADY,M_AXI_GP0_ARREADY;
 logic [11:0] M_AXI_GP0_BID,M_AXI_GP0_RID;
 logic [1:0] M_AXI_GP0_BRESP,M_AXI_GP0_RRESP;
 logic M_AXI_GP0_BVALID,M_AXI_GP0_RVALID,M_AXI_GP0_RLAST;
 image_control_bridge bridge(.*);
 logic [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata=0;
 logic imem_re,dmem_re,dmem_we;logic [3:0] dmem_wstrb;
 cpu_core #(.SRAM_SIZE(16384)) cpu(.*);
 imem_rom #(.IMEM_SIZE(8192),.INIT_FILE("firmware/ees331_cpu/program.mem")) rom(.*);

 logic [31:0] cnn_reg[0:21];
 logic cnn_running=0,resvalid=0;
 integer fence_wait=0,fence_count=0,starts=0,acks=0;
 logic [31:0] cache_start=0,cache_bytes=0;
 always_comb begin
  cnn_mmio_rdata=cnn_reg[cnn_mmio_addr[6:2]];
  if(cnn_mmio_addr==4)cnn_mmio_rdata=32'h11 | (cnn_running?2:0) | (resvalid?32:0);
  cache_csr_rdata=0;
  if(cache_csr_addr==0)cache_csr_rdata=1 | (fence_wait>0?2:0);
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   for(integer i=0;i<22;i++)cnn_reg[i]<=0;
   cnn_running<=0;resvalid<=0;fence_wait<=0;fence_count<=0;starts<=0;acks<=0;
  end else begin
   if(fence_wait>0)fence_wait<=fence_wait-1;
   if(cache_csr_we)case(cache_csr_addr)
    8:cache_start<=cache_csr_wdata;
    12:cache_bytes<=cache_csr_wdata;
    4:begin fence_wait<=20;fence_count<=fence_count+1;end
    default:begin end
   endcase
   if(cnn_mmio_we)begin
    if(cnn_mmio_addr==8)begin
     if(cnn_mmio_wdata[0])begin cnn_reg[21]<=cnn_reg[21]+1;cnn_running<=0;resvalid<=0;end
     if(cnn_mmio_wdata[1])begin cnn_running<=1;starts<=starts+1;end
     if(cnn_mmio_wdata[4])begin
      resvalid<=1;cnn_reg[12]<=cnn_reg[11];cnn_reg[13]<=32'h20000;cnn_reg[14]<=128;
     end
     if(cnn_mmio_wdata[5])begin
      assert(cnn_reg[19]==cnn_reg[12] && cnn_reg[20]==cnn_reg[21]);
      resvalid<=0;cnn_running<=0;acks<=acks+1;
     end
    end else cnn_reg[cnn_mmio_addr[6:2]]<=cnn_mmio_wdata;
   end
  end
 end

 task automatic wr(input logic[31:0] off,val,input logic[1:0] expected=0);
  @(negedge clk);M_AXI_GP0_WDATA=val;M_AXI_GP0_WVALID=1;
  repeat(3)@(negedge clk); // W arrives before AW; must not be accepted early.
  assert(!M_AXI_GP0_WREADY);
  M_AXI_GP0_AWADDR=32'h40000000+off;M_AXI_GP0_AWVALID=1;
  do @(posedge clk);while(!M_AXI_GP0_AWREADY);
  @(negedge clk);M_AXI_GP0_AWVALID=0;
  do @(posedge clk);while(!M_AXI_GP0_WREADY);
  @(negedge clk);M_AXI_GP0_WVALID=0;
  while(!M_AXI_GP0_BVALID)@(negedge clk);
  repeat(4)begin @(negedge clk);assert(M_AXI_GP0_BVALID && M_AXI_GP0_BRESP==expected && M_AXI_GP0_BID==12'h123);end
  M_AXI_GP0_BREADY=1;@(negedge clk);M_AXI_GP0_BREADY=0;
 endtask
 task automatic rd(input logic[31:0] off,output logic[31:0] value,input logic[1:0] expected=0);
  @(negedge clk);M_AXI_GP0_ARADDR=32'h40000000+off;M_AXI_GP0_ARVALID=1;
  do @(posedge clk);while(!M_AXI_GP0_ARREADY);
  @(negedge clk);M_AXI_GP0_ARVALID=0;
  while(!M_AXI_GP0_RVALID)@(negedge clk);
  value=M_AXI_GP0_RDATA;
  repeat(3)begin @(negedge clk);assert(M_AXI_GP0_RVALID && M_AXI_GP0_RDATA==value && M_AXI_GP0_RRESP==expected && M_AXI_GP0_RID==12'h456 && M_AXI_GP0_RLAST);end
  M_AXI_GP0_RREADY=1;@(negedge clk);M_AXI_GP0_RREADY=0;
 endtask
 task automatic rejected_bursts();
  @(negedge clk);M_AXI_GP0_AWADDR=32'h40000010;M_AXI_GP0_AWLEN=2;M_AXI_GP0_AWVALID=1;
  do @(posedge clk);while(!M_AXI_GP0_AWREADY);
  @(negedge clk);M_AXI_GP0_AWVALID=0;
  for(integer k=0;k<3;k++)begin
   M_AXI_GP0_WVALID=1;M_AXI_GP0_WDATA=32'hBAD00000+k;M_AXI_GP0_WLAST=k==2;
   do @(posedge clk);while(!M_AXI_GP0_WREADY);
   @(negedge clk);M_AXI_GP0_WVALID=0;
  end
  while(!M_AXI_GP0_BVALID)@(negedge clk);
  assert(M_AXI_GP0_BRESP==2 && M_AXI_GP0_BID==12'h123);
  M_AXI_GP0_BREADY=1;@(negedge clk);M_AXI_GP0_BREADY=0;
  M_AXI_GP0_AWLEN=0;M_AXI_GP0_WLAST=1;
  M_AXI_GP0_ARADDR=32'h40000000;M_AXI_GP0_ARLEN=2;M_AXI_GP0_ARVALID=1;
  do @(posedge clk);while(!M_AXI_GP0_ARREADY);
  @(negedge clk);M_AXI_GP0_ARVALID=0;
  for(integer k=0;k<3;k++)begin
   while(!M_AXI_GP0_RVALID)@(negedge clk);
   repeat(2)begin @(negedge clk);assert(M_AXI_GP0_RRESP==2 && M_AXI_GP0_RID==12'h456 && M_AXI_GP0_RLAST==(k==2));end
   M_AXI_GP0_RREADY=1;@(negedge clk);M_AXI_GP0_RREADY=0;
  end
  M_AXI_GP0_ARLEN=0;
 endtask
 logic [31:0] seq=0,value,resp[0:3];
 task automatic rpc(input logic[31:0] op,a=0,b=0,c=0,d=0,expected=0);
  wr(16,op);wr(20,a);wr(24,b);wr(28,c);wr(32,d);
  seq++;wr(8,seq);
  for(integer k=0;k<10000;k++)begin rd(12,value);if(value==seq)break;if(k==9999)$fatal(1,"CPU timeout op%0d",op);end
  rd(80,value);assert(value==expected) else $fatal(1,"RPC op%0d status%0d expected%0d",op,value,expected);
  for(integer k=0;k<4;k++)rd(84+4*k,resp[k]);
 endtask
 initial begin
  repeat(5)@(negedge clk);rst_n=1;
  for(integer k=0;k<100;k++)begin rd(100,value);if(value==32'h43505532)break;end
  assert(value==32'h43505532) else $fatal(1,"CPU did not boot");
  rd(0,value);assert(value==32'h45455332);
  wr(12,1,2);wr(32'h1000,1,2); // PS cannot ACK or access CNN directly.
  M_AXI_GP0_WSTRB=1;wr(16,99,2);M_AXI_GP0_WSTRB=15;
  M_AXI_GP0_WID=12'h124;wr(16,99,2);M_AXI_GP0_WID=12'h123;
  rd(1,value,2);rd(32'h2000,value,2);
  rejected_bursts();rd(16,value);assert(value==0);
  rpc(4,0,0,0,0,4); // DDR not published yet
  rpc(1,32'h44524459);rpc(8);
  rpc(2,12,4);rpc(2,16,1023);rpc(3,4);rpc(4);
  assert(starts==1);
  rpc(2,12,1,0,0,3); // immutable config while running
  rpc(5,0,100);rpc(6);
  assert(resp[0]==100 && resp[1]==32'h20000 && resp[2]==128 && resp[3]==1);
  assert(fence_count==2 && fence_wait==0 && cache_start==32'h20000 && cache_bytes==128);
  rpc(7,100,0,0,0,8);assert(acks==0); // stale epoch rejected
  rpc(7,100,1);assert(acks==1);
  rpc(6,0,0,0,0,2);
  rpc(8);rpc(10);assert(resp[3]==2);
  wr(8,seq); // repeated publication is a no-op, not another reset
  repeat(100)@(negedge clk);assert(cnn_reg[21]==2);
  $display("PASS EES331 real RV32I / GP0 mailbox / fence / epoch control");$finish;
 end
 initial begin #50000000;$fatal(1,"global timeout");end
endmodule
