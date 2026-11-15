module data_sram_tdp #(
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000
) (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [31:0] a_addr,
    input  logic [31:0] a_wdata,
    input  logic [3:0]  a_wstrb,
    input  logic        a_re,
    input  logic        a_we,
    output logic [31:0] a_rdata,

    input  logic        b_req,
    input  logic        b_we,
    input  logic [31:0] b_addr,
    input  logic [31:0] b_wdata,
    input  logic [3:0]  b_be,
    output logic        b_gnt,
    output logic        b_rvalid,
    output logic [31:0] b_rdata,
    output logic        b_error
);
    localparam integer WORDS = SRAM_SIZE / 4;
    localparam integer INDEX_WIDTH = $clog2(WORDS);

    logic [31:0] mem [0:WORDS-1];
    logic a_in_range, b_in_range, b_aligned, b_be_valid;
    logic b_conflict, b_request_error;
    logic [INDEX_WIDTH-1:0] a_word_index, b_word_index;
    logic b_rvalid_q, b_read_error_q;
    logic [31:0] b_rdata_q;

    assign a_in_range = (a_addr >= SRAM_BASE) &&
                        (a_addr < (SRAM_BASE + SRAM_SIZE));
    assign b_in_range = (b_addr >= SRAM_BASE) &&
                        (b_addr < (SRAM_BASE + SRAM_SIZE));
    assign a_word_index = (a_addr - SRAM_BASE) >> 2;
    assign b_word_index = (b_addr - SRAM_BASE) >> 2;
    assign b_aligned = (b_addr[1:0] == 2'b00);
    assign b_be_valid = b_we ? (b_be != 4'b0000) : (b_be == 4'b0000);

    /* A has priority for same-word write/read conflicts. Read/read is allowed. */
    assign b_conflict = a_in_range && b_in_range &&
                        (a_word_index == b_word_index) &&
                        ((a_we && b_req) || (a_re && b_req && b_we));
    assign b_request_error = !b_in_range || !b_aligned || !b_be_valid || b_conflict;

    /* The v1 wrapper has no internal wait state. An invalid request is still
       granted so the requester cannot deadlock; b_error reports the failure. */
    assign b_gnt = rst_n && b_req;
    assign b_rvalid = b_rvalid_q;
    assign b_rdata = b_rdata_q;
    assign b_error = (b_gnt && b_we && b_request_error) ||
                     (b_rvalid_q && b_read_error_q);

    always_ff @(posedge clk) begin : memory_accesses
        integer lane;
        if (!rst_n) begin
            a_rdata <= 32'b0;
            b_rvalid_q <= 1'b0;
            b_rdata_q <= 32'b0;
            b_read_error_q <= 1'b0;
        end else begin
            b_rvalid_q <= 1'b0;
            b_read_error_q <= 1'b0;

            if (a_re) begin
                if (a_in_range) a_rdata <= mem[a_word_index];
                else a_rdata <= 32'b0;
            end

            if (a_we && a_in_range) begin
                for (lane = 0; lane < 4; lane = lane + 1)
                    if (a_wstrb[lane])
                        mem[a_word_index][lane*8 +: 8] <= a_wdata[lane*8 +: 8];
            end

            if (b_gnt && b_we && !b_request_error) begin
                for (lane = 0; lane < 4; lane = lane + 1)
                    if (b_be[lane])
                        mem[b_word_index][lane*8 +: 8] <= b_wdata[lane*8 +: 8];
            end

            if (b_gnt && !b_we) begin
                b_rvalid_q <= 1'b1;
                b_read_error_q <= b_request_error;
                if (b_request_error) b_rdata_q <= 32'b0;
                else b_rdata_q <= mem[b_word_index];
            end
        end
    end

`ifndef SYNTHESIS
    always_ff @(posedge clk) begin
        if (rst_n) begin
            assert (!(a_re && a_we))
                else $error("Data SRAM A port read/write asserted together");
            assert (!a_we || (a_wstrb != 4'b0000))
                else $error("Data SRAM A port write has zero strobe");
        end
    end
`endif
endmodule
