`timescale 1ns/1ps
module tb_cnn_controller;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,reset=0,start=0,valid=1;
    reg [31:0] cp='h200113;
    wire [31:0] ci,co,cw,cb,sz,ch,params,x,y;
    wire [15:0] ic,oc; wire [3:0] tap; wire [1:0] sample,sel;
    wire cv,write_cmd,byte_cmd,busy,done,error,clear,iw,ww,bw,al,mac,iz,pf,pv,ow;
    wire [4:0] state;
    reg ready=0,rv=0; integer ticks=0,delay_count=0;
    integer macs=0,pools=0,outs=0,requests=0,biases=0;
    cnn_controller dut(clk,rst_n,reset,start,'h1000,'h8000,'h4000,'h6000,
        {16'd5,16'd5},{16'd2,16'd2},cp,ci,co,cw,cb,sz,ch,params,
        valid,(tap==0),32'd2,32'd1,1'b1,ready,rv,cv,write_cmd,byte_cmd,sel,
        busy,done,error,clear,iw,ww,bw,al,mac,iz,pf,pv,ow,x,y,ic,oc,tap,sample,state);
    always @(negedge clk) begin ticks=ticks+1; ready=(ticks%3!=0); end
    always @(posedge clk) begin
        rv<=0;
        if(reset || !rst_n) delay_count<=0;
        else begin
            if(delay_count>0) begin
                delay_count<=delay_count-1;
                if(delay_count==1) rv<=1;
            end
            if(cv && ready) begin
                if(delay_count!=0) $fatal(1,"multiple outstanding commands");
                delay_count<=2; requests=requests+1;
                if(sel==2) begin
                    if(byte_cmd || write_cmd) $fatal(1,"bias must read word");
                    biases=biases+1;
                end
                if(write_cmd && (sel!=3 || !byte_cmd)) $fatal(1,"output write selection");
            end
            if(mac) macs=macs+1;
            if(pv) pools=pools+1;
            if(ow) outs=outs+1;
        end
    end
    task kick;
        @(negedge clk); start=1; @(negedge clk); start=0;
    endtask
    task run(input pooling);
        macs=0;pools=0;outs=0;requests=0;biases=0;
        cp=pooling ? 'h200113 : 'h113;
        kick(); if(!busy) $fatal(1,"not busy");
        // Live configuration changes must not affect the captured operation.
        cp='hffffffff;
        while(!done && !error) @(negedge clk);
        if(error || macs!=4*(pooling?4:1)*18 || pools!=4*(pooling?4:1) || outs!=4 ||
           biases!=4*(pooling?4:1) || requests!=4*(pooling?4:1)*35+4)
            $fatal(1,"FSM counts mac=%0d pool=%0d out=%0d requests=%0d",macs,pools,outs,requests);
        @(negedge clk); if(busy) $fatal(1,"not idle after done");
    endtask
    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        run(1); run(0);
        valid=0; requests=0; kick(); while(!error) @(negedge clk);
        if(requests) $fatal(1,"invalid parameters touched RAM");
        @(negedge clk); valid=1; kick();
        repeat(10) @(negedge clk); reset=1;
        @(negedge clk); reset=0; if(busy || cv || mac) $fatal(1,"soft reset");
        $display("PASS tb_cnn_controller"); $finish;
    end
    initial begin #1000000; $fatal(1,"timeout"); end
endmodule
