module if_id_reg (
    input logic clk, rst_n, en, flush,
    input logic valid_i,
    input logic [31:0] instr_i, pc_i, pc4_i,
    output logic valid_o,
    output logic [31:0] instr_o, pc_o, pc4_o
);
    always_ff @(posedge clk) begin
        // A flushed entry is ignored because valid_o is cleared.
        if (!rst_n || flush)
            valid_o <= 1'b0;
        else if (en)
            valid_o <= valid_i;

        if (!rst_n) begin
            instr_o <= '0;
            pc_o <= '0;
            pc4_o <= '0;
        end else if (en) begin
            instr_o <= instr_i;
            pc_o <= pc_i;
            pc4_o <= pc4_i;
        end
    end
endmodule
