// 图 CPU CONTROL 顶层：组合译码、冒险、分支及安全限定。
// clk 仅预留，流水状态由 Datapath 保存；rst_n 低时输出安全值。
module cpu_control (
    input  logic        clk,
    input  logic        rst_n,

    // 原规格：Datapath -> Control
    input  logic [31:0] instr_d,
    input  logic [4:0]  rs1_d,
    input  logic [4:0]  rs2_d,
    input  logic [4:0]  rd_e,
    input  logic [4:0]  rd_m,
    input  logic [4:0]  rd_w,
    input  logic        regwrite_m,
    input  logic        regwrite_w,
    input  logic        memread_e,
    input  logic        cmp_eq_e,
    input  logic        cmp_lt_e,
    input  logic        cmp_ltu_e,
    input  logic        mul_busy,

    // C1 补充：Datapath -> Control
    input  logic        valid_d,
    input  logic        valid_e,
    input  logic        valid_m,
    input  logic        valid_w,
    input  logic [4:0]  rs1_e,
    input  logic [4:0]  rs2_e,
    input  logic        uses_rs1_e,
    input  logic        uses_rs2_e,
    input  logic [2:0]  branch_type_e,
    input  logic [1:0]  jump_e,
    input  logic        memread_m,

    // 原规格：Control -> Datapath
    output logic [1:0]  pc_sel,
    output logic        pc_en,
    output logic        if_id_en,
    output logic        if_id_flush,
    output logic        id_ex_flush,
    output logic [3:0]  alu_ctrl,       // ID 输出，先进入 ID/EX
    output logic [1:0]  alu_src_a_sel,  // ID 输出，先进入 ID/EX
    output logic [1:0]  alu_src_b_sel,  // ID 输出，先进入 ID/EX
    output logic [1:0]  fwd_a,          // 当前 EX 级即时选择
    output logic [1:0]  fwd_b,          // 当前 EX 级即时选择
    output logic [1:0]  fwd_store,      // 当前 EX Store 数据选择
    output logic        regwrite_d,
    output logic        memread_d,
    output logic        memwrite_d,
    output logic [2:0]  load_type_d,
    output logic [1:0]  store_type_d,
    output logic [1:0]  wb_sel_d,
    output logic [2:0]  branch_type_d,
    output logic [1:0]  jump_d,

    // C1 补充：Control -> Datapath
    output logic [2:0]  imm_type_d,
    output logic        uses_rs1_d,
    output logic        uses_rs2_d
);
  import cpu_control_pkg::*;
  decode_t decoded_main, decoded_safe;
  logic legal_main, legal_alu, illegal_d;
  logic [3:0] decoded_alu;
  logic load_use, redirect, operand_unready;
  logic [1:0] raw_fwd_a, raw_fwd_b, raw_fwd_store, redirect_sel;
  main_decoder u_main_decoder (.instr_d(instr_d), .decoded(decoded_main), .legal_main(legal_main));
  alu_decoder u_alu_decoder (.opcode(instr_d[6:0]), .funct3(instr_d[14:12]),
    .funct7(instr_d[31:25]), .alu_decoded(decoded_alu), .legal_alu(legal_alu));
  always_comb begin
    decoded_safe='0;
    illegal_d=rst_n && valid_d && !(legal_main && legal_alu);
    if (rst_n && valid_d && legal_main && legal_alu) begin
      decoded_safe=decoded_main;
      decoded_safe.alu=decoded_alu;
    end
  end
  assign alu_ctrl=decoded_safe.alu;
  assign alu_src_a_sel=decoded_safe.src_a;
  assign alu_src_b_sel=decoded_safe.src_b;
  assign regwrite_d=decoded_safe.regwrite;
  assign memread_d=decoded_safe.memread;
  assign memwrite_d=decoded_safe.memwrite;
  assign load_type_d=decoded_safe.load_type;
  assign store_type_d=decoded_safe.store_type;
  assign wb_sel_d=decoded_safe.wb;
  assign branch_type_d=decoded_safe.branch;
  assign jump_d=decoded_safe.jump;
  assign imm_type_d=decoded_safe.imm;
  assign uses_rs1_d=decoded_safe.use1;
  assign uses_rs2_d=decoded_safe.use2;
  hazard_unit u_hazard_unit (
    .valid_d(valid_d),
    .valid_e(valid_e),
    .valid_m(valid_m),
    .valid_w(valid_w),
    .rs1_d(rs1_d),
    .rs2_d(rs2_d),
    .rs1_e(rs1_e),
    .rs2_e(rs2_e),
    .rd_e(rd_e),
    .rd_m(rd_m),
    .rd_w(rd_w),
    .uses_rs1_d(uses_rs1_d),
    .uses_rs2_d(uses_rs2_d),
    .uses_rs1_e(uses_rs1_e),
    .uses_rs2_e(uses_rs2_e),
    .memread_e(memread_e),
    .memread_m(memread_m),
    .regwrite_m(regwrite_m),
    .regwrite_w(regwrite_w),
    .load_use(load_use),
    .operand_unready(operand_unready),
    .fwd_a(raw_fwd_a), .fwd_b(raw_fwd_b), .fwd_store(raw_fwd_store));
  assign fwd_a=rst_n ? raw_fwd_a : 2'b00;
  assign fwd_b=rst_n ? raw_fwd_b : 2'b00;
  assign fwd_store=rst_n ? raw_fwd_store : 2'b00;
  branch_control u_branch_control (
    .valid_e(valid_e), .branch_type_e(branch_type_e), .jump_e(jump_e),
    .cmp_eq_e(cmp_eq_e), .cmp_lt_e(cmp_lt_e), .cmp_ltu_e(cmp_ltu_e),
    .redirect(redirect), .redirect_sel(redirect_sel));
  pipeline_control u_pipeline_control (
    .rst_n(rst_n), .redirect(redirect), .load_use(load_use), .redirect_sel(redirect_sel),
    .pc_en(pc_en), .if_id_en(if_id_en), .if_id_flush(if_id_flush), .id_ex_flush(id_ex_flush), .pc_sel(pc_sel));
endmodule
