`timescale 1ns/1ps
module tb_operator_control;
    reg clk=0;always #5 clk=~clk;reg rst_n=0;
    reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(32768,5) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    integer i,t,scenario,id,phase=0,reads0,writes0;
    reg [3:0] launched=0,finished=0;reg early_independent=0;
    task word(input integer a,input [31:0] value);
        ram.bytes[a]=value[7:0];ram.bytes[a+1]=value[15:8];ram.bytes[a+2]=value[23:16];ram.bytes[a+3]=value[31:24];
    endtask
    task desc(input integer n,op,ia,oa,wa,ba,fs,lp);
        word('h4000+32*n,'h100|op);word('h4004+32*n,ia);word('h4008+32*n,oa);word('h400c+32*n,wa);
        word('h4010+32*n,ba);word('h4014+32*n,fs);word('h4018+32*n,'h10001);word('h401c+32*n,lp);
    endtask
    task wrreg(input [31:0] off,value);
        @(negedge clk);addr='h40000000+off;wdata=value;we=1;@(negedge clk);we=0;
    endtask
    task launch(input integer n);
        launched=0;finished=0;early_independent=0;wrreg(8,'h4000);wrreg(24,n);wrreg(0,61);
    endtask
    task waitstatus(input [31:0] expected);
        @(negedge clk);addr='h40000004;re=1;#1;
        while(rdata[0]) begin @(negedge clk);#1;end
        if(rdata!==expected) $fatal(1,"status %h expected %h",rdata,expected);
        @(negedge clk);re=0;
    endtask
    always @(posedge clk) if(rst_n && phase==1) begin
        for(integer u=0;u<8;u=u+1) begin
            if(dut.unit_start[u]) begin
                id=dut.dispatch_id;
                if(launched[id]) $fatal(1,"duplicate");
                launched[id]=1;
                if(id==2 && !finished[1]) $fatal(1,"bypassed older pending RAW/WAR/WAW/word dependency scenario %0d",scenario);
                if(id==3 && !finished[0] && !launched[1]) early_independent=1;
            end
            if(dut.unit_done[u]) begin
                id=dut.unit_task_ids[u*32+:32];finished[id]=1;
                if(id==1 && ram.bytes[scenario==3 ? 'h701 : 'h700]!==3) $fatal(1,"older reader/result corrupted");
            end
        end
    end
    initial begin
        for(i=0;i<32768;i=i+1) ram.bytes[i]='ha5;
        repeat(2) @(negedge clk);rst_n=1;
        for(scenario=0;scenario<4;scenario=scenario+1) begin
            for(i=0;i<256;i=i+1) begin ram.bytes['h1000+i]=2;ram.bytes['h2000+i]='ha5;end
            for(i=0;i<16;i=i+1) begin ram.bytes['h200+i]=3;ram.bytes['h300+i]=5;ram.bytes['h400+i]=7;ram.bytes['h3000+i]=9;end
            desc(0,6,'h1000,'h2000,0,0,'h10100,0);
            desc(1,6,'h200,scenario==3 ? 'h701 : 'h700,0,0,scenario==3 ? 'h10001 : 'h10010,0);
            desc(2,3,scenario==0 ? 'h700 : 'h400,
                scenario==0 ? 'h900 : scenario==1 ? 'h200 : scenario==2 ? 'h700 : 'h702,
                'h300,0,scenario==3 ? 'h10001 : 'h10010,0);
            desc(3,8,'h3000,'h3400,0,0,'h40004,'h22);
            phase=1;launch(4);waitstatus(2);phase=0;
            if(!early_independent || finished!=15 || dut.queue_completed!=4) $fatal(1,"independent bypass/count");
            if(ram.bytes[scenario==0 ? 'h900 : scenario==1 ? 'h200 : scenario==2 ? 'h700 : 'h702] !== (scenario==0 ? 8'd8 : 8'd12)) $fatal(1,"younger output");
        end
        // Runtime parameter fault: other in-flight operator must drain successfully.
        desc(0,6,'h1000,'h2000,0,0,'h10100,0);
        desc(1,7,'h200,'h800,0,'h3800,'h10010,0);
        word('h3800,1);word('h3804,1);word('h3808,64);word('h380c,0);word('h3810,0);word('h3814,96);
        launch(2);waitstatus(4);
        if(dut.queue_completed!=1 || dut.unit_allocated!=0) $fatal(1,"runtime fault drain");
        // Reset concurrent scalar engines during a stalled external transaction.
        desc(1,3,'h200,'h800,'h300,0,'h10010,0);
        launch(2);
        while(!((dut.unit_allocated & 8'h18)==8'h18 && (rd || wr) && !mready)) @(negedge clk);
        wrreg(0,2);waitstatus(0);reads0=ram.reads;writes0=ram.writes;
        repeat(30) @(negedge clk);
        if(dut.unit_allocated || dut.queue_buffered || rd || wr || ram.reads!=reads0 || ram.writes!=writes0) $fatal(1,"reset drain");
        launch(2);waitstatus(2);
        if(dut.queue_completed!=2 || ram.bytes['h800]!==8) $fatal(1,"restart");
        $display("PASS tb_operator_control (pending RAW/WAR/WAW/shared-word, independent bypass, parameter fault drain, reset/restart)");$finish;
    end
    initial begin #10000000;$fatal(1,"timeout");end
endmodule
