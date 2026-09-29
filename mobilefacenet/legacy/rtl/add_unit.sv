`timescale 1ns/1ps
// Inputs must share the same quantization scale and zero point (zero).
// Widen BEFORE adding; saturation/shift are downstream.
module add_unit(input wire signed [7:0] input_a,input_b,
                output wire signed [31:0] result);
    assign result={{24{input_a[7]}},input_a}+{{24{input_b[7]}},input_b};
endmodule
