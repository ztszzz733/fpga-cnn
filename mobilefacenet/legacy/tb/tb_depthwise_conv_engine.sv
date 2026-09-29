`timescale 1ns/1ps
module tb_depthwise_conv_engine;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0,start=0,valid=0;reg [3:0] k=3;
    reg signed [31:0] bias=0;reg signed [7:0] a=0,b=0;
    wire ready,busy,done,error;wire signed [31:0] result;
    depthwise_conv_engine dut(clk,rst_n,clear,start,k,bias,valid,ready,a,b,busy,done,error,result);
    task channel(input integer kernel,v,w,bs);
        integer i;
        @(negedge clk);k=kernel;bias=bs;start=1;
        @(negedge clk);start=0;a=v;b=w;
        for(i=0;i<kernel*kernel;i=i+1) begin
            valid=0;@(negedge clk);valid=1;
            if(!ready) $fatal(1,"ready");
            @(negedge clk);
            if(done && i!=kernel*kernel-1) $fatal(1,"early done");
        end
        valid=0;
        if(done!==1 || result!==kernel*kernel*v*w+bs) $fatal(1,"channel result %d",result);
        @(negedge clk);
    endtask
    initial begin
        repeat(2) @(negedge clk);rst_n=1;
        channel(3,2,3,1); // 55
        channel(3,-4,2,-7); // -79; must not include the previous channel's 55
        channel(7,-128,-128,0); // 802816
        k=1;start=1;@(negedge clk);start=0;if(error!==1) $fatal(1,"invalid kernel");
        $display("PASS tb_depthwise_conv_engine");$finish;
    end
    initial begin #100000; $fatal(1,"timeout");end
endmodule
