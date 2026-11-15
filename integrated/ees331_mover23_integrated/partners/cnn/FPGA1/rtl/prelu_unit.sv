`timescale 1ns/1ps
module prelu_unit(input wire signed [31:0] value,input wire signed [63:0] negative_scaled,
    output wire signed [63:0] result);
    assign result=value<0 ? negative_scaled : {{32{value[31]}},value};
endmodule
