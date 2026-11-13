`timescale 1ns/1ps
module tb_soc_overlap;
    parameter integer ENABLE_OVERLAP=1, BANKS=4;
    parameter bit OBSERVE_FAULT=0;
    parameter integer UART_BAUD=25000000, UART_CHUNK_BYTES=256;
    `include "overlap_vectors.svh"
    localparam integer BIT_NS=10*(100000000/UART_BAUD);
    logic sys_clk=0,rst_n_in=0,uart_rx=1;
    wire uart_tx,led_ready,led_busy,led_error;
    always #5 sys_clk=~sys_clk;
`ifdef ORIGINAL_SOC
    face_soc_autoload_top #(
`else
    face_soc_overlap_top #(.BANKS(BANKS),.ENABLE_OVERLAP(ENABLE_OVERLAP),
`endif
        .CLOCK_HZ(100000000),.BAUD(UART_BAUD),.CHUNK_BYTES(UART_CHUNK_BYTES),.UART_TIMEOUT_CYCLES(10000),
        .LOAD_BYTES(LOAD_BYTES),.EXPECTED_CRC32(DEMO_CRC),
        .IMEM_SIZE(4096),.SRAM_SIZE(16384),.IMEM_INIT_FILE("program.mem")) dut (.*);
    reg [7:0] external_memory[0:LOAD_BYTES-1],request_bytes[0:15],reply_bytes[0:271];
    reg [31:0] expected[0:LOAD_BYTES/4-1];
    integer request_count=0,chunk_addr,chunk_len,cycles=0,start_cycle=-1,done_cycle=-1;
    integer dispatched=0,completed=0,load_compute=0,store_compute=0,load_store=0,multi_bank=0,max_grants=0;
    integer own_load_compute=0,own_store_compute=0,compute_cycles=0,multi_active=0,hazard_cycles=0;
    integer mac_ops=0,peak_active=0;
    integer timeline,finish_value=0,grants,active_units,writes=0,starts=0;
    integer load_start_cycle=-1,load_done_cycle=-1;
    reg finished=0,ld_fire,st_fire;
    reg [31:0] crc,actual,observed;
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;
        begin c=old^value;for(integer k=0;k<8;k=k+1) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;crc_byte=c;end
    endfunction
    task automatic receive_byte(output reg [7:0] value);
        begin
            @(negedge uart_tx);#(BIT_NS+BIT_NS/2);
            for(integer b=0;b<8;b=b+1) begin value[b]=uart_tx;#(BIT_NS);end
            if(uart_tx!==1) $fatal(1,"bad UART stop");
        end
    endtask
    task automatic send_byte(input [7:0] value);
        begin
            uart_rx=0;#(BIT_NS);
            for(integer b=0;b<8;b=b+1) begin uart_rx=value[b];#(BIT_NS);end
            uart_rx=1;#(BIT_NS);
        end
    endtask
    initial begin
`ifdef DUMP_WAVES
`ifdef TOP_WAVES
        $dumpfile("wave.vcd");$dumpvars(0,dut);
`else
        // Start at CNN submission to keep the lengthy UART preload out of this trace.
        wait(start_cycle>=0);$dumpfile("wave.vcd");$dumpvars(0,dut.u_cnn);
