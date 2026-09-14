`timescale 1ns/1ps
module tb_relu_unit;
    reg signed [31:0] value; reg enable;
    wire signed [31:0] result;
    relu_unit dut(value,enable,result);
    task check(input signed [31:0] v, input en, input signed [31:0] expected);
        value=v; enable=en; #1;
        if(result!==expected) $fatal(1,"ReLU %d -> %d expected %d",v,result,expected);
    endtask
    initial begin
        check(-9,1,0); check(0,1,0); check(123,1,123);
        check(32'sh80000000,1,0); check(32'sh7fffffff,1,32'sh7fffffff);
        check(-9,0,-9); check(32'sh80000000,0,32'sh80000000);
        $display("PASS tb_relu_unit"); $finish;
    end
endmodule
