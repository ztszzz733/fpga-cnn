`timescale 1ns/1ps
module tb_systolic_pe;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0,ce=1,load=0,av=0,bv=0;reg signed [7:0] a,b;
    reg signed [31:0] seed;wire signed [31:0] sum;wire [7:0] ao,bo;wire va,vb;
    integer i,j;reg signed [31:0] expected;
    systolic_pe dut(clk,rst_n,clear,ce,load,seed,a,b,av,bv,ao,bo,va,vb,sum);
    initial begin
        a=0;b=0;seed=0;@(negedge clk);rst_n=1;
        for(i=-128;i<128;i=i+1) for(j=-128;j<128;j=j+1) begin
            load=1;seed=32'h7ffffff0;@(negedge clk);load=0;a=i;b=j;av=1;bv=1;
            expected=32'h7ffffff0+i*j;@(negedge clk);
            if(sum!==expected || ao!==a || bo!==b || !va || !vb) $fatal(1,"signed product/wrap");
        end
        ce=0;a=0;b=0;repeat(3) @(negedge clk);if(sum!==expected) $fatal(1,"stall");
        clear=1;@(negedge clk);if(sum!==0 || va || vb) $fatal(1,"clear while paused");
        clear=0;ce=1;av=1;bv=0;load=0;@(negedge clk);if(sum!==0) $fatal(1,"invalid pair");
        $display("PASS tb_systolic_pe (65536 signed pairs, wrap, stall, clear)");$finish;
    end
endmodule
