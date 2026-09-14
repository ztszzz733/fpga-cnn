`timescale 1ns/1ps
module tb_top_smoke;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0; reg [31:0] addr=0,data=0; reg we=0,re=0;
    wire [31:0] result,ma,md,mr; wire ready,rd,wr,mready;
    cnn_accelerator_top dut(clk,rst_n,addr,data,we,re,result,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(4096,0) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    task write_reg(input [31:0] off,d);
        @(negedge clk); addr='h40000000+off;data=d;we=1;
        @(negedge clk); we=0;
    endtask
    integer i;
    initial begin
        if($test$plusargs("vcd")) begin
            $dumpfile("build/top_smoke.vcd");
            $dumpvars(0,dut);
        end
        for(i=0;i<4096;i=i+1) ram.bytes[i]='ha5;
        for(i=0;i<9;i=i+1) begin ram.bytes['h100+i]=i+1; ram.bytes['h200+i]=1; end
        for(i=0;i<4;i=i+1) ram.bytes['h300+i]=0;
        repeat(2) @(negedge clk); rst_n=1;
        write_reg(8,'h100);write_reg(12,'h401);write_reg(16,'h200);write_reg(20,'h300);
        write_reg(24,'h30003);write_reg(28,'h10001);write_reg(32,'h13);write_reg(0,1);
        @(negedge clk); addr='h40000004;re=1;#1;
        if(!result[0]) $fatal(1,"missing BUSY");
        while(!result[1] && !result[2]) begin @(negedge clk); #1; end
        if(result!==2 || ram.bytes['h401]!==45 || ram.bytes['h400]!=='ha5 || ram.bytes['h402]!=='ha5)
            $fatal(1,"smoke got status=%h output=%d",result,ram.bytes['h401]);
        $display("PASS tb_top_smoke");$finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
