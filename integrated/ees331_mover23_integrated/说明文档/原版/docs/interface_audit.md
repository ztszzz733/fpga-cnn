# 接口审计 — C1 / D1 原则接受，公共参数待冻结

设计资料为 FACE-SOC-SPEC-001 v0.1、CPU_CONTROL 任务书和用户此前提供的架构图；2026-09-14 增补 [D1 原文](inputs/CPU-DP-IF-D1.md)。项目有生产 Control、共享 cpu_control_pkg 和验证 stub，没有生产 cpu_datapath/CNN 或实际存储器 wrapper。没有修改其他负责人的生产实现。原图未作为文件归档。

| 原规格条目 | 问题 | 本次候选解决方式 | 影响模块 | 确认状态 |
|---|---|---|---|---|
| §5.1 只有 rs_d | EX 前递缺少当前消费者编号 | 增 rs1_e/rs2_e | ID/EX、Hazard | D1 原则接受 C1 |
| §5.2 只有 branch_d/jump_d | D 指令不能解释 E 比较 | 增 branch_type_e/jump_e | ID/EX、Branch | C1 |
| §5 无源使用标志 | 立即数字段假相关 | 增 uses_rs1/2_d/e | Decoder、Hazard、ID/EX | C1 |
| §5 无 memread_m | Load 地址可能被当结果 | 增 memread_m，禁 M Load 前递并遮挡旧 W | EX/MEM、Hazard | C1 |
| 图 valid/flush，表无 valid | 气泡和错误路径副作用 | 增 valid_d/e/m/w，按级限定 | 所有流水寄存器 | C1 |
| §3.1 立即数类型无输出 | ImmGen 无契约 | 增 imm_type_d | Decoder、ImmGen | C1 |
| alu_ctrl/ALUSrc 无后缀 | 可能跨级错接 | 保留名，明示 D 译码，先经过 ID/EX | ALU、MUX | C1 |
| mul_busy 无完整握手 | 不能可靠保持 E/防重复提交 | 基线固定 0，非零为验证输入错误 | 未来乘法扩展 | 不支持 |
| 图 CNN Driver 在 Control 内 | 误以为有 STATUS FSM | LW/SW 软件，Control 不增 CNN 端口 | 软件、LSU | 依 §3.1 |
| §7 SRAM 一周期 | 采样边沿未冻结 | M 周期内完成，M→W 沿锁存；更慢内存需扩展 ABI | 存储 wrapper、流水 | C1 待确认 |
| 图 CONTROL RW / §6 W1P | start 保持造成重复启动 | 软件写 1；Datapath 产生 start/soft_reset 单周期脉冲 | CNN 寄存器组 | D1 接受分工；真实行为未验证 |
| §4 地址至少 4 字节对齐 / §8 LB/SB | 字节访问范围不明确 | 按 D1：字节任意地址、半字 2 字节对齐、字 4 字节对齐；Control 验类型，stub 仅对齐 LW/SW | LSU | 项目采用第一版限制；真实 LSU 未验证 |
| §4 建议同步释放 | 同步/异步复位未冻结 | stub 同步低有效；Control 组合安全限定 | 流水寄存器 | C1 |
| §8 非法/ECALL/FENCE | trap/NOP 未冻结 | 非法安全 NOP+内部标志；ECALL/EBREAK 和普通 FENCE 项目 NOP | Decoder、软件 | 简化选择，无 trap |
| §6 CNN_PARAM/基地址 | 未给出冻结位域/基地址 | 软件接受调用者提供值 | 软件、CNN | 待确认 |
| §16 argmax / 图 embedding | 端到端路径存在阶段区别 | 不实现识别；示例只启动单层 | 系统软件 | 不在本次验证范围 |

不创建 interface-v1.0 标签，不声称三方已签字。候选端口数量变化是明确的 ABI 补充，不能用常量适配成真实 Datapath 联调通过。

D1 已原则接受 C1 全部端口和编码、ID/EX 控制与反馈、前递/重定向优先级、37 条指令及安全 NOP，并计划显式 WB→ID 旁路。仍未冻结的事项包括系统复位、RESET_PC、CNN_MMIO_BASE、同步 IMEM/Data SRAM 和 MMIO 精确时序；“原则接受”不升级为“接口双方已确认”。本次不改 ABI，详见 [对齐记录](control_reply_to_D1.md)。
