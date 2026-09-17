`timescale 1ns/1ps
module tb_systolic_matmul;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,clear=0,ce=1,start=0,accumulate=0,dw=0,aw=0,bw=0,biw=0;
    reg [3:0] nr,nc,nk;reg [2:0] rr,cc,kk;reg signed [7:0] value;reg signed [31:0] bias;
    wire busy,done;wire [2047:0] sums;reg [2047:0] held;
    integer m,n,k,mb,nb,kb,r,c,q,step,fd,case_id=0,checked=0;reg signed [31:0] expected,actual;
    systolic_tile dut(clk,rst_n,clear,ce,start,accumulate,dw,nr,nc,nk,aw,bw,biw,rr,cc,kk,value,bias,busy,done,sums);
    function integer wa(input integer row,red);wa=((row*31+red*13)%256)-128;endfunction
    function integer xb(input integer row,col,red,mode);xb=((col*17+red*7+mode*row*11)%256)-128;endfunction
    task matrix(input integer mm,nn,km,mode);
        begin
            m=mm;n=nn;k=km;dw=mode;
            for(mb=0;mb<m;mb=mb+8) for(nb=0;nb<n;nb=nb+8) begin
                nr=(m-mb<8)?m-mb:8;nc=(n-nb<8)?n-nb:8;
                for(r=0;r<nr;r=r+1) begin rr=r;bias=32'h7fff0000+r+mb;biw=1;@(negedge clk);biw=0;end
                for(kb=0;kb<k;kb=kb+8) begin
                    nk=k-kb<8 ? k-kb : 8;
                    for(r=0;r<nr;r=r+1) for(q=0;q<nk;q=q+1) begin
                        rr=r;kk=q;value=wa(mb+r,kb+q);aw=1;@(negedge clk);aw=0;
                    end
                    for(r=0;r<(mode ? nr : 1);r=r+1) for(c=0;c<nc;c=c+1) for(q=0;q<nk;q=q+1) begin
                        rr=r;cc=c;kk=q;value=xb(mb+r,nb+c,kb+q,mode);bw=1;@(negedge clk);bw=0;
                    end
                    accumulate=kb!=0;start=1;@(negedge clk);start=0;step=0;
                    while(busy) begin
                        ce=step%4!=1;held=sums;@(negedge clk);
                        if(!ce && sums!==held) $fatal(1,"array changed while paused");step=step+1;
                    end
                    ce=1;
                end
                for(r=0;r<nr;r=r+1) for(c=0;c<nc;c=c+1) begin
                    expected=32'h7fff0000+mb+r;
                    for(q=0;q<k;q=q+1) expected=expected+wa(mb+r,q)*xb(mb+r,nb+c,q,mode);
                    actual=$signed(sums[(r*8+c)*32+:32]);
                    $fwrite(fd,"%0d,%0d,%0d,%0d,%0d,%0d\n",case_id,mode,mb+r,nb+c,expected,actual);
                    if(actual!==expected) $fatal(1,"matmul mode%0d M%0d N%0d K%0d cell%0d,%0d got%0d want%0d",mode,m,n,k,mb+r,nb+c,actual,expected);
                    checked=checked+1;
                end
            end
            case_id=case_id+1;
        end
    endtask
    initial begin
        nr=1;nc=1;nk=1;rr=0;cc=0;kk=0;value=0;bias=0;
        fd=$fopen("build/systolic_matmul.csv","w");$fwrite(fd,"case,dw,row,col,expected,actual\n");
        @(negedge clk);rst_n=1;
        matrix(1,1,1,0);matrix(3,5,2,0);matrix(8,8,8,0);matrix(9,10,17,0);matrix(17,9,13,0);
        matrix(11,13,9,1);matrix(9,10,49,1);matrix(2,3,7,0);
        start=1;@(negedge clk);start=0;ce=0;clear=1;@(negedge clk);
        if(busy || sums!==0 || done) $fatal(1,"tile reset during pause");
        clear=0;ce=1;matrix(1,2,1,0);
        $fclose(fd);$display("PASS tb_systolic_matmul (%0d exact INT32 results, tiled tails, DW, stalls, reset)",checked);$finish;
    end
    initial begin repeat(1000000) @(posedge clk);$fatal(1,"timeout");end
endmodule
