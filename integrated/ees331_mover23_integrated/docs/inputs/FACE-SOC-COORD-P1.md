# 发给 M 负责人和 Z 负责人的项目进度与协作需求

| 项目 | 内容 |
|---|---|
| 项目名称 | 32 位五级流水线 CPU + 外部 CNN 加速器人脸识别数字系统 |
| 文档编号 | FACE-SOC-COORD-P1 |
| 版本 | v0.1 |
| 日期 | 2026-09-14 |
| 发送方 | CPU Datapath 负责人 |
| 接收方 | M 负责人（CPU Control Path）、Z 负责人（CNN Accelerator） |
| 当前阶段 | Datapath 基础模块 M1 已完成；准备进入 M2 顶层数据通路集成 |

## 1. 本文目的

本文用于同步 CPU Datapath 当前进度，明确下一阶段的开发安排，并列出需要 M 负责人和 Z 负责人提供、确认或共同冻结的内容。

本文仅表示 Datapath 基础模块已经完成单元级验证，不表示完整 CPU、CPU—Control 或 CPU—CNN 已完成联调。

## 2. 当前总体进度

### 2.1 已完成的前期设计工作

目前三方已经具备以下共同设计基础：

1. 简易项目规格书 `face_recognition_soc_spec_v0.1.md`。
2. 项目硬件底层架构图。
3. Control—Datapath 候选接口协议 `CPU-CD-IF-C1`。
4. Datapath 对 C1 的回复协议 `CPU-DP-IF-D1`。
5. C1 共享控制编码文件 `rtl/common/cpu_control_pkg.sv`。

目前 Datapath 侧原则接受 C1 的端口、位宽、编码和五级流水线控制方式。但 C1 原文件仍标记为“候选、尚未冻结”，因此需要 M 负责人完成正式确认。

### 2.2 Datapath M1 已完成内容

Datapath 已实现并验证以下基础模块：

- `cpu_control_pkg.sv`：C1 共享控制编码。
- `alu.sv`：32 位 RV32I 基础算术、逻辑、比较和移位。
- `imm_gen.sv`：I/S/B/U/J 五类立即数生成。
- `pc.sv`：32 位 PC、同步复位和写使能。
- `regfile.sv`：32×32 位寄存器堆、`x0` 恒零、WB→ID 同周期旁路。
- `if_id_reg.sv`：IF/ID 流水寄存器，支持 `enable` 与 `flush`。
- `id_ex_reg.sv`：ID/EX 流水寄存器，支持 `flush` 插入气泡。
- `ex_mem_reg.sv`：EX/MEM 流水寄存器。
- `mem_wb_reg.sv`：MEM/WB 流水寄存器。

### 2.3 M1 验收结果

M1 已在本机 MSYS2 UCRT64 + Verilator 环境完成扩展单元测试和最终干净构建验收：

- ALU 全部已支持运算及关键边界值通过。
- I/S/B/U/J 型立即数、正负数符号扩展和 B/J 对齐通过。
- PC 复位、更新、保持和控制优先级通过。
- 寄存器堆双读、写回、WB→ID bypass、禁止写入和 `x0` 保护通过。
- 四组流水寄存器均已实际实例化并完成适用项测试。
- 所有新增断言均已实际执行。
- Verilator 测试结果为 `PASS: base datapath modules`。
- Bash 与 PowerShell 最终退出码均为 `0`。
- 没有为了通过测试而修改模块接口或 C1 编码，也没有全局关闭 lint。

因此，以下里程碑已经完成：

> **M1：Datapath 基础模块实现与单元测试完成——PASS。**

除后续真实联调发现明确接口或功能问题外，以上模块进入相对冻结状态，不再进行无依据的接口修改。

## 3. 尚未完成的 Datapath 内容

以下内容不属于 M1，后续将在 M2/M3 阶段完成：

- 完整 `cpu_datapath.sv` 顶层。
- ALU 操作数选择器和前递 MUX。
- Store 数据前递通路。
- 分支比较、Branch/JAL/JALR 目标计算与 Next-PC 通路。
- WB 写回选择器。
- Load/Store Unit（LSU）、字节使能和加载扩展。
- IMEM 与 Data SRAM wrapper。
- CNN MMIO 地址译码和九个控制/状态寄存器连接。
- Control stub 条件下的 Datapath 集成测试。
- 与 M 负责人真实 `cpu_control` RTL 的接口联调。
- 与 Z 负责人 CNN stub/真实 CNN 的联调。
- RV32I 指令程序级仿真和系统级人脸识别流程验证。

## 4. Datapath 后续工作计划

### M2：CPU 内部数据通路集成

Datapath 负责人计划按以下顺序推进：

