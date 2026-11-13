`timescale 1ns/1ps
module tb_mobilefacenet;
    parameter RAM_BYTES=262144,USE_SYSTOLIC=1;
    // The test adapter places each tasks.txt entry in a real one-entry RAM queue.
    localparam QUEUE_BASE=(RAM_BYTES-32)&32'hffffffe0;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(RAM_BYTES,3) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    reg [7:0] golden[0:RAM_BYTES-1],before_ram[0:RAM_BYTES-1];
    reg [31:0] status,back,op,ia,oa,wa,ba,fs,ch,lp,nout;
    string init_file,case_name,golden_file,task_file;
    integer fd,n,rc,i,j,limit=0,cycles=0,begin_cycle,old_writes,old_reads,expected_status,feature_fd,perf_fd,detail_fd;
    always @(posedge clk) cycles=cycles+1;
    task write_reg(input [31:0] off,value);
        @(negedge clk);addr='h40000000+off;wdata=value;we=1;#1;
        if(ready!==1) $fatal(1,"MMIO ready");@(negedge clk);we=0;
    endtask
    task read_reg(input [31:0] off,output [31:0] value);
        @(negedge clk);addr='h40000000+off;re=1;#1;
        if(ready!==1) $fatal(1,"MMIO ready");value=rdata;@(negedge clk);re=0;
    endtask
    task word(input integer a,input [31:0] value);
        ram.bytes[a]=value[7:0];ram.bytes[a+1]=value[15:8];
        ram.bytes[a+2]=value[23:16];ram.bytes[a+3]=value[31:24];
    endtask
    task configure;
        word(QUEUE_BASE,32'h100 | op);word(QUEUE_BASE+4,ia);word(QUEUE_BASE+8,oa);
        word(QUEUE_BASE+12,wa);word(QUEUE_BASE+16,ba);word(QUEUE_BASE+20,fs);
        word(QUEUE_BASE+24,ch);word(QUEUE_BASE+28,lp);
        write_reg(8,QUEUE_BASE);write_reg(24,1);
    endtask
    task wait_complete;
        read_reg(4,status);
        while(status[0]) begin repeat(64) @(negedge clk);read_reg(4,status);end
    endtask
    task bad_config(input [3:0] mode,input [31:0] off,value);
        ia='h101;oa='h10001;wa='h20003;ba='h30000;fs='h30003;ch='h10001;lp='h13;op=mode;
        case(off)
            8:ia=value;12:oa=value;16:wa=value;20:ba=value;
            24:fs=value;28:ch=value;32:lp=value;default:;
        endcase
        configure();
        old_reads=ram.reads;old_writes=ram.writes;
        write_reg(0,61);wait_complete();
        // Only the eight descriptor words may be read for an invalid task.
        if(status!==4 || ram.reads-old_reads!=8 || ram.writes!=old_writes)
            $fatal(1,"invalid accepted mode=%d off=%h value=%h status=%h",mode,off,value,status);
        write_reg(0,2);read_reg(4,status);if(status!==0) $fatal(1,"reset status");
    endtask
    initial begin
        if($test$plusargs("vcd")) begin $dumpfile("build/mobilefacenet.vcd");$dumpvars(0,dut);end
        perf_fd=$fopen("build/operator_metrics.csv","w");$fwrite(perf_fd,"task,bytes,cycles,reads,writes\n");
        detail_fd=$fopen("build/operator_comparison.csv","w");$fwrite(detail_fd,"task,index,expected,actual\n");
        task_file="build/vectors/tasks.txt";
        if($value$plusargs("tasks=%s",task_file)) begin end
        if($value$plusargs("limit=%d",limit)) begin end
        fd=$fopen(task_file,"r");if(!fd) $fatal(1,"cannot open %s",task_file);
        rc=$fscanf(fd,"%d",n);if(rc!=1 || n<=0) $fatal(1,"task header");
        repeat(2) @(negedge clk);rst_n=1;
        if(limit>0 && limit<n) n=limit;
        for(j=0;j<n;j=j+1) begin
            rc=$fscanf(fd,"%s %s %h %h %h %h %h %h %h %h %h %s",init_file,case_name,op,ia,oa,wa,ba,fs,ch,lp,nout,golden_file);
            if(rc!=12 || nout==0 || nout>RAM_BYTES) $fatal(1,"task parse %d",j);
            if(init_file!="-") begin
                for(i=0;i<RAM_BYTES;i=i+1) ram.bytes[i]='ha5;
                $readmemh(init_file,ram.bytes);
            end
            $readmemh(golden_file,golden,0,nout-1);
            configure();
            for(i=0;i<RAM_BYTES;i=i+1) before_ram[i]=ram.bytes[i];
            old_writes=ram.writes;old_reads=ram.reads;begin_cycle=cycles;expected_status=2;
            write_reg(0,61);read_reg(4,status);
            if(status!==1) $fatal(1,"missing BUSY %s %h",case_name,status);
            if(j==0) begin
                write_reg(24,0);read_reg(24,back);if(back!==1) $fatal(1,"queue count unlocked");
                write_reg(0,61);expected_status=6;
            end
            wait_complete();
            if(status!==expected_status) $fatal(1,"%s status %h",case_name,status);
            for(i=0;i<nout;i=i+1) if(ram.bytes[oa+i]!==golden[i])
                $fatal(1,"%s byte[%0d] got %0d expected %0d",case_name,i,$signed(ram.bytes[oa+i]),$signed(golden[i]));
            for(i=0;i<RAM_BYTES;i=i+1) if((i<oa || i>=oa+nout) && ram.bytes[i]!==before_ram[i])
                $fatal(1,"%s clobbered %h",case_name,i);
            if(ram.writes-old_writes!=nout) $fatal(1,"write count");
            repeat(8) @(negedge clk);read_reg(4,status);
            if(status!==expected_status || ram.writes-old_writes!=nout) $fatal(1,"sticky done/restart");
            if(nout==128 && j==n-1) begin
                if(nout!=128) $fatal(1,"final length");
                feature_fd=$fopen("build/rtl_features.bin","wb");
                for(i=0;i<128;i=i+1) $fwrite(feature_fd,"%c",ram.bytes[oa+i]);
                $fclose(feature_fd);
            end
            $display("LAYER PASS %s: %0d bytes, %0d cycles",case_name,nout,cycles-begin_cycle);$fflush();
            $fwrite(perf_fd,"%s,%0d,%0d,%0d,%0d\n",case_name,nout,cycles-begin_cycle,ram.reads-old_reads,ram.writes-old_writes);
            for(i=0;i<nout;i=i+1) $fwrite(detail_fd,"%s,%0d,%0d,%0d\n",case_name,i,$signed(golden[i]),$signed(ram.bytes[oa+i]));
        end
        $fclose(perf_fd);$fclose(detail_fd);
        $fclose(fd);
        bad_config(0,32,'h17);bad_config(1,32,'h11);bad_config(0,32,3);
        bad_config(0,24,0);bad_config(0,28,0);bad_config(1,28,'h20001);
        bad_config(0,20,'h30001);bad_config(0,8,'hfffffffc);bad_config(0,12,'h101);
        bad_config(0,16,'hfffffffc);bad_config(0,32,'h400013);bad_config(0,32,'h1000013);
        for(i=2;i<15;i=i+1) bad_config(i,'hffffffff,0);
        bad_config(0,32,'h100013);bad_config(0,32,'h200013);
        // Abort RAM, then restart an identity Conv1 through the array.
        op=0;ia='h101;oa='h10001;wa='h20003;ba='h30000;fs='h50005;ch='h10001;lp='h113;configure();
        write_reg(0,61);while(!rd) @(negedge clk);write_reg(0,2);wait_complete();
        if(status!==0) $fatal(1,"abort status");
        old_reads=ram.reads;old_writes=ram.writes;repeat(32) @(negedge clk);
        if(ram.reads!=old_reads || ram.writes!=old_writes) $fatal(1,"work after abort");
        fs='h10008;lp='h11;ram.bytes[wa]=1;
        for(i=0;i<4;i=i+1) ram.bytes[ba+i]=0;configure();write_reg(0,61);wait_complete();
        if(status!==2) $fatal(1,"restart status");
        for(i=0;i<8;i=i+1) if(ram.bytes[oa+i]!==ram.bytes[ia+i]) $fatal(1,"restart identity Conv1");
        $display("PASS tb_mobilefacenet (%0d layer comparisons, removed ops/activation and invalid configs, busy START, reset/restart)",n);$finish;
    end
    initial begin repeat(100000000) @(posedge clk);$fatal(1,"timeout");end
endmodule
