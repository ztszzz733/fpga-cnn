`timescale 1ns/1ps
module tb_task_queue;
    parameter RAM_BYTES=262144,PREFETCH_DEPTH=4,USE_SYSTOLIC=1;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top #(.TASK_PREFETCH_DEPTH(PREFETCH_DEPTH)) dut(
        clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(RAM_BYTES,3) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    reg [31:0] meta[0:1],dest[0:4095],lengths[0:4095];
    string golden_files[0:4095];
    reg [7:0] expected[0:RAM_BYTES-1],before_ram[0:RAM_BYTES-1];
    string folder,path;
    integer i,j,fd,rc,n,checked=0,desc_reads=0,max_buffered=0,old_writes=0,old_reads=0,outfd;
    reg monitoring=0;reg [31:0] status;
    reg experiment=0;
    reg overview=0;
    // Observation-only signals for a single successful whole-accelerator run.
    integer overview_fd,overview_outputs,timing_fd,task_begin_ns;
    reg [31:0] active_task=0,output_index=0,next_output=0;
    reg [3:0] active_op=0;
    reg [31:0] active_input=0,active_output=0,active_size=0,active_channels=0,active_param=0;
    reg [31:0] output_address_seen=0;
    reg signed [7:0] output_value_seen=0;
    wire queue_start=dut.start,core_busy=dut.core_busy,queue_active=dut.queue_active;
    wire status_done=dut.regs.done_sticky,status_error=dut.regs.error_sticky;
    wire [3:0] queue_state=dut.queue_state;
    wire [31:0] queue_fetched=dut.queue_fetched,queue_buffered=dut.queue_buffered,queue_completed=dut.queue_completed;
    wire exec_start=dut.exec_start,exec_done=dut.exec_done,array_running=dut.array_running;
    wire output_issue=monitoring && !dut.fetch_phase && dut.bus_ready &&
        (dut.sx_valid && dut.sx_write);
    wire [31:0] issued_address=dut.sx_addr;
    wire signed [7:0] issued_value=dut.sx_wdata[7:0];
    wire final_output_issue=output_issue && active_task==n-1;
    wire task_fetch=dut.fetch_phase;
    wire bias_load,weight_load,conv_input_load,conv_postprocess,conv_writeback;
    wire input_load=conv_input_load;
    wire postprocess=conv_postprocess;
    wire writeback=conv_writeback;
    wire ram_wait=(rd || wr) && !mready;
    wire [63:0] pe_fire_map;
    reg [6:0] mac_active_count;
    integer pi;
    always @* begin
        mac_active_count=0;
        for(pi=0;pi<64;pi=pi+1) mac_active_count=mac_active_count+{6'd0,pe_fire_map[pi]};
    end
    generate if(USE_SYSTOLIC) begin:overview_array_probe
        assign bias_load=dut.systolic_path.engine.state==2 || dut.systolic_path.engine.state==3;
        assign weight_load=dut.systolic_path.engine.state==4 || dut.systolic_path.engine.state==5;
        assign conv_input_load=dut.systolic_path.engine.state==6 || dut.systolic_path.engine.state==7;
        assign conv_postprocess=dut.systolic_path.engine.state==10;
        assign conv_writeback=dut.systolic_path.engine.state==11 || dut.systolic_path.engine.state==12;
        for(genvar pr=0;pr<8;pr=pr+1) begin:pe_rows
            for(genvar pc=0;pc<8;pc=pc+1) begin:pe_cols
                assign pe_fire_map[pr*8+pc]=dut.systolic_path.engine.tile.array_ce &&
                    !dut.systolic_path.engine.tile.array.load &&
                    dut.systolic_path.engine.tile.array.rows[pr].cols[pc].pe.a_valid &&
                    dut.systolic_path.engine.tile.array.rows[pr].cols[pc].pe.b_valid;
            end
        end
        initial begin
            #0;
            if($test$plusargs("overview")) $dumpvars(0,
                dut.systolic_path.engine.state,dut.systolic_path.engine.mb,dut.systolic_path.engine.nb,
                dut.systolic_path.engine.kb,dut.systolic_path.engine.nr,dut.systolic_path.engine.nc,
                dut.systolic_path.engine.nk,dut.systolic_path.engine.dw,dut.systolic_path.engine.a_we,
                dut.systolic_path.engine.b_we,dut.systolic_path.engine.bias_we,
                dut.systolic_path.engine.row,dut.systolic_path.engine.col,dut.systolic_path.engine.kidx,
                dut.systolic_path.engine.tile.wr_value,dut.systolic_path.engine.tile.wr_bias,
                dut.systolic_path.engine.tile.start,dut.systolic_path.engine.tile.done,
                dut.systolic_path.engine.tile.tick,dut.systolic_path.engine.raw,
                dut.systolic_path.engine.shifted,
                dut.systolic_path.engine.out_value);
        end
    end else begin:overview_no_array
        assign bias_load=0;assign weight_load=0;assign conv_input_load=0;
        assign conv_postprocess=0;assign conv_writeback=0;assign pe_fire_map=0;
    end endgenerate
    always @(posedge clk) if(overview && rst_n && monitoring) begin
        $fwrite(timing_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            $time,exec_start ? dut.queue_completed : active_task,task_fetch,bias_load,weight_load,input_load,
            array_running,postprocess,writeback,mac_active_count,rd,wr,ram_wait,exec_start,exec_done,queue_buffered);
        if(exec_start) begin
            active_task<=dut.queue_completed;active_op<=dut.task_op;
            active_input<=dut.task_ia;active_output<=dut.task_oa;active_size<=dut.task_fs;
            active_channels<=dut.task_ch;active_param<=dut.task_lp;
            next_output<=0;task_begin_ns=$time;
        end
        if(output_issue) begin
            output_index<=next_output;next_output<=next_output+1;
            output_address_seen<=issued_address;output_value_seen<=issued_value;
            $fwrite(overview_outputs,"%0d,%0d,%0d,%0d,%0d\n",$time,active_task,next_output,issued_address,issued_value);
        end
        if(exec_done) begin
            $fwrite(overview_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",active_task,active_op,
                task_begin_ns,$time,active_input,active_output,active_size,active_channels,active_param);
        end
    end
    integer perf_fd,detail_fd,cycles=0,layer_cycle,layer_reads,queue_cycle,queue_reads,queue_writes;
    always @(posedge clk) cycles=cycles+1;
    always @(posedge clk) if(rst_n && dut.exec_start) begin
        if(!dut.queue_active || dut.queue_state!=3 || !dut.task_queue.head_valid || !dut.task_queue.head_ready)
            $fatal(1,"compute launch must come from a queued descriptor");
    end
    integer capture_fd,mac_fd,ram_fd,capture_task,capture_address,sample_tap,sample_a,sample_w;
    task write_reg(input [31:0] off,value);
        @(negedge clk);addr='h40000000+off;wdata=value;we=1;#1;
        if(ready!==1) $fatal(1,"MMIO ready");@(negedge clk);we=0;
    endtask
    task read_reg(input [31:0] off,output [31:0] value);
        @(negedge clk);addr='h40000000+off;re=1;#1;value=rdata;
        if(ready!==1) $fatal(1,"MMIO read ready");@(negedge clk);re=0;
    endtask
    task launch(input [31:0] base,count);
        write_reg(8,base);write_reg(24,count);write_reg(0,61);
    endtask
    task wait_status(input [31:0] expected_status);
        read_reg(4,status);
        while(status[0]) begin repeat(8) @(negedge clk);read_reg(4,status);end
        if(status!==expected_status) $fatal(1,"status got %h expected %h",status,expected_status);
    endtask
    task word(input integer address,input [31:0] value);
        ram.bytes[address]=value[7:0];ram.bytes[address+1]=value[15:8];
        ram.bytes[address+2]=value[23:16];ram.bytes[address+3]=value[31:24];
    endtask
    task identity_task(input integer index,destination,input [31:0] header);
        word('h20000+index*32,header);word('h20004+index*32,'h101);word('h20008+index*32,destination);
        word('h2000c+index*32,'h801);word('h20010+index*32,'h900);word('h20014+index*32,'h10010);
        word('h20018+index*32,'h10001);word('h2001c+index*32,'h11);
        ram.bytes['h801]=1;word('h900,0);
    endtask
    task bad_launch(input [31:0] base,count);
        old_reads=ram.reads;old_writes=ram.writes;launch(base,count);wait_status(4);
        if(ram.reads!=old_reads || ram.writes!=old_writes) $fatal(1,"invalid queue accessed RAM");
    endtask
    task abort_and_check;
        write_reg(0,2);wait_status(0);old_reads=ram.reads;old_writes=ram.writes;
        repeat(40) @(negedge clk);
        if(dut.core_busy || rd || wr || dut.queue_buffered!=0 || ram.reads!=old_reads || ram.writes!=old_writes)
            $fatal(1,"activity after reset drain");
    endtask
    always @(posedge clk) if(monitoring && rd && mready && dut.fetch_phase) begin
        if(ma!==meta[0]+desc_reads*4 || desc_reads>=n*8) $fatal(1,"descriptor read order");
        desc_reads=desc_reads+1;
    end
    // Observe stable post-edge state before the following active edge.
    always @(negedge clk) if(monitoring) begin
        if(dut.queue_buffered>max_buffered) max_buffered=dut.queue_buffered;
        if(dut.queue_active && !dut.core_busy) $fatal(1,"BUSY gap");
        if(dut.exec_start) begin
            if(checked>=n || dut.task_oa!==dest[checked]) $fatal(1,"dispatch order");
            if(checked==0 && desc_reads!=8*(n<PREFETCH_DEPTH ? n : PREFETCH_DEPTH))
                $fatal(1,"prefetch batch not filled before first execution");
            old_writes=ram.writes;
            layer_reads=ram.reads;layer_cycle=cycles;
            for(i=0;i<RAM_BYTES;i=i+1) before_ram[i]=ram.bytes[i];
        end
        if(dut.exec_done) begin
            if(dut.done || !dut.core_busy || dut.exec_error) $fatal(1,"per-layer DONE leaked");
            path=golden_files[checked];$readmemh(path,expected,0,lengths[checked]-1);
            for(i=0;i<lengths[checked];i=i+1) if(ram.bytes[dest[checked]+i]!==expected[i])
                $fatal(1,"queue task %0d byte %0d got %0d expected %0d",checked,i,$signed(ram.bytes[dest[checked]+i]),$signed(expected[i]));
            for(i=0;i<RAM_BYTES;i=i+1) if((i<dest[checked] || i>=dest[checked]+lengths[checked]) && ram.bytes[i]!==before_ram[i])
                $fatal(1,"queue task %0d clobbered %h",checked,i);
            if(ram.writes-old_writes!=lengths[checked]) $fatal(1,"write count");
            $fwrite(perf_fd,"%0d,%0d,%0d,%0d,%0d\n",checked,lengths[checked],cycles-layer_cycle,ram.reads-layer_reads,ram.writes-old_writes);
            for(i=0;i<lengths[checked];i=i+1) $fwrite(detail_fd,"%0d,%0d,%0d,%0d\n",checked,i,$signed(expected[i]),$signed(ram.bytes[dest[checked]+i]));
            if(experiment) for(i=0;i<lengths[checked];i=i+1)
                $fwrite(ram_fd,"%0d,%0d,%0d,%0d,%0d\n",$time,checked,i,$signed(expected[i]),$signed(ram.bytes[dest[checked]+i]));
            $display("QUEUE LAYER PASS %0d: %0d bytes",checked,lengths[checked]);$fflush();checked=checked+1;
        end
    end
    initial begin
        folder="build/queue_vectors";if($value$plusargs("queue_dir=%s",folder)) begin end
        perf_fd=$fopen("build/queue_metrics.csv","w");$fwrite(perf_fd,"task,bytes,cycles,reads,writes\n");
        detail_fd=$fopen("build/queue_comparison.csv","w");$fwrite(detail_fd,"task,index,expected,actual\n");
        experiment=$test$plusargs("experiment");
        overview=$test$plusargs("overview");
        if(overview) begin
            overview_fd=$fopen("build/accelerator_wave/tasks.csv","w");
            overview_outputs=$fopen("build/accelerator_wave/output_events.csv","w");
            timing_fd=$fopen("build/accelerator_wave/timing_cycles.csv","w");
            if(!overview_fd || !overview_outputs || !timing_fd) $fatal(1,"create build/accelerator_wave before overview");
            $fwrite(timing_fd,"time_ns,task,task_fetch,bias_load,weight_load,input_load,array_running,postprocess,writeback,macs,ram_read,ram_write,ram_wait,exec_start,exec_done,buffered\n");
            $fwrite(overview_fd,"task,op,start_ns,done_ns,input_addr,output_addr,feature_size,channels,param\n");
            $fwrite(overview_outputs,"time_ns,task,index,address,value\n");
            $dumpfile("build/accelerator_wave/accelerator.vcd");
            // Do not dump RAM arrays or all 64 PE internals into this overview.
            $dumpvars(0,clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,mr,rd,wr,mready,
                queue_start,core_busy,queue_active,status_done,status_error,queue_state,
                queue_fetched,queue_buffered,queue_completed,exec_start,exec_done,array_running,
                active_task,active_op,active_input,active_output,active_size,active_channels,active_param,
                output_issue,final_output_issue,output_index,output_address_seen,output_value_seen,
                task_fetch,bias_load,weight_load,input_load,postprocess,writeback,ram_wait,mac_active_count);
        end
        if($test$plusargs("vcd")) begin
            if(experiment) path={folder,"/custom_queue.vcd"};else path="build/task_queue.vcd";
            $dumpfile(path);$dumpvars(0,dut);
        end
        if(experiment) begin
            path={folder,"/actual_outputs.csv"};capture_fd=$fopen(path,"w");
            path={folder,"/actual_mac.csv"};mac_fd=$fopen(path,"w");
            path={folder,"/ram_comparison.csv"};ram_fd=$fopen(path,"w");
            if(!capture_fd || !mac_fd || !ram_fd) $fatal(1,"capture file open");
            $fwrite(capture_fd,"time_ns,task,address_hex,value\n");
            $fwrite(mac_fd,"time_ns,tap,input,weight,acc_after\n");
            $fwrite(ram_fd,"time_ns,task,index,expected,actual\n");
        end
        path={folder,"/meta.hex"};$readmemh(path,meta);
        path={folder,"/queue_ram.hex"};$readmemh(path,ram.bytes);
        path={folder,"/queue_checks.txt"};fd=$fopen(path,"r");if(!fd) $fatal(1,"missing queue checks");
        rc=$fscanf(fd,"%d",n);if(rc!=1 || n<1 || n>4096 || meta[1]!==n) $fatal(1,"queue count");
        for(j=0;j<n;j=j+1) begin
            rc=$fscanf(fd,"%h %h %s",dest[j],lengths[j],path);golden_files[j]=path;
            if(rc!=3 || lengths[j]==0 || dest[j]+lengths[j]>RAM_BYTES) $fatal(1,"check entry");
        end
        $fclose(fd);repeat(2) @(negedge clk);rst_n=1;monitoring=1;
        queue_cycle=cycles;queue_reads=ram.reads;queue_writes=ram.writes;
        launch(meta[0],meta[1]);read_reg(4,status);if(status!==1) $fatal(1,"missing queue BUSY");
        write_reg(8,0);read_reg(8,status);if(status!==meta[0]) $fatal(1,"config unlocked");
        wait_status(2);monitoring=0;
        $fwrite(perf_fd,"TOTAL,128,%0d,%0d,%0d\n",cycles-queue_cycle,ram.reads-queue_reads,ram.writes-queue_writes);
        $fclose(perf_fd);$fclose(detail_fd);
        if(checked!=n || desc_reads!=8*n || dut.queue_completed!==n || dut.queue_fetched!==n ||
           max_buffered!=(n<PREFETCH_DEPTH ? n : PREFETCH_DEPTH)) $fatal(1,"counts or FIFO occupancy");
        if(lengths[n-1]!=128) $fatal(1,"fixture must finish with 128 features");
        outfd=$fopen("build/queue_features.bin","wb");for(i=0;i<128;i=i+1) $fwrite(outfd,"%c",ram.bytes[dest[n-1]+i]);$fclose(outfd);
        repeat(10) @(negedge clk);read_reg(4,status);if(status!==2) $fatal(1,"DONE not sticky");
        if(overview) begin
            $fclose(overview_fd);$fclose(overview_outputs);$fclose(timing_fd);
            $display("PASS tb_task_queue (overview: %0d tasks, per-layer golden, untouched RAM, STATUS=2)",n);$finish;
        end
        if(experiment) begin
            $fclose(capture_fd);$fclose(mac_fd);$fclose(ram_fd);
            path={folder,"/features.actual.bin"};outfd=$fopen(path,"wb");
            for(i=0;i<128;i=i+1) $fwrite(outfd,"%c",ram.bytes[dest[n-1]+i]);$fclose(outfd);
            $display("PASS tb_task_queue (editable experiment, %0d tasks, STATUS=2)",n);$finish;
        end
        bad_launch('h20000,0);bad_launch('h20004,1);bad_launch('hffffffe0,2);
        identity_task(0,'h1101,'h200);old_writes=ram.writes;launch('h20000,1);wait_status(4);
        if(ram.writes!=old_writes) $fatal(1,"bad version executed");
        identity_task(0,'h1101,'h10f);launch('h20000,1);wait_status(4);
        identity_task(0,'h1101,'h10100);launch('h20000,1);wait_status(4);
        if(ram.writes!=old_writes) $fatal(1,"reserved header executed");
        identity_task(0,'h20004,'h100);launch('h20000,1);wait_status(4);
        if(ram.writes!=old_writes) $fatal(1,"descriptor table overwritten");
        // Conv output may not overwrite a future (possibly unprefetched) descriptor.
        identity_task(0,'h20044,'h100);identity_task(1,'h1201,'h100);identity_task(2,'h1301,'h100);
        word('h2000c,'h801);word('h20010,'h900);word('h20014,'h10001);word('h2001c,'h11);
        launch('h20000,3);wait_status(4);
        if(ram.writes!=old_writes) $fatal(1,"conv overwrote future task table");
        // An execution error in task 1 stops before task 2; completed task 0 stays committed.
        identity_task(0,'h1101,'h100);identity_task(1,'h1201,'h100);identity_task(2,'h1301,'h100);
        word('h20034,0);old_writes=ram.writes;launch('h20000,3);wait_status(4);
        if(ram.writes-old_writes!=16 || dut.queue_completed!==1) $fatal(1,"fail-stop execution");
        // Rejected busy START must not duplicate a queue.
        for(j=2;j<=5;j=j+1) begin
            identity_task(0,'h1101,32'h100+j);old_writes=ram.writes;launch('h20000,1);wait_status(4);
            if(ram.writes!=old_writes) $fatal(1,"removed operator wrote RAM");
        end
        identity_task(0,'h1101,'h100);old_writes=ram.writes;launch('h20000,1);write_reg(0,61);wait_status(6);
        if(ram.writes-old_writes!=16) $fatal(1,"duplicate START executed");
        // Cancel once during descriptor fetch and once during an output write.
        identity_task(0,'h1101,'h100);identity_task(1,'h1201,'h100);launch('h20000,2);
        while(!(rd && dut.fetch_phase && !mready)) @(negedge clk);abort_and_check();
        launch('h20000,2);while(!(wr && !mready)) @(negedge clk);abort_and_check();
        if(USE_SYSTOLIC) begin
            identity_task(0,'h1101,'h100);word('h2000c,'h801);word('h20010,'h900);
            word('h20014,'h10001);word('h2001c,'h11);launch('h20000,1);
            while(!dut.sx_busy) @(negedge clk);
            // Observe the array run via a debug wire available in both configurations.
            while(!dut.array_running) @(negedge clk);abort_and_check();
            identity_task(0,'h1101,'h100);
        end
        launch('h20000,2);wait_status(2);
        if(dut.queue_completed!==2) $fatal(1,"restart count");
        for(i=0;i<16;i=i+1) if(ram.bytes['h1101+i]!==ram.bytes['h101+i] || ram.bytes['h1201+i]!==ram.bytes['h101+i]) $fatal(1,"restart data");
        $display("PASS tb_task_queue (depth=%0d, %0d layers, headers/ranges/fail-stop/busy START/reset/restart)",PREFETCH_DEPTH,n);$finish;
    end
    initial begin repeat(100000000) @(posedge clk);$fatal(1,"timeout");end
endmodule