1. 实现前递 MUX、ALU 输入选择和 Store 数据选择。
2. 实现分支比较器、Branch/JAL/JALR 目标计算及 Next-PC MUX。
3. 实现 WB MUX，并完成寄存器写回通路。
4. 按 C1 组装 `cpu_datapath.sv` 顶层端口和各级控制字段。
5. 使用 Control stub 验证普通算术、数据相关、load-use、分支和跳转的数据通路行为。
6. 接入 M 负责人提供的真实 `cpu_control`，完成 Control—Datapath 定向联调。

### M3：存储器与 CNN MMIO 集成

完成公共地址和存储器时序冻结后，Datapath 负责人将：

1. 实现 LSU 的 LB/LH/LW/LBU/LHU 和 SB/SH/SW。
2. 实现 SRAM/MMIO 地址译码。
3. 实现九个 CNN MMIO 寄存器及 `start`、`soft_reset` 脉冲。
4. 实现 `STATUS` 回读。
5. 接入 IMEM/Data SRAM wrapper，验证同步读取时序。
6. 先接 CNN stub，再接 Z 负责人真实 CNN RTL。

## 5. 需要 M 负责人完成的事项

M 负责人负责 CPU Control Path。为使 M2 能够进入真实联调，请完成或回复以下事项。

### 5.1 必须优先确认

1. **正式确认 C1。** 请确认 `CPU-CD-IF-C1` 是否可以冻结为 Control—Datapath v1.0 开发基线。
2. **确认 D1 回复。** 请逐项确认 `CPU-DP-IF-D1` 中的接受项、建议项和待确认项；若有异议，请按信号名逐项提出。
3. **共享 package 唯一性。** 确认双方只使用同一份 `rtl/common/cpu_control_pkg.sv`，不得各自维护不同编码。
4. **确认复位规则。** 当前 Datapath 按上升沿同步低有效 `rst_n` 实现，请确认 Control 保持一致。
5. **确认控制优先级。** 建议共同采用：复位 > EX 重定向/flush > load-use 暂停 > 正常推进。
6. **确认非法指令策略。** 第一版建议非法指令、FENCE、ECALL、EBREAK 作为安全 NOP，不产生寄存器写、存储器写或跳转副作用。

### 5.2 需要提供的开发交付物

1. 可编译的 `cpu_control.sv` 真实 RTL，而不是空模块或接口占位文件。
2. 与 C1 完全一致的顶层端口表和编译依赖文件清单。
3. Control 侧单元测试结果，至少覆盖：
   - RV32I 指令译码；
   - `uses_rs1/uses_rs2`；
   - EX/MEM 与 MEM/WB 前递选择；
   - load-use 停顿；
   - Branch/JAL/JALR 重定向；
   - `valid` 对副作用和冒险判断的门控。
4. 一组用于 Control—Datapath 联调的定向测试序列及期望控制信号。
5. 若 Control 实现与 C1 不一致，请在交付前给出差异表，不要通过常量接线隐藏缺失端口。

### 5.3 希望 M 负责人回复的格式

请至少回复：

- C1：接受 / 有差异。
- D1：接受 / 有差异。
- `rst_n` 时序：确认值。
- PC 复位地址建议：确认 / 修改建议。
- Control RTL 预计交付物：文件清单。
- 当前尚未解决的问题。

## 6. 需要 Z 负责人完成的事项

Z 负责人负责 CNN Accelerator。CNN 内部计算实现可以与 CPU 开发并行，但以下外部接口和行为必须尽早冻结，否则会阻塞 Datapath 的 MMIO、LSU 和存储器连接。

### 6.1 必须优先确认

1. **确认九个固定 32 位接口及方向：**
   - CPU/Datapath → CNN：`CONTROL`、`INPUT_ADDR`、`OUTPUT_ADDR`、`WEIGHT_ADDR`、`BIAS_ADDR`、`IMAGE_SIZE`、`CHANNELS`、`CNN_PARAM`；
   - CNN → CPU/Datapath：`STATUS`。
2. **确认 `STATUS` 位定义：** 建议 `[0]=busy`、`[1]=done`、`[2]=error`，其余位读零。
3. **确认启动和复位语义：**
   - `CONTROL[0]` 写 1 产生单周期 `start` 脉冲；
   - `CONTROL[1]` 写 1 产生单周期 `soft_reset` 脉冲；
   - `done/error` 是否为粘滞位；
   - `busy=1` 时再次收到 `start` 的处理方式。
