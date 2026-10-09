`timescale 1ns/1ps
module maxpool_unit(input wire signed [31:0] sample,maximum,input wire first,
    output wire signed [31:0] result);
    assign result=first || sample>maximum ? sample : maximum;
endmodule
