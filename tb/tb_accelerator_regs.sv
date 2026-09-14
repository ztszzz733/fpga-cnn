`timescale 1ns/1ps
module tb_accelerator_regs;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0;
    reg [31:0] addr=0, wdata=0;
    reg we=0,re=0,busy=0,done=0,error=0;
    wire [31:0] rdata,ia,oa,wa,ba,sz,ch,cp;
    wire ready,start,reset;
    accelerator_regs dut(clk,rst_n,addr,wdata,we,re,rdata,ready,start,reset,
                         busy,done,error,ia,oa,wa,ba,sz,ch,cp);
    task wr(input [31:0] a,d);
        @(negedge clk); addr=a; wdata=d; we=1;
        #1; if (!ready) $fatal(1,"write not acknowledged");
        @(negedge clk); we=0;
    endtask
    task rd(input [31:0] a,d);
        @(negedge clk); addr=a; re=1; #1;
        if (!ready || rdata!==d) $fatal(1,"read %h got %h expected %h",a,rdata,d);
        @(negedge clk); re=0;
    endtask
    integer i;
    initial begin
        repeat(2) @(negedge clk); rst_n=1;
        rd('h40000018,{16'd224,16'd224}); rd('h4000001c,'h00010003);
        rd('h40000020,'h00100113); rd('h40000004,0);
        for (i=2;i<9;i=i+1) begin wr('h40000000+4*i,32'h12340000+i); rd('h40000000+4*i,32'h12340000+i); end
        wr('h40000004,7); rd('h40000004,0);
        wr('h40000000,1); if (!start) $fatal(1,"missing START");
        busy=1; @(negedge clk); if(start) $fatal(1,"START not pulse");
        wr('h40000008,99); rd('h40000008,'h12340002);
        wr('h40000000,1); if(start) $fatal(1,"START while busy");
        rd('h40000004,5);
        busy=0; done=1; @(negedge clk); done=0;
        rd('h40000004,6); rd('h40000004,6);
        wr('h40000000,3); if(!reset || start) $fatal(1,"RESET priority");
        done=1; error=1; @(negedge clk); done=0; error=0;
        rd('h40000004,0); rd('h40000000,0);
        error=1; @(negedge clk); error=0; rd('h40000004,4);
        wr('h40000000,1); rd('h40000004,0);
        @(negedge clk); addr='h40000024; re=1; #1;
        if(ready || rdata!==0) $fatal(1,"invalid address");
        addr='h40000009; #1; if(ready) $fatal(1,"unaligned address");
        addr='h50000008; #1; if(ready) $fatal(1,"base decode");
        $display("PASS tb_accelerator_regs"); $finish;
    end
    initial begin #10000; $fatal(1,"timeout"); end
endmodule