4. **确认 `CNN_PARAM` 精确位域。** 需要冻结 kernel、stride、padding、quant_shift、activation、pool_mode 和 op_type 的位置与合法值。
5. **确认数据 SRAM B 口归属。** 建议 CNN 的 memory master 由 Z 负责人实现并连接 Data SRAM B 口，CPU Datapath 使用 A 口。
6. **确认 CNN memory master 的完整端口和时序。** 包括请求、读写、地址、写数据、字节使能、返回数据、响应有效信号，以及是否允许多个未完成请求。

### 6.2 需要提供的开发交付物

1. `cnn_accelerator` 顶层模块端口声明及信号方向/位宽表。
2. CNN memory master 接口协议和至少一张边沿级时序表。
3. 可用于 CPU 联调的 CNN stub：收到 `start` 后产生可预测的 `busy/done/error`，不要求先实现完整卷积。
4. CNN 单层测试向量，包括输入、权重、bias、期望输出及参数配置。
5. 数据格式说明：
   - 输入/权重/bias/输出的位宽和有无符号；
   - 定点格式和量化规则；
   - 张量在 SRAM 中的排列顺序；
   - 地址步进和对齐要求；
   - 最终输出是分类分数还是 embedding。
6. CNN 独立测试结果及当前未实现功能清单。

### 6.3 希望 Z 负责人回复的格式

请至少回复：

- 九个 CNN 端口：接受 / 有差异。
- `STATUS`、`start`、`soft_reset` 行为：确认值。
- `CNN_PARAM` 位域：确认表或修改表。
- SRAM B 口/memory master：端口和时序说明。
- CNN stub 与真实 RTL 预计交付物：文件清单。
- 数据格式与测试向量状态。
- 当前尚未解决的问题。

## 7. 需要三方共同冻结的系统事项

以下问题不能由 Datapath 单方面决定，需要三方形成一份共同结论：

| 编号 | 需要冻结的事项 | 当前建议 | 主要影响 |
|---|---|---|---|
| S-01 | C1 是否成为正式 v1.0 接口 | 正式冻结 | Control—Datapath 联调 |
| S-02 | PC 复位地址 | `32'h0000_0000` | 启动与程序装载 |
| S-03 | 全局复位时序 | 上升沿同步低有效 `rst_n` | 全部 RTL |
| S-04 | IMEM 容量、端口和读延迟 | 固定时延、无 ready/stall | IF 时序与重定向 |
| S-05 | Data SRAM 容量、双口结构和读延迟 | CPU 使用 A 口，CNN 使用 B 口 | LSU、DMA与load-use |
| S-06 | CNN MMIO 完整基地址和范围 | 待共同确定 | CPU 地址译码 |
| S-07 | CNN memory master 接口 | 由 Z 负责人提出并冻结 | Data SRAM B 口连接 |
| S-08 | `CNN_PARAM` 位域 | 由 Z 负责人确认 | 软件配置与CNN执行 |
| S-09 | tensor/weight/bias/output 数据格式 | 由 Z 负责人提出，三方确认 | 数据装载和结果解释 |
| S-10 | 程序结束判据或 `tohost` 地址 | 待共同确定 | 系统级自动测试 |

第一版 C1 没有 `imem_ready`、`mem_ready` 或全局可变延迟等待接口，因此 IMEM/Data SRAM 必须先采用固定时延模型。若后续改为任意延迟存储器，三方必须升级接口版本，不能由某一方私自增加信号。

## 8. 建议的三方联调顺序

1. M 负责人确认 C1/D1，Z 负责人确认 CNN 外部接口。
2. 三方冻结 S-01 至 S-10，并记录版本和日期。
3. Datapath 完成 M2 顶层；M 负责人完成 Control RTL；Z 负责人先提供 CNN stub。
4. 先完成 CPU Control—Datapath 联调，验证 RV32I 基础程序。
5. 再完成 LSU、MMIO 与 CNN stub 联调，验证 CPU 配置、启动和轮询流程。
6. 最后把 CNN stub 替换为真实 CNN RTL，并加入 Data SRAM B 口访问和单层测试向量。
7. 完成系统级仿真后，再进入 FPGA 综合、时序约束和上板验证。

## 9. 当前结论

Datapath M1 已通过最终干净构建，可以进入 M2。当前最大的跨组阻塞项不是 ALU或寄存器堆，而是：

1. C1 尚未由 M 负责人正式冻结；
2. IMEM/Data SRAM 的精确时序尚未冻结；
3. CNN MMIO 基地址尚未确定；
4. CNN memory master 与 SRAM B 口协议尚未确定；
5. `CNN_PARAM` 和 CNN 数据格式尚未冻结。

请 M 负责人和 Z 负责人按第 5、6 节回复。三方共同事项确认后，Datapath 将继续完成完整顶层、LSU、MMIO及真实联调。

