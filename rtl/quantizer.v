`timescale 1ns/1ps
// No rounding: arithmetic shift, then saturate. ReLU-off uses signed INT8.
module quantizer(input wire signed [31:0] value,
                 input wire [7:0] quant_shift, input wire relu_enable,
                 output reg signed [7:0] result);
    wire signed [31:0] shifted = value >>> quant_shift;
    always @* begin
        if (shifted > 32'sd127) result = 8'sd127;
        else if (relu_enable && shifted < 0) result = 0;
        else if (shifted < -32'sd128) result = -8'sd128;
        else result = shifted[7:0];
    end
endmodule
