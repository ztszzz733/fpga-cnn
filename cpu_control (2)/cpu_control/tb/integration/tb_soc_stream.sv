`timescale 1ns/1ps
module tb_soc_stream;
    parameter integer WIDTH=524,HEIGHT=524,FRAMES=6,CHUNK=1024,FAULT=0;
    localparam integer N=WIDTH*HEIGHT,TOTAL=N*FRAMES,OW=(WIDTH-2)/2,OH=(HEIGHT-2)/2,
                       FRAME_BYTES=OW*OH*2,RESULT_BYTES=FRAME_BYTES*FRAMES,BIT_NS=40;
    logic sys_clk=0,rst_n_in=0,uart_rx=1;
    wire uart_tx,led_ready,led_busy,led_error;
    always #5 sys_clk=~sys_clk;
    face_soc_stream_top #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.FRAMES(FRAMES),.CHUNK(CHUNK)) dut(.*);
    reg [7:0] external_memory[0:TOTAL-1],expected[0:RESULT_BYTES-1];
    reg [7:0] request_bytes[0:15],reply_bytes[0:CHUNK+15];
    integer requests=0,received_payload=0,consumed=0,checked_frames=0,write_count=0;
    integer cycles=0,rx_compute_overlap=0,compute_cycles=0,rx_write_overlap=0;
    integer f,offset,chunk_len,chunk_addr,frame_first[0:FRAMES-1],frame_last_rx[0:FRAMES-1];
    integer events,fd,word,bank,idx;
    reg [31:0] crc,actual,expected_checksum=0;
    reg finished=0,host_payload_active=0;
    reg [7:0] stalled_data;reg stalled=0;
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;
        begin c=old^value;for(integer k=0;k<8;k++) c=c[0] ? (c>>1)^32'hedb88320:c>>1;return c;end
    endfunction
    function automatic [7:0] result_byte(input integer address);
        integer w;
        begin w=address/4;return dut.u_datasram.mem[w%4][w/4]>>(8*(address%4));end
    endfunction
    task automatic receive_byte(output reg [7:0] value);
        @(negedge uart_tx);#(BIT_NS+BIT_NS/2);
        for(integer b=0;b<8;b++) begin value[b]=uart_tx;#(BIT_NS);end
        if(uart_tx!==1) $fatal(1,"UART request bad stop");
    endtask
    task automatic send_byte(input [7:0] value);
        uart_rx=0;#(BIT_NS);
        for(integer b=0;b<8;b++) begin uart_rx=value[b];#(BIT_NS);end
        uart_rx=1;#(BIT_NS);
    endtask
    initial begin
        $readmemh("external.mem",external_memory);$readmemh("expected.mem",expected);
        for(integer j=0;j<FRAMES;j++) begin frame_first[j]=-1;frame_last_rx[j]=-1;end
        for(integer j=0;j<RESULT_BYTES;j+=2) expected_checksum+=expected[j]+(32'(expected[j+1])<<8);
        events=$fopen("events.csv","w");$fdisplay(events,"cycle,event,frame,value");
`ifdef DUMP_WAVES
        $dumpfile("wave.fst");$dumpvars(1,dut);
