`timescale 1ns/1ps
module tb_neureka_fx8_frames;
    logic sys_clk=0,rst_n_in=0;
    logic [7:0] fx8_rx_data=0;
    logic fx8_rx_valid=0,fx8_tx_ready=0;
    wire fx8_clk,fx8_reset_n,fx8_rx_ready,fx8_tx_valid;
    wire [7:0] fx8_tx_data;
    wire led_ready,led_busy,led_error;
    integer peer_ticks=0,word_writes=0;
    always @(negedge fx8_clk) peer_ticks<=peer_ticks+1;
    always #5 sys_clk=~sys_clk;
    face_soc_neureka_fx8_top #(.CLOCK_HZ(100000000),
        .LINK_TIMEOUT_CYCLES(2000),.CHUNK_BYTES(256),.IMEM_INIT_FILE("cpu.hex")) dut(.*);
    reg [31:0] initial_mem[0:65535];
    reg [7:0] external_memory[0:1619],golden[0:1819],request_bytes[0:15],reply_bytes[0:271];
    integer mode=0,jobs=0,starts=0,loads=0,writes=0,descriptor_reads=0,requests=0;
    integer simultaneous=0,cpu_overlap=0,bank_overlap=0,cycles=0;
    integer chunk_addr,chunk_len,frame_id,finish_writes;
    logic last_done=0,last_req=0;
    reg [31:0] crc;
    function automatic [31:0] word_at(input integer a);
        word_at=dut.u_datasram.mem[(a/4)%4][(a/4)/4];
    endfunction
    function automatic [7:0] byte_at(input integer a);
        byte_at=(word_at(a)>>(8*(a%4)))&255;
    endfunction
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;
        begin
            c=old^value;for(integer k=0;k<8;k++) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
            return c;
        end
    endfunction
    // Deliberate peer backpressure and gaps, with stable sender data until accepted.
    task automatic receive_byte(output reg [7:0] value);
        do begin
            @(negedge fx8_clk);fx8_tx_ready=(peer_ticks%7!=0);
            @(posedge fx8_clk);
        end while(!(fx8_tx_valid && fx8_tx_ready));
        value=fx8_tx_data;
        @(negedge fx8_clk);fx8_tx_ready=0;
    endtask
    task automatic send_byte(input [7:0] value);
        if(peer_ticks%11==0) repeat(3) @(negedge fx8_clk);
        @(negedge fx8_clk);fx8_rx_data=value;fx8_rx_valid=1;
        do @(posedge fx8_clk); while(!fx8_rx_ready);
        @(negedge fx8_clk);fx8_rx_valid=0;
    endtask
    initial begin
        if(!$value$plusargs("TEST_MODE=%d",mode)) mode=0;
        $readmemh("sram.hex",initial_mem);$readmemh("external.hex",external_memory);
        $readmemh("frames_golden.hex",golden);
        for(integer i=0;i<65536;i++) dut.u_datasram.mem[i%4][i/4]=initial_mem[i];
        repeat(8) @(negedge sys_clk);rst_n_in=1;
    end
    initial forever begin
        for(integer i=0;i<16;i++) receive_byte(request_bytes[i]);
        crc=32'hffffffff;
        for(integer i=0;i<12;i++) crc=crc_byte(crc,request_bytes[i]);
        if({request_bytes[15],request_bytes[14],request_bytes[13],request_bytes[12]}!==~crc ||
           {request_bytes[0],request_bytes[1],request_bytes[2],request_bytes[3]}!==32'h494d494f || request_bytes[4]!=2)
            $fatal(1,"bad FX8 request");
        chunk_addr={request_bytes[11],request_bytes[10],request_bytes[9],request_bytes[8]};
        chunk_len={request_bytes[7],request_bytes[6]};frame_id=chunk_addr/405;
        if(chunk_addr!=((requests/2)*405+(requests%2)*256) ||
           chunk_len!=(requests%2==1 ? 149 : 256) || frame_id>3 || request_bytes[5]!==8'(requests))
            $fatal(1,"wrong next-frame request addr=%h len=%d request=%d tag=%h",chunk_addr,chunk_len,requests,request_bytes[5]);
        requests++;
        #240;
        reply_bytes[0]='h49;reply_bytes[1]='h4d;reply_bytes[2]='h4f;reply_bytes[3]='h52;
        reply_bytes[4]=0;reply_bytes[5]=request_bytes[5];
        reply_bytes[6]=chunk_len;reply_bytes[7]=chunk_len>>8;
        for(integer i=0;i<4;i++) reply_bytes[8+i]=chunk_addr>>(8*i);
        for(integer i=0;i<chunk_len;i++) reply_bytes[12+i]=external_memory[chunk_addr+i];
        // Valid packet CRC with deliberately bad whole-frame contents on frame 1.
        if(mode==1 && chunk_addr==405) reply_bytes[12]=reply_bytes[12]^1;
        crc=32'hffffffff;
        for(integer i=0;i<12+chunk_len;i++) crc=crc_byte(crc,reply_bytes[i]);
        crc=~crc;
        for(integer i=0;i<4;i++) reply_bytes[12+chunk_len+i]=crc>>(8*i);
        for(integer i=0;i<16+chunk_len;i++) send_byte(reply_bytes[i]);
    end
    always @(posedge sys_clk) if(dut.rst_n) begin
        cycles++;
        last_req<=dut.load_req;last_done<=dut.u_cnn.pipe_done;
        if(dut.load_req && !last_req) begin
            if(loads>=2 && word_at('h88)<loads-1) $fatal(1,"reused unconsumed frame slot");
            loads++;
        end
        if(dut.u_cnn.scheduler.cfg_we && dut.u_cnn.scheduler.cfg_addr==32'h40000000 && dut.u_cnn.scheduler.cfg_wdata==1) starts++;
        if(dut.u_cnn.pipe_busy && dut.bridge_busy) simultaneous++;
        if(dut.u_cnn.pipe_busy && (dut.dmem_re || dut.dmem_we)) cpu_overlap++;
        if(dut.io_mem_req && dut.io_mem_gnt) begin
            if(dut.io_mem_we) begin
                if(dut.io_mem_error) $fatal(1,"image SRAM error");
                if(dut.io_mem_addr<32'h2000 || dut.io_mem_addr>=32'h3198) $fatal(1,"image overwrote metadata or output");
                if(dut.u_cnn.pipe_busy && dut.io_mem_addr>=32'h2000+((starts-1)%2)*32'h1000 &&
                   dut.io_mem_addr<32'h2000+((starts-1)%2)*32'h1000+405)
                    $fatal(1,"image overwrote active CNN input");
                writes+=$countones(dut.io_mem_be);word_writes++;
            end else descriptor_reads++;
            if((dut.dmem_re || dut.dmem_we) && |(dut.cnn_valid&dut.cnn_ready)) bank_overlap++;
        end
        if(dut.u_cnn.pipe_done && !last_done) begin
            if(dut.u_cnn.pipe_fault) $fatal(1,"CNN scheduler fault");
            for(integer i=0;i<455;i++) if(byte_at('h12000+(jobs%2)*'h1000+i)!==golden[jobs*455+i])
                $fatal(1,"frame result mismatch frame=%d byte=%d actual=%h expected=%h",jobs,i,
                    byte_at('h12000+(jobs%2)*'h1000+i),golden[jobs*455+i]);
            if(byte_at('h11fff)!==8'ha5 || byte_at('h121c7)!==8'ha5 || byte_at('h12fff)!==8'ha5 || byte_at('h131c7)!==8'ha5)
                $fatal(1,"output guard overwritten");
            jobs++;
        end
        if(dut.cnn_mem_fault || dut.cnn_fault) $fatal(1,"unexpected CNN memory/control fault");
        if(word_at('h80)==32'h600dcafe) begin
            if(mode!=0 || jobs!=4 || starts!=4 || loads!=4 || writes!=1620 || descriptor_reads!=20 || requests!=8 || word_writes!=408 ||
               simultaneous==0 || cpu_overlap==0 || word_at('h8c)==0 || dut.load_req || dut.load_complete || led_error)
                $fatal(1,"incomplete frame overlap jobs=%d starts=%d loads=%d writes=%d reads=%d work=%d",jobs,starts,loads,writes,descriptor_reads,word_at('h8c));
            $display("FRAME_METRICS overlap=%d cpu_access_while_cnn=%d three_way_bank_access=%d cpu_result_work=%d",simultaneous,cpu_overlap,bank_overlap,word_at('h8c));
            $display("PASS tb_neureka_fx8_frames mode=0: main CPU, FX8 bridge, banked SRAM, mailbox and frame scheduling");$finish;
        end
        if((word_at('h80)>>16)==16'hdead) begin
            if(mode!=1 || word_at('h80)!=32'hdead0006 || word_at('h90)!=32'hffffffed ||
               starts>1 || loads!=2 || !led_error || dut.load_req || dut.load_complete)
                $fatal(1,"unexpected firmware failure code=%h detail=%h starts=%d loads=%d",word_at('h80),word_at('h90),starts,loads);
            $display("PASS tb_neureka_fx8_frames mode=1: bad next frame never submitted to CNN, ownership frozen");$finish;
        end
        if(cycles>2000000) $fatal(1,"watchdog PC=%h finish=%h jobs=%d loads=%d bridge=%d",dut.imem_addr,word_at('h80),jobs,loads,dut.u_image_bridge.u_loader.state);
    end
endmodule
