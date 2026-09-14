`timescale 1ns/1ps
module tb_maxpool_unit;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,clear=0,valid=0,first=0;
    reg signed [31:0] value=0; wire signed [31:0] result;
    maxpool_unit dut(clk,rst_n,clear,valid,first,value,result);
    task put(input signed [31:0] v,input f,input signed [31:0] exp);
        @(negedge clk); valid=1; value=v; first=f;
        @(negedge clk); valid=0;
        if(result!==exp) $fatal(1,"maxpool got %d expected %d",result,exp);
    endtask
    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        put(-9,1,-9); put(-3,0,-3); put(-20,0,-3); put(-4,0,-3);
        put(2,1,2); put(99,0,99); put(99,0,99); put(8,0,99);
        put(32'sh80000000,1,32'sh80000000); put(32'sh7fffffff,0,32'sh7fffffff);
        @(negedge clk); clear=1; @(negedge clk);
        if(result!==0) $fatal(1,"clear");
        $display("PASS tb_maxpool_unit"); $finish;
    end
endmodule
