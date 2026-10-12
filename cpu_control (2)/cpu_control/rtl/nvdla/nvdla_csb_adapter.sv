// CPU byte-addressed MMIO -> NVDLA word-addressed CSB. One outstanding command.
// All writes are non-posted: ready means the engine acknowledged the write.
module nvdla_csb_adapter #(
    parameter logic [31:0] MMIO_BASE=32'h4000_0000
)(
    input logic clk,rst_n,
    input logic [31:0] mmio_addr,mmio_wdata,
    input logic mmio_we,mmio_re,
    output logic [31:0] mmio_rdata,output logic mmio_ready,
    output logic csb_valid,input logic csb_ready,
    output logic [15:0] csb_addr,output logic [31:0] csb_wdata,
    output logic csb_write,csb_nposted,
    input logic csb_rvalid,input logic [31:0] csb_rdata,
    input logic csb_wr_complete,
    output logic [1:0] config_state,output logic config_fault
);
    localparam IDLE=2'd0,SEND=2'd1,WAIT_REPLY=2'd2,ACK=2'd3;
    wire [31:0] mmio_offset=mmio_addr-MMIO_BASE;
    assign csb_valid=config_state==SEND;
    assign csb_nposted=1'b1;
    assign mmio_ready=config_state==ACK;
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            config_state<=IDLE;config_fault<=0;mmio_rdata<=0;
            csb_addr<=0;csb_wdata<=0;csb_write<=0;
        end else case(config_state)
            IDLE: if(mmio_re||mmio_we) begin
                if(mmio_addr<MMIO_BASE || mmio_addr-MMIO_BASE>=32'h40000 ||
                   mmio_addr[1:0]!=0 || (mmio_re&&mmio_we)) begin
                    config_fault<=1;mmio_rdata<=32'hdead_bad0;config_state<=ACK;
                end else begin
                    csb_addr<=mmio_offset[17:2];
                    csb_wdata<=mmio_wdata;csb_write<=mmio_we;config_state<=SEND;
                end
            end
            SEND: if(csb_ready) config_state<=WAIT_REPLY;
            WAIT_REPLY: if((csb_write&&csb_wr_complete)||(!csb_write&&csb_rvalid)) begin
                mmio_rdata<=csb_rdata;config_state<=ACK;
            end
            ACK: if(!(mmio_re||mmio_we)) config_state<=IDLE;
            default: config_state<=IDLE;
        endcase
    end
endmodule
