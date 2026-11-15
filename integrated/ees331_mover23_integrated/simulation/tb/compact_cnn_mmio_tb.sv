`timescale 1ns/1ps
module compact_cnn_mmio_tb;
 logic clk=0;always #5 clk=!clk;
 logic rst_n=0;
 logic [31:0] cnn_mmio_addr=0,cnn_mmio_wdata=0,cnn_mmio_rdata;
 logic cnn_mmio_re=0,cnn_mmio_we=0;wire cnn_mmio_ready;
 wire [9:0] cnn_valid,cnn_write,cnn_byte;wire [319:0] cnn_addr,cnn_wdata;
 logic [9:0] cnn_ready=0,cnn_response=0;logic [319:0] cnn_rdata=0;
 wire cnn_cancel,busy,done,error;logic cnn_mem_fault=0;
 wire [9:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work;
 wire [9:0][9:0] unit_node;wire [10:0] completed_count;
 cnn_ees331 dut(.*);
 byte unsigned memory[65536];
 integer cycle=0,delay_left[10],macs=0,overlap=0;
 logic [9:0] pending=0,pwrite,pbyte;
 logic [31:0] paddr[10],pdata[10];
 integer seen[4];
 always_comb begin
  cnn_ready=0;
  for(integer u=0;u<10;u++)cnn_ready[u]=!pending[u] && !cnn_cancel && (cycle+u)%7!=0;
 end
 always @(posedge clk)begin
  cycle<=cycle+1;cnn_response<=0;
  if(!rst_n || cnn_cancel)pending<=0;
  else begin
   if($countones(operator_work[5:2])>1)overlap<=overlap+1;
   macs<=macs+$countones(operator_work[5:2]);
   for(integer u=0;u<10;u++)begin
    if(cnn_valid[u] && cnn_ready[u])begin
     if(pending[u])$fatal(1,"multiple requests/client");
     pending[u]<=1;paddr[u]<=cnn_addr[u*32+:32];pdata[u]<=cnn_wdata[u*32+:32];
     pwrite[u]<=cnn_write[u];pbyte[u]<=cnn_byte[u];delay_left[u]<=2+(cycle+u)%11;
    end
    if(pending[u])begin
     if(delay_left[u]>0)delay_left[u]<=delay_left[u]-1;
     else begin
      if(paddr[u]>=65536)$fatal(1,"address overflow");
      pending[u]<=0;cnn_response[u]<=1;
      if(pwrite[u])begin
       if(pbyte[u])memory[paddr[u]]<=pdata[u][7:0];
       else for(integer b=0;b<4;b++)memory[paddr[u]+b]<=pdata[u][b*8+:8];
       cnn_rdata[u*32+:32]<=0;
      end else if(pbyte[u])cnn_rdata[u*32+:32]<={{24{memory[paddr[u]][7]}},memory[paddr[u]]};
      else for(integer b=0;b<4;b++)cnn_rdata[u*32+b*8+:8]<=memory[paddr[u]+b];
     end
    end
   end
  end
 end
 task automatic wr(input logic [31:0] a,v);
  @(negedge clk);cnn_mmio_addr=a;cnn_mmio_wdata=v;cnn_mmio_we=1;
  @(negedge clk);cnn_mmio_we=0;cnn_mmio_addr=0;
 endtask
 task automatic rd(input logic [31:0] a,output logic [31:0] v);
  @(negedge clk);cnn_mmio_addr=a;cnn_mmio_re=1;#1;v=cnn_mmio_rdata;
  if(!cnn_mmio_ready)$fatal(1,"MMIO must be zero wait");
  @(negedge clk);cnn_mmio_re=0;cnn_mmio_addr=0;
 endtask
 task automatic configure(input bit bad_tag=0,input integer bad_lease=0);
  logic [31:0] words[20];
  for(integer w=0;w<20;w++)words[w]=0;
  // 1x1 convolution, 8 inputs / 8 outputs and 4x4 pixels. All UINT8=5+f,
  // all INT8 weights=-3. Produces 512 bytes (128 signed INT32 values).
  words[0]=5;words[2]=32'h80;words[6]=8;words[7]=4;words[8]=4;words[9]=8;words[10]=1;
  words[16]=32'h8001;words[19]=512;
  wr('h0c,bad_lease!=0?1:4);wr('h14,0);wr('h18,0);
  if(bad_lease!=0)begin
   // Two syntactically valid steps with an impossible lifetime plan.
   // Case1 prematurely releases owner0 but step1 still reads it.
   // Case2 retains owner0 until step1, which attempts to allocate that slot.
   words[16]=1;words[18]=bad_lease==2?32'h00010001:0;words[19]=0;
   for(integer w=0;w<20;w++)wr('h1c,words[w]);wr('h08,4);
   words[3]=1024;words[16]=bad_lease==1?32'h00018051:32'h00018001;
   words[18]=0;words[19]=512;wr('h14,1);
  end
  for(integer w=0;w<20;w++)wr('h1c,words[w]);wr('h08,4);
  for(integer f=0;f<(bad_lease!=0?1:4);f++)begin
   wr('h20,f);wr('h24,'h100+f*256);wr('h28,'h1000+f*4096);wr('h2c,100+f);wr('h08,8);
  end
  wr('h08,2);
  for(integer f=0;f<((bad_tag || bad_lease!=0)?1:4);f++)begin wr('h20,f);wr('h2c,bad_tag?999:100+f);wr('h08,16);end
 endtask
 initial begin:run
  logic [31:0] v,tag,addr,len,ep,status;
  integer received,timeout;logic signed [31:0] actual;
  for(integer a=0;a<65536;a++)memory[a]='ha5;
  for(integer a=0;a<64;a++)memory['h80+a]=8'hfd;
  for(integer f=0;f<4;f++)begin
   seen[f]=0;for(integer a=0;a<128;a++)memory['h100+f*256+a]=8'(5+f);
  end
  repeat(4)@(negedge clk);rst_n=1;repeat(3)@(negedge clk);
  rd(0,v);if(v!==32'h434e4e32)$fatal(1,"identity");
  // Invalid start cannot silently launch an empty graph.
  wr(8,2);repeat(3)@(negedge clk);rd('h3c,v);if(v!=3)$fatal(1,"invalid start not rejected");
  wr(8,1);repeat(3)@(negedge clk);rd('h54,ep);if(ep!=1)$fatal(1,"clear epoch");
  configure();received=0;timeout=0;
  while(received<4 && timeout<20000)begin
   rd(4,status);timeout++;
   if(status[3])begin rd('h3c,v);$fatal(1,"core error=%h",v);end
   if(status[5])begin
    rd('h30,tag);rd('h34,addr);rd('h38,len);
    if(tag<100 || tag>103 || seen[tag-100] || len!=512 || addr!='h1000+(tag-100)*4096)$fatal(1,"descriptor");
    // Result lease must survive a slow consumer and descriptor must stay stable.
    repeat(25)@(negedge clk);rd('h30,v);if(v!=tag)$fatal(1,"descriptor changed");
    for(integer a=0;a<512;a+=4)begin
     actual={memory[addr+a+3],memory[addr+a+2],memory[addr+a+1],memory[addr+a]};
     if(actual!=-24*(5+integer'(tag)-100))$fatal(1,"result value=%d tag=%d",actual,tag);
    end
    wr('h4c,tag);wr('h50,ep);wr(8,32);seen[tag-100]=1;received++;
   end
  end
  if(received!=4 || macs!=4096 || overlap==0)$fatal(1,"missing actual parallel work results=%0d macs=%0d overlap=%0d",received,macs,overlap);
  repeat(15)@(negedge clk);rd(4,status);if(!status[2] || status[1])$fatal(1,"batch not drained");
  // Stale ACK is rejected, not interpreted as an ACK for a future batch.
  wr('h50,ep-1);wr(8,32);rd('h3c,v);if(v!='h205)$fatal(1,"stale ACK accepted");
  wr(8,1);repeat(3)@(negedge clk);rd('h54,v);if(v!=ep+1)$fatal(1,"second epoch");
  // Delayed frame IDs must never expose the wrong input to the CNN.
  configure(1);repeat(8)@(negedge clk);rd('h3c,v);
  if(v!=4 || busy)$fatal(1,"wrong frame ID must reject and drain busy");
  wr(8,1);repeat(4)@(negedge clk);configure();
  // Above successful configure starts a new batch; injected memory fault must cancel.
  cnn_mem_fault=1;repeat(3)@(negedge clk);rd('h3c,v);if(v!='h100 || !cnn_cancel)$fatal(1,"memory fault cancellation");
  cnn_mem_fault=0;wr(8,1);repeat(4)@(negedge clk);rd(4,status);if(status[3] || !status[0])$fatal(1,"clear recovery");
  for(integer bad=1;bad<=2;bad++)begin
   configure(0,bad);timeout=0;
   do begin rd(4,status);timeout++;end while(!status[3] && timeout<10000);
   repeat(8)@(negedge clk);rd('h3c,v);
   if(v!=6 || busy || completed_count!=1)$fatal(1,"invalid lease plan must error6 and drain case=%0d err=%h completed=%0d",bad,v,completed_count);
   wr(8,1);repeat(4)@(negedge clk);rd(4,status);if(status[3] || !status[0])$fatal(1,"lease fault recovery");
  end
  $display("PASS compact_cnn_mmio_tb results=4 macs=4096 overlap_cycles=%0d epoch_errors_and_invalid_leases=PASS",overlap);
  $finish;
 end
 initial begin #100000000;$fatal(1,"watchdog");end
endmodule
