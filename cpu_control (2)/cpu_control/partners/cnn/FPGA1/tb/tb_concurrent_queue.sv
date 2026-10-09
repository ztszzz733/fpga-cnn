`timescale 1ns/1ps
module tb_concurrent_queue;
    parameter WAIT_CYCLES=3,PREFETCH_DEPTH=4;
    localparam RAM_BYTES=262144;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top #(.TASK_PREFETCH_DEPTH(PREFETCH_DEPTH)) dut(
        clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(RAM_BYTES,WAIT_CYCLES) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    reg [31:0] meta[0:1],dest[0:63],lengths[0:63],status;
    reg [7:0] golden[0:RAM_BYTES-1],before_ram[0:RAM_BYTES-1];
    string files[0:63],folder,path,case_name;
    integer i,j,c,id,n,fd,rc,events,comparisons,metrics,done_count=0,dispatch_count=0;
    integer first_dispatch=0,second_dispatch=0,first_done=0,dual_live=0,dual_mac=0,fetch_compute=0;
    integer starts[0:63],finishes[0:63],cycles=0,macs0,macs1;
    reg check_hazard=0,changed;reg [63:0] finished=0;
    wire [1:0] context_start=dut.context_start,allocated=dut.allocated,array_running=dut.ctx_running;
    wire [1:0] context_done=dut.context_done;
    wire [31:0] task_id0=dut.task_id0,task_id1=dut.task_id1,queue_fetched=dut.queue_fetched,queue_completed=dut.queue_completed;
    wire [7:0] pe_mask0=dut.pe_mask0,pe_mask1=dut.pe_mask1;
    wire [3:0] rows0=dut.row_count0,rows1=dut.row_count1;
    wire [2:0] base0=dut.row_base0,base1=dut.row_base1;
    wire hazard_wait=dut.hazard_wait,resource_wait=dut.resource_wait,fetch_phase=dut.fetch_phase;
    wire [3:0] ram_owner=dut.bus_owner;
    always @* begin
        macs0=0;macs1=0;
        for(integer p=0;p<64;p=p+1) begin
            if(pe_mask0[p/8] && dut.pe_fire_map[p]) macs0=macs0+1;
            if(pe_mask1[p/8] && dut.pe_fire_map[p]) macs1=macs1+1;
        end
    end
    task write_reg(input [31:0] off,value);
        @(negedge clk);addr='h40000000+off;wdata=value;we=1;@(negedge clk);we=0;
    endtask
    always @(posedge clk) if(rst_n) begin
        cycles=cycles+1;
        if(pe_mask0 & pe_mask1) $fatal(1,"duplicate PE ownership");
        if(allocated==3) dual_live=dual_live+1;
        if(macs0>0 && macs1>0) dual_mac=dual_mac+1;
        if(fetch_phase && (|dut.context_busy)) fetch_compute=fetch_compute+1;
        $fwrite(metrics,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            $time,context_start,allocated,task_id0,task_id1,pe_mask0,pe_mask1,array_running,macs0,macs1,fetch_phase,hazard_wait,ram_owner);
        for(c=0;c<2;c=c+1) begin
            if(context_start[c]) begin
                id=dut.dispatch_id;
                if(starts[id]!=0 || !dut.task_queue.head_valid || !dut.task_queue.head_ready) $fatal(1,"dispatch order/source");
                if(id==0) begin
                    first_dispatch=cycles;
                    if(queue_fetched!=1) $fatal(1,"waited for a batch instead of first descriptor");
                end
                if(id==1) begin
                    second_dispatch=cycles;
                    if(!check_hazard && (!allocated[0] || dut.row_count0!=2 || dut.dispatch_rows!=6)) $fatal(1,"expected 2+6 row allocation");
                    if(check_hazard && !finished[0]) $fatal(1,"memory dependency bypassed");
                end
                starts[id]=cycles;dispatch_count=dispatch_count+1;
                $fwrite(events,"%0d,DISPATCH,%0d,%0d,%0d\n",$time,id,c,dut.dispatch_rows);
            end
            if(context_done[c]) begin
                id=c ? task_id1 : task_id0;
                if(finished[id]) $fatal(1,"duplicate completion");
                path=files[id];$readmemh(path,golden,0,lengths[id]-1);
                for(j=0;j<lengths[id];j=j+1) begin
                    if(ram.bytes[dest[id]+j]!==golden[j]) $fatal(1,"task%0d byte%0d got%0d expected%0d",id,j,$signed(ram.bytes[dest[id]+j]),$signed(golden[j]));
                    $fwrite(comparisons,"%0d,%0d,%0d,%0d\n",id,j,$signed(golden[j]),$signed(ram.bytes[dest[id]+j]));
                end
                finishes[id]=cycles;finished[id]=1;done_count=done_count+1;if(id==0) first_done=cycles;
                $fwrite(events,"%0d,DONE,%0d,%0d,0\n",$time,id,c);
            end
        end
    end
    initial begin
        folder="build/concurrent_vectors/mixed";case_name="mixed";
        if($value$plusargs("case=%s",case_name)) folder={"build/concurrent_vectors/",case_name};
        check_hazard=case_name!="mixed";
        path={folder,"/events.csv"};events=$fopen(path,"w");$fwrite(events,"time_ns,event,task,context,rows\n");
        path={folder,"/comparison.csv"};comparisons=$fopen(path,"w");$fwrite(comparisons,"task,index,expected,actual\n");
        path={folder,"/timing.csv"};metrics=$fopen(path,"w");$fwrite(metrics,"time_ns,start,allocated,task0,task1,mask0,mask1,running,macs0,macs1,fetch,hazard,owner\n");
        if($test$plusargs("vcd")) begin
            path={folder,"/concurrent.vcd"};$dumpfile(path);
            $dumpvars(0,clk,rst_n,context_start,allocated,context_done,array_running,task_id0,task_id1,pe_mask0,pe_mask1,
                rows0,rows1,base0,base1,macs0,macs1,queue_fetched,queue_completed,hazard_wait,resource_wait,fetch_phase,ram_owner,
                rd,wr,mready,ma,dut.regs.done_sticky,dut.regs.error_sticky);
        end
        path={folder,"/queue_ram.hex"};$readmemh(path,ram.bytes);
        for(i=0;i<64;i=i+1) starts[i]=0;
        for(i=0;i<RAM_BYTES;i=i+1) before_ram[i]=ram.bytes[i];
        path={folder,"/meta.hex"};$readmemh(path,meta);
        path={folder,"/queue_checks.txt"};fd=$fopen(path,"r");rc=$fscanf(fd,"%d",n);
        if(rc!=1 || n<2 || n>64) $fatal(1,"checks header");
        for(i=0;i<n;i=i+1) begin rc=$fscanf(fd,"%h %h %s",dest[i],lengths[i],path);files[i]=path;if(rc!=3) $fatal(1,"check row");end
        $fclose(fd);repeat(2) @(negedge clk);rst_n=1;
        write_reg(8,meta[0]);write_reg(24,meta[1]);write_reg(0,61);
        @(negedge clk);addr='h40000004;re=1;#1;
        while(rdata[0]) begin @(negedge clk);#1;end
        if(rdata!==2 || done_count!=n || dispatch_count!=n || queue_completed!=n) $fatal(1,"queue completion");
        if(!check_hazard && (second_dispatch>=first_done || dual_live==0 || fetch_compute==0)) $fatal(1,"no task/fetch overlap");
        if(!check_hazard && WAIT_CYCLES==3 && PREFETCH_DEPTH==4 && dual_mac==0) $fatal(1,"expected simultaneous MACs in both partitions");
        for(i=0;i<RAM_BYTES;i=i+1) begin
            changed=0;for(j=0;j<n;j=j+1) if(i>=dest[j] && i<dest[j]+lengths[j]) changed=1;
            if(!changed && ram.bytes[i]!==before_ram[i]) $fatal(1,"unrelated RAM changed %h",i);
        end
        $fclose(events);$fclose(comparisons);$fclose(metrics);
        path={folder,"/summary.txt"};fd=$fopen(path,"w");
        $fwrite(fd,"cycles=%0d\nfirst_dispatch=%0d\nsecond_dispatch=%0d\nfirst_done=%0d\ndual_live=%0d\ndual_mac=%0d\nfetch_compute=%0d\nreads=%0d\nwrites=%0d\n",cycles,first_dispatch,second_dispatch,first_done,dual_live,dual_mac,fetch_compute,ram.reads,ram.writes);$fclose(fd);
        $display("PASS tb_concurrent_queue (%s tasks=%0d dual_live=%0d dual_MAC=%0d first_start=%0d second_start=%0d first_done=%0d)",case_name,n,dual_live,dual_mac,first_dispatch,second_dispatch,first_done);$finish;
    end
    initial begin repeat(3000000) @(posedge clk);$fatal(1,"timeout");end
endmodule
