`timescale 1ns/1ps
// INT32 two's-complement wraparound is intentional.
module accumulator(input wire clk, rst_n, clear, load_bias, enable,
                   input wire signed [31:0] bias, product,
                   output reg signed [31:0] value);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) value <= 0;
        else if (clear) value <= 0;
        else if (load_bias) value <= bias;
        else if (enable) value <= value + product;
    end
endmodule
