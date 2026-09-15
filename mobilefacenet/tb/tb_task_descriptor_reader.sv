`timescale 1ns/1ps
module tb_task_descriptor_reader;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0,start=0,ready=0,rv=0,dr=0;
    reg [31:0] rsp=0;wire idle,cv,dv;wire [31:0] ca;wire [255:0] descriptor;
    task_descriptor_reader dut(clk,rst_n,clear,start,32'h400,idle,cv,ready,ca,rv,rsp,dv,dr,descriptor);
    integer tick=0,pending=0,index=0,i;
    always @(negedge clk) begin tick=tick+1;ready=tick%3!=0;end
    always @(posedge clk) begin
        rv<=0;
        if(clear || !rst_n) begin pending<=0;index<=0;end
        else begin
            if(cv && ready) begin
                if(pending || ca!==32'h400+index*4) $fatal(1,"fetch address/order");
                pending<=3;
            end
            if(pending>0) begin
                pending<=pending-1;
                if(pending==1) begin rv<=1;rsp<=32'habc00000+index;index<=index+1;end
            end
        end
    end
    initial begin
        repeat(2) @(negedge clk);rst_n=1;start=1;@(negedge clk);start=0;
        while(!dv) @(negedge clk);
        for(i=0;i<8;i=i+1) if(descriptor[i*32+:32]!==32'habc00000+i) $fatal(1,"word assembly");
        repeat(5) begin @(negedge clk);if(dv!==1 || cv || idle) $fatal(1,"publish hold");end
        dr=1;@(negedge clk);dr=0;if(!idle) $fatal(1,"not idle");
        clear=1;@(negedge clk);clear=0;start=1;@(negedge clk);start=0;
        repeat(5) @(negedge clk);clear=1;@(negedge clk);clear=0;
        if(!idle || cv || dv) $fatal(1,"reset mid-read");
        $display("PASS tb_task_descriptor_reader");$finish;
    end
    initial begin #20000;$fatal(1,"timeout");end
endmodule
