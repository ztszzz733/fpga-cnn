`timescale 1ns/1ps
// Nine word-wide MMIO registers. A request is accepted on each rising edge
// with ready=1. CONTROL commands read as zero; STATUS is read-only.
module accelerator_regs #(
    parameter [31:0] BASE_ADDR = 32'h4000_0000
)(
    input wire clk, input wire rst_n,
    input wire [31:0] mmio_addr, mmio_wdata,
    input wire mmio_we, mmio_re,
    output reg [31:0] mmio_rdata, output wire mmio_ready,
    output reg accelerator_start, accelerator_reset,
    output reg [3:0] op_type,
    input wire accelerator_busy, accelerator_done, accelerator_error,
    output reg [31:0] input_addr, output_addr, weight_addr, bias_addr,
    output reg [31:0] feature_size, channels, layer_param
);
    reg done_sticky, error_sticky;
    wire [31:0] offset = mmio_addr - BASE_ADDR;
    wire selected = (mmio_addr >= BASE_ADDR) && (offset <= 32'h20)
                    && (mmio_addr[1:0] == 0);
    wire locked = accelerator_busy || accelerator_start || accelerator_reset;
    assign mmio_ready = selected && (mmio_we || mmio_re);
    always @* begin
        mmio_rdata = 0;
        if (selected && mmio_re) begin
            case (offset)
                32'h00: mmio_rdata = {26'd0,op_type,2'b00};
                32'h04: mmio_rdata = {29'b0, error_sticky, done_sticky,
                                      accelerator_busy | accelerator_start};
                32'h08: mmio_rdata = input_addr;
                32'h0c: mmio_rdata = output_addr;
                32'h10: mmio_rdata = weight_addr;
                32'h14: mmio_rdata = bias_addr;
                32'h18: mmio_rdata = feature_size;
                32'h1c: mmio_rdata = channels;
                32'h20: mmio_rdata = layer_param;
                default: mmio_rdata = 0;
            endcase
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accelerator_start <= 0; accelerator_reset <= 0; op_type <= 0;
            done_sticky <= 0; error_sticky <= 0;
            input_addr <= 0; output_addr <= 0; weight_addr <= 0; bias_addr <= 0;
            feature_size <= {16'd112,16'd112};
            channels <= {16'd1,16'd3};
            layer_param <= 32'h0010_0113; // 3x3, stride=1, pad=1, ReLU
        end else begin
            accelerator_start <= 0; accelerator_reset <= 0;
            if (accelerator_done && !accelerator_reset) done_sticky <= 1;
            if (accelerator_error && !accelerator_reset) error_sticky <= 1;
            if (selected && mmio_we) begin
                if (offset == 0) begin
                    if (!locked && !mmio_wdata[1]) op_type <= mmio_wdata[5:2];
                    if (mmio_wdata[1]) begin // RESET takes priority over START
                        accelerator_reset <= 1;
                        done_sticky <= 0; error_sticky <= 0;
                    end else if (mmio_wdata[0]) begin
                        if (!locked) begin
                            accelerator_start <= 1;
                            done_sticky <= 0; error_sticky <= 0;
                        end else error_sticky <= 1;
                    end
                end else if ((offset >= 8) && !locked) begin
                    case (offset)
                        32'h08: input_addr <= mmio_wdata;
                        32'h0c: output_addr <= mmio_wdata;
                        32'h10: weight_addr <= mmio_wdata;
                        32'h14: bias_addr <= mmio_wdata;
                        32'h18: feature_size <= mmio_wdata;
                        32'h1c: channels <= mmio_wdata;
                        32'h20: layer_param <= mmio_wdata;
                        default: ;
                    endcase
                end
            end
        end
    end
endmodule
