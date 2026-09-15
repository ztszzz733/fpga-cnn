`timescale 1ns/1ps
// Fetch eight little-endian words, then publish ONE complete descriptor.
// The ready/valid output can later be fed by a burst/multi-task fetch engine.
module task_descriptor_reader(
    input wire clk,rst_n,clear,start,input wire [31:0] base_address,
    output wire idle,
    output wire cmd_valid,input wire cmd_ready,output wire [31:0] cmd_addr,
    input wire rsp_valid,input wire [31:0] rsp_data,
    output wire descriptor_valid,input wire descriptor_ready,output wire [255:0] descriptor
);
    localparam IDLE=0,REQUEST=1,WAIT_WORD=2,PUBLISH=3;
    reg [1:0] state;
    reg [2:0] word_index;
    reg [31:0] address;
    reg [255:0] words;
    assign idle=state==IDLE;
    assign cmd_valid=state==REQUEST && !clear;
    assign cmd_addr=address;
    assign descriptor_valid=state==PUBLISH && !clear;
    assign descriptor=words;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin state<=IDLE;word_index<=0;address<=0;words<=0;end
        else if(clear) begin state<=IDLE;word_index<=0;address<=0;words<=0;end
        else case(state)
            IDLE:if(start) begin address<=base_address;word_index<=0;state<=REQUEST;end
            REQUEST:if(cmd_ready) state<=WAIT_WORD;
            WAIT_WORD:if(rsp_valid) begin
                words[word_index*32 +: 32]<=rsp_data;
                if(word_index==7) state<=PUBLISH;
                else begin word_index<=word_index+1'b1;address<=address+4;state<=REQUEST;end
            end
            PUBLISH:if(descriptor_ready) state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
