`timescale 1ns/1ps
// Prove there is no CPU-to-compute bypass, even with valid old-style parameters.
module tb_queue_only;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(4096,3) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    reg [31:0] status;
    integer i,op,dispatches=0,descriptor_reads=0,previous_reads,previous_writes,previous_dispatches;
    always @(posedge clk) if(rst_n) begin
        if(dut.exec_start) begin
            if(!dut.queue_active || dut.queue_state!=3 || !dut.task_queue.head_valid || !dut.task_queue.head_ready)
                $fatal(1,"compute start bypassed descriptor FIFO");
            dispatches=dispatches+1;
        end
        if(rd && mready && dut.fetch_phase) descriptor_reads=descriptor_reads+1;
    end
    task word(input integer a,input [31:0] d);
        ram.bytes[a]=d[7:0];ram.bytes[a+1]=d[15:8];
        ram.bytes[a+2]=d[23:16];ram.bytes[a+3]=d[31:24];
    endtask
    task write_reg(input [31:0] off,value);
        @(negedge clk);addr='h40000000+off;wdata=value;we=1;
        @(negedge clk);we=0;
    endtask
    task read_reg(input [31:0] off,output [31:0] value);
        @(negedge clk);addr='h40000000+off;re=1;#1;
        if(!ready) $fatal(1,"MMIO read not ready");value=rdata;
        @(negedge clk);re=0;
    endtask
    task wait_status(input [31:0] expected);
        read_reg(4,status);
        while(status[0]) begin repeat(4) @(negedge clk);read_reg(4,status);end
        if(status!==expected) $fatal(1,"status %h expected %h",status,expected);
    endtask
    task reject_direct(input integer mode);
        previous_reads=ram.reads;previous_writes=ram.writes;previous_dispatches=dispatches;
        write_reg(0,(mode<<2)|1);wait_status(4);
        repeat(12) @(negedge clk);
        if(ram.reads!=previous_reads || ram.writes!=previous_writes || dispatches!=previous_dispatches || dut.array_running)
            $fatal(1,"direct opcode %0d caused work",mode);
    endtask
    initial begin
        for(i=0;i<4096;i=i+1) ram.bytes[i]='ha5;
        ram.bytes['h100]=7;ram.bytes['h200]=2;word('h300,3);
        // One real descriptor: output = 7*2+3 = 17, quant_shift=0.
        word('h800,'h100);word('h804,'h100);word('h808,'h401);word('h80c,'h200);
        word('h810,'h300);word('h814,'h10001);word('h818,'h10001);word('h81c,'h11);
        repeat(2) @(negedge clk);rst_n=1;
        // Old seven-register programming sequence is no longer an execution path.
        write_reg(8,'h100);write_reg(12,'h401);write_reg(16,'h200);write_reg(20,'h300);
        write_reg(24,'h10001);write_reg(28,'h10001);write_reg(32,'h11);
        for(op=0;op<15;op=op+1) reject_direct(op);
        // Reserved register writes have no stored layer configuration.
        for(i=12;i<=32;i=i+4) if(i!=24) begin
            write_reg(i,'hffffffff);read_reg(i,status);
            if(status!==0) $fatal(1,"reserved register %h stored a value",i);
        end
        write_reg(8,'h800);write_reg(24,1);write_reg(0,61);wait_status(2);
        if(dispatches!=1 || descriptor_reads!=8 || dut.queue_completed!=1 || ram.bytes['h401]!==17)
            $fatal(1,"one-entry queue failed");
        if(ram.bytes['h400]!=='ha5 || ram.bytes['h402]!=='ha5) $fatal(1,"guard bytes clobbered");
        // Valid queue registers and stale FIFO bits must never enable a direct START.
        for(op=0;op<15;op=op+1) reject_direct(op);
        write_reg(0,2);wait_status(0);
        ram.bytes['h100]=8;write_reg(0,61);wait_status(2);
        if(dispatches!=2 || descriptor_reads!=16 || ram.bytes['h401]!==19) $fatal(1,"queue restart failed");
        $display("PASS tb_queue_only (30 direct-mode rejects, reserved registers, FIFO-only start, single-task queue, restart)");
        $finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
