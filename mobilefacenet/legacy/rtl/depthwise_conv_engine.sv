`timescale 1ns/1ps
// One channel's output dot product: exactly K*K pairs, never IC*K*K.
// The external address generator uses the same channel for input/weight/bias.
module depthwise_conv_engine(
    input wire clk,rst_n,clear,start,
    input wire [3:0] kernel_size, input wire signed [31:0] bias,
    input wire sample_valid, output wire sample_ready,
    input wire signed [7:0] input_value,weight_value,
    output reg busy,done,error, output wire signed [31:0] result
);
    reg [5:0] remaining;
    wire legal=kernel_size==3 || kernel_size==7;
    wire begin_dot=start && !busy && legal && !clear;
    wire take=sample_valid && sample_ready;
    wire signed [31:0] product;
    assign sample_ready=busy && !clear;
    mac_unit multiply(input_value,weight_value,product);
    accumulator sum(clk,rst_n,clear,begin_dot,take,bias,product,result);
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin busy<=0;done<=0;error<=0;remaining<=0; end
        else begin
            done<=0;error<=0;
            if(clear) begin busy<=0;remaining<=0; end
            else if(start && !busy) begin
                if(legal) begin remaining<={2'd0,kernel_size}*kernel_size;busy<=1; end
                else error<=1;
            end else if(take) begin
                remaining<=remaining-1;
                if(remaining==1) begin busy<=0;done<=1; end
            end
        end
    end
endmodule
