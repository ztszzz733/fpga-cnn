`timescale 1ns/1ps
module tb_accelerator_mem_if;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,cancel=0,cv=0,cw=0,cb=0;
    reg [31:0] ca=0,cd=0; wire cr,rv,idle;
    wire [31:0] rr,ma,md,mr; wire rd,wr,ready;
    accelerator_mem_if dut(clk,rst_n,cancel,cv,cr,cw,cb,ca,cd,rv,rr,idle,ma,md,rd,wr,mr,ready);
    model_data_ram #(64,5) ram(clk,rst_n,ma,md,rd,wr,mr,ready);
    task issue(input w,b,input [31:0] a,d);
        @(negedge clk); while(!cr) @(negedge clk);
        cv=1; cw=w; cb=b; ca=a; cd=d;
        @(negedge clk); cv=0;
    endtask
    task response(input [31:0] expected);
        while(!rv) @(negedge clk);
        if(rr!==expected) $fatal(1,"RAM response got %h expected %h",rr,expected);
    endtask
    task drain;
        while(!idle) begin @(negedge clk); if(rv) $fatal(1,"cancelled response"); end
        @(negedge clk); cancel=0;
    endtask
    initial begin
        ram.bytes[0]='h00; ram.bytes[1]='h7f; ram.bytes[2]='h80; ram.bytes[3]='hff;
        ram.bytes[4]='h44; ram.bytes[5]='h33; ram.bytes[6]='h22; ram.bytes[7]='h11;
        ram.bytes[12]='ha5;ram.bytes[13]='ha5;ram.bytes[14]='ha5;ram.bytes[15]='ha5;
        repeat(2) @(negedge clk); rst_n=1;
        issue(0,0,0,0); response('hff807f00);
        issue(0,1,0,0); response(0); issue(0,1,1,0); response(127);
        issue(0,1,2,0); response('hffffff80); issue(0,1,3,0); response('hffffffff);
        issue(1,1,5,'ha5); response(0); issue(0,0,4,0); response('h1122a544);
        issue(1,0,8,'hdeadbeef); response(0); issue(0,0,8,0); response('hdeadbeef);
        issue(1,1,5,'h99); cancel=1; drain();
        issue(0,0,4,0); response('h1122a544); // aborted before RMW write
        issue(0,1,0,0); cancel=1; drain();
        issue(1,0,8,'h12345678); cancel=1; drain(); // presented write must drain
        issue(0,0,8,0); response('h12345678);
        issue(1,1,6,'hc3); while(!wr) @(negedge clk); cancel=1; drain();
        issue(0,0,4,0); response('h11c3a544); // byte write already presented: drain it
        issue(1,1,12,'h11);response(0);issue(1,1,13,'h80);response(0);
        issue(1,1,14,'hfe);response(0);issue(1,1,15,'h7f);response(0);
        issue(0,0,12,0);response('h7ffe8011);
        $display("PASS tb_accelerator_mem_if"); $finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
