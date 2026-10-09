module id_ex_reg (
    input logic clk, rst_n, flush,
    input logic valid_d,
    input logic [31:0] pc_d, pc4_d, rd1_d, rd2_d, imm_d,
    input logic [4:0] rs1_d, rs2_d, rd_d,
    input logic uses_rs1_d, uses_rs2_d,
    input logic [3:0] alu_ctrl_d,
    input logic [1:0] alu_src_a_sel_d, alu_src_b_sel_d,
    input logic regwrite_d, memread_d, memwrite_d,
    input logic [2:0] load_type_d,
    input logic [1:0] store_type_d, wb_sel_d,
    input logic [2:0] branch_type_d,
    input logic [1:0] jump_d,
    output logic valid_e,
    output logic [31:0] pc_e, pc4_e, rd1_e, rd2_e, imm_e,
    output logic [4:0] rs1_e, rs2_e, rd_e,
    output logic uses_rs1_e, uses_rs2_e,
    output logic [3:0] alu_ctrl_e,
    output logic [1:0] alu_src_a_sel_e, alu_src_b_sel_e,
    output logic regwrite_e, memread_e, memwrite_e,
    output logic [2:0] load_type_e,
    output logic [1:0] store_type_e, wb_sel_e,
    output logic [2:0] branch_type_e,
    output logic [1:0] jump_e
);
    always_ff @(posedge clk) begin
        if (!rst_n || flush) begin
            valid_e<=0; pc_e<=0; pc4_e<=0; rd1_e<=0; rd2_e<=0; imm_e<=0;
            rs1_e<=0; rs2_e<=0; rd_e<=0; uses_rs1_e<=0; uses_rs2_e<=0;
            alu_ctrl_e<=0; alu_src_a_sel_e<=0; alu_src_b_sel_e<=0;
            regwrite_e<=0; memread_e<=0; memwrite_e<=0; load_type_e<=0;
            store_type_e<=0; wb_sel_e<=0; branch_type_e<=0; jump_e<=0;
        end else begin
            valid_e<=valid_d; pc_e<=pc_d; pc4_e<=pc4_d; rd1_e<=rd1_d;
            rd2_e<=rd2_d; imm_e<=imm_d; rs1_e<=rs1_d; rs2_e<=rs2_d; rd_e<=rd_d;
            uses_rs1_e<=uses_rs1_d; uses_rs2_e<=uses_rs2_d; alu_ctrl_e<=alu_ctrl_d;
            alu_src_a_sel_e<=alu_src_a_sel_d; alu_src_b_sel_e<=alu_src_b_sel_d;
            regwrite_e<=regwrite_d; memread_e<=memread_d; memwrite_e<=memwrite_d;
            load_type_e<=load_type_d; store_type_e<=store_type_d; wb_sel_e<=wb_sel_d;
            branch_type_e<=branch_type_d; jump_e<=jump_d;
        end
    end
endmodule
