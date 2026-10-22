`timescale 1ns/1ps
module tb_fx8_fifo;
    logic wr_clk=0,rd_clk=0,wr_rst_n=0,rd_rst_n=0;
    always #7 wr_clk=~wr_clk;
    always #11 rd_clk=~rd_clk;
    logic wr_valid=0,rd_ready=0;
    logic [7:0] wr_data=0;
    wire wr_ready,rd_valid;
    wire [7:0] rd_data;
    integer full_cycles=0,empty_cycles=0,stalls=0;
    logic held=0;reg [7:0] held_data;
    fx8_async_fifo #(.ADDR_BITS(4)) dut(.*);
    always @(posedge wr_clk) if(wr_rst_n && !wr_ready) full_cycles++;
    always @(posedge rd_clk) begin
        if(!rd_rst_n) held<=0;
        else begin
            if(!rd_valid) empty_cycles++;
            if(held && (!rd_valid || rd_data!==held_data)) $fatal(1,"FIFO head changed under stall");
            held<=rd_valid&&!rd_ready;held_data<=rd_data;
            if(rd_valid&&!rd_ready) stalls++;
        end
    end
    task automatic reset_fifo;
        wr_rst_n=0;rd_rst_n=0;wr_valid=0;rd_ready=0;
        #100;@(negedge wr_clk);wr_rst_n=1;@(negedge rd_clk);rd_rst_n=1;
    endtask
    task automatic phase(input integer seed,input integer count);
        fork
            begin
                for(integer i=0;i<count;i++) begin
                    if(i%29==0) repeat(30) @(negedge wr_clk);
                    @(negedge wr_clk);wr_data=(i*31+seed)&255;wr_valid=1;
                    do @(posedge wr_clk);while(!wr_ready);
                    @(negedge wr_clk);wr_valid=0;
                end
            end
            begin
                repeat(100) @(negedge rd_clk);
                for(integer i=0;i<count;i++) begin
                    if(i%13==0) repeat(17) @(negedge rd_clk);
                    @(negedge rd_clk);rd_ready=1;
                    do @(posedge rd_clk);while(!rd_valid);
                    if(rd_data!==8'((i*31+seed)&255)) $fatal(1,"FIFO ordering mismatch at %d",i);
                    @(negedge rd_clk);rd_ready=0;
                end
            end
        join
        repeat(5) @(negedge rd_clk);
        if(rd_valid) $fatal(1,"FIFO did not drain");
    endtask
    initial begin
        reset_fifo();phase(11,2000);
        // Reset a nonempty FIFO and prove no pre-reset data escapes afterwards.
        @(negedge wr_clk);wr_valid=1;wr_data='hee;
        repeat(8) @(negedge wr_clk);wr_valid=0;
        reset_fifo();phase(93,2000);
        if(full_cycles==0 || empty_cycles==0 || stalls==0) $fatal(1,"insufficient FIFO coverage");
        $display("PASS tb_fx8_fifo: 4000 bytes, independent clocks, wrap, full/empty, stalled head, reset flush");$finish;
    end
    initial begin #2000000;$fatal(1,"FIFO watchdog");end
endmodule
