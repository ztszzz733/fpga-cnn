module imem_model #(
    parameter int unsigned MEM_BYTES = 65536
) (
    input logic clk,
    input logic re,
    input logic [31:0] addr,
    output logic [31:0] rdata
);
    localparam logic [31:0] NOP = 32'h0000_0013;
    logic [7:0] mem [0:MEM_BYTES-1];
    logic request_legal;

    always_comb
        request_legal = (addr[1:0] == 2'b00) &&
                        (({1'b0,addr} + 33'd3) < {1'b0,MEM_BYTES});

    /* verilator lint_off MULTIDRIVEN */
    initial rdata = NOP;
    always_ff @(posedge clk) begin
        if (re) begin
            if (request_legal)
                rdata <= {mem[addr+3],mem[addr+2],mem[addr+1],mem[addr]};
            else
                rdata <= NOP;
        end
    end
    /* verilator lint_on MULTIDRIVEN */
endmodule
