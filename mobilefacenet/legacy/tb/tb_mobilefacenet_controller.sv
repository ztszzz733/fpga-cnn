`timescale 1ns/1ps
module tb_mobilefacenet_controller;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,reset=0,start=0,valid=1;reg [3:0] op=0;
    wire [31:0] ci,co,cw,cb,sz,ch,lp,x,y,index;wire [3:0] cfg_op;
    wire [15:0] ic,oc;wire [5:0] tap;wire [2:0] sel;wire [4:0] state;
    wire cv,wr,byte_cmd,busy,done,error,clear,iw,ww,bw,es,sv,ow,zero;
    reg ready=0,rv=0,er=0,ed=0;integer ticks=0,delay_count=0,remaining=0;
    integer samples=0,requests=0,outputs=0,starts=0;
    mobilefacenet_controller dut(clk,rst_n,reset,start,'h100,'h1000,'h2000,'h3000,
        'h50005,'h20002,'h113,op,ci,co,cw,cb,sz,ch,lp,cfg_op,valid,(tap==0),
        32'd2,32'd1,32'd4,1'b1,ready,rv,er,ed,1'b0,cv,wr,byte_cmd,sel,busy,done,error,clear,
        iw,ww,bw,es,sv,ow,zero,x,y,index,ic,oc,tap,state);
    always @(negedge clk) begin ticks=ticks+1;ready=ticks%3!=0;er=ticks%4!=0;end
    always @(posedge clk) begin
        rv<=0;ed<=0;
        if(reset || !rst_n) begin delay_count<=0;remaining<=0;end
        else begin
            if(delay_count>0) begin delay_count<=delay_count-1;if(delay_count==1) rv<=1;end
            if(cv && ready) begin
                if(delay_count!=0) $fatal(1,"outstanding commands");
                delay_count<=2;requests=requests+1;
            end
            if(es) begin remaining<=cfg_op==0 ? 18 : 9;starts=starts+1;end
            if(sv && er) begin
                samples=samples+1;remaining<=remaining-1;if(remaining==1) ed<=1;
            end
            if(ow) outputs=outputs+1;
        end
    end
    task run(input integer mode,exp_samples,exp_requests,exp_starts);
        @(negedge clk);op=mode;samples=0;requests=0;outputs=0;starts=0;start=1;
        @(negedge clk);start=0;op=15;
        while(!done && !error) @(negedge clk);
        if(error || samples!=exp_samples || requests!=exp_requests || outputs!=4 || starts!=exp_starts)
            $fatal(1,"mode=%d samples=%d requests=%d outputs=%d starts=%d",mode,samples,requests,outputs,starts);
        @(negedge clk);if(busy) $fatal(1,"not idle");
    endtask
    initial begin
        repeat(2) @(negedge clk);rst_n=1;
        run(0,72,144,4);run(1,36,76,4);run(2,0,8,0);run(3,0,12,0);run(4,0,8,0);run(5,0,8,0);
        valid=0;requests=0;start=1;@(negedge clk);start=0;
        while(!error) @(negedge clk);if(requests) $fatal(1,"invalid touched RAM");
        @(negedge clk);valid=1;op=0;start=1;@(negedge clk);start=0;
        repeat(10) @(negedge clk);reset=1;@(negedge clk);reset=0;
        if(busy || cv || sv) $fatal(1,"reset");
        $display("PASS tb_mobilefacenet_controller");$finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
