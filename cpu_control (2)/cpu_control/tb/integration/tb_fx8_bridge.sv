`timescale 1ns/1ps
module tb_fx8_bridge;
    logic clk=0,rst_n=0;always #5 clk=~clk;
    logic [7:0] fx8_rx_data=0;
    logic fx8_rx_valid=0,fx8_tx_ready=0,load_req=0;
    wire fx8_clk,fx8_reset_n,fx8_rx_ready,fx8_tx_valid;
    wire [7:0] fx8_tx_data;
    wire load_complete,load_error,io_mem_req,io_mem_we,bridge_ready,bridge_busy,bridge_error;
    wire [31:0] io_mem_addr,io_mem_wdata;
    wire [3:0] io_mem_be;
    wire io_mem_gnt,io_mem_error;
    logic io_mem_rvalid=0;
    logic [31:0] io_mem_rdata=0;
    image_bridge_fx8 #(.TIMEOUT_CYCLES(600),.SRAM_SIZE(4096)) dut(.*);
    reg [7:0] memory[0:4095],request_bytes[0:15],reply[0:271];
    integer kind=0,ticks=0,writes=0,bytes_written=0,requests=0,expected_addr=0;
    logic stalled=0;
    reg [67:0] held_write;
    assign io_mem_gnt=io_mem_req && ticks%5==0 && !(kind==16 && io_mem_we);
    assign io_mem_error=kind==15 && io_mem_we;
    function automatic [7:0] payload(input integer addr);
        return (addr*37+(addr>>3)+19)&255;
    endfunction
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;
        c=old^value;for(integer k=0;k<8;k++) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
        return c;
    endfunction
    task automatic put_word(input integer addr,input reg [31:0] value);
        for(integer b=0;b<4;b++) memory[addr+b]=value>>(8*b);
    endtask
    always @(posedge clk) begin
        ticks<=ticks+1;io_mem_rvalid<=0;
        if(!rst_n) stalled<=0;
        else begin
            if(stalled && !bridge_error && (!io_mem_req || !io_mem_we || {io_mem_addr,io_mem_wdata,io_mem_be}!==held_write))
                $fatal(1,"SRAM write changed under backpressure");
            stalled<=io_mem_req && io_mem_we && !io_mem_gnt && !bridge_error;
            held_write<={io_mem_addr,io_mem_wdata,io_mem_be};
            if(io_mem_req && io_mem_gnt) begin
                if(io_mem_addr[1:0]!=0) $fatal(1,"unaligned SRAM transaction");
                if(io_mem_we) begin
                    if(io_mem_be==0) $fatal(1,"empty SRAM write");
                    if(!io_mem_error) begin
                        writes<=writes+1;bytes_written<=bytes_written+$countones(io_mem_be);
                        for(integer b=0;b<4;b++) if(io_mem_be[b]) memory[io_mem_addr+b]<=io_mem_wdata[8*b+:8];
                    end
                end else begin
                    if(io_mem_be!=0) $fatal(1,"read with byte enables");
                    io_mem_rdata<={memory[io_mem_addr+3],memory[io_mem_addr+2],memory[io_mem_addr+1],memory[io_mem_addr]};
                    io_mem_rvalid<=1;
                end
            end
        end
    end
    task automatic recv_byte(output reg [7:0] value);
        @(negedge fx8_clk);fx8_tx_ready=0;
        repeat(3) @(negedge fx8_clk);
        fx8_tx_ready=1;
        do @(posedge fx8_clk); while(!fx8_tx_valid);
        value=fx8_tx_data;
        @(negedge fx8_clk);fx8_tx_ready=0;
    endtask
    task automatic send_byte(input reg [7:0] value);
        @(negedge fx8_clk);fx8_rx_data=value;fx8_rx_valid=1;
        do @(posedge fx8_clk); while(!fx8_rx_ready);
        @(negedge fx8_clk);fx8_rx_valid=0;
    endtask
    task automatic peer(input integer count);
        integer addr,len;
        reg [31:0] crc;
        if(kind==14) begin wait(bridge_error);return;end
        while(expected_addr<count) begin
            for(integer b=0;b<16;b++) recv_byte(request_bytes[b]);
            crc=32'hffffffff;for(integer b=0;b<12;b++) crc=crc_byte(crc,request_bytes[b]);
            addr={request_bytes[11],request_bytes[10],request_bytes[9],request_bytes[8]};
            len={request_bytes[7],request_bytes[6]};
            if({request_bytes[0],request_bytes[1],request_bytes[2],request_bytes[3]}!==32'h494d494f ||
               request_bytes[4]!=2 || request_bytes[5]!=requests || addr!=expected_addr ||
               len!=((count-addr)>256 ? 256 : count-addr) ||
               {request_bytes[15],request_bytes[14],request_bytes[13],request_bytes[12]}!==~crc)
                $fatal(1,"bad read command");
            if(kind==13) begin wait(bridge_error);return;end
            reply[0]='h49;reply[1]='h4d;reply[2]='h4f;reply[3]='h52;
            reply[4]=0;reply[5]=request_bytes[5]+(kind==12 ? 1 : 0);
            reply[6]=len;reply[7]=len>>8;
            for(integer b=0;b<4;b++) reply[8+b]=addr>>(8*b);
            for(integer b=0;b<len;b++) reply[12+b]=payload(addr+b);
            crc=32'hffffffff;for(integer b=0;b<12+len;b++) crc=crc_byte(crc,reply[b]);
            crc=~crc;if(kind==10) crc=crc^1;
            for(integer b=0;b<4;b++) reply[12+len+b]=crc>>(8*b);
            // Sustained 25 MB/s response burst, one byte per link clock.
            @(negedge fx8_clk);fx8_rx_valid=1;
            for(integer b=0;b<16+len;b++) begin
                fx8_rx_data=reply[b];
                do @(posedge fx8_clk);while(!fx8_rx_ready);
                @(negedge fx8_clk);
            end
            fx8_rx_valid=0;
            expected_addr+=len;requests++;
        end
    endtask
    task automatic run_case(input integer mode,input integer dest,input integer count,input integer err);
        reg [31:0] crc;
        integer expected_words,pos,n;
        @(negedge clk);rst_n=0;load_req=0;fx8_tx_ready=0;fx8_rx_valid=0;kind=mode;
        writes=0;bytes_written=0;requests=0;expected_addr=0;
        for(integer i=0;i<4096;i++) memory[i]='ha5;
        crc=32'hffffffff;for(integer i=0;i<count;i++) crc=crc_byte(crc,payload(i));
        put_word('h60,32'h31444c49);put_word('h64,0);put_word('h68,dest);put_word('h6c,count);
        put_word('h70,~crc^(kind==11 ? 1 : 0));
        repeat(8) @(negedge clk);rst_n=1;
        repeat(20) @(negedge clk);load_req=1;
        fork
            peer(count);
            begin
                wait(load_complete);
            end
        join
        if(!load_complete || load_error!=(err!=0) || dut.u_loader.error_code!=err)
            $fatal(1,"case=%d completion error=%d expected=%d",mode,dut.u_loader.error_code,err);
        if(err==0 || err==8) begin
            expected_words=0;pos=0;
            while(pos<count) begin n=count-pos>256 ? 256 : count-pos;expected_words+=(((dest+pos)%4+n+3)/4);pos+=n;end
            if(bytes_written!=count || writes!=expected_words) $fatal(1,"packing count bytes=%d words=%d expected=%d",bytes_written,writes,expected_words);
            for(integer i=0;i<count;i++) if(memory[dest+i]!==payload(i)) $fatal(1,"payload mismatch byte=%d",i);
        end else if(bytes_written!=0) $fatal(1,"bad packet/failed store modified payload");
        for(integer i='h100;i<4096;i++) if((i<dest || i>=dest+count) && memory[i]!==8'ha5) $fatal(1,"guard modified %h",i);
        repeat(4) begin @(negedge clk);if(!load_complete) $fatal(1,"completion not held");end
        load_req=0;repeat(12) @(negedge clk);
        if(load_complete || (err!=0 ? !bridge_error || bridge_ready || fx8_rx_ready || fx8_tx_valid || fx8_reset_n : !bridge_ready || !fx8_reset_n))
            $fatal(1,"acknowledgement or fault lock failed");
        if(err!=0) begin
            // Late stale bytes must be rejected and must not resurrect SRAM writes.
            fx8_rx_valid=1;fx8_rx_data='hff;
            repeat(20) begin @(negedge fx8_clk);if(fx8_rx_ready || io_mem_req) $fatal(1,"late reply accepted after fault");end
            fx8_rx_valid=0;
        end
        $display("PASS fx8_bridge case=%d destination=%h bytes=%d error=%d writes=%d",mode,dest,count,err,writes);
    endtask
    initial begin
        run_case(0,'h200,256,0);run_case(0,'h201,1,0);run_case(0,'h202,7,0);
        run_case(0,'h203,2,0);run_case(0,'h203,257,0);run_case(0,'h201,405,0);
        run_case(10,'h200,17,5);run_case(11,'h200,17,8);run_case(12,'h200,17,4);
        run_case(13,'h200,17,3);run_case(14,'h200,17,3);
        run_case(15,'h200,17,6);run_case(16,'h200,17,7);
        run_case(0,'h200,3,0);
        $display("PASS tb_fx8_bridge: aligned/unaligned packing, tails, backpressure, CRC, timeouts, fault lock and reset recovery");$finish;
    end
    initial begin #5000000;$fatal(1,"bridge watchdog");end
endmodule
