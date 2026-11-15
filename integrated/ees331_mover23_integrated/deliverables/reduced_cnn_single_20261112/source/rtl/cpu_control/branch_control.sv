// 图 PC / Branch Control：仅使用 EX 元数据与已前递的 EX 比较标志。
// 组合逻辑；无效/保留类型默认顺序取指。目标地址由 Datapath 生成。
module branch_control (
  input logic valid_e,
  input logic [2:0] branch_type_e,
  input logic [1:0] jump_e,
  input logic cmp_eq_e, cmp_lt_e, cmp_ltu_e,
  output logic redirect,
  output logic [1:0] redirect_sel
);
  import cpu_control_pkg::*;
  logic taken;
  always_comb begin
    taken=0; redirect=0; redirect_sel=PC_NEXT;
    case (branch_type_e)
      BR_EQ: taken=cmp_eq_e;
      BR_NE: taken=!cmp_eq_e;
      BR_LT: taken=cmp_lt_e;
      BR_GE: taken=!cmp_lt_e;
      BR_LTU: taken=cmp_ltu_e;
      BR_GEU: taken=!cmp_ltu_e;
      default: taken=0;
    endcase
    if (valid_e) begin
      if (jump_e==J_JALR) begin redirect=1; redirect_sel=PC_JALR; end
      else if (jump_e==J_JAL || taken) begin redirect=1; redirect_sel=PC_TARGET; end
    end
  end
endmodule
