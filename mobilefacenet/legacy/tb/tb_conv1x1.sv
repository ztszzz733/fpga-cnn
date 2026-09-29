`timescale 1ns/1ps
module tb_conv1x1;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,clear=0,start=0,valid=0; reg [3:0] k=3;
    reg [15:0] ci=2; reg signed [31:0] bias=-5;
    reg signed [7:0] a=0,b=0; wire ready,busy,done,error;
    wire signed [31:0] result;
    conv_engine dut(clk,rst_n,clear,start,k,ci,bias,valid,ready,a,b,busy,done,error,result);
    task run(input integer channels,input integer kernel);
        integer i,expected;
        @(negedge clk); ci=channels;k=kernel;start=1;expected=-5;
        @(negedge clk); start=0;
        for(i=0;i<channels*kernel*kernel;i=i+1) begin
            if(i%3==0) begin valid=0; repeat(2) @(negedge clk); end
            a=i-9;b=(i%5)-2;valid=1;expected=expected+(i-9)*((i%5)-2);
            if(!ready) $fatal(1,"not ready");
            @(negedge clk);
            if(i<channels*kernel*kernel-1 && done) $fatal(1,"early done");
        end
        valid=0;
        if(done!==1 || busy || result!==expected) $fatal(1,"dot got %d expected %d",result,expected);
        @(negedge clk); if(done) $fatal(1,"done not pulse");
    endtask
    initial begin
        repeat(2) @(negedge clk);rst_n=1;
        run(1,1); run(3,1); run(16,1);
        k=7;start=1;@(negedge clk);start=0;
        if(error!==1 || busy) $fatal(1,"invalid kernel");
        $display("PASS tb_conv1x1");$finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
