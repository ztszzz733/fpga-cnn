`timescale 1ns/1ps
module tb_quantizer;
    reg signed [31:0] value; reg [7:0] shift; reg relu;
    wire signed [7:0] result;
    quantizer dut(value,shift,relu,result);
    task check(input signed [31:0] v,input [7:0] s,input en,input signed [7:0] expected);
        value=v; shift=s; relu=en; #1;
        if(result!==expected) $fatal(1,"quant %d >>> %d got %d expected %d",v,s,result,expected);
    endtask
    initial begin
        check(127,0,0,127); check(128,0,0,127); check(-128,0,0,-128);
        check(-129,0,0,-128); check(-1,0,1,0); check(255,1,1,127);
        check(-3,1,0,-2); check(32'sh7fffffff,31,0,0);
        check(32'sh80000000,31,0,-1); check(-1,255,0,-1); check(17,255,1,0);
        $display("PASS tb_quantizer"); $finish;
    end
endmodule
