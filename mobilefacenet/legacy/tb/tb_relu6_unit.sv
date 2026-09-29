`timescale 1ns/1ps
module tb_relu6_unit;
    reg signed [31:0] v;reg r,r6;wire signed [31:0] y;
    relu6_unit #(.RELU6_MAX(96)) dut(v,r,r6,y);
    task check(input integer value,input a,b,input integer expected);
        v=value;r=a;r6=b;#1;if(y!==expected) $fatal(1,"relu got %d expected %d",y,expected);
    endtask
    initial begin
        check(-128,0,1,0);check(0,0,1,0);check(95,0,1,95);check(96,0,1,96);
        check(97,0,1,96);check(2147483647,0,1,96);check(-5,0,0,-5);
        check(-5,1,0,0);check(120,1,0,120);check(120,1,1,96);
        $display("PASS tb_relu6_unit");$finish;
    end
endmodule
