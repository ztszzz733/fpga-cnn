`timescale 1ns/1ps
// Common final signed INT8 saturation. Scaling/rounding happens before this.
module requantize_unit(input wire signed [63:0] value,input wire [7:0] shift,
    output wire signed [7:0] result);
    wire signed [63:0] shifted=value >>> shift;
    assign result=shifted>127 ? 8'sd127 : (shifted< -128 ? -8'sd128 : shifted[7:0]);
endmodule
