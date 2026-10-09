module dmem_model #(
    parameter int unsigned MEM_BYTES = 262144
) (
    input  logic        clk,
    input  logic        re,
    input  logic        we,
    input  logic [3:0]  wstrb,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] addr,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [31:0] wdata,
    output logic [31:0] rdata
);
    logic [7:0] mem [0:MEM_BYTES-1];
    logic       word_in_range;
    integer     lane;

    always_comb begin
        word_in_range = ({1'b0, addr[31:2], 2'b00} + 33'd3) < {1'b0, MEM_BYTES};
    end

    // There is intentionally no reset port. Initialization keeps the model's
    // externally visible value deterministic before its first read request.
    /* verilator lint_off MULTIDRIVEN */
    initial rdata = 32'b0;

    // A request present during cycle N is sampled at its ending rising edge.
    // Nonblocking assignment makes the selected word visible after that edge.
    always_ff @(posedge clk) begin
        if (re) begin
            if (word_in_range) begin
                rdata <= {mem[{addr[31:2], 2'b00} + 3],
                          mem[{addr[31:2], 2'b00} + 2],
                          mem[{addr[31:2], 2'b00} + 1],
                          mem[{addr[31:2], 2'b00} + 0]};
            end else begin
                rdata <= 32'b0;
            end
        end

        if (we && word_in_range) begin
            for (lane = 0; lane < 4; lane = lane + 1) begin
                if (wstrb[lane])
                    mem[{addr[31:2], 2'b00} + lane] <= wdata[lane*8 +: 8];
            end
        end
    end
    /* verilator lint_on MULTIDRIVEN */
endmodule
