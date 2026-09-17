`timescale 1ns/1ps
module tb_mobilefacenet;
    parameter RAM_BYTES=262144,USE_SYSTOLIC=1;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;reg [31:0] addr=0,wdata=0;reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top #(.USE_SYSTOLIC(USE_SYSTOLIC)) dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
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
    task configure;
        write_reg(8,ia);write_reg(12,oa);write_reg(16,wa);write_reg(20,ba);
        write_reg(24,fs);write_reg(28,ch);write_reg(32,lp);
    endtask
    task wait_complete;
        read_reg(4,status);
        while(status[0]) begin repeat(64) @(negedge clk);read_reg(4,status);end
    endtask
    task bad_config(input [3:0] mode,input [31:0] off,value);
        ia='h101;oa='h10001;wa='h20003;ba='h30000;fs='h30003;ch='h10001;lp='h13;configure();
        if(off!='hffffffff) write_reg(off,value);
        old_reads=ram.reads;old_writes=ram.writes;
        write_reg(0,(mode<<2)|1);wait_complete();
        if(status!==4 || ram.reads!=old_reads || ram.writes!=old_writes)
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
            for(i=0;i<RAM_BYTES;i=i+1) before_ram[i]=ram.bytes[i];
            configure();old_writes=ram.writes;old_reads=ram.reads;begin_cycle=cycles;expected_status=2;
            write_reg(0,(op<<2)|1);read_reg(4,status);
            if(status!==1) $fatal(1,"missing BUSY %s %h",case_name,status);
            if(j==0) begin
                write_reg(24,0);read_reg(24,back);if(back!==fs) $fatal(1,"config unlocked");
                write_reg(0,(op<<2)|1);expected_status=6;
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
            if(op==5) begin
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
        bad_config(0,16,'hfffffffc);bad_config(0,32,'h400013);bad_config(0,32,'h800013);
        bad_config(7,'hffffffff,0);bad_config(5,32,0);
        // Abort an active RAM operation, then restart a COPY without hard reset.
        ia='h101;oa='h10001;wa='h20003;ba='h30000;fs='h50005;ch='h10001;lp='h113;configure();
        write_reg(0,1);while(!rd) @(negedge clk);write_reg(0,2);wait_complete();
        if(status!==0) $fatal(1,"abort status");
        old_reads=ram.reads;old_writes=ram.writes;repeat(32) @(negedge clk);
        if(ram.reads!=old_reads || ram.writes!=old_writes) $fatal(1,"work after abort");
        fs='h10008;lp=0;configure();write_reg(0,17);wait_complete();
        if(status!==2) $fatal(1,"restart status");
        for(i=0;i<8;i=i+1) if(ram.bytes[oa+i]!==ram.bytes[ia+i]) $fatal(1,"restart copy");
        $display("PASS tb_mobilefacenet (%0d layer comparisons, 14 invalid cases, busy START, reset/restart)",n);$finish;
    end
    initial begin repeat(100000000) @(posedge clk);$fatal(1,"timeout");end
endmodule
