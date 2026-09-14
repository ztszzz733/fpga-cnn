`timescale 1ns/1ps
module relu_unit(input wire signed [31:0] value,
                 input wire enable, output wire signed [31:0] result);
    assign result = (enable && value[31]) ? 32'sd0 : value;
endmodule
