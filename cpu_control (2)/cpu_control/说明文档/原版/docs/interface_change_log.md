# 接口变更记录

| 版本/日期 | 变更 | 原因/影响 | 状态与迁移 |
|---|---|---|---|
| FACE-SOC-SPEC-001 v0.1 / 2026-09-11 | 用户原始草案 | 原 Control 表缺少 EX 消费元数据、valid 和 MEM Load 信息 | 原资料保留 |
| CPU_CONTROL C1 / 2026-09-13 | 新增 valid_d/e/m/w、rs1_e/rs2_e、uses_rs1_e/uses_rs2_e、branch_type_e/jump_e、memread_m 输入；imm_type_d、uses_rs1_d/uses_rs2_d 输出 | 支持正确跨级冒险、分支与无效指令限定 | 候选；待 Datapath 负责人共同采用 |
| CPU_CONTROL C1 / 2026-09-13 | 固定共享编码、同步低有效流水复位、MEM 固定边沿契约、非法安全 NOP | 原文未冻结 | 作为本次默认实现，非三方冻结结论 |
| C1 / D1 对齐记录 / 2026-09-14 | 归档 CPU-DP-IF-D1；更新原则接受状态、唯一 package、WB→ID 旁路、对齐约束和 CNN 分工；stub/样例增加 RESET_PC 参数默认零，新增参数复位和安全 NOP 执行测试 | 不变更 C1 端口/编码/流水级/采样契约；参数仅用于 test-only PC | Datapath 原则接受，Control 已对齐；公共地址/复位及真实存储时序待三方冻结，真实联调未运行 |

原有端口名、宽度和方向保留；alu_ctrl/ALUSrc 明确为 D 级。没有新增 CNN、访存数据或 trap 端口。Control 内没有跨级影子状态。

本次未改动其他负责人生产代码、未创建冻结标签、未改变原始两份资料。未来接口升级仍需三方确认。
