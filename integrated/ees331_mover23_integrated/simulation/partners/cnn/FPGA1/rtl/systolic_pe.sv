`timescale 1ns/1ps
// A moves east, B moves south. All registers freeze when ce=0.
// clear beats ce; load beats MAC. INT32 overflow wraps modulo 2**32.
module systolic_pe(
    input wire clk,rst_n,clear,ce,load,
    input wire signed [31:0] initial_sum,
    input wire signed [7:0] a_in,b_in,input wire a_valid,b_valid,
    output reg signed [7:0] a_out,b_out,output reg a_out_valid,b_out_valid,
    output reg signed [31:0] sum
);
    wire signed [15:0] product=a_in*b_in;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin sum<=0;a_out<=0;b_out<=0;a_out_valid<=0;b_out_valid<=0;end
        else if(clear) begin sum<=0;a_out<=0;b_out<=0;a_out_valid<=0;b_out_valid<=0;end
        else if(ce) begin
            a_out<=a_in;b_out<=b_in;a_out_valid<=a_valid;b_out_valid<=b_valid;
            if(load) begin sum<=initial_sum;a_out_valid<=0;b_out_valid<=0;end
            else if(a_valid && b_valid) sum<=sum+{{16{product[15]}},product};
        end
    end
endmodule
