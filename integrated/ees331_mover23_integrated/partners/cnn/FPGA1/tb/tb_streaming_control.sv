`timescale 1ns/1ps
module tb_streaming_control;
    reg clk=0;always #5 clk=~clk;reg rst_n=0;
    reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(8192,5) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    integer i,reads0,writes0;
    task word(input integer a,input [31:0] x);
        ram.bytes[a]=x[7:0];ram.bytes[a+1]=x[15:8];ram.bytes[a+2]=x[23:16];ram.bytes[a+3]=x[31:24];
    endtask
    task regwrite(input [31:0] off,x);
        @(negedge clk);addr='h40000000+off;wdata=x;we=1;@(negedge clk);we=0;
    endtask
    task waitstatus(input [31:0] expected);
        @(negedge clk);addr='h40000004;re=1;#1;
        while(rdata[0]) begin @(negedge clk);#1;end
        if(rdata!==expected) $fatal(1,"status %h expected %h",rdata,expected);
        @(negedge clk);re=0;
    endtask
    task launch(input integer count);
        regwrite(8,'h1000);regwrite(24,count);regwrite(0,61);
    endtask
    task check_outputs;
        for(i=0;i<34;i=i+1) if(ram.bytes['h800+i]!==3) $fatal(1,"job0 result");
        for(i=0;i<102;i=i+1) if(ram.bytes['h900+i]!==3) $fatal(1,"job1 result");
    endtask
    initial begin
        for(i=0;i<8192;i=i+1) ram.bytes[i]='ha5;
        for(i=0;i<51;i=i+1) begin ram.bytes['h100+i]=1;ram.bytes['h200+i]=1;end
        for(i=0;i<18;i=i+1) begin ram.bytes['h400+i]=1;ram.bytes['h500+i]=1;end
        for(i=0;i<8;i=i+1) ram.bytes['h600+i]=0;
        for(i=0;i<24;i=i+1) ram.bytes['h620+i]=0;
        word('h1000,'h100);word('h1004,'h100);word('h1008,'h800);word('h100c,'h400);
        word('h1010,'h600);word('h1014,'h10011);word('h1018,'h20003);word('h101c,'h11);
        word('h1020,'h100);word('h1024,'h200);word('h1028,'h900);word('h102c,'h500);
        word('h1030,'h620);word('h1034,'h10011);word('h1038,'h60003);word('h103c,'h11);
        // Invalid younger task is detected while two older tasks are live.
        word('h1040,'h102);
        repeat(2) @(negedge clk);rst_n=1;
        launch(3);while(dut.allocated!=3) @(negedge clk);waitstatus(4);
        if(dut.queue_completed!=2 || dut.queue_dispatched!=2) $fatal(1,"error drain dropped/reissued a task");
        check_outputs();
        launch(2);while(!(dut.allocated==3 && (rd || wr) && !mready)) @(negedge clk);
        regwrite(0,2);waitstatus(0);reads0=ram.reads;writes0=ram.writes;
        repeat(40) @(negedge clk);
        if(dut.allocated || dut.queue_buffered || dut.core_busy || rd || wr || ram.reads!=reads0 || ram.writes!=writes0)
            $fatal(1,"reset did not drain both contexts and bus");
        launch(2);while(dut.allocated!=3) @(negedge clk);regwrite(0,1);waitstatus(6);check_outputs();
        if(dut.queue_completed!=2) $fatal(1,"busy START duplicated job");
        launch(2);waitstatus(2);check_outputs();
        $display("PASS tb_streaming_control (two-live-task error drain, reset/drain, busy START, restart)");$finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
