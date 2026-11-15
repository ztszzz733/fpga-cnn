module imm_gen (
    input  logic [31:0] instr,
    input  logic [2:0]  imm_type,
    output logic [31:0] imm_ext
);
    import cpu_control_pkg::*;
    always_comb begin
        unique case (imm_type)
            IMM_I: imm_ext = {{20{instr[31]}}, instr[31:20]};
            IMM_S: imm_ext = {{20{instr[31]}}, instr[31:25], instr[11:7]};
            IMM_B: imm_ext = {{19{instr[31]}}, instr[31], instr[7],
                              instr[30:25], instr[11:8], 1'b0};
            IMM_U: imm_ext = {instr[31:12], 12'b0};
            IMM_J: imm_ext = {{11{instr[31]}}, instr[31], instr[19:12],
                              instr[20], instr[30:21], 1'b0};
            default: imm_ext = 32'b0;
        endcase
    end
endmodule