`endif
        repeat(6) @(negedge sys_clk);rst_n_in=1;
    end
    // Image data enters exclusively via UART pins. Hierarchical RAM access is read-only checking.
    initial forever begin
        for(integer j=0;j<16;j++) receive_byte(request_bytes[j]);
        crc=32'hffffffff;for(integer j=0;j<12;j++) crc=crc_byte(crc,request_bytes[j]);
        actual={request_bytes[15],request_bytes[14],request_bytes[13],request_bytes[12]};
        chunk_addr={request_bytes[11],request_bytes[10],request_bytes[9],request_bytes[8]};
        chunk_len={request_bytes[7],request_bytes[6]};f=received_payload/N;offset=received_payload%N;
        if(actual!==~crc || {request_bytes[0],request_bytes[1],request_bytes[2],request_bytes[3]}!==32'h494d494f ||
           request_bytes[4]!=2 || request_bytes[5]!=(requests%256) || chunk_addr!=received_payload ||
           chunk_len!=((N-offset<CHUNK)?N-offset:CHUNK)) $fatal(1,"bad request %0d",requests);
        requests++;
        if(FAULT==2 && requests==3) begin wait(finished);end
        #(BIT_NS*3);
        reply_bytes[0]='h49;reply_bytes[1]='h4d;reply_bytes[2]='h4f;reply_bytes[3]='h52;
        reply_bytes[4]=0;reply_bytes[5]=request_bytes[5];reply_bytes[6]=chunk_len;reply_bytes[7]=chunk_len>>8;
        for(integer j=0;j<4;j++) reply_bytes[8+j]=chunk_addr>>(8*j);
        for(integer j=0;j<chunk_len;j++) reply_bytes[12+j]=external_memory[chunk_addr+j];
        crc=32'hffffffff;for(integer j=0;j<12+chunk_len;j++) crc=crc_byte(crc,reply_bytes[j]);crc=~crc;
        if(FAULT==1 && requests==3) crc^=1;
        for(integer j=0;j<4;j++) reply_bytes[12+chunk_len+j]=crc>>(8*j);
        for(integer j=0;j<16+chunk_len;j++) begin
            host_payload_active=j>=12 && j<12+chunk_len;send_byte(reply_bytes[j]);
            if(host_payload_active) begin
                received_payload++;
                if(received_payload%N==0) begin
                    frame_last_rx[f]=cycles;$fdisplay(events,"%0d,last_uart_pixel,%0d,%0d",cycles,f,received_payload);
                end
            end
        end
        host_payload_active=0;
    end
    always @(posedge sys_clk) if(dut.rst_n) begin
        cycles++;
        if(cycles>TOTAL*80+RESULT_BYTES*40+1000000) $fatal(1,"simulation timeout");
        if(stalled && !dut.bridge_error) begin
            assert(dut.pixel_valid && dut.pixel_data==stalled_data) else $fatal(1,"unstable stalled pixel");
        end
        stalled=dut.pixel_valid && !dut.pixel_ready;stalled_data=dut.pixel_data;
        if(dut.pixel_valid && dut.pixel_ready) begin
            assert(dut.pixel_data===external_memory[consumed] && dut.pixel_frame==consumed/N)
                else $fatal(1,"pixel ordering mismatch %0d",consumed);
            consumed++;
        end
        if(dut.compute_fire) begin
            compute_cycles++;
            if(frame_first[dut.frames_done]<0) begin
                frame_first[dut.frames_done]=cycles;
                $fdisplay(events,"%0d,first_compute,%0d,%0d",cycles,dut.frames_done,received_payload);
            end
            if(host_payload_active && dut.rx_receiving) rx_compute_overlap++;
        end
        for(integer c=0;c<2;c++) if(dut.cnn_valid[c] && dut.cnn_ready[c]) begin
            write_count++;
            assert(dut.cnn_addr[c*32+:32]>=4096 && dut.cnn_addr[c*32+:32]<4096+RESULT_BYTES)
                else $fatal(1,"output address outside allocation");
            if(host_payload_active && dut.rx_receiving) rx_write_overlap++;
        end
        if(dut.frame_done) begin
            assert(dut.frames_done==checked_frames+1) else $fatal(1,"frame ordering");
            for(integer j=0;j<FRAME_BYTES;j++) begin
                if(result_byte(4096+checked_frames*FRAME_BYTES+j)!==expected[checked_frames*FRAME_BYTES+j])
                    $fatal(1,"feature mismatch frame=%0d byte=%0d got=%h expected=%h",checked_frames,j,
                           result_byte(4096+checked_frames*FRAME_BYTES+j),expected[checked_frames*FRAME_BYTES+j]);
            end
            $fdisplay(events,"%0d,frame_done,%0d,%0d",cycles,checked_frames,FRAME_BYTES);
            $display("FRAME_PASS frame=%0d cycle=%0d first_compute=%0d last_uart_pixel=%0d",checked_frames,cycles,
                     frame_first[checked_frames],frame_last_rx[checked_frames]);
            checked_frames++;
        end
        if(dut.dmem_we && dut.dmem_addr==32'h88 && dut.dmem_wdata!=0) begin
            if(FAULT!=0) begin
                assert(dut.dmem_wdata==32'hdead0001 && dut.bridge_error && !dut.u_cnn.done_sticky)
                    else $fatal(1,"fault was not rejected");
                assert(consumed<=CHUNK*2) else $fatal(1,"bad packet leaked pixels");
                finished=1;
            end else begin
                assert(dut.dmem_wdata==32'h600d && checked_frames==FRAMES && consumed==TOTAL && write_count==RESULT_BYTES)
                    else $fatal(1,"final accounting failed");
                assert(dut.u_datasram.mem[0][8]===expected_checksum) else $fatal(1,"CPU checksum mismatch");
                assert(compute_cycles==(WIDTH-2)*(HEIGHT-2)*FRAMES) else $fatal(1,"compute count mismatch");
                if(N>CHUNK*3) begin
                    for(integer j=0;j<FRAMES;j++) assert(frame_first[j]<frame_last_rx[j]) else $fatal(1,"not same-frame streaming");
                    if(CHUNK>=1024) assert(rx_compute_overlap>0 && rx_write_overlap>0) else $fatal(1,"no real UART RX/compute overlap");
                end
                fd=$fopen("actual.bin","wb");
                for(integer j=0;j<RESULT_BYTES;j++) $fwrite(fd,"%c",result_byte(4096+j));
                $fclose(fd);finished=1;
            end
        end
    end
    initial begin
        wait(finished);
        if(FAULT!=0) begin
            repeat(20) @(negedge sys_clk);rst_n_in=0;repeat(5) @(negedge sys_clk);
            assert(dut.soc_fault==0 && dut.soc_module_state==0) else $fatal(1,"fault reset failed");
        end
        $display("METRICS frames=%0d pixels=%0d outputs=%0d requests=%0d compute_cycles=%0d rx_compute_overlap=%0d rx_write_overlap=%0d total_cycles=%0d",checked_frames,consumed,write_count,requests,compute_cycles,rx_compute_overlap,rx_write_overlap,cycles);
        $display("PASS tb_soc_stream");$fclose(events);$finish;
    end
endmodule
