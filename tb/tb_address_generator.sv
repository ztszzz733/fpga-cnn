`timescale 1ns/1ps
module tb_address_generator;
    reg [31:0] ib='h1001,ob='h8001,wb='h4003,bb='h6000;
    reg [31:0] sz={16'd5,16'd5},channels={16'd2,16'd3},cp='h113;
    reg [31:0] x=0,y=0; reg [15:0] ic=0,oc=0;
    reg [3:0] tap=0; reg [1:0] pool=0;
    wire [31:0] ia,oa,wa,ba,cw,ch,ow,oh; wire pad,valid;
    address_generator dut(ib,ob,wb,bb,sz,channels,cp,x,y,ic,oc,tap,pool,
                          ia,oa,wa,ba,pad,valid,cw,ch,ow,oh);
    task good; #1; if(valid!==1'b1) $fatal(1,"valid config rejected"); endtask
    task bad; #1; if(valid!==1'b0) $fatal(1,"invalid config accepted"); endtask
    initial begin
        good(); if(cw!==5 || ow!==5 || pad!==1'b1) $fatal(1,"dimensions/pad");
        tap=4; ic=2; oc=1; #1;
        if(pad!==1'b0 || ia!=='h1003 || wa!=='h402c || ba!=='h6004 || oa!=='h8002)
            $fatal(1,"layout pad=%b ia=%h wa=%h ba=%h oa=%h",pad,ia,wa,ba,oa);
        x=4; y=4; tap=8; #1; if(pad!==1'b1) $fatal(1,"bottom right pad");
        cp='h200023; x=0; y=0; tap=0; pool=3; good();
        if(cw!==2 || ow!==1 || oh!==1 || ia!=='h1027) $fatal(1,"stride/pool address %h",ia);
        cp='h3; bad(); cp='h114; bad(); cp='h400113; bad();
        cp='h113; bb='h6001; bad(); bb='h6000;
        sz=0; bad(); sz={16'd224,16'd224}; ob='h80000000; good();
        channels=0; bad(); channels={16'd2,16'd3};
        ib='hfffffffc; bad(); ib='h1001;
        ob=ib; bad(); ob='h4003; bad(); ob='h6000; bad(); ob='h80000000; good();
        ob='hfffffff0; bad(); ob='h8001;
        sz={16'd1,16'd1}; cp='h13; bad(); cp='h200113; bad();
        sz={16'd3,16'd3}; cp='h13; ib='h1001; channels='h10001;
        ob='hffffffff; good(); // final legal byte at top of address space
        $display("PASS tb_address_generator"); $finish;
    end
endmodule
