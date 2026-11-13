`timescale 1ns/1ps
// Teaching bench uses the real 8x8 tile; only its top-left 2x2 cells are valid.
// Input windows are two columns, each containing three reduction elements.
module tb_systolic_wave;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,clear=0,ce=1,start=0;
    reg a_we=0,b_we=0,bias_we=0;
    reg [2:0] wr_row=0,wr_col=0,wr_k=0;
    reg signed [7:0] wr_value=0;
    reg signed [31:0] wr_bias=0;
    wire busy,done;
    wire [2047:0] sums;
    reg [31:0] data[0:13];
    integer r,c,k,fd,tick_before,time_before;
    integer pw[0:3],px[0:3],pf[0:3];
    systolic_tile dut(clk,rst_n,clear,ce,start,1'b0,1'b0,4'd2,4'd2,4'd3,
        a_we,b_we,bias_we,wr_row,wr_col,wr_k,wr_value,wr_bias,busy,done,sums);
    wire array_ce=dut.array_ce;
    wire load_bias=dut.array.load;
    wire [5:0] run_tick=dut.tick;
    wire signed [7:0] w00=dut.array.rows[0].cols[0].pe.a_in;
    wire signed [7:0] x00=dut.array.rows[0].cols[0].pe.b_in;
    wire signed [7:0] w01=dut.array.rows[0].cols[1].pe.a_in;
    wire signed [7:0] x01=dut.array.rows[0].cols[1].pe.b_in;
    wire signed [7:0] w10=dut.array.rows[1].cols[0].pe.a_in;
    wire signed [7:0] x10=dut.array.rows[1].cols[0].pe.b_in;
    wire signed [7:0] w11=dut.array.rows[1].cols[1].pe.a_in;
    wire signed [7:0] x11=dut.array.rows[1].cols[1].pe.b_in;
    wire fire00=array_ce && !load_bias && dut.array.rows[0].cols[0].pe.a_valid && dut.array.rows[0].cols[0].pe.b_valid;
    wire fire01=array_ce && !load_bias && dut.array.rows[0].cols[1].pe.a_valid && dut.array.rows[0].cols[1].pe.b_valid;
    wire fire10=array_ce && !load_bias && dut.array.rows[1].cols[0].pe.a_valid && dut.array.rows[1].cols[0].pe.b_valid;
    wire fire11=array_ce && !load_bias && dut.array.rows[1].cols[1].pe.a_valid && dut.array.rows[1].cols[1].pe.b_valid;
    wire signed [31:0] acc00=sums[0+:32],acc01=sums[32+:32];
    wire signed [31:0] acc10=sums[256+:32],acc11=sums[288+:32];
    always @(posedge clk) if(rst_n && dut.state==2) begin
        tick_before=run_tick;time_before=$time;
        pw[0]=w00;pw[1]=w01;pw[2]=w10;pw[3]=w11;
        px[0]=x00;px[1]=x01;px[2]=x10;px[3]=x11;
        pf[0]=fire00;pf[1]=fire01;pf[2]=fire10;pf[3]=fire11;
        #1; // Capture updated sums after nonblocking assignments.
        $fwrite(fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            time_before,tick_before,pw[0],px[0],pf[0],acc00,pw[1],px[1],pf[1],acc01,
            pw[2],px[2],pf[2],acc10,pw[3],px[3],pf[3],acc11);
    end
    initial begin
        $readmemh("build/systolic_wave/input.hex",data);
        $dumpfile("build/systolic_wave/systolic.vcd");$dumpvars(1,tb_systolic_wave);
        fd=$fopen("build/systolic_wave/actual.csv","w");
        $fwrite(fd,"time_ns,tick,w00,x00,fire00,acc00,w01,x01,fire01,acc01,w10,x10,fire10,acc10,w11,x11,fire11,acc11\n");
        repeat(2) @(negedge clk);rst_n=1;
        for(r=0;r<2;r=r+1) begin
            bias_we=1;wr_row=r;wr_bias=data[12+r];@(negedge clk);bias_we=0;
        end
        for(r=0;r<2;r=r+1) for(k=0;k<3;k=k+1) begin
            a_we=1;wr_row=r;wr_k=k;wr_value=data[r*3+k];@(negedge clk);a_we=0;
        end
        for(c=0;c<2;c=c+1) for(k=0;k<3;k=k+1) begin
            b_we=1;wr_row=0;wr_col=c;wr_k=k;wr_value=data[6+c*3+k];@(negedge clk);b_we=0;
        end
        start=1;@(negedge clk);start=0;
        wait(done);repeat(3) @(negedge clk);
        $fclose(fd);$display("PASS tb_systolic_wave (capture complete; Python checks every sample)");$finish;
    end
    initial begin #10000;$fatal(1,"wave example timeout");end
endmodule
