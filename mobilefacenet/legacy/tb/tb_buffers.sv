`timescale 1ns/1ps
module tb_buffers;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,clear=0,we=0;
    reg [5:0] wa=0,ra=0; reg signed [7:0] wd=0;
    reg signed [31:0] bw=0;
    wire signed [7:0] ir,wr,orr; wire signed [31:0] br;
    input_buffer ib(clk,we,wa,ra,wd,ir);
    weight_buffer wb(clk,we,wa,ra,wd,wr);
    bias_buffer bb(clk,rst_n,clear,we,bw,br);
    output_buffer ob(clk,rst_n,clear,we,wd,orr);
    integer i;
    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        for(i=0;i<49;i=i+1) begin
            @(negedge clk); we=1; wa=i; wd=-120+i*5; bw=-32'sd1234567;
        end
        @(negedge clk); we=0;
        for(i=0;i<49;i=i+1) begin
            ra=i; #1;
            if($signed(ir)!==-120+i*5 || ir!==wr) $fatal(1,"scratchpad index %d",i);
        end
        if(br!==-1234567 || orr!==120) $fatal(1,"scalar buffers");
        ra=63; #1; if(ir!==0 || wr!==0) $fatal(1,"bounds");
        @(negedge clk); clear=1; @(negedge clk);
        if(br!==0 || orr!==0) $fatal(1,"clear");
        $display("PASS tb_buffers"); $finish;
    end
endmodule
