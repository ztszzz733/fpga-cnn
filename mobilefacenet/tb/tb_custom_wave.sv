`timescale 1ns/1ps
// A single 3x3 convolution: editable data comes from custom_wave.py.
// No busy-START injection or extra error cases: a clean waveform for hand checks.
module tb_custom_wave;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0;
    reg [31:0] addr=0,wdata=0; reg we=0,re=0;
    wire [31:0] rdata,ma,md,mr;
    wire ready,rd,wr,mready;
    mobilefacenet_accelerator_top dut(clk,rst_n,addr,wdata,we,re,rdata,ready,ma,md,rd,wr,mr,mready);
    model_data_ram #(4096,3) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    // [0] bias, [1] layer param, [2] expected output;
    // subsequent triplets: input, weight, expected accumulator after this MAC.
    reg [31:0] expected[0:29];
    integer i,step=0,log_fd;
    integer cap_a,cap_w,cap_tap,cap_before;
    time sample_time;
    task write_reg(input [31:0] offset,value);
        @(negedge clk);addr='h40000000+offset;wdata=value;we=1;
        #1;if(ready!==1) $fatal(1,"MMIO not ready");
        @(negedge clk);we=0;
    endtask
    // Capture operands BEFORE the active edge updates tap; inspect acc AFTER NBA.
    always @(posedge clk) begin
        if(rst_n && dut.sv && dut.engine_ready) begin
            if(step>=9) $fatal(1,"too many MAC samples");
            cap_a=$signed(dut.av);cap_w=$signed(dut.wv);
            cap_tap=dut.tap;cap_before=$signed(dut.normal_result);sample_time=$time;
            if(dut.tap!==step || $signed(dut.av)!==$signed(expected[3+3*step]) ||
               $signed(dut.wv)!==$signed(expected[4+3*step])) $fatal(1,"operand/tap mismatch at step %0d",step);
            if(step==0 && dut.normal_result!==expected[0]) $fatal(1,"initial bias mismatch");
            #1;
            $fdisplay(log_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d",step+1,sample_time,cap_tap,cap_a,cap_w,cap_before,$signed(dut.normal_result));
            if(dut.normal_result!==expected[5+3*step])
                $fatal(1,"MAC %0d: got %0d expected %0d",step+1,$signed(dut.normal_result),$signed(expected[5+3*step]));
            step=step+1;
        end
    end
    initial begin
        $dumpfile("build/custom_wave/custom.vcd");$dumpvars(0,dut);
        $readmemh("build/custom_wave/expected.hex",expected);
        log_fd=$fopen("build/custom_wave/actual_steps.csv","w");
        if(!log_fd) $fatal(1,"cannot open step log");
        $fdisplay(log_fd,"step,time_ns,tap,input,weight,acc_before,acc_after");
        for(i=0;i<4096;i=i+1) ram.bytes[i]='ha5;
        $readmemh("build/custom_wave/ram.hex",ram.bytes);
        repeat(2) @(negedge clk);rst_n=1;
        write_reg(8,'h100);write_reg(12,'h401);write_reg(16,'h200);write_reg(20,'h300);
        write_reg(24,'h30003);write_reg(28,'h10001);write_reg(32,expected[1]);write_reg(0,1);
        @(negedge clk);addr='h40000004;re=1;#1;
        if(rdata!==1) $fatal(1,"missing BUSY");
        while(rdata[0]) begin @(negedge clk);#1;end
        if(rdata!==2 || step!=9 || ram.bytes['h401]!==expected[2][7:0] ||
           dut.out_value!==expected[2][7:0] || ram.writes!=1)
            $fatal(1,"final status=%h samples=%0d RAM=%0d expected=%0d",rdata,step,$signed(ram.bytes['h401]),$signed(expected[2]));
        if(ram.bytes['h400]!=='ha5 || ram.bytes['h402]!=='ha5 || ram.bytes['h403]!=='ha5)
            $fatal(1,"neighbor bytes changed");
        $display("FINAL RAM[0x401] = %0d (0x%02h), STATUS=2",$signed(ram.bytes['h401]),ram.bytes['h401]);
        repeat(5) @(negedge clk);$fclose(log_fd);
        $display("PASS tb_custom_wave");$finish;
    end
    initial begin #1000000;$fatal(1,"custom waveform timeout");end
endmodule
