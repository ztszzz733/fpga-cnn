module cnn_mmio_regs #(
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000
) (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [31:0] mmio_addr,
    input  logic [31:0] mmio_wdata,
    input  logic        mmio_re,
    input  logic        mmio_we,
    output logic [31:0] mmio_rdata,
    output logic        mmio_ready,

    output logic [31:0] CONTROL,
    input  logic [31:0] STATUS,
    output logic [31:0] INPUT_ADDR,
    output logic [31:0] OUTPUT_ADDR,
    output logic [31:0] WEIGHT_ADDR,
    output logic [31:0] BIAS_ADDR,
    output logic [31:0] IMAGE_SIZE,
    output logic [31:0] CHANNELS,
    output logic [31:0] CNN_PARAM
);
    logic [5:0] offset;
    logic register_hit;

    assign offset = mmio_addr[5:0];
    assign register_hit = (mmio_addr >= CNN_MMIO_BASE) &&
                          (mmio_addr <= (CNN_MMIO_BASE + 32'h20)) &&
                          (mmio_addr[1:0] == 2'b00);
    assign mmio_ready = rst_n && (mmio_re || mmio_we) && register_hit;

    always_comb begin
        mmio_rdata = 32'b0;
        if (mmio_re && register_hit) begin
            case (offset)
                6'h04: mmio_rdata = STATUS;
                6'h08: mmio_rdata = INPUT_ADDR;
                6'h0c: mmio_rdata = OUTPUT_ADDR;
                6'h10: mmio_rdata = WEIGHT_ADDR;
                6'h14: mmio_rdata = BIAS_ADDR;
                6'h18: mmio_rdata = IMAGE_SIZE;
                6'h1c: mmio_rdata = CHANNELS;
                6'h20: mmio_rdata = CNN_PARAM;
                default: mmio_rdata = 32'b0;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            CONTROL <= 32'b0;
            INPUT_ADDR <= 32'b0;
            OUTPUT_ADDR <= 32'b0;
            WEIGHT_ADDR <= 32'b0;
            BIAS_ADDR <= 32'b0;
            IMAGE_SIZE <= 32'b0;
            CHANNELS <= 32'b0;
            CNN_PARAM <= 32'b0;
        end else begin
            CONTROL <= 32'b0;
            if (mmio_we && register_hit) begin
                case (offset)
                    6'h00: CONTROL <= {30'b0, mmio_wdata[1:0]};
                    6'h08: INPUT_ADDR <= mmio_wdata;
                    6'h0c: OUTPUT_ADDR <= mmio_wdata;
                    6'h10: WEIGHT_ADDR <= mmio_wdata;
                    6'h14: BIAS_ADDR <= mmio_wdata;
                    6'h18: IMAGE_SIZE <= mmio_wdata;
                    6'h1c: CHANNELS <= mmio_wdata;
                    6'h20: CNN_PARAM <= mmio_wdata;
                    default: begin end
                endcase
            end
        end
    end
endmodule
