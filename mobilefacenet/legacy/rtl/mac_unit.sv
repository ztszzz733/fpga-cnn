`timescale 1ns/1ps
module mac_unit(input wire signed [7:0] input_value, weight_value,
                output wire signed [31:0] product);
    wire signed [15:0] product16 = input_value * weight_value;
    assign product = {{16{product16[15]}}, product16};
endmodule
