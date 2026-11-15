`timescale 1ns/1ps
module tb_vector_math;
    reg signed [31:0] value,multiplier,other;reg [7:0] shift,limit;reg round_mode,clip,first;
    wire signed [63:0] scaled,activated,prelu,added;wire signed [31:0] maximum;wire signed [7:0] quantized;
    fixed_scale_unit scale(value,multiplier,shift,round_mode,scaled);
    activation_unit activation(scaled,clip,limit,activated);
    prelu_unit prelu_math(value,scaled,prelu);
    residual_add_unit addition(scaled,64'sd200,added);
    maxpool_unit pool(value,other,first,maximum);
    requantize_unit quant(scaled,8'd0,quantized);
    integer v,m,s,mode,count=0;reg signed [63:0] product,expected,mag;
    initial begin
        clip=1;limit=96;first=0;other=-17;
        for(v=-128;v<=127;v=v+1) for(m=-3;m<=3;m=m+1)
        for(s=0;s<10;s=s+1) for(mode=0;mode<2;mode=mode+1) begin
            value=v;multiplier=m;shift=s;round_mode=mode;#1;
            product=v*m;mag=product<0 ? -product : product;
            if(mode && s!=0) expected=(mag+(64'd1<<(s-1)))>>s;
            else expected=product>>>s;
            if(mode && s!=0 && product<0) expected=-expected;
            if(scaled!==expected) $fatal(1,"scale v%0d m%0d s%0d",v,m,s);
            if(added!==expected+200) $fatal(1,"add");
            if(prelu!==(v<0 ? expected : v)) $fatal(1,"prelu");
            if(activated!==(expected<0 ? 64'sd0 : expected>96 ? 64'sd96 : expected)) $fatal(1,"activation");
            if($signed(quantized)!==(expected>127 ? 64'sd127 : expected< -128 ? -64'sd128 : expected)) $fatal(1,"saturation");
            if(maximum!==(v> -17 ? v : -17)) $fatal(1,"maxpool");
            count=count+1;
        end
        value=32'sh80000000;multiplier=32'sh80000000;shift=63;round_mode=1;#1;
        if(scaled!==1) $fatal(1,"INT64 rounding boundary");
        shift=255;#1;if(scaled!==0) $fatal(1,"large rounded shift");
        round_mode=0;value=-1;multiplier=1;#1;if(scaled!==-64'sd1) $fatal(1,"large arithmetic shift");
        first=1;other=100;#1;if(maximum!==-1) $fatal(1,"pool seed");
        $display("PASS tb_vector_math (%0d signed scale/activation/PReLU/add/pool/quant cases)",count);$finish;
    end
endmodule
