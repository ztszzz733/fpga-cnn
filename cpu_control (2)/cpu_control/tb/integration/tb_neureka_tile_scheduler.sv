`timescale 1ns/1ps
module tb_neureka_tile_scheduler;
    logic clk=0;always #5 clk=~clk;
    logic rst_n=0,cfg_we=0,host_reject=0;
    logic [31:0] cfg_addr=0,cfg_wdata=0,cfg_rdata;
    wire busy,done,fault;wire [31:0] error_code;
    wire mem_valid;wire [31:0] mem_addr;
    logic mem_ready,mem_response=0,mem_fault=0;logic [31:0] mem_rdata=0;
    wire conv_start;wire [31:0] conv_config_address;
    logic conv_busy=0,conv_done=0,conv_error=0,conv_cfg_valid=0;
    logic [31:0] conv_cfg_addr=0;wire conv_cfg_ready,conv_cfg_response;wire [31:0] conv_cfg_rdata;
    wire vec_we;wire [31:0] vec_addr,vec_wdata;
    logic vec_busy=0,vec_done=0,vec_fault=0,vec_loaded=1,vec_idle=1;
    wire [31:0] cycles,overlap_cycles,produced,completed;wire [3:0] slot_status;
    wire [31:0] conv_output_base,conv_output_capacity;
    neureka_tile_scheduler #(.MAX_CYCLES(10000)) dut(.*);
    logic [31:0] mem[0:4095];
    integer tick=0,latency=0,ct=0,vt=0,drain=0,cjob=0,vjob=0;
    integer conv_delay=150,vec_delay=400,stalls=0;
    logic pending=0,freeze=0;logic [31:0] address;
    logic [31:0] vsrc,vdst,vlen;
    integer owner[0:1]; // 0=free, 1=producer, 2=ready, 3=consumer
    always_comb mem_ready=!pending && tick%5!=0;
    always @(posedge clk) begin
        tick<=tick+1;mem_response<=0;conv_done<=0;conv_cfg_valid<=0;
        if(!rst_n) begin
            pending<=0;conv_busy<=0;vec_busy<=0;vec_done<=0;vec_idle<=1;
            ct<=0;vt<=0;drain<=0;cjob<=0;vjob<=0;owner[0]<=0;owner[1]<=0;
        end else begin
            if(mem_valid && !mem_ready) stalls<=stalls+1;
            if(mem_valid && mem_ready) begin
                if(pending) $fatal(1,"multiple descriptor requests");
                pending<=1;address<=mem_addr;latency<=tick%4+1;
            end
            if(pending) begin
                if(latency==0) begin mem_response<=1;mem_rdata<=mem[address>>2];pending<=0;end
                else latency<=latency-1;
            end
            if(conv_start) begin
                if(conv_busy || owner[cjob%2]!=0) $fatal(1,"overwrite live slot %d",cjob);
                owner[cjob%2]<=1;ct<=conv_delay;conv_busy<=1;
                conv_cfg_valid<=1;conv_cfg_addr<=8;
            end
            if(conv_cfg_response && conv_cfg_rdata!=(cjob%2 ? 32'h2800 : 32'h2000))
                $fatal(1,"output pointer not patched");
            if(conv_busy && !freeze) begin
                if(ct==0) begin conv_busy<=0;conv_done<=1;owner[cjob%2]<=2;cjob<=cjob+1;end
                else ct<=ct-1;
            end
            if(vec_we) case(vec_addr-32'h40040000)
                4:vsrc<=vec_wdata;
                8:vdst<=vec_wdata;
                12:vlen<=vec_wdata;
                0:begin
                    if(vec_busy || owner[vjob%2]!=2) $fatal(1,"consume before convolution completion");
                    if(vsrc!=(vjob%2 ? 32'h2800 : 32'h2000) || vdst!=32'h3000+vjob*64 ||
                       vlen!=(vjob==4 ? 7 : 64)) $fatal(1,"wrong tile arguments");
                    owner[vjob%2]<=3;vec_busy<=1;vec_done<=0;vec_idle<=0;vt<=vec_delay;
                end
                default:;
            endcase
            if(vec_busy) begin
                if(vt==0) begin vec_busy<=0;vec_done<=1;drain<=7;end
                else vt<=vt-1;
            end
            if(drain!=0) begin
                if(slot_status[(vjob%2)*2+:2]!=3) $fatal(1,"slot freed before stores drain");
                drain<=drain-1;
                if(drain==1) begin vec_idle<=1;owner[vjob%2]<=0;vjob<=vjob+1;end
            end
        end
    end
    task wr(input integer offset,input logic[31:0] data);
        @(negedge clk);cfg_addr=32'h40000000+offset;cfg_wdata=data;cfg_we=1;
        @(negedge clk);cfg_we=0;
    endtask
    task reset_dut;
        @(negedge clk);rst_n=0;mem_fault=0;vec_fault=0;conv_error=0;freeze=0;vec_loaded=1;
        repeat(4) @(negedge clk);rst_n=1;
    endtask
    task setup(input integer serial_mode);
        wr(8,32'h100);wr(12,5);wr(16,32'h2000);wr(20,32'h2800);wr(24,512);wr(28,serial_mode);
    endtask
    task wait_done;
        for(integer t=0;t<11000;t++) begin
            @(negedge clk);
            if(done) return;
        end
        $fatal(1,"watchdog failed");
    endtask
    integer serial_cycles,parallel_cycles;
    initial begin
        for(integer i=0;i<4096;i++) mem[i]=0;
        for(integer i=0;i<5;i++) begin
            mem[64+i*4]=32'h400+i*96;mem[65+i*4]=32'h3000+i*64;
            mem[66+i*4]=i==4 ? 7 : 64;mem[67+i*4]=0;
        end
        reset_dut();setup(1);wr(0,1);wait_done();
        if(fault || completed!=5 || produced!=5 || overlap_cycles!=0) $fatal(1,"serial failed");
        serial_cycles=cycles;
        // Repeat without a reset; both sticky completion signals are still high.
        cjob=0;vjob=0;
        setup(0);wr(0,1);wait_done();
        if(fault || completed!=5 || produced!=5 || overlap_cycles==0 || cycles>=serial_cycles)
            $fatal(1,"pipeline/restart failed");
        parallel_cycles=cycles;
        $display("CONTROL_METRICS serial=%0d parallel=%0d overlap=%0d stalls=%0d",serial_cycles,parallel_cycles,overlap_cycles,stalls);
        // Opposite imbalance: producer slower than consumer.
        reset_dut();conv_delay=500;vec_delay=15;setup(0);wr(0,1);
        wr(16,32'h3000); // rejected busy write must not alter buffer address
        wait_done();
        if(fault || completed!=5 || !dut.rejected || dut.buffers[0]!=32'h2000) $fatal(1,"slow producer/config lock");
        reset_dut();setup(0);wr(20,32'h2100);wr(0,1);wait_done();
        if(!fault || error_code!=1 || mem_valid || conv_start) $fatal(1,"overlap validation");
        reset_dut();setup(0);wr(12,0);wr(0,1);wait_done();
        if(!fault || error_code!=1) $fatal(1,"zero tiles");
        reset_dut();setup(0);mem[64]=32'hfffffff0;wr(0,1);wait_done();
        if(!fault || error_code!=2) $fatal(1,"config bounds");mem[64]=32'h400;
        reset_dut();setup(0);mem[66]=513;wr(0,1);wait_done();
        if(!fault || error_code!=3) $fatal(1,"tile bounds");mem[66]=64;
        reset_dut();setup(0);wr(0,1);repeat(20) @(negedge clk);mem_fault=1;wait_done();
        if(!fault || error_code!=6 || mem_valid || vec_we || conv_start) $fatal(1,"memory fault");
        reset_dut();setup(0);freeze=1;wr(0,1);wait_done();
        if(!fault || error_code!=7) $fatal(1,"timeout");
        reset_dut();setup(0);vec_loaded=0;wr(0,1);wait_done();
        if(!fault || error_code!=1) $fatal(1,"unloaded program");
        $display("PASS tb_neureka_tile_scheduler (control handshake models, not arithmetic cores)");$finish;
    end
endmodule
