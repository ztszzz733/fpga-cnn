module imem_rom #(
    parameter logic [31:0] IMEM_BASE = 32'h0000_0000,
    parameter logic [31:0] IMEM_SIZE = 32'h0001_0000,
    parameter string INIT_FILE = ""
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] imem_addr,
    input  logic        imem_re,
    output logic [31:0] imem_rdata
);
    localparam integer WORDS = IMEM_SIZE / 4;
    localparam integer INDEX_WIDTH = $clog2(WORDS);
    localparam logic [31:0] SAFE_NOP = 32'h0000_0013;

    logic [31:0] mem [0:WORDS-1];
    logic addr_valid;
    logic [INDEX_WIDTH-1:0] word_index;

    assign addr_valid = (imem_addr >= IMEM_BASE) &&
                        (imem_addr < (IMEM_BASE + IMEM_SIZE)) &&
                        (imem_addr[1:0] == 2'b00);
    assign word_index = (imem_addr - IMEM_BASE) >> 2;

    initial begin
        if (INIT_FILE != "") $readmemh(INIT_FILE, mem);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) imem_rdata <= SAFE_NOP;
        else if (imem_re) begin
            if (addr_valid) imem_rdata <= mem[word_index];
            else imem_rdata <= SAFE_NOP;
        end
    end
endmodule