`endif
`endif
    end
    initial begin
        $readmemh("external.mem",external_memory);$readmemh("expected.mem",expected);
        timeline=$fopen("events.csv","w");$fdisplay(timeline,"cycle,event,task_id,unit");
        repeat(6) @(negedge sys_clk);rst_n_in=1;
    end
    // Only external pins provide the dataset. No hierarchical memory writes.
    initial forever begin
        for(integer i=0;i<16;i=i+1) receive_byte(request_bytes[i]);
        crc=32'hffffffff;
        for(integer i=0;i<12;i=i+1) crc=crc_byte(crc,request_bytes[i]);
        actual={request_bytes[15],request_bytes[14],request_bytes[13],request_bytes[12]};
        chunk_addr={request_bytes[11],request_bytes[10],request_bytes[9],request_bytes[8]};
        chunk_len={request_bytes[7],request_bytes[6]};
        if(actual!==~crc || {request_bytes[0],request_bytes[1],request_bytes[2],request_bytes[3]}!==32'h494d494f ||
           request_bytes[4]!=2 || chunk_addr!=request_count*UART_CHUNK_BYTES ||
           chunk_len!=((LOAD_BYTES-chunk_addr<UART_CHUNK_BYTES) ? LOAD_BYTES-chunk_addr : UART_CHUNK_BYTES) ||
           chunk_addr+chunk_len>LOAD_BYTES)
            $fatal(1,"bad external load request");
        request_count=request_count+1;
        #(BIT_NS*3);
        reply_bytes[0]='h49;reply_bytes[1]='h4d;reply_bytes[2]='h4f;reply_bytes[3]='h52;
        reply_bytes[4]=0;reply_bytes[5]=request_bytes[5];reply_bytes[6]=chunk_len;reply_bytes[7]=chunk_len>>8;
        for(integer i=0;i<4;i=i+1) reply_bytes[8+i]=chunk_addr>>(8*i);
        for(integer i=0;i<chunk_len;i=i+1) reply_bytes[12+i]=external_memory[chunk_addr+i];
        crc=32'hffffffff;
        for(integer i=0;i<12+chunk_len;i=i+1) crc=crc_byte(crc,reply_bytes[i]);
        crc=~crc;
        for(integer i=0;i<4;i=i+1) reply_bytes[12+chunk_len+i]=crc>>(8*i);
        if(!OBSERVE_FAULT)
            for(integer i=0;i<16+chunk_len;i=i+1) send_byte(reply_bytes[i]);
    end
    always @(posedge sys_clk) if(dut.rst_n) begin
        cycles=cycles+1;
        if(dut.load_req && load_start_cycle<0) load_start_cycle=cycles;
        if(dut.load_complete && load_done_cycle<0) load_done_cycle=cycles;
        if(led_error && !OBSERVE_FAULT) $fatal(1,"system error: bridge=%b memory=%b",dut.bridge_error,dut.cnn_mem_fault);
        if(dut.io_mem_req && dut.io_mem_gnt && dut.io_mem_we) writes=writes+1;
        if(dut.cnn_mmio_we && dut.cnn_mmio_ready && dut.cnn_mmio_addr==32'h40000000 && dut.cnn_mmio_wdata==32'h3d) begin
            if(writes!=LOAD_BYTES || dut.load_req || dut.load_complete) $fatal(1,"premature CNN start");
            start_cycle=cycles;starts=starts+1;
        end
        if(dut.u_cnn.exec_start) begin
            dispatched=dispatched+1;
            for(integer u=0;u<8;u=u+1) if(dut.u_cnn.unit_start[u])
                $fdisplay(timeline,"%0d,dispatch,%0d,%0d",cycles,dut.u_cnn.dispatch_id,u);
        end
        for(integer u=0;u<8;u=u+1) if(dut.u_cnn.unit_done[u] && dut.u_cnn.unit_allocated[u]) begin
            completed=completed+1;
            $fdisplay(timeline,"%0d,complete,%0d,%0d",cycles,dut.u_cnn.unit_task_ids[u*32+:32],u);
        end
        if(dut.u_cnn.queue_done && done_cycle<0) done_cycle=cycles;
        if(start_cycle>=0 && done_cycle<0) begin
            active_units=$countones(dut.u_cnn.unit_busy);
            if(active_units>peak_active) peak_active=active_units;
            mac_ops=mac_ops+$countones(dut.u_cnn.pe_fire_map);
            if(active_units>1) multi_active=multi_active+1;
            if(dut.u_cnn.hazard_wait) hazard_cycles=hazard_cycles+1;
            if(|dut.u_cnn.pe_fire_map) compute_cycles=compute_cycles+1;
