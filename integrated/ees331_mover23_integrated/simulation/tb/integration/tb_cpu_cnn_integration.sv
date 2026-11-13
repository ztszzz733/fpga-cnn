`timescale 1ns/1ps
module tb_cpu_cnn_integration;
    logic clk=0, rst_n=0;
    always #5 clk=~clk;
    logic io_mem_req=0, io_mem_we=0;
    logic [31:0] io_mem_addr=0, io_mem_wdata=0;
    logic [3:0] io_mem_be=0;
    wire io_mem_gnt, io_mem_rvalid, io_mem_error, cnn_mem_fault;
    wire [31:0] io_mem_rdata;
    face_soc_cnn_top #(.IMEM_SIZE(4096), .SRAM_SIZE(8192)) dut (.*);
    integer pc=0, starts=0, io_writes=0, cnn_reads=0, cnn_writes=0;
    integer i;
    function automatic [31:0] itype(input integer imm, rs, f, rd, op);
        itype=((imm & 4095)<<20)|(rs<<15)|(f<<12)|(rd<<7)|op;
    endfunction
    function automatic [31:0] stype(input integer imm, rs, rt, f);
        stype=(((imm>>5)&127)<<25)|(rt<<20)|(rs<<15)|(f<<12)|((imm&31)<<7)|'h23;
    endfunction
    function automatic [31:0] branch(input integer off, rs, rt, f);
        branch=(((off>>12)&1)<<31)|(((off>>5)&63)<<25)|(rt<<20)|(rs<<15)|
               (f<<12)|(((off>>1)&15)<<8)|(((off>>11)&1)<<7)|'h63;
    endfunction
    task emit(input [31:0] ins);
        dut.u_imem.mem[pc/4]=ins; pc=pc+4;
    endtask
    task li(input integer rd, input [31:0] value);
        emit(((value+32'h800)&32'hfffff000)|(rd<<7)|'h37);
        emit(itype(value,rd,0,rd,'h13));
    endtask
    task write_word(input [31:0] address, value);
        li(2,address); li(3,value); emit(stype(0,2,3,2));
    endtask
    task mmio_write(input integer offset, input [31:0] value);
        li(3,value); emit(stype(offset,1,3,2));
    endtask
    task read_save(input [31:0] address, dest);
        li(2,address); emit(itype(0,2,2,4,'h03));
        li(2,dest); emit(stype(0,2,4,2));
    endtask
    task poll_status(input integer expected);
        integer retry;
        li(5,expected); li(6,20000); retry=pc;
        emit(itype(4,1,2,4,'h03));
        emit(branch(20,4,5,0));
        emit(itype(-1,6,0,6,'h13));
        emit(branch(retry-pc,6,0,1));
        emit(stype('h30,0,4,2)); // failure status mailbox
        emit(32'h0000006f);     // test timeout reports failed polling
    endtask
    always @(posedge clk) if(rst_n) begin
        if(dut.cnn_mmio_we && dut.cnn_mmio_ready)
            $display("MMIO_WRITE addr=%h data=%h time=%0t",dut.cnn_mmio_addr,dut.cnn_mmio_wdata,$time);
        if(cnn_mem_fault) $fatal(1,"unexpected SRAM fault");
        if(dut.cnn_mmio_we && dut.cnn_mmio_ready && dut.cnn_mmio_addr=='h40000000 && dut.cnn_mmio_wdata==61)
            starts=starts+1;
        if(dut.u_datasram.cnn_accept) begin
            if(dut.mem_write) cnn_writes=cnn_writes+1;
            else cnn_reads=cnn_reads+1;
        end
        if(io_mem_req && io_mem_gnt) begin
            if(io_mem_error) $fatal(1,"image master error");
            io_writes=io_writes+1;
        end
    end
    initial begin
        for(i=0;i<1024;i=i+1) dut.u_imem.mem[i]=32'h13;
        for(i=0;i<2048;i=i+1) dut.u_datasram.mem[i]=0;
        li(1,32'h40000000);
        write_word('h100,7); write_word('h200,2); write_word('h300,3);
        write_word('h400,32'ha5a5a5a5);
        write_word('h800,'h100); write_word('h804,'h100);
        write_word('h808,'h401); write_word('h80c,'h200);
        write_word('h810,'h300); write_word('h814,'h10001);
        write_word('h818,'h10001); write_word('h81c,'h11);
        mmio_write(8,'h800); mmio_write(24,1);
        // These must not modify QUEUE_BASE: illegal MMIO widths/alignment.
        li(3,32'hffff); emit(stype(8,1,3,0)); emit(stype(8,1,3,1));
        emit(stype(9,1,3,2));
        read_save('h40000008,'h910); read_save('h40000018,'h914);
        mmio_write(12,32'hffffffff); read_save('h4000000c,'h918);
        mmio_write(0,61);
        write_word('hc80,'h12345678); // CPU SRAM A while CNN uses B
        poll_status(2); read_save('h400,'h900);
        write_word('h100,8); mmio_write(0,61);
        poll_status(2); read_save('h400,'h904);
        // Unsupported descriptor version/opcode must report ERROR.
        write_word('h800,'h200); mmio_write(0,61); poll_status(4);
        mmio_write(0,2); poll_status(0);
        write_word('h908,'h600d); emit(32'h0000006f);
        repeat(5) @(negedge clk); rst_n=1;
        wait(dut.u_datasram.mem['h908/4]=='h600d);
        @(negedge clk);
        if(dut.u_datasram.mem['h900/4]!==32'ha5a511a5 ||
           dut.u_datasram.mem['h904/4]!==32'ha5a513a5)
            $fatal(1,"CPU did not read 17 then 19 with guards intact");
        if(dut.u_datasram.mem['h910/4]!==32'h800 ||
           dut.u_datasram.mem['h914/4]!==1 ||
           dut.u_datasram.mem['h918/4]!==0)
            $fatal(1,"MMIO readback/width/reserved register failure");
        if(starts!=3 || cnn_writes!=2 || cnn_reads<24 || io_writes<10 ||
           dut.u_datasram.mem['hc80/4]!==32'h12345678)
            $fatal(1,"transaction accounting or concurrent access failure");
        $display("PASS tb_cpu_cnn_integration CPU queue/readback, 17->19, guards, concurrent A/B, invalid descriptor, soft reset; starts=%0d cnn_reads=%0d cnn_writes=%0d io_writes=%0d", starts,cnn_reads,cnn_writes,io_writes);
        $finish;
    end
    initial begin
        wait(rst_n); wait(starts==1);
        @(negedge clk); io_mem_req=1; io_mem_we=1; io_mem_addr='hc00; io_mem_be=15;
        forever begin
            @(posedge clk);
            if(io_mem_gnt) begin
                @(negedge clk); io_mem_wdata=io_mem_wdata+1;
            end
        end
    end
    initial begin
        #3000000;
        $fatal(1,"CPU/CNN timeout; status=%h starts=%0d outputs=%h/%h descriptor=%h pc=%h",dut.u_datasram.mem['h30/4],starts,dut.u_datasram.mem['h900/4],dut.u_datasram.mem['h904/4],dut.u_datasram.mem['h800/4],dut.imem_addr);
    end
endmodule
