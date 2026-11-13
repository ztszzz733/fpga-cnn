`timescale 1ns/1ps
// Two independent one-word read buffers (input / parameters). Per-task invalidation.
// Fetch aligned 32-bit words and retain all four bytes. Never caches output writes.
module systolic_read_cache(
    input wire clk,rst_n,clear,req_valid,output wire req_ready,
    input wire [31:0] req_addr,input wire req_byte,req_bank,
    output reg response_valid,output reg [31:0] response_data,
    output wire cmd_valid,input wire cmd_ready,output wire [31:0] cmd_addr,
    input wire rsp_valid,input wire [31:0] rsp_data
);
    reg [1:0] state;reg [31:0] address;reg byte_mode,bank;
    reg [31:0] tags[0:1],data[0:1];reg [1:0] valid;
    wire hit=valid[req_bank] && tags[req_bank]=={req_addr[31:2],2'b0};
    assign req_ready=state==0 && !clear;
    assign cmd_valid=state==1 && !clear;assign cmd_addr={address[31:2],2'b0};
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin state<=0;valid<=0;response_valid<=0;response_data<=0;address<=0;byte_mode<=0;bank<=0;end
        else if(clear) begin state<=0;valid<=0;response_valid<=0;end
        else begin
            response_valid<=0;
            case(state)
                0:if(req_valid) begin
                    if(hit) begin response_data<=req_byte ? ((data[req_bank]>>(req_addr[1:0]*8)) & 32'hff) : data[req_bank];response_valid<=1;end
                    else begin address<=req_addr;byte_mode<=req_byte;bank<=req_bank;state<=1;end
                end
                1:if(cmd_ready) state<=2;
                2:if(rsp_valid) begin
                    tags[bank]<={address[31:2],2'b0};data[bank]<=rsp_data;valid[bank]<=1;
                    response_data<=byte_mode ? ((rsp_data>>(address[1:0]*8)) & 32'hff) : rsp_data;
                    response_valid<=1;state<=0;
                end
                default:state<=0;
            endcase
        end
    end
endmodule
