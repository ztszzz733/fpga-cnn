// 图 Control Output / Pipeline Gating Matrix：唯一门控组合仲裁器。
// 优先级 reset > EX redirect > load-use > 正常；不冻结 M/W。
module pipeline_control (
  input logic rst_n, redirect, load_use,
  input logic [1:0] redirect_sel,
  output logic pc_en, if_id_en, if_id_flush, id_ex_flush,
  output logic [1:0] pc_sel
);
  always_comb begin
    pc_en=1; if_id_en=1; if_id_flush=0; id_ex_flush=0; pc_sel=0;
    if (!rst_n) begin pc_en=0; if_id_en=0; if_id_flush=1; id_ex_flush=1; end
    else if (redirect) begin if_id_flush=1; id_ex_flush=1; pc_sel=redirect_sel; end
    else if (load_use) begin pc_en=0; if_id_en=0; id_ex_flush=1; end
  end
endmodule
