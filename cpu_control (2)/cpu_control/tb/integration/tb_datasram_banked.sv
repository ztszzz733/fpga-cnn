`timescale 1ns/1ps
module tb_datasram_banked;
    parameter integer BANKS=4, ENABLE_OVERLAP=1;
    logic clk=0,rst_n=0;
    always #5 clk=~clk;
    logic [31:0] dmem_addr=0,dmem_wdata=0;logic [3:0] dmem_wstrb=15;
    logic dmem_re=0,dmem_we=0;wire [31:0] dmem_rdata;
    logic [10:0] cnn_valid=0,cnn_write=0,cnn_byte=0;
    logic [351:0] cnn_addr=0,cnn_wdata=0;wire [10:0] cnn_ready,cnn_response;wire [351:0] cnn_rdata;
    logic cnn_cancel=0;wire cnn_mem_fault;
    logic io_mem_req=0,io_mem_we=0;logic [31:0] io_mem_addr=0,io_mem_wdata=0;
    logic [3:0] io_mem_be=0;wire io_mem_gnt,io_mem_rvalid,io_mem_error;wire [31:0] io_mem_rdata;
    datasram_banked #(.BANKS(BANKS),.SRAM_SIZE(256)) dut(.*);
    reg [10:0] accepted,seen;
    reg accepted_io,seen_io;
    integer grants=0,hotspot_cycles=0,same_bank_parallel=0;
    task tick;begin @(posedge clk);#1;end endtask
    task cpu_write(input [31:0] addr,value);
        begin @(negedge clk);dmem_addr=addr;dmem_wdata=value;dmem_we=1;tick();@(negedge clk);dmem_we=0;end
    endtask
    task cnn_access(input integer client,input bit wr,byt,input [31:0] addr,value,expected);
        begin
            @(negedge clk);cnn_valid[client]=1;cnn_write[client]=wr;cnn_byte[client]=byt;
            cnn_addr[client*32+:32]=addr;cnn_wdata[client*32+:32]=value;
            do begin @(posedge clk);end while(!cnn_ready[client]);
            #1;
            if(!cnn_response[client] || (!wr && cnn_rdata[client*32+:32]!==expected))
                $fatal(1,"client response mismatch client=%0d data=%h expected=%h",client,cnn_rdata[client*32+:32],expected);
            @(negedge clk);cnn_valid[client]=0;
        end
    endtask
    initial begin
        repeat(3) tick();@(negedge clk);rst_n=1;
        for(integer i=0;i<16;i=i+1) cpu_write(i*4,32'h10203040+i);
        // Eleven simultaneous clients, both same-bank and different-bank competition.
        @(negedge clk);cnn_valid='1;
        for(integer i=0;i<11;i=i+1) cnn_addr[i*32+:32]=i*4;
        seen=0;
        while(seen!='1) begin
            @(posedge clk);accepted=cnn_valid & cnn_ready;grants=grants+$countones(accepted);#1;
            if(cnn_response!==accepted) $fatal(1,"response routing");
            for(integer i=0;i<11;i=i+1) if(accepted[i] && cnn_rdata[i*32+:32]!==32'h10203040+i)
                $fatal(1,"parallel read data");
            seen=seen|accepted;@(negedge clk);cnn_valid=cnn_valid & ~accepted;
        end
        // CPU reserves bank zero while a CNN request remains stable under backpressure.
        cnn_valid=1;cnn_addr[0+:32]=0;dmem_addr=0;dmem_re=1;
        repeat(20) begin tick();if(cnn_ready[0] || cnn_response[0] || dmem_rdata!==32'h10203040) $fatal(1,"CPU priority");end
        @(negedge clk);dmem_re=0;tick();if(!cnn_response[0]) $fatal(1,"stalled request did not resume");
        @(negedge clk);cnn_valid=0;
        // True dual-port proof: CPU and CNN use the same bank but different
        // rows in the same cycle.  The old single-port bank stalled this case.
        cnn_valid=1;cnn_write=0;cnn_byte=0;cnn_addr[0+:32]=16;
        dmem_addr=0;dmem_re=1;tick();
        if(!cnn_ready[0] || !cnn_response[0] || cnn_rdata[0+:32]!==32'h10203044 ||
            dmem_rdata!==32'h10203040) $fatal(1,"same-bank dual-port access did not overlap");
        same_bank_parallel=same_bank_parallel+1;
        @(negedge clk);cnn_valid=0;dmem_re=0;
        // All twelve port-B requesters target bank zero.  A fair tree-backed
        // round robin must grant exactly one per cycle and serve all of them.
        cnn_valid='1;cnn_write=0;cnn_byte=0;
        for(integer i=0;i<11;i=i+1) cnn_addr[i*32+:32]=i*16;
        io_mem_req=1;io_mem_we=0;io_mem_be=0;io_mem_addr=176;
        seen=0;seen_io=0;hotspot_cycles=0;
        while(seen!='1 || !seen_io) begin
            @(posedge clk);accepted=cnn_valid & cnn_ready;accepted_io=io_mem_req && io_mem_gnt;
            if($countones(accepted)+accepted_io!=1) $fatal(1,"hotspot arbitration grant count");
            hotspot_cycles=hotspot_cycles+1;#1;
            if(cnn_response!==accepted || io_mem_rvalid!==accepted_io)
                $fatal(1,"hotspot response routing");
            seen=seen|accepted;seen_io=seen_io|accepted_io;
            @(negedge clk);cnn_valid=cnn_valid & ~accepted;if(accepted_io) io_mem_req=0;
        end
        if(hotspot_cycles!=12) $fatal(1,"round-robin fairness bound");
        cnn_access(0,1,1,1,32'h80,0);
        cnn_access(1,0,0,0,0,32'h10208040);
        cnn_access(2,0,1,1,0,32'hffffff80);
        // Two byte writers sharing a word must preserve each other's update.
        @(negedge clk);cnn_valid=3;cnn_write=3;cnn_byte=3;
        cnn_addr[0+:32]=2;cnn_addr[32+:32]=3;cnn_wdata[0+:32]='haa;cnn_wdata[32+:32]='hbb;
        while(cnn_valid!=0) begin @(posedge clk);accepted=cnn_valid & cnn_ready;#1;@(negedge clk);cnn_valid &= ~accepted;end
        cnn_access(3,0,0,0,0,32'hbbaa8040);
        // Cancel pending response/request without resetting SRAM.
        @(negedge clk);cnn_valid=1;cnn_write=0;cnn_byte=0;cnn_addr[0+:32]=0;tick();
        @(negedge clk);cnn_cancel=1;tick();if(|cnn_response || |cnn_ready) $fatal(1,"cancel leaked response");
        @(negedge clk);cnn_valid=0;cnn_cancel=0;
        cnn_access(0,0,0,0,0,32'hbbaa8040);
        // IO write byte enables and read-response error retain the original protocol.
        @(negedge clk);io_mem_req=1;io_mem_we=1;io_mem_addr=0;io_mem_be=2;io_mem_wdata='h00001100;
        do begin @(posedge clk);end while(!io_mem_gnt);
        @(negedge clk);io_mem_req=0;
        cnn_access(0,0,0,0,0,32'hbbaa1140);
        @(negedge clk);io_mem_req=1;io_mem_we=0;io_mem_be=0;io_mem_addr=256;
        do begin @(posedge clk);end while(!io_mem_gnt);
        #1;if(!io_mem_rvalid || !io_mem_error || io_mem_rdata!==0) $fatal(1,"IO range error lost");
        @(negedge clk);io_mem_req=0;
        // Misaligned word request faults without a grant, locks until system reset.
        cnn_valid=1;cnn_write=0;cnn_byte=0;cnn_addr[0+:32]=1;tick();
        if(!cnn_mem_fault || |cnn_ready) $fatal(1,"missing alignment fault");
        @(negedge clk);cnn_addr[0+:32]=0;cnn_cancel=1;tick();
        if(!cnn_mem_fault) $fatal(1,"soft reset cleared system fault");
        @(negedge clk);cnn_valid=0;cnn_cancel=0;rst_n=0;tick();
        @(negedge clk);rst_n=1;cnn_access(0,0,0,0,0,32'hbbaa1140);
        @(negedge clk);cnn_valid=1;cnn_addr[0+:32]=256;tick();
        if(!cnn_mem_fault || |cnn_ready) $fatal(1,"missing range fault");
        $display("METRICS clients=%0d grants=%0d stalled_cycles=20 same_bank_parallel=%0d hotspot_cycles=%0d",11,grants,same_bank_parallel,hotspot_cycles);
        $display("PASS tb_datasram_banked");$finish;
    end
    initial begin #100000;$fatal(1,"memory test timeout");end
endmodule
