`timescale 1ns/1ps
// Banked tile buffers: A[row][k] (64B), B[row][column][k] (512B).
// Normal mode uses only B[0][column][k]. DW mode uses every row bank.
// Buffers may be written only while idle. start snapshots dimensions/mode.
// accumulate=0 initializes all cells from per-row bias; =1 preserves sums.
// Normal tile takes depth+14 enabled RUN cycles, DW tile depth cycles.
module systolic_tile(
    input wire clk,rst_n,clear,ce,start,accumulate,dw,
    input wire [3:0] rows,cols,depth,
    input wire a_we,b_we,bias_we,input wire [2:0] wr_row,wr_col,wr_k,
    input wire signed [7:0] wr_value,input wire signed [31:0] wr_bias,
    output wire busy,output reg done,output wire [2047:0] sums
);
    reg signed [7:0] a[0:63],b[0:511];reg signed [31:0] bias[0:7];
    reg [1:0] state;reg [5:0] tick;reg [3:0] nr,nc,nk;reg mode,keep;
    reg [63:0] ae,be,dww,dwv;reg [7:0] av,bv;reg [511:0] dwi;reg [2047:0] seeds;
    integer r,c,t;
    assign busy=state!=0;
    wire array_ce=ce && (state==1 || state==2);
    always @* begin
        ae=0;be=0;av=0;bv=0;dww=0;dwv=0;dwi=0;seeds=0;
        for(r=0;r<8;r=r+1) begin
            t=$signed({1'b0,tick})-r;
            if(state==2 && r<nr && t>=0 && t<nk) begin ae[r*8+:8]=a[r*8+t];av[r]=1;end
            if(state==2 && r<nc && t>=0 && t<nk) begin be[r*8+:8]=b[r*8+t];bv[r]=1;end
            if(state==2 && tick<nk) dww[r*8+:8]=a[r*8+tick];
            for(c=0;c<8;c=c+1) begin
                seeds[(r*8+c)*32+:32]=bias[r];
                if(state==2 && tick<nk && r<nr && c<nc) begin
                    dwi[(r*8+c)*8+:8]=b[(r*8+c)*8+tick];dwv[r*8+c]=1;
                end
            end
        end
    end
    systolic_array8 array(clk,rst_n,clear,array_ce,state==1 && !keep,mode,seeds,ae,be,av,bv,dwi,dww,dwv,sums);
    always @(posedge clk) if(ce && !busy && !clear) begin
        if(a_we) a[{wr_row,wr_k}]<=wr_value;
        if(b_we) b[{wr_row,wr_col,wr_k}]<=wr_value;
        if(bias_we) bias[wr_row]<=wr_bias;
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin state<=0;done<=0;tick<=0;nr<=0;nc<=0;nk<=0;mode<=0;keep<=0;end
        else if(clear) begin state<=0;done<=0;tick<=0;end
        else if(ce) begin
            done<=0;
            case(state)
                0:if(start) begin nr<=rows;nc<=cols;nk<=depth;mode<=dw;keep<=accumulate;state<=1;tick<=0;end
                1:state<=2;
                2:if(tick==(mode ? nk-1 : nk+13)) begin done<=1;state<=0;end else tick<=tick+1'b1;
                default:state<=0;
            endcase
        end
    end
endmodule
