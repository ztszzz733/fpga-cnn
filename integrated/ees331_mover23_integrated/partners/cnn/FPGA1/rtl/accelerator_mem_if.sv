`timescale 1ns/1ps
// One outstanding command. External requests stay asserted until ready.
// Little-endian byte access; byte writes use a full-word read/modify/write.
// cancel drains an already presented bus transfer, suppresses its response,
// and prevents the write phase if a byte-write read has not completed yet.
module accelerator_mem_if(
    input wire clk, rst_n, cancel,
    input wire cmd_valid, output wire cmd_ready,
    input wire cmd_write, cmd_byte,
    input wire [31:0] cmd_addr, cmd_wdata,
    output reg rsp_valid, output reg [31:0] rsp_rdata,
    output wire idle,
    output wire [31:0] mem_addr, mem_wdata,
    output wire mem_read, mem_write,
    input wire [31:0] mem_rdata, input wire mem_ready
);
    localparam IDLE=0, READ_WORD=1, WRITE_WORD=2;
    reg [1:0] state;
    reg [31:0] address, write_data;
    reg [1:0] lane;
    reg byte_access, byte_write, dropped;
    wire [31:0] shifted_word = mem_rdata >> {lane,3'b000};
    wire [31:0] byte_mask = 32'hff << {lane,3'b000};
    assign cmd_ready = state==IDLE && !cancel;
    assign idle = state==IDLE;
    assign mem_addr=address;
    assign mem_wdata=write_data;
    assign mem_read=state==READ_WORD;
    assign mem_write=state==WRITE_WORD;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; rsp_valid<=0; rsp_rdata<=0;
            address<=0; write_data<=0; lane<=0;
            byte_access<=0; byte_write<=0; dropped<=0;
        end else begin
            rsp_valid<=0;
            if(cancel && state!=IDLE) dropped<=1;
            case(state)
                IDLE: begin
                    dropped<=0;
                    if(cmd_valid && cmd_ready) begin
                        address<={cmd_addr[31:2],2'b00}; lane<=cmd_addr[1:0];
                        byte_access<=cmd_byte; byte_write<=cmd_byte && cmd_write;
                        write_data<=cmd_wdata;
                        state<=(cmd_write && !cmd_byte) ? WRITE_WORD : READ_WORD;
                    end
                end
                READ_WORD: if(mem_ready) begin
                    if(dropped || cancel) state<=IDLE;
                    else if(byte_write) begin
                        write_data <= (mem_rdata & ~byte_mask) |
                                      ((write_data & 32'hff) << {lane,3'b000});
                        state<=WRITE_WORD;
                    end else begin
                        rsp_rdata <= byte_access ? {{24{shifted_word[7]}},shifted_word[7:0]} : mem_rdata;
                        rsp_valid<=1; state<=IDLE;
                    end
                end
                WRITE_WORD: if(mem_ready) begin
                    if(!dropped && !cancel) begin rsp_valid<=1; rsp_rdata<=0; end
                    state<=IDLE;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
