`timescale 1ns/1ps
module tb_quantizer;
    reg signed [31:0] v;reg [7:0] s;wire signed [31:0] shifted;wire signed [7:0] y;
    quantizer dut(v,s,shifted,y);
    task check(input integer value,shift,expected);
        v=value;s=shift;#1;if(y!==expected || shifted!==($signed(v)>>>s)) $fatal(1,"quant");
    endtask
    initial begin
        check(-256,0,-128);check(254,0,127);check(-128,0,-128);check(127,0,127);
        check(-3,1,-2);check(255,1,127);check(2147483647,31,0);
        check(-2147483648,31,-1);check(-5,255,-1);check(9,255,0);
        $display("PASS tb_quantizer");$finish;
    end
endmodule
