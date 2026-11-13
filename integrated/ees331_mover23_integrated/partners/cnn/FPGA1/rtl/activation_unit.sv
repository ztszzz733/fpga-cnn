`timescale 1ns/1ps
module activation_unit(input wire signed [63:0] value,input wire clip_six,
    input wire [7:0] limit,output wire signed [63:0] result);
    assign result=value<0 ? 64'sd0 : (clip_six && value>$signed({56'd0,limit}) ? $signed({56'd0,limit}) : value);
endmodule
