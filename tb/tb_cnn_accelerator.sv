`timescale 1ns/1ps
module tb_cnn_accelerator;
    localparam RAM_BYTES=262144, INPUT_BASE='h101, WEIGHT_BASE='h30003,
               BIAS_BASE='h31000, OUTPUT_BASE='h32001;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0;
    reg [31:0] addr=0,wdata=0; reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr; wire ready,rd,wr,mready;
    reg [7:0] golden[0:65535]; reg [7:0] before_ram[0:RAM_BYTES-1];
    reg [31:0] status,readback;
    integer cycles=0,passed=0;
    always @(posedge clk) cycles=cycles+1;
    cnn_accelerator_top dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(RAM_BYTES,3) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    task write_reg(input [31:0] off,d);
        @(negedge clk); addr='h40000000+off;wdata=d;we=1;#1;
        if(!ready) $fatal(1,"MMIO write not acknowledged");
        @(negedge clk); we=0;
    endtask
    task read_reg(input [31:0] off,output [31:0] d);
        @(negedge clk); addr='h40000000+off;re=1;#1;
        if(!ready) $fatal(1,"MMIO read not acknowledged"); d=rdata;
        @(negedge clk); re=0;
    endtask
    task configure(input integer w,h,ci,co,s,p,q,r,pool);
        write_reg(8,INPUT_BASE);write_reg(12,OUTPUT_BASE);
        write_reg(16,WEIGHT_BASE);write_reg(20,BIAS_BASE);
        write_reg(24,(h<<16)|w);write_reg(28,(co<<16)|ci);
        write_reg(32,3|(s<<4)|(p<<8)|(q<<12)|(r<<20)|(pool<<21));
    endtask
    task wait_complete;
        read_reg(4,status);
        while(status[0]) begin repeat(128) @(negedge clk); read_reg(4,status); end
    endtask
    task run_case(input string name,input integer w,h,ci,co,s,p,q,r,pool,nout);
        integer i,start_cycle,start_writes;
        $display("CASE START %s",name); $fflush();
        for(i=0;i<RAM_BYTES;i=i+1) ram.bytes[i]='ha5;
        $readmemh({"build/vectors/",name,".memh"},ram.bytes);
        $readmemh({"build/vectors/",name,".golden.hex"},golden,0,nout-1);
        for(i=0;i<RAM_BYTES;i=i+1) before_ram[i]=ram.bytes[i];
        configure(w,h,ci,co,s,p,q,r,pool);
        start_cycle=cycles; start_writes=ram.writes;
        write_reg(0,1); read_reg(4,status);
        if(status!==1) $fatal(1,"%s START status %h",name,status);
        write_reg(24,0); read_reg(24,readback);
        if(readback!==((h<<16)|w)) $fatal(1,"configuration changed while BUSY");
        wait_complete();
        if(status!==2) $fatal(1,"%s final status %h",name,status);
        for(i=0;i<nout;i=i+1)
            if(ram.bytes[OUTPUT_BASE+i]!==golden[i])
                $fatal(1,"%s output[%0d] got %0d expected %0d",name,i,$signed(ram.bytes[OUTPUT_BASE+i]),$signed(golden[i]));
        for(i=0;i<RAM_BYTES;i=i+1)
            if((i<OUTPUT_BASE || i>=OUTPUT_BASE+nout) && ram.bytes[i]!==before_ram[i])
                $fatal(1,"%s clobbered non-output byte %h",name,i);
        if(ram.writes-start_writes!=nout) $fatal(1,"unexpected write count");
        repeat(32) @(negedge clk); read_reg(4,status);
        if(status!==2 || ram.writes-start_writes!=nout) $fatal(1,"not sticky DONE or repeated start");
        passed=passed+1;
        $display("CASE PASS %s: %0d bytes, %0d cycles",name,nout,cycles-start_cycle);
        $fflush();
    endtask
    task invalid_config(input [31:0] off,value);
        integer nreads,nwrites;
        configure(3,3,1,1,1,0,0,0,0); write_reg(off,value);
        nreads=ram.reads; nwrites=ram.writes;
        write_reg(0,1); wait_complete();
        if(status!==4 || nreads!=ram.reads || nwrites!=ram.writes)
            $fatal(1,"invalid config status=%h or accessed RAM",status);
        write_reg(0,2); read_reg(4,status); if(status!==0) $fatal(1,"RESET status");
    endtask
    integer requests_after_reset;
    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        if($test$plusargs("vcd")) begin $dumpfile("build/cnn.vcd"); $dumpvars(0,dut); end
        `include "build/vectors/cases.svh"
        invalid_config(32,'h15); // unsupported kernel
        invalid_config(32,'h3); // stride zero
        invalid_config(24,0); // zero dimensions
        invalid_config(28,0); // zero channels
        invalid_config(20,BIAS_BASE+1);
        invalid_config(12,INPUT_BASE); // in-place output
        invalid_config(8,'hfffffffc); // wraparound
        invalid_config(32,'h200013); // pooling empty 1x1 convolution
        invalid_config(32,'h400013); // reserved parameter bits
        configure(5,5,3,2,1,1,0,1,0); write_reg(0,1);
        while(!(rd && !mready)) @(negedge clk);
        write_reg(0,2); wait_complete();
        if(status!==0) $fatal(1,"abort status %h",status);
        requests_after_reset=ram.reads+ram.writes;
        repeat(32) @(negedge clk); read_reg(4,status);
        if(status!==0 || ram.reads+ram.writes!=requests_after_reset) $fatal(1,"work after reset");
        // Restart after errors and mid-operation reset, without a hard reset.
        run_case("sanity",3,3,1,1,1,0,0,0,0,1);
        $display("PASS tb_cnn_accelerator (%0d golden runs, 9 invalid configs, soft reset/restart)",passed);
        $finish;
    end
    initial begin repeat(50000000) @(posedge clk); $fatal(1,"global timeout"); end
endmodule
