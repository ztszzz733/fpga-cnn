`timescale 1ns/1ps
// One output dot product. The controller streams K*K*IC signed pairs,
// with arbitrary gaps. Weight order is [OC][IC][KY][KX].
module conv_engine(
    input wire clk,rst_n,clear,start,
    input wire [3:0] kernel_size, input wire [15:0] input_channels,
    input wire signed [31:0] bias,
    input wire sample_valid, output wire sample_ready,
    input wire signed [7:0] input_value,weight_value,
    output reg busy,done,error, output wire signed [31:0] result
);
    reg [31:0] remaining;
    wire legal=(kernel_size==1 || kernel_size==3) && input_channels!=0;
    wire begin_dot=start && !busy && legal && !clear;
    wire take=sample_valid && sample_ready;
    wire signed [31:0] product;
    assign sample_ready=busy && !clear;
    mac_unit multiply(input_value,weight_value,product);
    accumulator sum(clk,rst_n,clear,begin_dot,take,bias,product,result);
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin busy<=0;done<=0;error<=0;remaining<=0; end
        else begin
            done<=0; error<=0;
            if(clear) begin busy<=0;remaining<=0; end
            else if(start && !busy) begin
                if(legal) begin
                    remaining<={28'd0,kernel_size}*kernel_size*input_channels; busy<=1;
                end else error<=1;
            end else if(take) begin
                remaining<=remaining-1;
                if(remaining==1) begin busy<=0;done<=1; end
            end
        end
    end
endmodule
