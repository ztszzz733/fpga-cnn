`timescale 1ns/1ps
// MMIO driver isolates reset/restart behavior from the full CPU/UART test.
module tb_overlap_restart;
    parameter integer BANKS=4,ENABLE_OVERLAP=1;
    `include "overlap_vectors.svh"
    logic clk=0,rst_n=0;
    always #5 clk=~clk;
    logic [31:0] mmio_addr=0,mmio_wdata=0;logic mmio_we=0,mmio_re=0;
    wire [31:0] mmio_rdata;wire mmio_ready;
    wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
    wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;wire cnn_cancel,cnn_mem_fault;
    wire status_busy,status_done,status_error;
    logic [31:0] dmem_addr=0,dmem_wdata=0;logic [3:0] dmem_wstrb=15;
    logic dmem_re=0,dmem_we=0;wire [31:0] dmem_rdata;
    wire io_mem_req=0,io_mem_we=0;wire [31:0] io_mem_addr=0,io_mem_wdata=0;
    wire [3:0] io_mem_be=0;wire io_mem_gnt,io_mem_rvalid,io_mem_error;wire [31:0] io_mem_rdata;
    mobilefacenet_overlap_top #(.ENABLE_OVERLAP(ENABLE_OVERLAP)) dut(.*);
    datasram_banked #(.BANKS(BANKS),.SRAM_SIZE(16384)) ram(.*);
    reg [7:0] input_bytes[0:LOAD_BYTES-1];reg [31:0] expected[0:LOAD_BYTES/4-1];
    integer completed=0,reset_count=0,stall_cycles=0;
    task mmio_write(input [31:0] offset,value);
        begin
            @(negedge clk);mmio_addr=32'h40000000+offset;mmio_wdata=value;mmio_we=1;
            @(posedge clk);if(!mmio_ready) $fatal(1,"MMIO not ready");
            @(negedge clk);mmio_we=0;
        end
    endtask
    task load_data;
        begin
            for(integer i=0;i<LOAD_BYTES/4;i=i+1) begin
                @(negedge clk);dmem_addr='h100+4*i;dmem_we=1;
                dmem_wdata={input_bytes[i*4+3],input_bytes[i*4+2],input_bytes[i*4+1],input_bytes[i*4]};
            end
            @(negedge clk);dmem_we=0;
        end
    endtask
    task start_queue;
        begin completed=0;mmio_write(8,'h100);mmio_write(24,TASKS);mmio_write(0,'h3d);end
    endtask
    task reset_queue;
        begin
            mmio_write(0,2);repeat(4) @(negedge clk);reset_count=reset_count+1;
            if(dut.unit_busy || dut.unit_allocated || cnn_valid || cnn_response || dut.queue_active)
                $fatal(1,"soft reset did not drain context/response state");
        end
    endtask
    task verify_queue;
        begin
            wait(dut.queue_done);repeat(2) @(negedge clk);
            if(completed!=TASKS) $fatal(1,"restart completion count %0d",completed);
            mmio_addr='h40000004;mmio_re=1;#1;
            if(mmio_rdata[2] || !mmio_rdata[1]) $fatal(1,"completion sticky status");
            mmio_re=0;
            for(integer i=0;i<LOAD_BYTES/4;i=i+1) begin
                @(negedge clk);dmem_addr='h100+4*i;dmem_re=1;
                @(posedge clk);#1;if(dmem_rdata!==expected[i])
                    $fatal(1,"restart data addr=%h expected=%h actual=%h",dmem_addr,expected[i],dmem_rdata);
            end
            @(negedge clk);dmem_re=0;
        end
    endtask
    always @(posedge clk) if(rst_n) begin
        if(cnn_mem_fault || dut.queue_error) $fatal(1,"unexpected restart fault");
        completed=completed+$countones(dut.unit_done & dut.unit_allocated);
    end
    initial begin
        $readmemh("external.mem",input_bytes);$readmemh("expected.mem",expected);
        repeat(4) @(negedge clk);rst_n=1;
        for(integer phase=0;phase<3;phase=phase+1) begin
            load_data();start_queue();
            case(phase)
                0:wait(cnn_valid[1] && cnn_ready[1]);
                1:wait(|dut.pe_fire_map);
                2:wait(cnn_valid[2] && cnn_ready[2]);
            endcase
            reset_queue();
        end
        // Reload externally after abort: soft reset cancels work, it does not roll back writes.
        load_data();start_queue();wait(cnn_valid[1]);
        @(negedge clk);dmem_addr=cnn_addr[32+:32];dmem_re=1;
        repeat(40) begin @(posedge clk);if(cnn_valid[1] && !cnn_ready[1]) stall_cycles=stall_cycles+1;end
        @(negedge clk);dmem_re=0;verify_queue();
        // A second successful submission without a system reset checks all stale state.
        load_data();start_queue();verify_queue();
        if(stall_cycles==0) $fatal(1,"no backpressure exercised");
        $display("METRICS resets=%0d successful_queues=2 tasks_per_queue=%0d stalled_cycles=%0d",reset_count,TASKS,stall_cycles);
        $display("PASS tb_overlap_restart");$finish;
    end
    initial begin #5000000;$fatal(1,"restart watchdog");end
endmodule
