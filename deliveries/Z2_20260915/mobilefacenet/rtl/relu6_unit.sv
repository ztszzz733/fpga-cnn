`timescale 1ns/1ps
// RELU6_MAX is expressed in the OUTPUT integer scale (e.g. 96 for scale=1/16).
// Apply after arithmetic requantization, before final INT8 saturation.
module relu6_unit #(parameter signed [31:0] RELU6_MAX=32'sd96)(
    input wire signed [31:0] value, input wire relu_enable,relu6_enable,
    output reg signed [31:0] result
);
    always @* begin
        if((relu_enable || relu6_enable) && value<0) result=0;
        else if(relu6_enable && value>RELU6_MAX) result=RELU6_MAX;
        else result=value;
    end
endmodule
