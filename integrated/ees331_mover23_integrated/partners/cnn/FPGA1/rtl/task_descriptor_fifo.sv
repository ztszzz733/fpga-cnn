`timescale 1ns/1ps
// Ready/valid descriptor boundary. Increasing DEPTH does not change the RAM ABI.
module task_descriptor_fifo #(parameter DEPTH=4)(
    input wire clk,rst_n,clear,
    input wire in_valid,output wire in_ready,input wire [255:0] in_data,
    output wire out_valid,input wire out_ready,output wire [255:0] out_data,
    output wire [31:0] level
);
    localparam PTR_W=DEPTH<=1 ? 1 : $clog2(DEPTH);
    reg [255:0] storage[0:DEPTH-1];
    reg [PTR_W-1:0] head,tail;
    reg [31:0] used;
    assign in_ready=!clear && used<DEPTH;
    assign out_valid=!clear && used!=0;
    assign out_data=used!=0 ? storage[head] : 256'd0;
    assign level=used;
    wire push=in_valid && in_ready,pop=out_valid && out_ready;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin head<=0;tail<=0;used<=0;end
        else if(clear) begin head<=0;tail<=0;used<=0;end
        else begin
            if(push) begin
                storage[tail]<=in_data;
                tail<=tail==DEPTH-1 ? 0 : tail+1'b1;
            end
            if(pop) head<=head==DEPTH-1 ? 0 : head+1'b1;
            case({push,pop})
                2'b10:used<=used+1;
                2'b01:used<=used-1;
                default:;
            endcase
        end
    end
endmodule
