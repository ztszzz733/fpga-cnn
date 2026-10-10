`timescale 1ns/1ps
module tb_neureka_bridge;
 import hci_package::*;
 reg clk=0;always #5 clk=~clk;reg rst_n=0,clear=0;
 hci_core_intf #(.DW(288),.UW(0),.IW(0),.EW(0),.EHW(0)) hci(.clk(clk));
 wire [8:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
 wire [287:0] cnn_addr,cnn_wdata,cnn_rdata;wire idle,cnn_mem_fault;
 int cycles=0;always @(posedge clk) cycles<=cycles+1;
 neureka_banked_bridge bridge(clk,rst_n,clear,hci,cnn_valid,cnn_write,cnn_byte,cnn_addr,cnn_wdata,cnn_ready,cnn_response,cnn_rdata,idle);
 datasram_banked #(.SRAM_SIZE(4096),.BANKS(4),.CLIENTS(9)) mem(
  .clk(clk),.rst_n(rst_n),.dmem_addr(32'h100),.dmem_wdata(32'b0),.dmem_wstrb(4'b0),.dmem_re(cycles%3!=0),.dmem_we(1'b0),.dmem_rdata(),
  .cnn_cancel(clear),.io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'b0),.io_mem_wdata(32'b0),.io_mem_be(4'b0),
  .io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error(),.*);
 reg [287:0] expected;
 task automatic transfer(input bit read_op,input logic [35:0] mask,input logic [287:0] data);
  @(negedge clk);hci.req=1;hci.wen=read_op;hci.add=32'h100;hci.be=mask;hci.data=data;
  do @(posedge clk);while(!hci.gnt);
  if(hci.r_valid) $fatal(1,"response before required one-cycle boundary");
  @(negedge clk);hci.req=0;
  @(posedge clk);
  if(!hci.r_valid) $fatal(1,"response not exactly one cycle after grant");
  if(read_op && hci.r_data!==expected) $fatal(1,"readback mismatch got=%h expected=%h",hci.r_data,expected);
  @(negedge clk);
 endtask
 initial begin
  hci.req=0;hci.wen=1;hci.add=0;hci.be=0;hci.data=0;hci.r_ready=1;
  hci.id=0;hci.user=0;hci.ecc=0;hci.ereq=0;hci.r_eready=1;
  for(int b=0;b<4;b++) for(int w=0;w<256;w++) mem.mem[b][w]=32'ha5a5a5a5;
  repeat(4) @(negedge clk);rst_n=1;expected={36{8'ha5}};
  transfer(1,0,0);
  for(int n=0;n<8;n++) begin
   reg [35:0] mask;reg [287:0] data;
   mask=n==0 ? 36'hfffffffff : n==1 ? 0 : 36'h123456789<<n;
   for(int b=0;b<36;b++) begin data[b*8+:8]=n*19+b;if(mask[b]) expected[b*8+:8]=n*19+b;end
   transfer(0,mask,data);transfer(1,0,0);
  end
  if(cnn_mem_fault) $fatal(1,"SRAM fault");
  $display("PASS tb_neureka_bridge: 17 transactions, partial-byte stores, bank contention, exact grant/response latency");$finish;
 end
 initial begin #100000;$fatal(1,"bridge timeout");end
endmodule
