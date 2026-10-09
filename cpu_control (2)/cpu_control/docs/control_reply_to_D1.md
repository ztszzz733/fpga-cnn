# Control 对 D1 的逐项正式回复

日期：2026-09-14；依据：CPU-DP-IF-D1、FACE-SOC-COORD-P1。**M / Control 侧接受 C1 作为 v1.0 开发基线，接受 D1 及其中明确的保留条件。** 本表更新本方确认状态；D1 对方原文及其中勾选框不改写，三方公共参数的最终确认不代签。

## D1 §2 的 12 项

| 项 | D1 事项 | Control 正式回复及边界 |
|---|---|---|
| 1 | 完整端口 | 接受。48 端口，26 输入、22 输出；Datapath 同名反向，clk/rst_n 为公共输入；真实顶层到位后逐端口核查。 |
| 2 | 共享编码 | 接受。唯一生产文件 rtl/common/cpu_control_pkg.sv，编译一次。交付哈希见 [P1 回复](control_reply_to_P1.md)；尚不能核对未提供的 Datapath 副本。 |
| 3 | ID 控制寄存、EX 反馈 | 接受。alu_ctrl/ALUSrc 和其他 D 级控制先入 ID/EX；rs1_e/rs2_e、uses_rs1_e/uses_rs2_e、branch_type_e/jump_e 必须对应同一 EX 指令。 |
| 4 | 前递/重定向/寄存器优先级 | 接受。MEM 非 Load 优先 WB；MEM Load 禁止地址前递并遮挡过期 WB 同名值。分支比较和 Store 数据使用前递值。复位 > 重定向 > load-use > 正常；流水寄存器复位 > flush > enable > 保持。 |
| 5 | 同步低有效复位 | M 正式接受上升沿同步低有效流水复位。Control 为组合逻辑，rst_n 低时立即输出安全值，无内部复位寄存器。全系统分发仍需 S-03 共同确认。 |
| 6 | RESET_PC | M 接受 32'h0000_0000 默认值及参数化建议；stub 已实现。最终系统地址仍需 S-02 归档，Control 无 PC 寄存器。 |
| 7 | LW→消费者停一拍 | 接受逻辑方案及真实时序待验证的保留条件。M 周期末 M→W 沿必须能捕获 Load 数据，随后消费者 EX 使用 FWD_WB。同步读的请求沿必须明确，不能仅按“一周期”接线。 |
| 8 | WB→ID bypass | 接受显式旁路；valid_w && regwrite_w && rd_w!=0 且源编号相同时读最终 wb_data；x0 永远零。stub 已验证，生产 Datapath 待验证。 |
| 9 | 同步 IMEM 返回处理 | 接受由 Datapath 保存请求 PC/valid、暂停保存返回、重定向丢弃错路返回。wrapper 未提供；如现有固定时延接口无法实现则共同升级 C1。 |
| 10 | 指令范围与 NOP | 接受 37 条 RV32I 子集；非法/FENCE/ECALL/EBREAK 安全零控制，无 trap。M/Zmmul、CSR、特权、压缩、原子扩展不支持，mul_busy=0。 |
| 11 | 访存对齐 | 接受：LB/LBU/SB 任意字节，LH/LHU/SH 2 字节对齐，LW/SW 4 字节对齐；CNN 张量基地址 4 字节对齐。不支持未对齐半字/字访问，测试软件应遵守。Control 只译码类型；test-only stub 后续补充了对齐字节/半字/字访问，仍不代表生产 LSU。 |
| 12 | package 归属/冲突 | M 提供本次 C1 package 作为共享交付基准。P1 报告 Datapath M1 已有 package，但未提供文件；跨工程哈希和编码一致性需接收方核对后统一引用。 |

## D1 §8 的 7 项确认

- [x] Control 接受 Datapath 对 C1 的原则确认及 D1 保留项。
- [x] Control 接受 RESET_PC 默认零的建议；最终系统值仍待共同确认。
- [x] 同意唯一共享 package，不各自维护不同编码。
- [x] 同意非法指令/FENCE/ECALL/EBREAK 安全 NOP。
- [x] 同意第一版未对齐访问限制。
- [x] 同意与 SoC/CNN 共同确定 IMEM/Data SRAM 时序；实际冻结未完成。
- [x] 同意与 SoC/CNN 共同确定 CNN_MMIO_BASE；具体地址未冻结。

勾选表示本方接受建议或协作责任，不表示三方参数已确定。

## 边界、验证和历史

CNN 九个端口仍位于 Datapath/CNN 边界：CPU 普通 LW/SW 访问 MMIO，Datapath 负责 CPU A 口、MMIO 路由和 start/soft_reset 脉冲，CNN master 使用 B 口。Control 不增 STATUS/CONTROL 端口。

本次只补充正式确认、生产编译清单及交付文档，未修改生产 RTL、共享编码或 test-only stub；回归证据见 [验证报告](verification_report.md)。真实 Datapath/CNN 未提供，不宣称真实 CPU 联调通过。

[D1 原文](inputs/CPU-DP-IF-D1.md) SHA-256：907492c9028893e4b4741c0a62a84f8d3937134e63db47ecf60e188ec51e0f78。早期过程保留在 [历史对齐记录](../说明文档/原版/docs/control_reply_to_D1.md)，当前交付以 [P1 正式回复](control_reply_to_P1.md) 为准。
