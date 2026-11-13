`timescale 1ns/1ps
module tb_shared_array;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0;reg [1:0] allocated=3,ce=3,ctx_clear=0,start=0,keep=0,mode=0;
    reg [3:0] depth=3;reg awe=0,bwe=0,biaswe=0;
    reg [2:0] rr=0,cc=0,kk=0;reg signed [7:0] av0=0,av1=0;
    wire [1:0] busy,done,ace,load,dw;wire [4095:0] seeds;
    wire [127:0] ae,be,dww,dwv;wire [15:0] av,bv;wire [1023:0] dwi;
    wire [2047:0] sums0,sums1;wire [63:0] fire;wire [7:0] mask0,mask1;
    systolic_tile_driver d0(clk,rst_n,clear || ctx_clear[0],ce[0],start[0],keep[0],mode[0],4'd2,4'd8,depth,
        awe,bwe,biaswe,rr,cc,kk,av0,32'sd11,busy[0],done[0],ace[0],load[0],dw[0],seeds[0+:2048],
        ae[0+:64],be[0+:64],dww[0+:64],dwv[0+:64],av[0+:8],bv[0+:8],dwi[0+:512]);
    systolic_tile_driver d1(clk,rst_n,clear || ctx_clear[1],ce[1],start[1],keep[1],mode[1],4'd6,4'd8,depth,
        awe,bwe,biaswe,rr,cc,kk,av1,-32'sd9,busy[1],done[1],ace[1],load[1],dw[1],seeds[2048+:2048],
        ae[64+:64],be[64+:64],dww[64+:64],dwv[64+:64],av[8+:8],bv[8+:8],dwi[512+:512]);
    systolic_shared_array8 dut(clk,rst_n,clear,allocated,3'd0,3'd2,4'd2,4'd6,ctx_clear,ace,load,dw,
        seeds,ae,be,dww,dwv,av,bv,dwi,sums0,sums1,fire,mask0,mask1);
    integer r,c,k,round,value0,value1,overlap=0;reg [1:0] seen;
    reg signed [31:0] expected0[0:15],expected1[0:47];reg [2047:0] frozen;
    always @(posedge clk) if(rst_n) begin
        if(mask0 & mask1) $fatal(1,"PE ownership overlaps");
        if((|fire[15:0]) && (|fire[63:16])) overlap=overlap+1;
    end
    task run_and_check(input integer pause_one);
        @(negedge clk);start=3;@(negedge clk);start=0;seen=0;
        if(pause_one) begin
            repeat(3) @(negedge clk);ce[0]=0;frozen=sums0;
            repeat(5) begin @(negedge clk);if(sums0!==frozen) $fatal(1,"partition0 did not freeze");end
            ce[0]=1;
        end
        while(seen!=3) begin @(negedge clk);seen=seen | done;end
        for(r=0;r<2;r=r+1) for(c=0;c<8;c=c+1)
            if($signed(sums0[(r*8+c)*32+:32])!==expected0[r*8+c]) $fatal(1,"partition0 result %0d,%0d",r,c);
        for(r=0;r<6;r=r+1) for(c=0;c<8;c=c+1)
            if($signed(sums1[(r*8+c)*32+:32])!==expected1[r*8+c]) $fatal(1,"partition1 result %0d,%0d",r,c);
    endtask
    initial begin
        repeat(2) @(negedge clk);rst_n=1;
        for(round=0;round<2;round=round+1) begin
            // Round0 normal x normal; round1 normal x DW, after clearing.
            clear=1;@(negedge clk);clear=0;mode=round ? 2'b10 : 2'b00;keep=0;
            for(r=0;r<16;r=r+1) expected0[r]=11;
            for(r=0;r<48;r=r+1) expected1[r]=-9;
            for(r=0;r<6;r=r+1) begin rr=r;biaswe=1;@(negedge clk);end
            biaswe=0;
            for(r=0;r<6;r=r+1) for(k=0;k<3;k=k+1) begin
                rr=r;kk=k;awe=1;av0=r+k-2;av1=2*r-k-3;@(negedge clk);
            end
            awe=0;
            for(r=0;r<6;r=r+1) for(c=0;c<8;c=c+1) for(k=0;k<3;k=k+1) begin
                rr=r;cc=c;kk=k;bwe=1;av0=c-k+1;av1=c+k+r-4;@(negedge clk);
            end
            bwe=0;
            for(r=0;r<2;r=r+1) for(c=0;c<8;c=c+1) for(k=0;k<3;k=k+1)
                expected0[r*8+c]=expected0[r*8+c]+(r+k-2)*(c-k+1);
            for(r=0;r<6;r=r+1) for(c=0;c<8;c=c+1) for(k=0;k<3;k=k+1)
                expected1[r*8+c]=expected1[r*8+c]+(2*r-k-3)*(c+k+(round ? r : 0)-4);
            run_and_check(0);
            // Reduction continuation keeps sums in the same physical PEs.
            keep=3;
            for(r=0;r<16;r=r+1) expected0[r]=2*expected0[r]-11;
            for(r=0;r<48;r=r+1) expected1[r]=2*expected1[r]+9;
            run_and_check(round==0);
            @(negedge clk);frozen=sums1;ctx_clear=1;@(negedge clk);ctx_clear=0;
            if(sums0!==0 || sums1!==frozen) $fatal(1,"per-context clear leaked across boundary");
        end
        if(overlap==0) $fatal(1,"no simultaneous MACs observed");
        $display("PASS tb_shared_array (256 INT32 comparisons, 2x8+6x8, normal/DW, partial sums, independent stall/reset; overlapping cycles=%0d)",overlap);
        $finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
