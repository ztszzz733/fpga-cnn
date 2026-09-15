`timescale 1ns/1ps
// Small scratchpad. Contents are intentionally not reset: fill before use.
// Replace this primitive to add synchronous BRAM or a larger tiled buffer.
module sample_buffer #(parameter WIDTH=8, DEPTH=49, ADDR_WIDTH=6)(
    input wire clk, input wire we,
    input wire [ADDR_WIDTH-1:0] waddr, raddr,
    input wire signed [WIDTH-1:0] wdata,
    output wire signed [WIDTH-1:0] rdata
);
    reg signed [WIDTH-1:0] data [0:DEPTH-1];
    always @(posedge clk) if (we && waddr < DEPTH) data[waddr] <= wdata;
    assign rdata = (raddr < DEPTH) ? data[raddr] : {WIDTH{1'b0}};
endmodule
