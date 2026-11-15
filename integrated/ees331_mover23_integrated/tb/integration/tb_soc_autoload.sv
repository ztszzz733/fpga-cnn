`timescale 1ns/1ps
// External device model drives only board reset and UART pins. It never writes
// DUT instruction/data arrays or forces internal request/state signals.
module tb_soc_autoload;
    parameter integer CHUNK_BYTES=64;
    localparam integer BIT_NS=80;
    logic sys_clk=0, rst_n_in=0, uart_rx=1;
    wire uart_tx,led_ready,led_busy,led_error;
    always #5 sys_clk=~sys_clk;
    face_soc_autoload_top #(.CLOCK_HZ(100000000),.BAUD(12500000),.UART_TIMEOUT_CYCLES(2000),
        .CHUNK_BYTES(CHUNK_BYTES),
        .IMEM_SIZE(4096),.SRAM_SIZE(4096),.IMEM_INIT_FILE("autoload_program.mem")) dut (.*);
    reg [7:0] external_memory[0:255];
    reg [7:0] request_bytes[0:15], reply_bytes[0:271];
    integer mode=0, request_count=0, writes=0, starts=0, cnn_writes=0, cnn_reads=0;
    integer req_edges=0, complete_edges=0, held_cycles=0, chunk_addr, chunk_len, writes_at_finish;
    logic last_req=0,last_complete=0;
    reg [31:0] crc, actual, finish_value=0;
    logic finished=0;

    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;
        begin
            c=old^value;
            for(integer k=0;k<8;k=k+1) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
            crc_byte=c;
        end
    endfunction
    task automatic receive_byte(output reg [7:0] value);
        begin
            @(negedge uart_tx); #(BIT_NS+BIT_NS/2);
            for(integer b=0;b<8;b=b+1) begin value[b]=uart_tx; #(BIT_NS); end
            if(uart_tx!==1) $fatal(1,"external peer: invalid TX stop bit");
        end
    endtask
    task automatic send_byte(input [7:0] value);
        begin
            uart_rx=0; #(BIT_NS);
            for(integer b=0;b<8;b=b+1) begin uart_rx=value[b]; #(BIT_NS); end
            uart_rx=1; #(BIT_NS);
        end
    endtask

    initial begin
        if (!$value$plusargs("TEST_MODE=%d",mode)) mode=0;
        $readmemh("autoload_external.mem",external_memory);
        repeat(6) @(negedge sys_clk);
        rst_n_in=1;
        $display("FLOW POWER_ON reset released, test_mode=%0d",mode);
    end

    // Compatible autonomous UART storage device: respond only after the FPGA
    // asks for a block. No PC action or simulation-side CNN MMIO commands.
    initial begin
        forever begin
            for(integer i=0;i<16;i=i+1) receive_byte(request_bytes[i]);
            crc=32'hffffffff;
            for(integer i=0;i<12;i=i+1) crc=crc_byte(crc,request_bytes[i]);
            actual={request_bytes[15],request_bytes[14],request_bytes[13],request_bytes[12]};
            if(actual!==~crc || {request_bytes[0],request_bytes[1],request_bytes[2],request_bytes[3]}!==32'h494d494f ||
               request_bytes[4]!==2) $fatal(1,"external peer: bad request or CRC");
            chunk_addr={request_bytes[11],request_bytes[10],request_bytes[9],request_bytes[8]};
            chunk_len={request_bytes[7],request_bytes[6]};
            if(chunk_len!=((256-request_count*CHUNK_BYTES < CHUNK_BYTES) ?
                          256-request_count*CHUNK_BYTES : CHUNK_BYTES) ||
               chunk_addr!=request_count*CHUNK_BYTES || request_bytes[5]!==8'(request_count))
                $fatal(1,"unexpected or repeated external read addr=%h length=%0d count=%0d",chunk_addr,chunk_len,request_count);
            request_count=request_count+1;
            $display("FLOW UART_READ chunk=%0d source=%h bytes=%0d time=%0t",request_count,chunk_addr,chunk_len,$time);
            // Case 2 deliberately replies after the loader has timed out.
            if(mode==2) #(100000);
            else #(BIT_NS*3);
            reply_bytes[0]='h49;reply_bytes[1]='h4d;reply_bytes[2]='h4f;reply_bytes[3]='h52;
            reply_bytes[4]=0;reply_bytes[5]=request_bytes[5];
            if(mode==4) reply_bytes[5]=request_bytes[5]+1;
            reply_bytes[6]=chunk_len;reply_bytes[7]=chunk_len>>8;
            for(integer i=0;i<4;i=i+1) reply_bytes[8+i]=chunk_addr>>(8*i);
            for(integer i=0;i<chunk_len;i=i+1) reply_bytes[12+i]=external_memory[chunk_addr+i];
            if(mode==3 && chunk_addr==0) reply_bytes[12]=2; // valid packet CRC, wrong whole-batch CRC
            crc=32'hffffffff;
            for(integer i=0;i<12+chunk_len;i=i+1) crc=crc_byte(crc,reply_bytes[i]);
            crc=~crc;
            if(mode==1 && request_count==2) crc=crc^1;
            for(integer i=0;i<4;i=i+1) reply_bytes[12+chunk_len+i]=crc>>(8*i);
            for(integer i=0;i<16+chunk_len;i=i+1) send_byte(reply_bytes[i]);
        end
    end

    always @(posedge sys_clk) if(dut.rst_n) begin
        if(dut.cnn_mem_fault) $fatal(1,"unexpected CNN SRAM fault");
        if(dut.load_req && !last_req) begin
            req_edges=req_edges+1;
            $display("FLOW CPU_LOAD_REQUEST time=%0t",$time);
        end
        if(dut.load_complete && !last_complete) begin
            complete_edges=complete_edges+1;
            if(mode==0 && (writes!=256 || dut.load_error)) $fatal(1,"early/failed load completion");
            if(mode!=0 && !dut.load_error) $fatal(1,"error case reported success");
            $display("FLOW LOAD_COMPLETE error=%0b writes=%0d code=%0d time=%0t",dut.load_error,writes,dut.u_image_bridge.error_code,$time);
        end
        if(last_complete && last_req && !dut.load_complete) $fatal(1,"completion did not remain held");
        if(dut.load_complete && dut.load_req) held_cycles=held_cycles+1;
        last_req=dut.load_req; last_complete=dut.load_complete;
        if(dut.io_mem_req && dut.io_mem_gnt) begin
            if(dut.io_mem_error || !dut.io_mem_we || dut.io_mem_addr!==32'(('h100+writes)&~3) ||
               dut.io_mem_be!==(4'b1<<(writes%4))) $fatal(1,"bad autoload SRAM write");
            if(((dut.io_mem_wdata>>(8*(writes%4)))&255)!==
               ((mode==3 && writes==0) ? 32'd2 : {24'b0,external_memory[writes]}))
                $fatal(1,"UART data not preserved at byte %0d",writes);
            writes=writes+1;
        end
        if(dut.dmem_re || dut.dmem_we) begin
            if(dut.dmem_addr>=32'h40 && dut.dmem_addr<32'h48)
                $fatal(1,"CPU-local register leaked onto SRAM port");
        end
        if(dut.dmem_we) begin
            if(dut.dmem_addr>=32'h100 && dut.dmem_addr<32'h200)
                $fatal(1,"CPU must not manufacture the external dataset");
            if(dut.dmem_addr==32'h88 && dut.dmem_wdata!=0) begin
                finish_value=dut.dmem_wdata; finished=1;
                $display("FLOW CPU_FINISH value=%h time=%0t",finish_value,$time);
            end
        end
        if(dut.cnn_mmio_we && dut.cnn_mmio_ready && dut.cnn_mmio_addr==32'h40000000 && dut.cnn_mmio_wdata==32'h3d) begin
            if(mode!=0 || writes!=256 || dut.load_req || dut.load_complete)
                $fatal(1,"CNN started before a successfully acknowledged load");
            starts=starts+1;
            $display("FLOW CPU_CNN_START time=%0t",$time);
        end
        if(dut.mem_ready && dut.mem_write) cnn_writes=cnn_writes+1;
        if(dut.mem_ready && dut.mem_read) cnn_reads=cnn_reads+1;
    end

    initial begin
        wait(finished); @(negedge sys_clk);
        if(req_edges!=1 || complete_edges!=1 || held_cycles<8 || dut.load_req || dut.load_complete)
            $fatal(1,"three-wire handshake incomplete or repeated");
        if(mode==0) begin
            if(finish_value!==32'h600d || request_count!=(256+CHUNK_BYTES-1)/CHUNK_BYTES || writes!=256 || starts!=1 || cnn_writes!=4 || cnn_reads<12)
                $fatal(1,"flow failed: finish=%h requests=%0d writes=%0d starts=%0d cnn_wr=%0d cnn_rd=%0d",finish_value,request_count,writes,starts,cnn_writes,cnn_reads);
            if(dut.u_datasram.mem['h80/4]!==32'h09ff05a5 || dut.u_datasram.mem['h84/4]!==32'ha5a5a50b || led_error)
                $fatal(1,"CPU did not return the expected 2x2 convolution and guards");
            $display("RESULT input=[1,-2,3,4] weight=2 bias=3 output=[5,-1,9,11]");
        end else begin
            if(finish_value!==32'hdead0001 || starts!=0 || cnn_writes!=0 || !led_error)
                $fatal(1,"bad load did not stop firmware before CNN start");
            if((mode==1 && (request_count!=2 || writes!=64)) ||
               (mode==2 && (request_count!=1 || writes!=0)) ||
               (mode==3 && (request_count!=4 || writes!=256)) ||
               (mode==4 && (request_count!=1 || writes!=0)))
                $fatal(1,"wrong rejection boundary mode=%0d requests=%0d writes=%0d",mode,request_count,writes);
        end
        // Wait through the timeout test's late reply; no unsolicited restarts.
        writes_at_finish=writes;
        #(200000);
        if(dut.io_mem_req || writes!=writes_at_finish || req_edges!=1 || complete_edges!=1)
            $fatal(1,"late reply/repeated request was accepted");
        $display("PASS tb_soc_autoload mode=%0d UART_requests=%0d SRAM_bytes=%0d CNN_starts=%0d CNN_writes=%0d",mode,request_count,writes,starts,cnn_writes);
        $finish;
    end
    initial begin #10000000; $fatal(1,"autoload test watchdog state=%0d PC=%h",dut.u_image_bridge.state,dut.imem_addr); end
endmodule
