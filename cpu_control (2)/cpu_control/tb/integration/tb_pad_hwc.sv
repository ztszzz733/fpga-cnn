`timescale 1ns/1ps
module tb_pad_hwc;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0;
 logic [31:0] source=64,destination=512,width=3,height=2,channels=3;
 logic [7:0] zero_point=128;
 wire busy,done,error,valid,write,byte_access;
 wire [31:0] addr,wdata;logic ready,response=0;logic [31:0] rdata=0;
 reg [7:0] mem[2048];integer cycles=0,delay_left=0,paddr,pdata,pbytes;
 logic pending=0,pwrite;integer checked=0;
 pad_hwc_engine dut(.*);
 assign ready=!pending && cycles%5!=2;
 always @(posedge clk)begin
  cycles<=cycles+1;response<=0;
  if(clear)begin pending<=0;response<=0;end
  else if(pending)begin
   if(delay_left==0)begin
    if(pwrite)for(integer b=0;b<pbytes;b++)mem[paddr+b]<=pdata>>(8*b);
    else begin rdata<=0;for(integer b=0;b<pbytes;b++)rdata[b*8+:8]<=mem[paddr+b];end
    response<=1;pending<=0;
   end else delay_left<=delay_left-1;
  end else if(valid && ready)begin
   if(addr>=2048)$fatal(1,"outside SRAM");
   pending<=1;paddr<=addr;pdata<=wdata;pbytes<=byte_access ? 1:4;pwrite<=write;delay_left<=cycles%3;
  end
  if(cycles>10000)$fatal(1,"watchdog");
 end
 initial begin
  for(integer i=0;i<2048;i++)mem[i]=8'ha5;
  repeat(4)@(negedge clk);rst_n=1;
  for(integer mode=0;mode<2;mode++)begin
   channels=mode==0 ? 3:8;zero_point=mode==0 ? 128:33;
   for(integer i=0;i<width*height*channels;i++)mem[source+i]=8'(i*7+19);
   @(negedge clk);start=1;@(negedge clk);start=0;
   wait(done);@(negedge clk);
   if(error || pending)$fatal(1,"bad completion");
   for(integer y=0;y<height+2;y++)for(integer x=0;x<width+2;x++)for(integer c=0;c<channels;c++)begin
    if(mem[destination+(y*(width+2)+x)*channels+c] !==
       ((x==0 || x==width+1 || y==0 || y==height+1) ? zero_point:8'((((y-1)*width+x-1)*channels+c)*7+19)))$fatal(1,"padding mismatch");
    checked++;
   end
   if(mem[destination-1]!==8'ha5 || mem[destination+(width+2)*(height+2)*channels]!==8'ha5)$fatal(1,"guard modified");
   repeat(3)@(negedge clk);
  end
  width=0;start=1;@(negedge clk);start=0;if(!error)$fatal(1,"bad width not rejected");
  @(negedge clk);width=3;start=1;@(negedge clk);start=0;repeat(7)@(negedge clk);clear=1;
  @(negedge clk);if(busy || valid)$fatal(1,"clear failed");clear=0;
  $display("PASS pad_hwc checked=%0d byte/word, stalls, delayed response, invalid width, clear",checked);$finish;
 end
endmodule
