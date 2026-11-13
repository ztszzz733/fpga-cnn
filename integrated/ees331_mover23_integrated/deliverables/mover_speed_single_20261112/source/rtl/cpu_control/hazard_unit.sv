// 图 Hazard / Forward：D/E load-use，E 消费者与 M/W 生产者组合比较。
// 默认不暂停、前递原值。MEM Load 遮挡旧 WB 值，不将 Load 地址前递。
module hazard_unit (
  input logic valid_d, valid_e, valid_m, valid_w,
  input logic [4:0] rs1_d, rs2_d, rs1_e, rs2_e, rd_e, rd_m, rd_w,
  input logic uses_rs1_d, uses_rs2_d, uses_rs1_e, uses_rs2_e,
  input logic memread_e, memread_m, regwrite_m, regwrite_w,
  output logic load_use,
  output logic [1:0] fwd_a, fwd_b, fwd_store,
  output logic operand_unready
);
  import cpu_control_pkg::*;
  logic match_ma, match_mb, match_wa, match_wb;
  always_comb begin
    match_ma=valid_m && regwrite_m && (rd_m!=0) && (rs1_e==rd_m);
    match_mb=valid_m && regwrite_m && (rd_m!=0) && (rs2_e==rd_m);
    match_wa=valid_w && regwrite_w && (rd_w!=0) && (rs1_e==rd_w);
    match_wb=valid_w && regwrite_w && (rd_w!=0) && (rs2_e==rd_w);
    fwd_a=FWD_REG; fwd_b=FWD_REG; operand_unready=0;
    if (valid_e && uses_rs1_e && rs1_e!=0) begin
      if (match_ma) begin
        if (!memread_m) fwd_a=FWD_MEM; else operand_unready=1;
      end else if (match_wa) fwd_a=FWD_WB;
    end
    if (valid_e && uses_rs2_e && rs2_e!=0) begin
      if (match_mb) begin
        if (!memread_m) fwd_b=FWD_MEM; else operand_unready=1;
      end else if (match_wb) fwd_b=FWD_WB;
    end
    fwd_store=fwd_b;
    load_use=valid_d && valid_e && memread_e && (rd_e!=0) &&
      ((uses_rs1_d && rs1_d==rd_e) || (uses_rs2_d && rs2_d==rd_e));
  end
endmodule
