`timescale 1ns/1ps
module output_buffer(input wire clk, rst_n, clear, we,
                     input wire signed [7:0] wdata,
                     output reg signed [7:0] rdata);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) rdata <= 0;
        else if (clear) rdata <= 0;
        else if (we) rdata <= wdata;
    end
endmodule
