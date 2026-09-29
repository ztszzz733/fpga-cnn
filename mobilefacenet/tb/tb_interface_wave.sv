`timescale 1ns/1ps
// Three real, chained queue tasks; observation only, no RTL changes.
module tb_interface_wave;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,mmio_we=0,mmio_re=0;
    reg [31:0] mmio_addr=0,mmio_wdata=0;
    wire [31:0] mmio_rdata,mem_addr,mem_wdata,mem_rdata;
    wire mmio_ready,mem_read,mem_write,mem_ready;
    mobilefacenet_accelerator_top dut(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
        mmio_rdata,mmio_ready,mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
    model_data_ram #(16384,3) ram(clk,rst_n,mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
    wire [7:0] quant_shift=dut.systolic_path.engine.clp[19:12];
    wire signed [31:0] sum_00=dut.systolic_path.engine.sums[0+:32];
    wire signed [31:0] sum_01=dut.systolic_path.engine.sums[32+:32];
    wire signed [31:0] sum_10=dut.systolic_path.engine.sums[256+:32];
    wire signed [31:0] sum_11=dut.systolic_path.engine.sums[288+:32];
    integer active_task=-1,starts=0,finishes=0,pushes=0,desc_words=0,output_writes=0;
    integer events,actual,i;
    reg [7:0] expected[0:16383];
    task event_row(input string kind,input integer task_id,input [31:0] address,value);
        $fwrite(events,"%0d,%s,%0d,%08h,%08h\n",$time,kind,task_id,address,value);
    endtask
    always @(posedge clk) if(rst_n) begin
        if(mmio_we && mmio_ready) event_row("MMIO",-1,mmio_addr,mmio_wdata);
        if(dut.task_queue.reader_valid && dut.task_queue.reader_ready) begin
            event_row("FIFO_PUSH",pushes,0,0);pushes=pushes+1;
        end
        if(dut.fetch_phase && mem_read && mem_ready) desc_words=desc_words+1;
        if(dut.exec_start) begin
            if(starts>=3 || dut.task_op!==(starts==1 ? 4'd1 : 4'd0)) $fatal(1,"dispatch order/type");
            if(dut.task_ia!==(starts==0 ? 32'h101 : starts==1 ? 32'h401 : 32'h801)) $fatal(1,"input chain");
            active_task=starts;starts=starts+1;
            event_row("TASK_START",active_task,dut.task_ia,dut.task_op);
        end
        if(dut.systolic_path.engine.tile.start)
            event_row("TILE_START",active_task,dut.systolic_path.engine.kb,
                {20'd0,dut.systolic_path.engine.nr,dut.systolic_path.engine.nc,dut.systolic_path.engine.nk});
        if(dut.sx_valid && dut.sx_write && dut.bus_ready && !dut.fetch_phase) begin
            output_writes=output_writes+1;event_row("OUTPUT",active_task,dut.sx_addr,dut.sx_wdata);
        end
        if(dut.exec_done) begin finishes=finishes+1;event_row("TASK_DONE",active_task,0,0);end
        if(dut.queue_error || dut.exec_error) $fatal(1,"unexpected hardware error");
    end
    task write_reg(input [31:0] offset,value);
        @(negedge clk);mmio_addr=32'h40000000+offset;mmio_wdata=value;mmio_we=1;
        @(negedge clk);mmio_we=0;
    endtask
    initial begin
        $readmemh("build/interface_wave/vectors/queue_ram.hex",ram.bytes);
        $readmemh("build/interface_wave/expected_ram.hex",expected);
        events=$fopen("build/interface_wave/events.csv","w");
        $fwrite(events,"time_ns,event,task,address_hex,value_hex\n");
        $dumpfile("build/interface_wave/interfaces.vcd");
        $dumpvars(0,dut);
        $dumpvars(0,clk,rst_n,active_task,quant_shift,sum_00,sum_01,sum_10,sum_11);
        repeat(3) @(negedge clk);rst_n=1;
        write_reg(8,32'h3000);write_reg(24,3);write_reg(0,32'h3d);
        wait(dut.regs.done_sticky || dut.regs.error_sticky);@(negedge clk);
        if(dut.regs.error_sticky || dut.core_busy || starts!=3 || finishes!=3 || pushes!=3 ||
            desc_words!=24 || output_writes!=39 || dut.queue_completed!=3 || dut.queue_fetched!=3 || dut.queue_buffered!=0)
            $fatal(1,"queue counts/status mismatch");
        mmio_addr=32'h40000004;mmio_re=1;#1;
        if(mmio_rdata!==32'd2) $fatal(1,"STATUS must be DONE only");
        actual=$fopen("build/interface_wave/actual_ram.hex","w");
        for(i=0;i<16384;i=i+1) begin
            if(ram.bytes[i]!==expected[i]) $fatal(1,"RAM mismatch at %h: expected %h got %h",i,expected[i],ram.bytes[i]);
            $fwrite(actual,"%02h\n",ram.bytes[i]);
        end
        $fclose(actual);event_row("QUEUE_DONE",active_task,0,dut.queue_completed);
        repeat(5) @(negedge clk);mmio_re=0;$fclose(events);
        $display("PASS tb_interface_wave: 3 tasks, 24 descriptor words, 39 outputs, all 16384 RAM bytes checked");
        $finish;
    end
    initial begin #1000000;$fatal(1,"interface waveform timeout");end
endmodule
