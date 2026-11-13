`timescale 1ns/1ps
module tb_operator_queue;
    parameter WAIT_CYCLES=3,PREFETCH_DEPTH=4;
    localparam RAM_BYTES=524288;
    reg clk=0;always #5 clk=~clk;reg rst_n=0;
    reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top #(.TASK_PREFETCH_DEPTH(PREFETCH_DEPTH)) dut(
        clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(RAM_BYTES,WAIT_CYCLES) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    reg [31:0] meta[0:1],dest[0:63],lengths[0:63];
    reg [7:0] golden[0:RAM_BYTES-1],before_ram[0:RAM_BYTES-1];
    reg [63:0] launched=0,finished=0;string files[0:63],path,folder;
    integer starts[0:63],ends[0:63];
    integer i,j,c,id,n,fd,rc,events,comparisons,timing,completed=0,cycles=0,max_live=0,live,units_seen=0;
    reg changed;integer array_vector_compute=0;
    wire [7:0] compute;
    assign compute[0]=|(dut.pe_fire_map & {{8{dut.pe_mask0[7]}},{8{dut.pe_mask0[6]}},{8{dut.pe_mask0[5]}},{8{dut.pe_mask0[4]}},{8{dut.pe_mask0[3]}},{8{dut.pe_mask0[2]}},{8{dut.pe_mask0[1]}},{8{dut.pe_mask0[0]}}});
    assign compute[1]=|(dut.pe_fire_map & {{8{dut.pe_mask1[7]}},{8{dut.pe_mask1[6]}},{8{dut.pe_mask1[5]}},{8{dut.pe_mask1[4]}},{8{dut.pe_mask1[3]}},{8{dut.pe_mask1[2]}},{8{dut.pe_mask1[1]}},{8{dut.pe_mask1[0]}}});
    genvar g;generate for(g=2;g<8;g=g+1) begin:compute_alias
        assign compute[g]=dut.operators[g].engine.state==7;
    end endgenerate
    wire [7:0] unit_start=dut.unit_start,unit_busy=dut.unit_busy,unit_done=dut.unit_done,allocated=dut.unit_allocated;
    wire [31:0] dispatch_id=dut.dispatch_id,queue_fetched=dut.queue_fetched,queue_completed=dut.queue_completed;
    wire hazard_wait=dut.hazard_wait,resource_wait=dut.resource_wait;
    wire [3:0] ram_owner=dut.bus_owner;
    wire conv0_busy=unit_busy[0],conv1_busy=unit_busy[1],relu6_busy=unit_busy[2],add_busy=unit_busy[3];
    wire relu_busy=unit_busy[4],prelu_busy=unit_busy[5],pool_busy=unit_busy[6],requant_busy=unit_busy[7];
    task write_reg(input [31:0] off,value);
        @(negedge clk);addr='h40000000+off;wdata=value;we=1;@(negedge clk);we=0;
    endtask
    always @(posedge clk) if(rst_n) begin
        cycles=cycles+1;live=0;
        if((|compute[1:0]) && (|compute[7:2])) array_vector_compute=array_vector_compute+1;
        if(dut.pe_mask0 & dut.pe_mask1) $fatal(1,"PE collision");
        for(c=0;c<8;c=c+1) begin
            if(allocated[c]) live=live+1;
            if(unit_start[c]) begin
                id=dispatch_id;
                if(launched[id] || allocated[c] || unit_busy[c]) $fatal(1,"duplicate/busy unit issue");
                if(id==0 && queue_fetched!=1) $fatal(1,"first descriptor did not start immediately");
                if(!$test$plusargs("generic") && id==1 && !finished[0]) $fatal(1,"same unit overlap");
                if(!$test$plusargs("generic") && ((id>=10 && id<=14) || id==16) && !finished[id-1]) $fatal(1,"producer bypass");
                starts[id]=cycles;launched[id]=1;units_seen=units_seen|(1<<c);
                $fwrite(events,"%0d,DISPATCH,%0d,%0d\n",$time,id,c);
            end
            if(unit_done[c]) begin
                id=dut.unit_task_ids[c*32+:32];
                if(!launched[id] || finished[id]) $fatal(1,"unexpected completion");
                path=files[id];$readmemh(path,golden,0,lengths[id]-1);
                for(j=0;j<lengths[id];j=j+1) begin
                    if(ram.bytes[dest[id]+j]!==golden[j]) $fatal(1,"task%0d byte%0d got%0d expected%0d",id,j,$signed(ram.bytes[dest[id]+j]),$signed(golden[j]));
                    $fwrite(comparisons,"%0d,%0d,%0d,%0d\n",id,j,$signed(golden[j]),$signed(ram.bytes[dest[id]+j]));
                end
                finished[id]=1;ends[id]=cycles;completed=completed+1;
                $fwrite(events,"%0d,DONE,%0d,%0d\n",$time,id,c);
            end
        end
        if(live>max_live) max_live=live;
        $fwrite(timing,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",$time,unit_start,unit_busy,unit_done,allocated,dispatch_id,hazard_wait,ram_owner);
    end
    initial begin
        folder="build/operator_vectors";
        if($value$plusargs("folder=%s",folder)) begin end
        path={folder,"/events.csv"};events=$fopen(path,"w");$fwrite(events,"time_ns,event,task,unit\n");
        path={folder,"/comparison.csv"};comparisons=$fopen(path,"w");$fwrite(comparisons,"task,index,expected,actual\n");
        path={folder,"/timing.csv"};timing=$fopen(path,"w");$fwrite(timing,"time_ns,start,busy,done,allocated,task,hazard,owner\n");
        if($test$plusargs("vcd")) begin
            path={folder,"/operators.vcd"};$dumpfile(path);
            $dumpvars(0,clk,rst_n,unit_start,unit_busy,unit_done,allocated,compute,dispatch_id,queue_fetched,queue_completed,
                hazard_wait,resource_wait,ram_owner,conv0_busy,conv1_busy,relu6_busy,add_busy,relu_busy,prelu_busy,pool_busy,requant_busy,rd,wr,mready,ma,dut.regs.done_sticky,dut.regs.error_sticky);
        end
        path={folder,"/queue_ram.hex"};$readmemh(path,ram.bytes);
        for(i=0;i<RAM_BYTES;i=i+1) before_ram[i]=ram.bytes[i];
        path={folder,"/meta.hex"};$readmemh(path,meta);
        path={folder,"/queue_checks.txt"};fd=$fopen(path,"r");rc=$fscanf(fd,"%d",n);
        if(rc!=1 || n<1 || n>64) $fatal(1,"checks header");
        for(i=0;i<n;i=i+1) begin
            rc=$fscanf(fd,"%h %h %s",dest[i],lengths[i],path);files[i]=path;
            if(rc!=3) $fatal(1,"checks row");
        end
        $fclose(fd);repeat(2) @(negedge clk);rst_n=1;
        write_reg(8,meta[0]);write_reg(24,meta[1]);write_reg(0,61);
        @(negedge clk);addr='h40000004;re=1;#1;
        while(rdata[0]) begin @(negedge clk);#1;end
        if(rdata!==2 || completed!=n || queue_completed!=n) $fatal(1,"queue status %h completed%0d",rdata,completed);
        if(!$test$plusargs("generic")) begin
            if(PREFETCH_DEPTH>1 && starts[2]>=starts[1]) $fatal(1,"head-of-line unit busy was not bypassed");
            if((PREFETCH_DEPTH>1 && max_live<6) || units_seen!=255) $fatal(1,"missing heterogeneous overlap live%0d units%h",max_live,units_seen);
        end
        for(i=0;i<RAM_BYTES;i=i+1) begin
            changed=0;for(j=0;j<n;j=j+1) if(i>=dest[j] && i<dest[j]+lengths[j]) changed=1;
            if(!changed && ram.bytes[i]!==before_ram[i]) $fatal(1,"RAM guard changed %h",i);
        end
        $fclose(events);$fclose(comparisons);$fclose(timing);
        path={folder,"/summary.txt"};fd=$fopen(path,"w");
        $fwrite(fd,"cycles=%0d\nmax_live=%0d\nunits_seen=%0d\narray_vector_compute=%0d\nreads=%0d\nwrites=%0d\n",cycles,max_live,units_seen,array_vector_compute,ram.reads,ram.writes);$fclose(fd);
        $display("PASS tb_operator_queue (%0d tasks; max live=%0d; units=%h; RAM guards intact)",n,max_live,units_seen);$finish;
    end
    initial begin repeat(4000000) @(posedge clk);$fatal(1,"timeout");end
endmodule
