`timescale 1ns/1ps
module tb_neureka_pipeline;
    logic sys_clk=0,rst_n_in=0,uart_rx=1;
    wire uart_tx,led_ready,led_busy,led_error;
    always #5 sys_clk=~sys_clk;
    face_soc_neureka_pipeline_top #(.IMEM_INIT_FILE("cpu.hex")) dut(.*);
    reg [31:0] initial_mem[0:65535];
    reg [7:0] golden[0:454];
    integer clocks=0,jobs=0,overlap_requests=0;
    reg last_done=0;
    function automatic [31:0] word_at(input integer address);
        word_at=dut.u_datasram.mem[(address/4)%4][(address/4)/4];
    endfunction
    function automatic [7:0] byte_at(input integer address);
        byte_at=(word_at(address)>>(8*(address%4)))&255;
    endfunction
    task check_output;
        for(integer i=0;i<455;i++) if(byte_at('h12000+i)!==golden[i])
            $fatal(1,"result mismatch job=%0d index=%0d got=%02x expected=%02x",jobs,i,byte_at('h12000+i),golden[i]);
        if(byte_at('h11fff)!==8'ha5 || byte_at('h12000+455)!==8'ha5) $fatal(1,"output guard overwritten");
        for(integer i=140;i<1024;i++)
            if(byte_at('h10000+i)!==8'ha5 || byte_at('h11000+i)!==8'ha5) $fatal(1,"slot guard overwritten");
    endtask
    initial begin
        $readmemh("sram.hex",initial_mem);$readmemh("golden.hex",golden);
        for(integer i=0;i<65536;i++) dut.u_datasram.mem[i%4][i/4]=initial_mem[i];
        // CPU completion/status locations start at zero, not the guard pattern.
        dut.u_datasram.mem[0][8]=0;dut.u_datasram.mem[1][8]=0;
        repeat(8) @(negedge sys_clk);rst_n_in=1;
    end
    always @(posedge sys_clk) if(dut.rst_n) begin
        clocks<=clocks+1;
        if(dut.cnn_valid[10] && |dut.cnn_valid[8:0]) overlap_requests<=overlap_requests+1;
        last_done<=dut.u_cnn.pipe_done;
        if(dut.u_cnn.pipe_done && !last_done) begin
            if(dut.u_cnn.pipe_fault) $fatal(1,"scheduler error %0d",dut.u_cnn.pipe_error);
            check_output();jobs<=jobs+1;
            $display("REAL_JOB job=%0d cycles=%0d overlap=%0d",jobs,dut.u_cnn.pipe_cycles,dut.u_cnn.overlap_cycles);
        end
        if(led_error) $fatal(1,"SoC fault conv=%b vec=%b pipe=%h",dut.u_cnn.conv_error,dut.u_cnn.vec_fault,dut.u_cnn.pipe_error);
        if(word_at('h80)==32'hdead0001) $fatal(1,"CPU reported error");
        if(word_at('h80)==32'h600dcafe) begin
            if(jobs!=2 || word_at('ha8)!=4 || word_at('hb8)!=4) $fatal(1,"job count");
            if(word_at('ha4)!=0 || word_at('hb4)==0 || overlap_requests==0) $fatal(1,"missing hardware overlap");
            check_output();
            $display("REAL_METRICS serial=%0d pipeline=%0d overlap=%0d concurrent_requests=%0d",word_at('ha0),word_at('hb0),word_at('hb4),overlap_requests);
            $display("PASS tb_neureka_pipeline: real CPU, NEureka, Vicuna, SRAM; 2 x 455 bytes and guards");$finish;
        end
        if(clocks>500000) $fatal(1,"watchdog cpu_phase=%h pipe=%h produced=%d completed=%d vec_cycles=%d",word_at('h84),dut.u_cnn.pipe_error,dut.u_cnn.produced,dut.u_cnn.completed,dut.u_cnn.vec_cycles);
    end
endmodule
