# 冒险、前递与门控规则（C1）

ID 的源使用信息来自主译码：R/Branch/Store 使用 rs1、rs2；I-ALU/Load/JALR 只使用 rs1；LUI/AUIPC/JAL/项目 NOP/非法指令不用源。无效 D 的 uses 清零。

| 条件，按顺序判断 | EX 选择 |
|---|---|
| E 无效、该源未使用或源为 x0 | 00 原值 |
| 有效 M 写同名非零 rd，且 M 不是 Load | 10 MEM |
| 有效 M 写同名非零 rd，但 M 是 Load | 00；内部 operand_unready=1；不得选择旧 W |
| 没有 M 同名写入，有效 W 写同名非零 rd | 01 WB |
| 其余 | 00 原值 |

A/B 各自独立选择。fwd_store 等于 rs2 的 EX 前递选择，仅在 Store 使用时有写存储器意义。MEM 总线必须是最终待写回值，包括 JAL/JALR 的 PC+4；WB 总线必须在 WB MUX 之后，包括 Load 数据。

`load_use = valid_d && valid_e && memread_e && rd_e!=0 && ((uses_rs1_d && rs1_d==rd_e) || (uses_rs2_d && rs2_d==rd_e))`。

| 优先级 | pc_en | if_id_en | if_id_flush | id_ex_flush | pc_sel |
|---|---:|---:|---:|---:|---|
| 复位 | 0 | 0 | 1 | 1 | 00 |
| 有效 EX redirect | 1 | 1 | 1 | 1 | Branch/JAL=01；JALR=10 |
| load-use | 0 | 0 | 0 | 1 | 00 |
| 正常 | 1 | 1 | 0 | 0 | 00 |

只有年轻 D/F 被冲刷；旧 E 仍进入 M，M/W 继续前进。redirect/stall 同时置位的测试在独立 pipeline_control 仲裁实例上人为构造，不表示真实指令同时是 Load 和 Jump。

BEQ/BNE 使用 eq/!eq；BLT/BGE 使用 lt/!lt；BLTU/BGEU 使用 ltu/!ltu。比较值与 branch_type_e/jump_e 都来自当前 E。Datapath 先前递后比较。JALR 目标最低位清零是 Datapath 责任。

多周期乘法未实现。mul_busy 保留且必须为 0；非零验证失败。扩展需明确 E 保持、M 插泡/保持、完成握手、重定向和单次提交策略。
