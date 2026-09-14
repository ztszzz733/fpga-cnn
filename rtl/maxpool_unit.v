`timescale 1ns/1ps
// Stream four INT32 values, first=1 on the first sample of each 2x2 group.
// A single sample with first=1 also implements pooling bypass.
module maxpool_unit(input wire clk, rst_n, clear, valid, first,
                    input wire signed [31:0] value,
                    output reg signed [31:0] result);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) result <= 0;
        else if (clear) result <= 0;
        else if (valid && (first || value > result)) result <= value;
    end
endmodule
