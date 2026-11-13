`timescale 1ns/1ps
// Normal mode: skewed edges, A east/B south, output stationary.
// DW mode: independent inputs to all 64 PEs, one weight broadcast per row.
// Results are flattened row-major, cell (r,c) at (r*8+c)*32.
module systolic_array8(
    input wire clk,rst_n,clear,ce,load,dw,
    input wire [2047:0] initial_sums,
    input wire [63:0] a_edge,b_edge,input wire [7:0] a_valid,b_valid,
    input wire [511:0] dw_inputs,input wire [63:0] dw_weights,dw_valid,
    output wire [2047:0] sums
);
    wire [7:0] a[0:7][0:8],b[0:8][0:7];
    wire av[0:7][0:8],bv[0:8][0:7];
    genvar r,c;
    generate for(r=0;r<8;r=r+1) begin:rows
        assign a[r][0]=a_edge[r*8+:8];assign av[r][0]=a_valid[r];
        assign b[0][r]=b_edge[r*8+:8];assign bv[0][r]=b_valid[r];
        for(c=0;c<8;c=c+1) begin:cols
            systolic_pe pe(clk,rst_n,clear,ce,load,initial_sums[(r*8+c)*32+:32],
                dw ? dw_inputs[(r*8+c)*8+:8] : a[r][c],
                dw ? dw_weights[r*8+:8] : b[r][c],
                dw ? dw_valid[r*8+c] : av[r][c],dw ? dw_valid[r*8+c] : bv[r][c],
                a[r][c+1],b[r+1][c],av[r][c+1],bv[r+1][c],sums[(r*8+c)*32+:32]);
        end
    end endgenerate
endmodule
