`timescale 1ns/1ps
// Signed INT32 x INT32 -> INT64. round_nearest: ties away from zero.
// Arithmetic truncation otherwise; shift >=64 sign-extends (rounded -> 0).
module fixed_scale_unit(input wire signed [31:0] value,multiplier,
    input wire [7:0] shift,input wire round_nearest,output reg signed [63:0] result);
    wire signed [63:0] product=$signed(value)*$signed(multiplier);
    reg [63:0] magnitude,rounded;
    always @* begin
        magnitude=product<0 ? -product : product;rounded=magnitude;
        if(shift==0) result=product;
        else if(shift>=64) result=round_nearest ? 64'sd0 : (product<0 ? -64'sd1 : 64'sd0);
        else if(round_nearest) begin
            rounded=(magnitude+(64'd1<<(shift-1)))>>shift;
            result=product<0 ? -$signed(rounded) : $signed(rounded);
        end else result=product>>>shift;
    end
endmodule
