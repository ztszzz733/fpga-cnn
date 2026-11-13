`timescale 1ns/1ps
module tb_operator_descriptor;
    reg [255:0] d;wire valid;wire [511:0] spans;
    reg [31:0] index=0;reg [1:0] tap=0;
    wire [31:0] a,b,o,p,count,channel_end;
    task_descriptor_info info(d,32'h8000,64'h8100,valid,spans);
    tensor_address_generator addresses(d[63:32],d[95:64],d[127:96],d[159:128],
        d[191:160],d[223:192],d[255:224],d[3:0],index,tap,a,b,o,p,count,channel_end);
    task setup(input integer op,fs,ch,lp);
        d={32'(lp),32'(ch),32'(fs),32'h4000,32'h3000,32'h2000,32'h1000,32'h100|32'(op)};
    endtask
    task expect_valid(input bit expected);#1;if(valid!==expected) $fatal(1,"descriptor %h valid%0d expected%0d",d,valid,expected);endtask
    initial begin
        setup(8,'h50007,'h30003,'h22);expect_valid(1);
        index=8;tap=3;#1;
        if(a!='h1000+47 || o!='h2008 || count!=18) $fatal(1,"pool CHW/tail address");
        setup(7,'h20003,'h30003,'h200000);index=7;expect_valid(1);
        if(p!='h4018 || channel_end!=12 || count!=18) $fatal(1,"per-channel record");
        d[159:128]=0;expect_valid(0);
        setup(10,'h20003,'h30003,'h100000);index=7;expect_valid(1);
        if(a!='h101c || spans[63:0]!='h1000 || spans[127:64]!='h1048) $fatal(1,"INT32 input range");
        d[63:32]='h1001;expect_valid(0);
        setup(6,'h10010,'h10002,0);expect_valid(0);
        setup(6,'h10010,'h10001,0);d[63:32]='hfffffff8;expect_valid(0);
        setup(6,'h10010,'h10001,0);d[95:64]='h8004;expect_valid(0);
        setup(6,'h10010,'h10001,0);d[95:64]='h1004;expect_valid(0);
        setup(6,'h10010,'h10001,0);d[159:128]='hfffffff0;expect_valid(0);
        setup(6,'h10010,'h10001,'h800000);expect_valid(0);
        setup(9,'h1000b,'h9000d,'h11);expect_valid(1);
        if(spans[511:448]!='h2064) $fatal(1,"MATMUL output range");
        d[255:224]='h800011;expect_valid(1);
        if(spans[511:448]!='h218c) $fatal(1,"INT32 MATMUL output range");
        d[95:64]='h2001;expect_valid(0);
        setup(9,'h2000b,'h9000d,'h11);expect_valid(0);
        setup(15,'h10010,'h10001,0);expect_valid(0);
        setup(6,'h10010,'h10001,0);d[31:16]=1;expect_valid(0);
        $display("PASS tb_operator_descriptor (scalar/matrix validation, wrap/overlap, CHW pooling, parameter/INT32 ranges)");$finish;
    end
endmodule
