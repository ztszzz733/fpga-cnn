`timescale 1ns/1ps
module tb_add_unit;
    reg signed [7:0] a,b;wire signed [31:0] y;integer i,j;
    add_unit dut(a,b,y);
    initial begin
        for(i=-128;i<=127;i=i+1) for(j=-128;j<=127;j=j+1) begin
            a=i;b=j;#1;if(y!==i+j) $fatal(1,"ADD overflow/sign %d %d",i,j);
        end
        $display("PASS tb_add_unit");$finish;
    end
endmodule
