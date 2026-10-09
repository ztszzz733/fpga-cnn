# Control 对 D1 的项目对齐记录

日期：2026-09-14。对应接口 CPU-CD-IF-C1，依据 [CPU-DP-IF-D1 原文](inputs/CPU-DP-IF-D1.md)。本记录是 Control 项目的实现与保留项说明，未代替负责人签字、三方冻结或真实 RTL 联调。

## 对 D1 第 8 节的逐项处理

| 事项 | Control 项目处理 | 后续条件 |
|---|---|---|
| 原则接受 C1 及保留项 | 已按 D1 对齐，保留 48 端口/22 输出及全部编码 | 完整接口尚未冻结 |
| RESET_PC 默认零 | stub/接线样例采用 32 位参数，默认 `32'h0000_0000`；Control 不持有 PC | 最终复位地址、系统复位方式待三方确认 |
| 共用 package | `rtl/common/cpu_control_pkg.sv` 为唯一编码来源，无重复副本 | Datapath 接入时明确共享文件归属及交付版本 |
| 非法/FENCE/ECALL/EBREAK 安全 NOP | 现有译码满足；新增连续执行检查，核对无写寄存器、Store 或重定向副作用 | 无 trap/CSR，不宣称标准异常处理 |
| 第一版地址对齐限制 | 已写入接口和时序契约；执行测试遵守对齐要求 | 字节/半字 LSU 数据行为待真实 Datapath 验证 |
| IMEM/Data SRAM 精确时序 | 保留固定时延基线，明确 D1 一周期同步读只是建议 | SoC/Datapath/CNN 三方确定 wrapper 采样沿并提供日志 |
| CNN_MMIO_BASE | 保持未冻结，软件仍由调用者传入地址；偏移 0x00～0x20 | 三方给出完整基地址；不凭空新增地址常量 |

## 实现核对

现有 Control RTL 已实现：ID 控制先由 Datapath 锁入 ID/EX；EX 元数据用于前递/分支；有效 MEM 非 Load 优先于 WB；MEM Load 不前递地址，也不会回退为过期 WB 同名值；EX 重定向优先于 load-use；无效级不引发副作用；`mul_busy=0`。stub 已实现前递后分支比较、Store 独立数据前递、JAL/JALR 的 PC+4 写回、JALR 清最低位及显式 WB→ID 旁路。

本次只为 stub 和接线样例补充 RESET_PC 参数；生产 Control 无新增状态或端口，共享编码数值不变。新增测试覆盖非零复位入口、PC/指令配对、AUIPC 与消费者、运行中同步复位，以及 NOP/非法指令连续执行后的架构副作用。

CNN/MMIO 的 start/soft_reset 单周期脉冲、STATUS 只读和 SRAM A/B 口分工已写入契约；没有生产 Datapath/CNN RTL，未实现或验证这些硬件。

## 版本和交付

- D1 原文按字节归档，不更改对方结论和待办勾选框。SHA-256：`907492c9028893e4b4741c0a62a84f8d3937134e63db47ecf60e188ec51e0f78`。
- C1 的端口、编码、流水级、复位方式和存储采样契约均未改变；此次是 D1 对齐记录及 test-only 参数化，不另起接口 ABI 版本。
- 本地修改前备份位于 `build/backups/pre_d1_20260914_124718/`。根目录两份设计输入及用户桌面的 D1 原文保持原样。
- 交付 Datapath 的文件为 `rtl/common/cpu_control_pkg.sv`、`rtl/cpu_control/` 六个生产 RTL 文件及接口/时序文档。接线样例位于 `tb/integration/`，其中 Datapath 明确为 test-only stub。
- 后续若端口、编码、流水级、复位或实际采样契约发生变更，需同步 C1/D1、package、相关 RTL 和测试并记录新版本；本次没有把状态标为“接口双方已确认”。

本次回归结果和产物入口见 [验证报告](verification_report.md)。真实 Datapath 到位后按 [连接清单](datapath_connection_checklist.md) 验收。
