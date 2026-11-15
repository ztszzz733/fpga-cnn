`timescale 1ns/1ps
module tb_task_descriptor_fifo;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0,iv=0,orr=0;reg [255:0] din=0;
    wire ir,ov;wire [255:0] dout;wire [31:0] level;
    task_descriptor_fifo #(.DEPTH(3)) dut(clk,rst_n,clear,iv,ir,din,ov,orr,dout,level);
    integer i;
    task push(input integer value);
        @(negedge clk);iv=1;din=value;if(ir!==1) $fatal(1,"unexpected full");
        @(negedge clk);iv=0;
    endtask
    task pop(input integer value);
        @(negedge clk);if(ov!==1 || dout!==value) $fatal(1,"FIFO order");orr=1;
        @(negedge clk);orr=0;
    endtask
    initial begin
        repeat(2) @(negedge clk);rst_n=1;
        push(11);push(22);push(33);
        if(ir!==0 || level!==3) $fatal(1,"full");
        iv=1;din=99;repeat(3) @(negedge clk);iv=0;
        if(dout!==11 || level!==3) $fatal(1,"backpressure");
        pop(11);
        @(negedge clk);iv=1;din=44;orr=1;
        @(negedge clk);iv=0;orr=0;
        if(level!==2 || dout!==33) $fatal(1,"simultaneous push/pop");
        pop(33);pop(44);if(ov!==0 || level!==0) $fatal(1,"empty");
        for(i=0;i<12;i=i+1) begin push(100+i);pop(100+i);end
        push(1);clear=1;@(negedge clk);clear=0;
        if(ov!==0 || level!==0) $fatal(1,"clear");
        $display("PASS tb_task_descriptor_fifo");$finish;
    end
    initial begin #20000;$fatal(1,"timeout");end
endmodule
