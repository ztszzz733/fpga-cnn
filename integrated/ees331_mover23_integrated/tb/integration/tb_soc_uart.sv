`timescale 1ns/1ps
module tb_soc_uart;
    localparam integer DIV=8, BIT_NS=80;
    logic sys_clk=0, rst_n_in=0, uart_rx=1;
    wire uart_tx, led_ready, led_busy, led_error;
    always #5 sys_clk=~sys_clk;
    face_soc_top #(.CLOCK_HZ(800000),.BAUD(100000),.UART_TIMEOUT_CYCLES(2000),
        .IMEM_SIZE(256),.SRAM_SIZE(1024)) dut (.*);
    reg [7:0] request_bytes[0:271], response_bytes[0:4095];
    integer response_count=0, start_response, n, j;
    reg [7:0] sampled;
    reg [31:0] c;
    function automatic [31:0] crc_byte(input [31:0] old, input [7:0] value);
        reg [31:0] v; integer k;
        begin
            v=old^value;
            for(k=0;k<8;k=k+1) v=v[0] ? (v>>1)^32'hedb88320 : v>>1;
            crc_byte=v;
        end
    endfunction
    task send_byte(input [7:0] value);
        integer b;
        begin
            uart_rx=0; #(BIT_NS);
            for(b=0;b<8;b=b+1) begin uart_rx=value[b]; #(BIT_NS); end
            uart_rx=1; #(BIT_NS);
        end
    endtask
    initial forever begin
        @(negedge uart_tx); #(BIT_NS+BIT_NS/2);
        for(integer b=0;b<8;b=b+1) begin sampled[b]=uart_tx; #(BIT_NS); end
        if(uart_tx!==1) $fatal(1,"UART TX stop bit");
        response_bytes[response_count]=sampled; response_count=response_count+1;
    end
    task command(input integer op, len, addr, bad_crc);
        integer total,k;
        reg [31:0] checksum;
        begin
            wait(led_ready); start_response=response_count;
            $display("UART command op=%0d len=%0d addr=%h at %0t",op,len,addr,$time);
            request_bytes[0]='h49; request_bytes[1]='h4d;
            request_bytes[2]='h49; request_bytes[3]='h4f;
            request_bytes[4]=op; request_bytes[5]='h7b;
            request_bytes[6]=len; request_bytes[7]=len>>8;
            for(k=0;k<4;k=k+1) request_bytes[8+k]=addr>>(8*k);
            total=12+((op==1)?len:0); checksum=32'hffffffff;
            for(k=0;k<total;k=k+1) checksum=crc_byte(checksum,request_bytes[k]);
            checksum=~checksum ^ bad_crc;
            for(k=0;k<4;k=k+1) request_bytes[total+k]=checksum>>(8*k);
            for(k=0;k<total+4;k=k+1) send_byte(request_bytes[k]);
        end
    endtask
    task response(input integer status,len,addr);
        integer k; reg [31:0] checksum,actual;
        begin
            wait(response_count>=start_response+16+len);
            checksum=32'hffffffff;
            for(k=0;k<12+len;k=k+1) checksum=crc_byte(checksum,response_bytes[start_response+k]);
            actual=0;
            for(k=0;k<4;k=k+1) actual=actual | (32'(response_bytes[start_response+12+len+k])<<(8*k));
            if(actual!==~checksum) $fatal(1,"response CRC");
            if({response_bytes[start_response],response_bytes[start_response+1],
                response_bytes[start_response+2],response_bytes[start_response+3]}!==32'h494d4f52 ||
                response_bytes[start_response+4]!==status || response_bytes[start_response+5]!==8'h7b ||
                {response_bytes[start_response+7],response_bytes[start_response+6]}!==16'(len))
                $fatal(1,"response header status=%0d expected=%0d",response_bytes[start_response+4],status);
            for(k=0;k<4;k=k+1)
                if(response_bytes[start_response+8+k]!==8'(addr>>(8*k))) $fatal(1,"response address");
            #(BIT_NS*2);
        end
    endtask
    task reset_board;
        begin
            @(negedge sys_clk); rst_n_in=0; #1;
            if(dut.rst_n!==0) $fatal(1,"reset must assert asynchronously");
            repeat(4) @(negedge sys_clk);
            rst_n_in=1;
            repeat(2) begin @(posedge sys_clk); #1; if(dut.rst_n!==0) $fatal(1,"early reset release"); end
            @(posedge sys_clk); #1; if(dut.rst_n!==1) $fatal(1,"reset must release on third clock");
            wait(led_ready);
        end
    endtask
    initial begin
        for(n=0;n<64;n=n+1) dut.u_imem.mem[n]=32'h0000006f;
        for(n=0;n<256;n=n+1) dut.u_datasram.mem[n]=32'ha5a5a5a5;
        reset_board();
        for(n=0;n<256;n=n+1) request_bytes[12+n]=n;
        command(1,256,'h41,0); response(0,0,'h41);
        if(dut.u_datasram.mem['h40/4]!==32'h020100a5 || dut.u_datasram.mem['h140/4]!==32'ha5a5a5ff)
            $fatal(1,"unaligned byte writes damaged guards");
        command(2,256,'h41,0); response(0,256,'h41);
        for(n=0;n<256;n=n+1)
            if(response_bytes[start_response+12+n]!==8'(n)) $fatal(1,"UART readback byte %0d",n);
        request_bytes[12]='hff;
        command(1,1,'h50,1); response(1,0,'h50);
        if(dut.u_datasram.mem['h50/4][7:0]!==8'h0f || !led_error) $fatal(1,"bad CRC mutated SRAM");
        command(1,4,1022,0); response(3,0,1022);
        if(dut.u_datasram.mem[255]!==32'ha5a5a5a5) $fatal(1,"out-of-range partial write");
        command(9,1,64,0); response(2,0,64);
        // An incomplete packet times out and the next valid packet resynchronizes.
        send_byte('h49); send_byte('h4d); repeat(2100) @(negedge sys_clk);
        // Low stop bit / break is rejected, then a high idle restores RX.
        uart_rx=0; #(BIT_NS*12); uart_rx=1; #(BIT_NS*3);
        command(2,1,'h41,0); response(0,1,'h41);
        // Sustained CNN ownership initially delays the image request, then releases it.
        fork
            begin
                wait(dut.io_mem_req);
                force dut.mem_read=1; force dut.mem_write=0; force dut.mem_addr=32'h300;
                repeat(30) @(negedge sys_clk);
                force dut.mem_read=0;
                @(negedge sys_clk);
                release dut.mem_read; release dut.mem_write; release dut.mem_addr;
            end
            begin command(2,1,'h42,0); response(0,1,'h42); end
        join
        if(response_bytes[start_response+12]!==1) $fatal(1,"arbitrated read data");
        // CPU A wins a colliding write; UART receives explicit memory error.
        force dut.dmem_we=1; force dut.dmem_addr=32'h340;
        force dut.dmem_wdata=32'h12345678; force dut.dmem_wstrb=4'hf;
        command(1,1,'h340,0); response(4,0,'h340);
        release dut.dmem_we; release dut.dmem_addr; release dut.dmem_wdata; release dut.dmem_wstrb;
        // A granted read with no completion must not be attributed to a later packet.
        force dut.io_mem_rvalid=0;
        command(2,1,'h41,0); response(5,0,'h41);
        release dut.io_mem_rvalid;
        if(led_ready || !led_error) $fatal(1,"memory timeout must halt until reset");
        reset_board();
        if(led_error) $fatal(1,"reset did not clear fault");
        command(2,1,'h41,0); response(0,1,'h41);
        if(response_bytes[start_response+12]!==0) $fatal(1,"reset must preserve SRAM contents");
        $display("PASS tb_soc_uart six blocks, reset, serial 256-byte read/write, CRC, range, command, timeout, B contention, A collision, halt/recovery");
        $finish;
    end
    initial begin #2000000; $fatal(1,"UART test timeout state=%0d count=%0d expected=%0d rx_count=%0d start=%0d cnn_read=%b fault=%b",dut.u_image_bridge.state,dut.u_image_bridge.count,dut.u_image_bridge.expected,response_count,start_response,dut.mem_read,dut.cnn_mem_fault); end
endmodule
