`timescale 1ns/1ps
module tb_address_generator;
    reg [31:0] ib='h101,ob='h1001,wb='h2003,bb='h3000,sz='h50005,ch='h30002,lp='h113;
    reg [3:0] op=0;reg [31:0] x=0,y=0,i=0;reg [15:0] ic=0,oc=0;reg [5:0] tap=0;
    wire [31:0] ia,wa,ba,oa,sa,ow,oh,count;wire pad,valid;
    address_generator dut(ib,ob,wb,bb,sz,ch,lp,op,x,y,i,ic,oc,tap,ia,wa,ba,oa,sa,ow,oh,count,pad,valid);
    task good;#1;if(valid!==1) $fatal(1,"valid rejected");endtask
    task bad;#1;if(valid!==0) $fatal(1,"invalid accepted");endtask
    initial begin
        good();if(ow!==5 || oh!==5 || pad!==1) $fatal(1,"pad");
        tap=4;ic=1;oc=2;x=1;y=2;#1;
        if(ia!=='h125 || wa!=='h2034 || ba!=='h3008 || oa!=='h103e) $fatal(1,"CHW ia=%h wa=%h oa=%h",ia,wa,oa);
        op=1;ch='h20002;oc=1;ic=0;good();
        if(ia!=='h125 || wa!=='h2010) $fatal(1,"depthwise channel select");
        op=1;lp='h17;sz='h70007;x=0;y=0;tap=48;good();
        if(ow!==1 || ia!==ib+97 || wa!==wb+97) $fatal(1,"DW7 last tap");
        op=0;lp='h11;sz='h50005;good();
        op=3;lp=0;i=7;good();if(ia!==ib+7 || sa!==wb+7 || oa!==ob+7) $fatal(1,"ADD");
        op=5;sz='h10001;ch='h800080;good();if(count!==128) $fatal(1,"final size");
        ch='h7f007f;bad();op=4;good();lp=1;bad();
        op=0;ch='h10001;sz='h30003;lp='h13;good();
        lp='h400013;bad();lp='h800013;bad();lp=3;bad();lp='h15;bad();
        lp='h13;bb='h3001;bad();bb='h3000;ob=ib;bad();ob='h1001;
        ib='hfffffffc;bad();ib='h101;ob='hffffffff;good();
        ob='h1001;op=1;ch='h20001;bad();op=6;bad();
        $display("PASS tb_address_generator");$finish;
    end
endmodule
