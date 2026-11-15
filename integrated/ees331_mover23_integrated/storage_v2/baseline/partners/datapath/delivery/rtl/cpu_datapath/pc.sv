module pc #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        pc_en,
    input  logic [31:0] next_pc,
    output logic [31:0] pc_q
);
    always_ff @(posedge clk) begin
        if (!rst_n) pc_q <= RESET_PC;
        else if (pc_en) pc_q <= next_pc;
    end
endmodule
