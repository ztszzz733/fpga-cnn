module address_decoder #(
    parameter logic [31:0] SRAM_BASE     = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE     = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000,
    parameter logic [31:0] CNN_MMIO_SIZE = 32'h0000_1000
) (
    input  logic [31:0] addr,
    output logic        sram_hit,
    output logic        mmio_window_hit,
    output logic        mmio_reg_hit,
    output logic        unmapped
);
    logic [32:0] sram_offset;
    logic [32:0] mmio_offset;

    always_comb begin
        sram_offset = {1'b0, addr} - {1'b0, SRAM_BASE};
        mmio_offset = {1'b0, addr} - {1'b0, CNN_MMIO_BASE};

        // In 33 bits, addr < BASE wraps to a value above 2^32, which cannot
        // be less than a 32-bit SIZE. This avoids BASE+SIZE overflow entirely.
        sram_hit = sram_offset < {1'b0, SRAM_SIZE};
        mmio_window_hit = mmio_offset < {1'b0, CNN_MMIO_SIZE};

        mmio_reg_hit = 1'b0;
        if (mmio_window_hit) begin
            case (mmio_offset)
                33'h0000_0000,
                33'h0000_0004,
                33'h0000_0008,
                33'h0000_000c,
                33'h0000_0010,
                33'h0000_0014,
                33'h0000_0018,
                33'h0000_001c,
                33'h0000_0020: mmio_reg_hit = 1'b1;
                default:       mmio_reg_hit = 1'b0;
            endcase
        end

        unmapped = !(sram_hit || mmio_window_hit);
    end
endmodule
