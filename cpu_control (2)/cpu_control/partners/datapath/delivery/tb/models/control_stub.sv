// TEST ONLY: independent RV32I control model matching C1 ports. It is not M RTL.
module control_stub (
    input logic clk, rst_n,
    /* verilator lint_off UNUSEDSIGNAL */
    input logic [31:0] instr_d,
    /* verilator lint_on UNUSEDSIGNAL */
    input logic [4:0] rs1_d, rs2_d, rd_e, rd_m, rd_w,
    input logic regwrite_m, regwrite_w, memread_e,
    input logic cmp_eq_e, cmp_lt_e, cmp_ltu_e, mul_busy,
    input logic valid_d, valid_e, valid_m, valid_w,
    input logic [4:0] rs1_e, rs2_e,
    input logic uses_rs1_e, uses_rs2_e,
    input logic [2:0] branch_type_e,
    input logic [1:0] jump_e,
    input logic memread_m,
    output logic [1:0] pc_sel,
    output logic pc_en, if_id_en, if_id_flush, id_ex_flush,
    output logic [3:0] alu_ctrl,
    output logic [1:0] alu_src_a_sel, alu_src_b_sel,
    output logic [1:0] fwd_a, fwd_b, fwd_store,
    output logic regwrite_d, memread_d, memwrite_d,
    output logic [2:0] load_type_d,
    output logic [1:0] store_type_d, wb_sel_d,
    output logic [2:0] branch_type_d,
    output logic [1:0] jump_d,
    output logic [2:0] imm_type_d,
    output logic uses_rs1_d, uses_rs2_d
);
    import cpu_control_pkg::*;
    logic legal_d, load_use, redirect, branch_taken;
    logic match_ma, match_mb, match_wa, match_wb;
    logic [6:0] opcode, funct7;
    logic [2:0] funct3;

    always_comb begin
        opcode=instr_d[6:0]; funct3=instr_d[14:12]; funct7=instr_d[31:25];
        legal_d=1'b0; alu_ctrl=ALU_ADD; alu_src_a_sel=A_REG; alu_src_b_sel=B_REG;
        regwrite_d=0; memread_d=0; memwrite_d=0; load_type_d=0;
        store_type_d=0; wb_sel_d=WB_ALU; branch_type_d=BR_NONE;
        jump_d=J_NONE; imm_type_d=IMM_NONE; uses_rs1_d=0; uses_rs2_d=0;
        case (opcode)
            7'b0110011: begin
                uses_rs1_d=1; uses_rs2_d=1; regwrite_d=1;
                case ({funct7,funct3})
                    {7'b0000000,3'b000}: begin alu_ctrl=ALU_ADD; legal_d=1; end
                    {7'b0100000,3'b000}: begin alu_ctrl=ALU_SUB; legal_d=1; end
                    {7'b0000000,3'b111}: begin alu_ctrl=ALU_AND; legal_d=1; end
                    {7'b0000000,3'b110}: begin alu_ctrl=ALU_OR; legal_d=1; end
                    {7'b0000000,3'b100}: begin alu_ctrl=ALU_XOR; legal_d=1; end
                    {7'b0000000,3'b010}: begin alu_ctrl=ALU_SLT; legal_d=1; end
                    {7'b0000000,3'b011}: begin alu_ctrl=ALU_SLTU; legal_d=1; end
                    {7'b0000000,3'b001}: begin alu_ctrl=ALU_SLL; legal_d=1; end
                    {7'b0000000,3'b101}: begin alu_ctrl=ALU_SRL; legal_d=1; end
                    {7'b0100000,3'b101}: begin alu_ctrl=ALU_SRA; legal_d=1; end
                    default: legal_d=0;
                endcase
            end
            7'b0010011: begin
                uses_rs1_d=1; regwrite_d=1; alu_src_b_sel=B_IMM; imm_type_d=IMM_I;
                case (funct3)
                    3'b000: begin alu_ctrl=ALU_ADD; legal_d=1; end
                    3'b111: begin alu_ctrl=ALU_AND; legal_d=1; end
                    3'b110: begin alu_ctrl=ALU_OR; legal_d=1; end
                    3'b100: begin alu_ctrl=ALU_XOR; legal_d=1; end
                    3'b010: begin alu_ctrl=ALU_SLT; legal_d=1; end
                    3'b011: begin alu_ctrl=ALU_SLTU; legal_d=1; end
                    3'b001: if (funct7==7'b0000000) begin alu_ctrl=ALU_SLL; legal_d=1; end
                    3'b101: begin
                        if (funct7==7'b0000000) begin alu_ctrl=ALU_SRL; legal_d=1; end
                        else if (funct7==7'b0100000) begin alu_ctrl=ALU_SRA; legal_d=1; end
                    end
                    default: legal_d=0;
                endcase
            end
            7'b0110111: begin legal_d=1; regwrite_d=1; alu_src_a_sel=A_ZERO;
                alu_src_b_sel=B_IMM; imm_type_d=IMM_U; end
            7'b0010111: begin legal_d=1; regwrite_d=1; alu_src_a_sel=A_PC;
                alu_src_b_sel=B_IMM; imm_type_d=IMM_U; end
            7'b0000011: begin
                uses_rs1_d=1; regwrite_d=1; memread_d=1; wb_sel_d=WB_LOAD;
                alu_src_b_sel=B_IMM; imm_type_d=IMM_I; load_type_d=funct3;
                legal_d=(funct3==LOAD_LB)||(funct3==LOAD_LH)||(funct3==LOAD_LW)||
                        (funct3==LOAD_LBU)||(funct3==LOAD_LHU);
            end
            7'b0100011: begin
                uses_rs1_d=1; uses_rs2_d=1; memwrite_d=1;
                alu_src_b_sel=B_IMM; imm_type_d=IMM_S; store_type_d=funct3[1:0];
                legal_d=(funct3==3'b000)||(funct3==3'b001)||(funct3==3'b010);
            end
            7'b1100011: begin
                uses_rs1_d=1; uses_rs2_d=1; imm_type_d=IMM_B;
                case(funct3)
                    3'b000: begin branch_type_d=BR_EQ; legal_d=1; end
                    3'b001: begin branch_type_d=BR_NE; legal_d=1; end
                    3'b100: begin branch_type_d=BR_LT; legal_d=1; end
                    3'b101: begin branch_type_d=BR_GE; legal_d=1; end
                    3'b110: begin branch_type_d=BR_LTU; legal_d=1; end
                    3'b111: begin branch_type_d=BR_GEU; legal_d=1; end
                    default: legal_d=0;
                endcase
            end
            7'b1101111: begin legal_d=1; regwrite_d=1; wb_sel_d=WB_PC4;
                jump_d=J_JAL; imm_type_d=IMM_J; end
            7'b1100111: if (funct3==0) begin legal_d=1; uses_rs1_d=1;
                regwrite_d=1; wb_sel_d=WB_PC4; jump_d=J_JALR;
                imm_type_d=IMM_I; alu_src_b_sel=B_IMM; end
            default: legal_d=0;
        endcase
        if (!rst_n || !valid_d || !legal_d) begin
            alu_ctrl=ALU_ADD; alu_src_a_sel=A_REG; alu_src_b_sel=B_REG;
            regwrite_d=0; memread_d=0; memwrite_d=0; load_type_d=0;
            store_type_d=0; wb_sel_d=WB_ALU; branch_type_d=BR_NONE;
            jump_d=J_NONE; imm_type_d=IMM_NONE; uses_rs1_d=0; uses_rs2_d=0;
        end
    end

    always_comb begin
        match_ma=valid_m&&regwrite_m&&(rd_m!=0)&&(rs1_e==rd_m);
        match_mb=valid_m&&regwrite_m&&(rd_m!=0)&&(rs2_e==rd_m);
        match_wa=valid_w&&regwrite_w&&(rd_w!=0)&&(rs1_e==rd_w);
        match_wb=valid_w&&regwrite_w&&(rd_w!=0)&&(rs2_e==rd_w);
        fwd_a=FWD_REG; fwd_b=FWD_REG;
        if (valid_e&&uses_rs1_e&&(rs1_e!=0)) begin
            if (match_ma&&!memread_m) fwd_a=FWD_MEM;
            else if (!match_ma&&match_wa) fwd_a=FWD_WB;
        end
        if (valid_e&&uses_rs2_e&&(rs2_e!=0)) begin
            if (match_mb&&!memread_m) fwd_b=FWD_MEM;
            else if (!match_mb&&match_wb) fwd_b=FWD_WB;
        end
        fwd_store=fwd_b;
        load_use=valid_d&&valid_e&&memread_e&&(rd_e!=0)&&
            ((uses_rs1_d&&(rs1_d==rd_e))||(uses_rs2_d&&(rs2_d==rd_e)));

        branch_taken=0;
        case(branch_type_e)
            BR_EQ: branch_taken=cmp_eq_e;
            BR_NE: branch_taken=!cmp_eq_e;
            BR_LT: branch_taken=cmp_lt_e;
            BR_GE: branch_taken=!cmp_lt_e;
            BR_LTU: branch_taken=cmp_ltu_e;
            BR_GEU: branch_taken=!cmp_ltu_e;
            default: branch_taken=0;
        endcase
        redirect=valid_e&&((jump_e!=J_NONE)||branch_taken);
        pc_en=1; if_id_en=1; if_id_flush=0; id_ex_flush=0; pc_sel=PC_NEXT;
        if (!rst_n) begin pc_en=0; if_id_en=0; if_id_flush=1; id_ex_flush=1; end
        else if (redirect) begin
            if_id_flush=1; id_ex_flush=1;
            pc_sel=(jump_e==J_JALR)?PC_JALR:PC_TARGET;
        end else if (load_use) begin pc_en=0; if_id_en=0; id_ex_flush=1; end
    end

    /* verilator lint_off UNUSED */
    logic unused_inputs;
    assign unused_inputs = clk ^ mul_busy;
    /* verilator lint_on UNUSED */
endmodule
