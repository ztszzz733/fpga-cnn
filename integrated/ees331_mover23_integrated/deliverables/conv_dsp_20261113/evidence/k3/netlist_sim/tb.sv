`timescale 1ns/1ps
module tb_conv_dsp_netlist;
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0,clear=0,start=0,depthwise=0;
 reg [31:0] input_base=1024,weight_base=16384,output_base=32768;
 reg [31:0] width=5,height=5,in_channels=3,out_channels=3,stride=1;
 wire busy,done,error,valid,write,byte_access,mac_fire;
 wire [31:0] addr,wdata,input_reads,weight_reads,mac_count;wire[3:0] phase;
 reg ready=0,response=0;reg[31:0]rdata=0;
`ifdef K3
 localparam KERNEL=3;
 resource_k3 dut(.*);
`else
 localparam KERNEL=1;
 resource_pw8 dut(.*);
`endif
 reg[7:0] memory[0:65535],expected[0:32767];
 reg seen[0:32767];integer cycle=0,delay_left=0,paddr=0,pbytes=0,pdata=0,written=0,output_bytes=0;
 reg pending=0,pwrite=0,checking=0;
 integer test_count=0;
 always @(negedge clk)ready=checking && !pending && cycle%5!=2;
 always @(posedge clk)begin
  cycle<=cycle+1;response<=0;
  if(!rst_n || clear)begin pending<=0;response<=0;end
  else if(pending)begin
   if(delay_left==0)begin
    if(pwrite)begin
     for(integer b=0;b<pbytes;b++)begin
      if(seen[paddr-output_base+b])$fatal(1,"DSP netlist duplicate output");
      if((8'(pdata>>(8*b)))!==expected[paddr-output_base+b])$fatal(1,"DSP netlist numeric mismatch addr=%h got=%h exp=%h",paddr+b,8'(pdata>>(8*b)),expected[paddr-output_base+b]);
      memory[paddr+b]<=pdata>>(8*b);seen[paddr-output_base+b]<=1;
     end
     written<=written+pbytes;
    end else begin
     rdata<=0;for(integer b=0;b<pbytes;b++)rdata[b*8+:8]<=memory[paddr+b];
    end
    pending<=0;response<=1;
   end else delay_left<=delay_left-1;
  end else if(checking && valid && ready)begin
   paddr<=addr;pdata<=wdata;pbytes<=byte_access?1:4;pwrite<=write;pending<=1;delay_left<=cycle%3;
   if(!byte_access && addr[1:0]!=0)$fatal(1,"DSP netlist unaligned word");
   if(write)begin
    if(addr<output_base || addr+(byte_access?1:4)>output_base+output_bytes)$fatal(1,"DSP netlist output overrun");
   end else if(!((addr>=input_base && addr+(byte_access?1:4)<=input_base+width*height*in_channels) ||
                 (addr>=weight_base && addr+(byte_access?1:4)<=weight_base+out_channels*KERNEL*KERNEL*(depthwise?1:in_channels))))$fatal(1,"DSP netlist read overrun");
  end
  if(checking && error)$fatal(1,"DSP netlist DUT error");
  if(cycle>200000)$fatal(1,"DSP netlist watchdog");
 end
 task run_case(input integer ww,hh,ci,co,st,dw);
  integer ow,oh,wi,ii,signed_weight,sum,at;
  begin
   checking=0;rst_n=0;start=0;repeat(4)@(negedge clk);
   width=ww;height=hh;in_channels=ci;out_channels=co;stride=st;depthwise=dw;
   ow=(ww-KERNEL)/st+1;oh=(hh-KERNEL)/st+1;output_bytes=ow*oh*co*4;
   for(integer i=0;i<65536;i++)memory[i]=8'ha5;
   for(integer i=0;i<32768;i++)begin expected[i]=0;seen[i]=0;end
   for(integer i=0;i<ww*hh*ci;i++)memory[input_base+i]=8'((i%4==0)?255:((i%4==1)?128:((i*73+19)%256)));
   for(integer i=0;i<co*KERNEL*KERNEL*(dw?1:ci);i++)memory[weight_base+i]=8'((i%4==0)?128:((i%4==1)?127:((i*37+7)%256)));
   at=0;
   for(integer y=0;y<oh;y++)for(integer x=0;x<ow;x++)for(integer o=0;o<co;o++)begin
    sum=0;
    for(integer ky=0;ky<KERNEL;ky++)for(integer kx=0;kx<KERNEL;kx++)for(integer c=0;c<(dw?1:ci);c++)begin
     wi=((o*KERNEL+ky)*KERNEL+kx)*(dw?1:ci)+c;
     ii=(((y*st+ky)*ww+x*st+kx)*ci)+(dw?o:c);
     signed_weight=memory[weight_base+wi];if(signed_weight>=128)signed_weight=signed_weight-256;
     sum=sum+integer'(memory[input_base+ii])*signed_weight;
    end
    for(integer b=0;b<4;b++)expected[at+b]=8'(sum>>(8*b));at=at+4;
   end
   written=0;pending=0;rst_n=1;checking=1;repeat(3)@(negedge clk);start=1;@(negedge clk);start=0;
   wait(done);@(negedge clk);
   if(pending || written!=output_bytes)$fatal(1,"DSP netlist premature completion written=%0d expected=%0d",written,output_bytes);
   if(mac_count!=ow*oh*co*KERNEL*KERNEL*(dw?1:ci))$fatal(1,"DSP netlist MAC count");
   for(integer i=1;i<=16;i++)if(memory[output_base-i]!==8'ha5 || memory[output_base+output_bytes+i-1]!==8'ha5)$fatal(1,"DSP netlist guard");
   test_count=test_count+1;$display("DSP_NETLIST_CASE_PASS case=%0d bytes=%0d macs=%0d",test_count,output_bytes,mac_count);
   checking=0;repeat(3)@(negedge clk);
  end
 endtask
 initial begin
  // Allow the vendor global reset to release before functional reset tests.
  #200;
`ifdef K3
  run_case(5,4,3,3,1,0);run_case(5,5,3,3,1,1);run_case(6,5,5,3,2,0);
`else
  run_case(5,3,5,3,1,0);run_case(11,9,64,17,1,0);run_case(1,1,512,1,1,0);
`endif
  $display("CONV_DSP_NETLIST_PASS cases=%0d",test_count);$finish;
 end
endmodule
