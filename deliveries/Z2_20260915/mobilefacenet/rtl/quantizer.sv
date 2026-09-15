`timescale 1ns/1ps
module quantizer(input wire signed [31:0] value,input wire [7:0] quant_shift,
                 output wire signed [31:0] shifted,
                 output reg signed [7:0] result);
    assign shifted=value >>> quant_shift;
    always @* begin
        if(shifted>127) result=127;
        else if(shifted< -128) result=-128;
        else result=shifted[7:0];
    end
endmodule
