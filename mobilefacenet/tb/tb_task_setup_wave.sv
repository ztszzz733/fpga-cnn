`timescale 1ns/1ps
// Full production top and RAM, one queued Conv1x1 task: IC=3, OC=2, H=1, W=2.
// Same PE operands as tb_systolic_wave, now fetched through the real controller.
`define ENG dut.systolic_path.engine
`define TILE dut.systolic_path.engine.tile
module tb_task_setup_wave;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;
    reg [31:0] mmio_addr=0,mmio_wdata=0;
    reg mmio_we=0,mmio_re=0;
    wire [31:0] mmio_rdata,mem_addr,mem_wdata,mem_rdata;
    wire mmio_ready,mem_read,mem_write,mem_ready;
    mobilefacenet_accelerator_top dut(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
        mmio_rdata,mmio_ready,mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
    model_data_ram #(8192,3) ram(clk,rst_n,mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
    // Short waveform names; these are observation wires, not replacement logic.
    wire queue_start=dut.start,queue_active=dut.queue_active,exec_start=dut.exec_start;
    wire [3:0] queue_state=dut.queue_state,conv_state=`ENG.state;
    wire [2:0] desc_word=dut.task_queue.reader.word_index;
    wire desc_valid=dut.task_queue.reader_valid,desc_ready=dut.task_queue.reader_ready;
    wire [31:0] queue_buffered=dut.queue_buffered,queue_completed=dut.queue_completed;
    wire [3:0] task_op=dut.task_op;
    wire [31:0] cfg_input=`ENG.cia,cfg_output=`ENG.coa,cfg_weight=`ENG.cwa,cfg_bias=`ENG.cba;
    wire [31:0] cfg_size=`ENG.cfs,cfg_channels=`ENG.cch,cfg_param=`ENG.clp;
    wire core_busy=dut.core_busy,status_done=dut.regs.done_sticky,status_error=dut.regs.error_sticky;
    wire read_request=`ENG.read_request,read_ready=`ENG.read_ready,read_done=`ENG.read_done;
    wire [31:0] read_address=`ENG.read_address,read_data=`ENG.read_data;
    wire bias_we=`ENG.bias_we,a_we=`ENG.a_we,b_we=`ENG.b_we;
    wire [2:0] wr_row=`ENG.row,wr_col=`ENG.col,wr_k=`ENG.kidx;
    wire signed [7:0] wr_value=`TILE.wr_value;
    wire signed [31:0] wr_bias=`TILE.wr_bias;
    wire tile_start=`TILE.start,tile_busy=`TILE.busy,tile_done=`TILE.done;
    wire [3:0] tile_rows=`TILE.rows,tile_cols=`TILE.cols,tile_depth=`TILE.depth;
    wire tile_accumulate=`TILE.accumulate,tile_dw=`TILE.dw;
    wire array_ce=`TILE.array_ce,load_bias=`TILE.array.load;
    wire [5:0] run_tick=`TILE.tick;
    wire signed [7:0] w00=`TILE.array.rows[0].cols[0].pe.a_in,x00=`TILE.array.rows[0].cols[0].pe.b_in;
    wire signed [7:0] w01=`TILE.array.rows[0].cols[1].pe.a_in,x01=`TILE.array.rows[0].cols[1].pe.b_in;
    wire signed [7:0] w10=`TILE.array.rows[1].cols[0].pe.a_in,x10=`TILE.array.rows[1].cols[0].pe.b_in;
    wire signed [7:0] w11=`TILE.array.rows[1].cols[1].pe.a_in,x11=`TILE.array.rows[1].cols[1].pe.b_in;
    wire fire00=array_ce && !load_bias && `TILE.array.rows[0].cols[0].pe.a_valid && `TILE.array.rows[0].cols[0].pe.b_valid;
    wire fire01=array_ce && !load_bias && `TILE.array.rows[0].cols[1].pe.a_valid && `TILE.array.rows[0].cols[1].pe.b_valid;
    wire fire10=array_ce && !load_bias && `TILE.array.rows[1].cols[0].pe.a_valid && `TILE.array.rows[1].cols[0].pe.b_valid;
    wire fire11=array_ce && !load_bias && `TILE.array.rows[1].cols[1].pe.a_valid && `TILE.array.rows[1].cols[1].pe.b_valid;
    wire signed [31:0] acc00=`ENG.sums[0+:32],acc01=`ENG.sums[32+:32];
    wire signed [31:0] acc10=`ENG.sums[256+:32],acc11=`ENG.sums[288+:32];
    integer events,macs,output_file,i,tick_before,time_before;
    integer pw[0:3],px[0:3],pf[0:3];
    task event_row(input string kind,input integer a,b,c,input [31:0] value);
        $fwrite(events,"%0d,%s,%0d,%0d,%0d,%08h\n",$time,kind,a,b,c,value);
    endtask
    // Events refer to the rising edge accepting the PRE-edge signal values.
    always @(posedge clk) if(rst_n) begin
        if(mmio_we && mmio_ready) event_row("MMIO",mmio_addr,0,0,mmio_wdata);
        if(queue_start) event_row("QUEUE_START",0,0,0,0);
        if(mem_read && mem_ready) event_row(dut.fetch_phase ? "DESC_READ" : "RAM_READ",mem_addr,0,0,mem_rdata);
        if(mem_write && mem_ready) event_row("RAM_WRITE",mem_addr,0,0,mem_wdata);
        if(desc_valid && desc_ready) event_row("FIFO_PUSH",0,0,0,0);
        if(exec_start) event_row("DISPATCH",0,0,0,0);
        if(bias_we) event_row("BIAS",wr_row,0,0,wr_bias);
        if(a_we) event_row("WEIGHT",wr_row,wr_col,wr_k,{{24{wr_value[7]}},wr_value});
        if(b_we) event_row("INPUT",wr_row,wr_col,wr_k,{{24{wr_value[7]}},wr_value});
        if(tile_start) begin
            event_row("TILE_START",tile_rows,tile_cols,tile_depth,0);
            if(tile_rows!=2 || tile_cols!=2 || tile_depth!=3 || tile_accumulate || tile_dw)
                $fatal(1,"unexpected tile config");
        end
        if(load_bias) event_row("LOAD_BIAS",0,0,0,0);
        if(tile_done) event_row("TILE_DONE",0,0,0,0);
        if(dut.exec_done) event_row("EXEC_DONE",0,0,0,0);
        if(dut.queue_done) event_row("QUEUE_DONE",0,0,0,0);
    end
    always @(posedge clk) if(rst_n && exec_start) begin
        #1;
        if(cfg_input!=='h101 || cfg_output!=='h401 || cfg_weight!=='h201 || cfg_bias!=='h300 ||
           cfg_size!=='h10002 || cfg_channels!=='h20003 || cfg_param!=='h11)
            $fatal(1,"descriptor config not latched");
    end
    always @(posedge clk) if(rst_n && `TILE.state==2) begin
        tick_before=run_tick;time_before=$time;
        pw[0]=w00;pw[1]=w01;pw[2]=w10;pw[3]=w11;
        px[0]=x00;px[1]=x01;px[2]=x10;px[3]=x11;
        pf[0]=fire00;pf[1]=fire01;pf[2]=fire10;pf[3]=fire11;
        #1;$fwrite(macs,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            time_before,tick_before,pw[0],px[0],pf[0],acc00,pw[1],px[1],pf[1],acc01,
            pw[2],px[2],pf[2],acc10,pw[3],px[3],pf[3],acc11);
    end
    task write_reg(input [31:0] offset,value);
        @(negedge clk);mmio_addr='h40000000+offset;mmio_wdata=value;mmio_we=1;
        @(negedge clk);mmio_we=0;
    endtask
    initial begin
        for(i=0;i<8192;i=i+1) ram.bytes[i]=8'ha5;
        $readmemh("build/task_setup_wave/ram.hex",ram.bytes);
        events=$fopen("build/task_setup_wave/events.csv","w");
        macs=$fopen("build/task_setup_wave/actual.csv","w");
        $fwrite(events,"time_ns,kind,a,b,c,value_hex\n");
        $fwrite(macs,"time_ns,tick,w00,x00,fire00,acc00,w01,x01,fire01,acc01,w10,x10,fire10,acc10,w11,x11,fire11,acc11\n");
        $dumpfile("build/task_setup_wave/task_setup.vcd");$dumpvars(1,tb_task_setup_wave);
        repeat(2) @(negedge clk);rst_n=1;
        write_reg(8,'h1000);write_reg(24,1);write_reg(0,'h3d);
        wait(status_done || status_error);@(negedge clk);
        if(status_error || core_busy || dut.queue_completed!=1 || dut.queue_fetched!=1)
            $fatal(1,"queue did not complete normally");
        mmio_addr='h40000004;mmio_re=1;#1;
        if(mmio_rdata!==2) $fatal(1,"STATUS != DONE");
        output_file=$fopen("build/task_setup_wave/output.csv","w");$fwrite(output_file,"index,value\n");
        for(i=0;i<4;i=i+1) $fwrite(output_file,"%0d,%0d\n",i,$signed(ram.bytes['h401+i]));
        if(ram.bytes['h400]!==8'ha5 || ram.bytes['h405]!==8'ha5 || ram.bytes['h406]!==8'ha5 || ram.bytes['h407]!==8'ha5)
            $fatal(1,"partial word write corrupted neighboring bytes");
        $fclose(output_file);repeat(4) @(negedge clk);mmio_re=0;
        $fclose(events);$fclose(macs);
        $display("PASS tb_task_setup_wave (real queue, config latch, tile config, DONE, guard bytes)");$finish;
    end
    initial begin #100000;$fatal(1,"task setup timeout");end
endmodule
`undef ENG
`undef TILE
