`timescale 1ns/1ps
module tb_cnn_native_memory;
    logic clk=0, rst_n=0;
    always #5 clk=~clk;
    logic [31:0] mem_addr=0, mem_wdata=0;
    logic mem_read=0, mem_write=0;
    wire [31:0] mem_rdata;
    wire mem_ready, cnn_mem_fault;
    logic io_mem_req=0, io_mem_we=0;
    logic [31:0] io_mem_addr=0, io_mem_wdata=0;
    logic [3:0] io_mem_be=0;
    wire io_mem_gnt, io_mem_rvalid, io_mem_error;
    wire [31:0] io_mem_rdata;
    logic dmem_we=0, dmem_re=0;
    logic [31:0] dmem_addr=0;
    logic [31:0] dmem_wdata=32'h12345678;
    logic [3:0] dmem_wstrb=4'hf;
    wire [31:0] dmem_rdata;
    datasram #(.SRAM_SIZE(256)) dut (.*);
    integer writes=0, reads=0;
    always @(posedge clk) if(rst_n && dut.cnn_accept) begin
        if(mem_write) writes=writes+1;
        else reads=reads+1;
    end
    task tick; @(posedge clk); #1; endtask
    task reset;
        @(negedge clk); rst_n=0; mem_read=0; mem_write=0; io_mem_req=0; dmem_we=0; dmem_re=0;
        tick(); @(negedge clk); rst_n=1;
    endtask
    task failed;
        #1; if(mem_ready) $fatal(1,"failed transfer acknowledged");
        tick();
        if(!cnn_mem_fault || mem_ready || dut.cnn_accept) $fatal(1,"fault not latched");
        repeat(3) tick();
        if(mem_ready || dut.cnn_accept) $fatal(1,"fault allowed another transfer");
    endtask
    initial begin
        reset();
        mem_write=1; mem_addr=32'h40; mem_wdata=32'hdeadbeef;
        #1; if(!mem_ready) $fatal(1,"write not ready"); tick();
        @(negedge clk); mem_addr=32'h44; mem_wdata=32'hcafebabe;
        #1; if(!mem_ready) $fatal(1,"continuous write not ready"); tick();
        @(negedge clk); mem_write=0; mem_read=1; mem_addr=32'h40;
        #1; if(mem_ready) $fatal(1,"read acknowledged before data");
        tick();
        if(!mem_ready || mem_rdata!==32'hdeadbeef || dut.cnn_accept)
            $fatal(1,"read data or duplicate request");
        tick(); @(negedge clk); mem_addr=32'h44;
        #1; if(mem_ready) $fatal(1,"second read acknowledged early");
        tick(); if(!mem_ready || mem_rdata!==32'hcafebabe) $fatal(1,"second read");
        tick(); @(negedge clk); mem_read=0; mem_write=1; mem_addr=32'h48; mem_wdata=17;
        tick(); @(negedge clk); mem_write=0;
        if(writes!=3 || reads!=2 || dut.mem[18]!==17)
            $fatal(1,"continuous transaction count");
        // An IO read already in flight must delay the native CNN request.
        io_mem_req=1; io_mem_addr=32'h40;
        tick(); @(negedge clk); io_mem_req=0; mem_read=1; mem_addr=32'h44;
        #1; if(dut.cnn_accept || mem_ready || !io_mem_rvalid || io_mem_rdata!==32'hdeadbeef)
            $fatal(1,"pending IO ownership");
        tick(); if(mem_ready) $fatal(1,"CNN accepted before IO completion");
        tick(); if(!mem_ready || mem_rdata!==32'hcafebabe) $fatal(1,"CNN after IO");
        tick(); @(negedge clk); mem_read=0;
        reset(); mem_write=1; mem_addr=32'h100; failed(); // range error
        if(dut.mem[16]!==32'hdeadbeef) $fatal(1,"range wrapped");
        reset(); mem_write=1; mem_addr=32'h41; failed(); // alignment error
        reset(); mem_read=1; mem_addr=32'h100;
        tick(); failed(); // error arrives with synchronous read response
        reset(); mem_write=1; mem_addr=32'h40; dmem_addr=32'h40; dmem_we=1;
        failed(); // simultaneous A/B write conflict
        reset(); mem_read=1; mem_write=1; failed();
        reset(); mem_read=1; mem_addr=32'h44; tick(); reset();
        if(cnn_mem_fault || mem_ready || dut.cnn_accept) $fatal(1,"reset pending read");
        mem_write=1; mem_addr=32'h4c; mem_wdata=19; tick();
        @(negedge clk); mem_write=0;
        if(dut.mem[19]!==19) $fatal(1,"reset recovery");
        // Preserve fixed-cycle CPU reads and byte strobes at the last valid word.
        reset(); dmem_addr=32'hfc; dmem_we=1; dmem_wdata=32'h11223344;
        tick(); @(negedge clk); dmem_wstrb=4'b0101; dmem_wdata=32'haabbccdd;
        tick(); @(negedge clk); dmem_we=0; dmem_re=1;
        tick(); if(dmem_rdata!==32'h11bb33dd) $fatal(1,"CPU byte strobes or synchronous read");
        @(negedge clk); mem_read=1; mem_addr=32'hfc;
        tick(); if(mem_rdata!==dmem_rdata || !mem_ready || cnn_mem_fault)
            $fatal(1,"simultaneous A/B reads must succeed");
        tick(); reset();
        dmem_re=1; dmem_addr=32'hfc; mem_write=1; mem_addr=32'hfc;
        failed(); if(dmem_rdata!==32'h11bb33dd || dut.mem[63]!==32'h11bb33dd)
            $fatal(1,"CPU read/CNN write conflict corrupted memory");
        reset(); dmem_we=1; dmem_addr=32'hfc; dmem_wstrb=15;
        mem_read=1; mem_addr=32'hfc; tick(); failed();
        if(dut.mem[63]!==dmem_wdata) $fatal(1,"A write must win read conflict");
        // IO retains its explicit error channel for invalid reads and byte masks.
        reset(); io_mem_req=1; io_mem_we=0; io_mem_addr=32'h100; io_mem_be=0;
        tick(); if(!io_mem_rvalid || !io_mem_error || io_mem_rdata!==0 || cnn_mem_fault)
            $fatal(1,"IO invalid read response");
        @(negedge clk); io_mem_req=0; tick();
        @(negedge clk); io_mem_req=1; io_mem_we=1; io_mem_addr=32'hfc; io_mem_be=0;
        #1; if(!io_mem_gnt || !io_mem_error) $fatal(1,"IO zero byte mask must fail");
        tick(); if(dut.mem[63]!==dmem_wdata) $fatal(1,"invalid IO write changed RAM");
        reset();
        $display("PASS tb_cnn_native_memory real SRAM, continuous transfers, IO wait, range/alignment/conflict faults, reset recovery");
        $finish;
    end
    initial begin #10000; $fatal(1,"timeout"); end
endmodule
