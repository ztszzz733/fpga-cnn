`timescale 1ns/1ps
// Inputs are scaled INT8 branches, bounded to <2^39 each by the engine.
module residual_add_unit(input wire signed [63:0] a,b,output wire signed [63:0] result);
    assign result=a+b;
endmodule
