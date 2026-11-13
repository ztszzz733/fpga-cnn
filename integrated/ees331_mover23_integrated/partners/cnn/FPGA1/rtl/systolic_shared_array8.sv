`timescale 1ns/1ps
// One physical 8x8 array, two independently clock-enabled contiguous row regions.
// Local A propagates east. Local B is injected at each region's TOP boundary,
// then propagates south; it never crosses a task boundary. DW feeds each PE.
// Region ownership is held from task dispatch through final RAM write completion.
module systolic_shared_array8(
    input wire clk,rst_n,clear,input wire [1:0] allocated,
    input wire [2:0] base0,base1,input wire [3:0] rows0,rows1,
    input wire [1:0] ctx_clear,ce,load,dw,
    input wire [4095:0] initial_sums,input wire [127:0] a_edge,b_edge,dw_weights,dw_valid,
    input wire [15:0] a_valid,b_valid,input wire [1023:0] dw_inputs,
    output reg [2047:0] sums0,sums1,output wire [63:0] fire_map,
    output wire [7:0] mask0,mask1
);
    wire [7:0] a[0:7][0:8],b[0:8][0:7];
    wire av[0:7][0:8],bv[0:8][0:7];
    wire [2047:0] physical_sums;
    genvar r,c;
    generate for(r=0;r<8;r=r+1) begin:rows
        assign mask0[r]=allocated[0] && r>=base0 && r<({1'b0,base0}+rows0);
        assign mask1[r]=allocated[1] && r>=base1 && r<({1'b0,base1}+rows1);
        wire owned=mask0[r] || mask1[r];
        wire who=mask1[r];
        wire [3:0] local_row=r-(who ? base1 : base0);
        wire row_ce=owned && ce[who];
        wire row_load=owned && load[who];
        wire row_clear=clear || (owned && ctx_clear[who]);
        assign a[r][0]=a_edge[who*64+local_row*8+:8];
        assign av[r][0]=owned && a_valid[who*8+local_row];
        for(c=0;c<8;c=c+1) begin:cols
            wire [7:0] normal_b;
            wire normal_bv;
            if(r==0) begin
                assign normal_b=b_edge[who*64+c*8+:8];
                assign normal_bv=b_valid[who*8+c];
            end else begin
                assign normal_b=local_row==0 ? b_edge[who*64+c*8+:8] : b[r][c];
                assign normal_bv=local_row==0 ? b_valid[who*8+c] : bv[r][c];
            end
            wire pe_av=dw[who] ? dw_valid[who*64+local_row*8+c] : av[r][c];
            wire pe_bv=dw[who] ? dw_valid[who*64+local_row*8+c] : normal_bv;
            assign fire_map[r*8+c]=row_ce && !row_load && !row_clear && pe_av && pe_bv;
            systolic_pe pe(clk,rst_n,row_clear,row_ce,row_load,
                initial_sums[who*2048+(local_row*8+c)*32+:32],
                dw[who] ? dw_inputs[who*512+(local_row*8+c)*8+:8] : a[r][c],
                dw[who] ? dw_weights[who*64+local_row*8+:8] : normal_b,
                pe_av,pe_bv,a[r][c+1],b[r+1][c],av[r][c+1],bv[r+1][c],
                physical_sums[(r*8+c)*32+:32]);
        end
    end endgenerate
    integer rr,cc;
    always @* begin
        sums0=0;sums1=0;
        for(rr=0;rr<8;rr=rr+1) for(cc=0;cc<8;cc=cc+1) begin
            if(allocated[0] && rr<rows0 && base0+rr<8)
                sums0[(rr*8+cc)*32+:32]=physical_sums[((base0+rr)*8+cc)*32+:32];
            if(allocated[1] && rr<rows1 && base1+rr<8)
                sums1[(rr*8+cc)*32+:32]=physical_sums[((base1+rr)*8+cc)*32+:32];
        end
    end
endmodule
