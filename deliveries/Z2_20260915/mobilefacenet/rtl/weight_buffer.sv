`timescale 1ns/1ps
module weight_buffer #(parameter DEPTH=49, ADDR_WIDTH=6)(
    input wire clk, we,
    input wire [ADDR_WIDTH-1:0] waddr, raddr,
    input wire signed [7:0] wdata, output wire signed [7:0] rdata
);
    sample_buffer #(8,DEPTH,ADDR_WIDTH) storage(clk,we,waddr,raddr,wdata,rdata);
endmodule
