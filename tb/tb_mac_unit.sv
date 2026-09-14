`timescale 1ns/1ps
module tb_mac_unit;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,clear=0,load=0,en=0;
    reg signed [7:0] a=0,b=0;
    reg signed [31:0] bias=0;
    wire signed [31:0] prod,acc;
    mac_unit dut(a,b,prod);
    accumulator acc_dut(clk,rst_n,clear,load,en,bias,prod,acc);
    integer i,j;
    initial begin
        // Exhaust every INT8 product, including -128 * -128.
        for(i=-128;i<128;i=i+1) for(j=-128;j<128;j=j+1) begin
            a=i; b=j; #1; if(prod!==i*j) $fatal(1,"signed multiply");
        end
        @(negedge clk); rst_n=1; bias=-10; load=1;
        @(negedge clk); load=0; en=1; a=-3; b=4;
        @(negedge clk); if(acc!==-22) $fatal(1,"acc expected -22 got %d",acc);
        en=0; @(negedge clk); if(acc!==-22) $fatal(1,"hold");
        bias=32'sh7fffffff; load=1;
        @(negedge clk); load=0; en=1; a=1; b=1;
        @(negedge clk); if(acc!==32'sh80000000) $fatal(1,"wrap");
        clear=1; @(negedge clk); if(acc!==0) $fatal(1,"clear");
        $display("PASS tb_mac_unit"); $finish;
    end
endmodule
