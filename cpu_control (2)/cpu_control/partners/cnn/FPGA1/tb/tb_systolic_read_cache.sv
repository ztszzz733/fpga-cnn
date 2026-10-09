`timescale 1ns/1ps
module tb_systolic_read_cache;
    reg clk=0;always #5 clk=~clk;reg rst_n=0,clear=0,req=0,byte_mode=1,bank=0;
    reg [31:0] addr=0;wire ready,response,cmd;wire [31:0] data,ma;reg ack=0,rv=0;reg [31:0] rd=0;
    integer reads=0,delay_count=0;reg [31:0] held=0;
    systolic_read_cache dut(clk,rst_n,clear,req,ready,addr,byte_mode,bank,response,data,cmd,ack,ma,rv,rd);
    always @(negedge clk) begin
        ack=0;rv=0;
        if(cmd) begin
            if(delay_count==0) held=ma;
            if(ma!==held) $fatal(1,"request unstable");
            delay_count=delay_count+1;
            if(delay_count==3) begin ack=1;reads=reads+1;end
        end else if(delay_count!=0) begin
            delay_count=delay_count+1;
            if(delay_count==6) begin rv=1;rd=held ^ 32'h807fff01;delay_count=0;end
        end
    end
    task get(input [31:0] address,input bm,bk,input [31:0] expected);
        @(posedge clk);#1;addr=address;byte_mode=bm;bank=bk;req=1;
        @(posedge clk);#1;req=0;while(!response) begin @(posedge clk);#1;end
        if(data!==expected) $fatal(1,"cache addr%h got%h want%h",address,data,expected);
    endtask
    initial begin
        @(posedge clk);#1;rst_n=1;
        get(0,1,0,'h01);get(1,1,0,'hff);get(2,1,0,'h7f);get(3,1,0,'h80);
        if(reads!=1) $fatal(1,"failed four-byte reuse");
        get(4,0,1,'h807fff05);get(1,1,0,'hff);if(reads!=2) $fatal(1,"banks interfered");
        get(4,1,0,5);get(0,1,0,1);if(reads!=4) $fatal(1,"cache tag replacement");
        clear=1;@(posedge clk);#1;clear=0;get(0,1,0,1);if(reads!=5) $fatal(1,"task invalidation");
        $display("PASS tb_systolic_read_cache (unpack, banks, replacement, stalls, invalidation)");$finish;
    end
    initial begin #100000;$fatal(1,"timeout");end
endmodule