`ifndef ORIGINAL_SOC
            grants=$countones(dut.cnn_valid & dut.cnn_ready);
            if(grants>max_grants) max_grants=grants;
            if(grants>1) multi_bank=multi_bank+1;
            ld_fire=(dut.cnn_valid[1] && dut.cnn_ready[1]) || (dut.cnn_valid[3] && dut.cnn_ready[3]);
            st_fire=(dut.cnn_valid[2] && dut.cnn_ready[2]) || (dut.cnn_valid[4] && dut.cnn_ready[4]);
            if(ld_fire && |dut.u_cnn.pe_fire_map) load_compute=load_compute+1;
            if(st_fire && |dut.u_cnn.pe_fire_map) store_compute=store_compute+1;
            if(ld_fire && st_fire) load_store=load_store+1;
            if((dut.cnn_valid[1] && dut.cnn_ready[1] && |(dut.u_cnn.pe_fire_map & row_mask(dut.u_cnn.pe_mask0))) ||
               (dut.cnn_valid[3] && dut.cnn_ready[3] && |(dut.u_cnn.pe_fire_map & row_mask(dut.u_cnn.pe_mask1))))
                own_load_compute=own_load_compute+1;
            if((dut.cnn_valid[2] && dut.cnn_ready[2] && |(dut.u_cnn.pe_fire_map & row_mask(dut.u_cnn.pe_mask0))) ||
               (dut.cnn_valid[4] && dut.cnn_ready[4] && |(dut.u_cnn.pe_fire_map & row_mask(dut.u_cnn.pe_mask1))))
                own_store_compute=own_store_compute+1;
`endif
        end
        if(dut.dmem_we && dut.dmem_addr==32'h88 && dut.dmem_wdata!=0) begin
            finish_value=dut.dmem_wdata;finished=1;
        end
    end
    function automatic [63:0] row_mask(input [7:0] rows);
        for(integer r=0;r<8;r=r+1) row_mask[r*8+:8]={8{rows[r]}};
    endfunction
    initial begin
        if(!OBSERVE_FAULT) begin
        wait(finished);@(negedge sys_clk);
        // Check every output byte, original input/weights, descriptors and guards.
        for(integer i=0;i<LOAD_BYTES/4;i=i+1) begin
`ifdef ORIGINAL_SOC
            observed=dut.u_datasram.mem['h100/4+i];
`else
            observed=dut.u_datasram.mem[('h100/4+i)%BANKS][('h100/4+i)/BANKS];
`endif
            if(observed!==expected[i]) $fatal(1,"data mismatch address=%h expected=%h actual=%h",'h100+i*4,expected[i],observed);
        end
        if(finish_value!==32'h600d || starts!=1 || dispatched!=TASKS || completed!=TASKS || done_cycle<0 || multi_active==0)
            $fatal(1,"CPU/queue failure finish=%h dispatch=%0d completed=%0d",finish_value,dispatched,completed);
`ifndef ORIGINAL_SOC
        if(ENABLE_OVERLAP && (own_load_compute==0 || own_store_compute==0 || (BANKS>1 && load_store==0)))
            $fatal(1,"no true access/compute overlap ld=%0d st=%0d ls=%0d",own_load_compute,own_store_compute,load_store);
        if(!ENABLE_OVERLAP && (own_load_compute!=0 || own_store_compute!=0)) $fatal(1,"serial control overlaps");
        if(BANKS>1 && multi_bank==0) $fatal(1,"no bank concurrency");
`endif
        if(request_count!=(LOAD_BYTES+UART_CHUNK_BYTES-1)/UART_CHUNK_BYTES) $fatal(1,"unexpected UART packet count");
        $display("METRICS cnn_cycles=%0d tasks=%0d compute_cycles=%0d mac_ops=%0d peak_active=%0d multi_active=%0d hazard_cycles=%0d load_compute=%0d store_compute=%0d own_load_compute=%0d own_store_compute=%0d load_store=%0d multi_bank=%0d max_grants=%0d total_cycles=%0d uart_baud=%0d chunk_bytes=%0d uart_requests=%0d load_cycles=%0d",
            done_cycle-start_cycle,TASKS,compute_cycles,mac_ops,peak_active,multi_active,hazard_cycles,load_compute,store_compute,own_load_compute,own_store_compute,load_store,multi_bank,max_grants,cycles,
            UART_BAUD,UART_CHUNK_BYTES,request_count,load_done_cycle-load_start_cycle);
        $fclose(timeline);
        $display("PASS tb_soc_overlap");$finish;
        end
    end
`ifndef ORIGINAL_SOC
    reg [5:0] observed_work=0,observed_idle=0;
    // Independently check monitor definitions against the sampled module I/O.
    always @(posedge sys_clk) begin:observer_check
        reg [5:0] work;
        if(dut.rst_n && !led_error && !dut.cnn_status_error && !dut.cnn_cancel) begin
            work={1'b1,dut.bridge_busy,dut.imem_re,
                  (dut.dmem_re || dut.dmem_we || (|dut.cnn_valid) || (|dut.cnn_response) || dut.io_mem_req || dut.io_mem_rvalid),
                  dut.cnn_status_busy,
                  (dut.imem_re || dut.dmem_re || dut.dmem_we || dut.cnn_mmio_re || dut.cnn_mmio_we || dut.load_req)};
            #1;
            if(dut.soc_active!==work || dut.soc_fault!==0) $fatal(1,"top module observer mismatch");
            observed_work=observed_work|work;
            observed_idle=observed_idle|~work;
        end
    end
    final if(!OBSERVE_FAULT && observed_work!=6'b111111) $error("not all top modules observed working");
    initial if(OBSERVE_FAULT) begin
        wait(led_error);repeat(3) @(negedge sys_clk);
        if(dut.bridge_state!==2'd3 || dut.soc_fault!==6'b010000 || dut.cnn_state!==2'd1)
            $fatal(1,"bridge fault not reflected in first-level state");
        rst_n_in=0;repeat(6) @(negedge sys_clk);
        if(dut.soc_module_state!==0 || dut.soc_active!==0 || dut.soc_fault!==0) $fatal(1,"observer reset failed");
        $display("METRICS bridge_fault_seen=1 reset_cleared=1");
        $display("PASS tb_soc_overlap");$finish;
    end
`endif
    initial begin #50000000;$fatal(1,"watchdog PC=%h dispatched=%0d completed=%0d",dut.imem_addr,dispatched,completed);end
    initial assert (UART_BAUD>0 && 100000000%UART_BAUD==0 && 100000000/UART_BAUD>=4 &&
                    UART_CHUNK_BYTES>=1 && UART_CHUNK_BYTES<=256) else $fatal(1,"invalid UART simulation parameters");
endmodule
