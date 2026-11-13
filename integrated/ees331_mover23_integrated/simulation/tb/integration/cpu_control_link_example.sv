// TEST ONLY：C1 显式接线样例，不是生产 cpu_datapath 或 SoC。
// 本模块仍只连接固定时序stub；真实Control+生产Datapath已另行完成有限程序联调。
module cpu_control_link_example #(
  parameter logic [31:0] RESET_PC = 32'h0000_0000
) (input logic clk, input logic rst_n);
  logic [31:0] instr_d;
  logic [4:0] rs1_d;
  logic [4:0] rs2_d;
  logic [4:0] rd_e;
  logic [4:0] rd_m;
  logic [4:0] rd_w;
  logic  regwrite_m;
  logic  regwrite_w;
  logic  memread_e;
  logic  cmp_eq_e;
  logic  cmp_lt_e;
  logic  cmp_ltu_e;
  logic  mul_busy;
  logic  valid_d;
  logic  valid_e;
  logic  valid_m;
  logic  valid_w;
  logic [4:0] rs1_e;
  logic [4:0] rs2_e;
  logic  uses_rs1_e;
  logic  uses_rs2_e;
  logic [2:0] branch_type_e;
  logic [1:0] jump_e;
  logic  memread_m;
  logic [1:0] pc_sel;
  logic  pc_en;
  logic  if_id_en;
  logic  if_id_flush;
  logic  id_ex_flush;
  logic [3:0] alu_ctrl;
  logic [1:0] alu_src_a_sel;
  logic [1:0] alu_src_b_sel;
  logic [1:0] fwd_a;
  logic [1:0] fwd_b;
  logic [1:0] fwd_store;
  logic  regwrite_d;
  logic  memread_d;
  logic  memwrite_d;
  logic [2:0] load_type_d;
  logic [1:0] store_type_d;
  logic [1:0] wb_sel_d;
  logic [2:0] branch_type_d;
  logic [1:0] jump_d;
  logic [2:0] imm_type_d;
  logic  uses_rs1_d;
  logic  uses_rs2_d;
  cpu_control u_control (
    .clk(clk),
    .rst_n(rst_n),
    .instr_d(instr_d),
    .rs1_d(rs1_d),
    .rs2_d(rs2_d),
    .rd_e(rd_e),
    .rd_m(rd_m),
    .rd_w(rd_w),
    .regwrite_m(regwrite_m),
    .regwrite_w(regwrite_w),
    .memread_e(memread_e),
    .cmp_eq_e(cmp_eq_e),
    .cmp_lt_e(cmp_lt_e),
    .cmp_ltu_e(cmp_ltu_e),
    .mul_busy(mul_busy),
    .valid_d(valid_d),
    .valid_e(valid_e),
    .valid_m(valid_m),
    .valid_w(valid_w),
    .rs1_e(rs1_e),
    .rs2_e(rs2_e),
    .uses_rs1_e(uses_rs1_e),
    .uses_rs2_e(uses_rs2_e),
    .branch_type_e(branch_type_e),
    .jump_e(jump_e),
    .memread_m(memread_m),
    .pc_sel(pc_sel),
    .pc_en(pc_en),
    .if_id_en(if_id_en),
    .if_id_flush(if_id_flush),
    .id_ex_flush(id_ex_flush),
    .alu_ctrl(alu_ctrl),
    .alu_src_a_sel(alu_src_a_sel),
    .alu_src_b_sel(alu_src_b_sel),
    .fwd_a(fwd_a),
    .fwd_b(fwd_b),
    .fwd_store(fwd_store),
    .regwrite_d(regwrite_d),
    .memread_d(memread_d),
    .memwrite_d(memwrite_d),
    .load_type_d(load_type_d),
    .store_type_d(store_type_d),
    .wb_sel_d(wb_sel_d),
    .branch_type_d(branch_type_d),
    .jump_d(jump_d),
    .imm_type_d(imm_type_d),
    .uses_rs1_d(uses_rs1_d),
    .uses_rs2_d(uses_rs2_d));
  control_datapath_stub #(.RESET_PC(RESET_PC)) u_datapath_stub (
    .clk(clk),
    .rst_n(rst_n),
    .instr_d(instr_d),
    .rs1_d(rs1_d),
    .rs2_d(rs2_d),
    .rd_e(rd_e),
    .rd_m(rd_m),
    .rd_w(rd_w),
    .regwrite_m(regwrite_m),
    .regwrite_w(regwrite_w),
    .memread_e(memread_e),
    .cmp_eq_e(cmp_eq_e),
    .cmp_lt_e(cmp_lt_e),
    .cmp_ltu_e(cmp_ltu_e),
    .mul_busy(mul_busy),
    .valid_d(valid_d),
    .valid_e(valid_e),
    .valid_m(valid_m),
    .valid_w(valid_w),
    .rs1_e(rs1_e),
    .rs2_e(rs2_e),
    .uses_rs1_e(uses_rs1_e),
    .uses_rs2_e(uses_rs2_e),
    .branch_type_e(branch_type_e),
    .jump_e(jump_e),
    .memread_m(memread_m),
    .pc_sel(pc_sel),
    .pc_en(pc_en),
    .if_id_en(if_id_en),
    .if_id_flush(if_id_flush),
    .id_ex_flush(id_ex_flush),
    .alu_ctrl(alu_ctrl),
    .alu_src_a_sel(alu_src_a_sel),
    .alu_src_b_sel(alu_src_b_sel),
    .fwd_a(fwd_a),
    .fwd_b(fwd_b),
    .fwd_store(fwd_store),
    .regwrite_d(regwrite_d),
    .memread_d(memread_d),
    .memwrite_d(memwrite_d),
    .load_type_d(load_type_d),
    .store_type_d(store_type_d),
    .wb_sel_d(wb_sel_d),
    .branch_type_d(branch_type_d),
    .jump_d(jump_d),
    .imm_type_d(imm_type_d),
    .uses_rs1_d(uses_rs1_d),
    .uses_rs2_d(uses_rs2_d));
endmodule
