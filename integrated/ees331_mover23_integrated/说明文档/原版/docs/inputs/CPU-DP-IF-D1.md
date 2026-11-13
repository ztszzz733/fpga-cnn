# 发给 CPU_CONTROL 负责人的 Datapath 接口对接回复

| 项目 | 内容 |
|---|---|
| 项目背景 | 32 位、五级流水线、Harvard CPU + CNN SoC |
| 回复文档编号 | CPU-DP-IF-D1 |
| 对应文档 | CPU-CD-IF-C1 |
| 日期 | 2026-09-14 |
| 回复方 | CPU_DATAPATH 负责人 |
| 当前状态 | 原则接受 C1；接口可按 C1 开发，存储器时序及公共地址参数待三方冻结和 RTL 验证 |

## 1. 回复结论

Datapath 侧已阅读 `CPU-CD-IF-C1`，并与 `face_recognition_soc_spec_v0.1.md` 和项目硬件架构图进行了核对。

Datapath 侧认为，C1 对原规格缺失的流水级有效位、EX 级源寄存器信息、源使用信息、EX 分支/跳转反馈、MEM Load 标志和立即数类型进行了必要补充。其端口方向、位宽、编码和五级流水线控制原则总体可实现。

因此，Datapath 侧对 C1 给出以下回复：

- **原则接受 C1 作为 Control—Datapath 的共同开发基线。**
- 接口冻结后，Datapath 将按 C1 的同名反向端口实现，不自行增删或改变编码。
- 当前尚无完整 Datapath RTL 和计划部署的存储器 wrapper，因此“接口结构接受”不等于“真实联调通过”。
- 同步 IMEM/Data SRAM 时序、PC 复位地址、MMIO 基地址等公共参数仍需确认后，才能完成顶层和时序验收。

## 2. 对 C1 第 11 节确认单的正式回复

### CPU_CONTROL / CPU_DATAPATH 接口确认

| 确认项 | Datapath 侧回复 |
|---|---|
| 文档编号 | CPU-CD-IF-C1 |
| Datapath 负责人 | 待组内填写姓名 |
| 日期 | 2026-09-14 |
| 1. 完整端口 | **接受。** Datapath 顶层对 C1 同名端口使用相反方向；`clk/rst_n` 仍为公共输入。IMEM、Data SRAM 和 CNN 端口继续保留，不计入 C1 的 48 个端口。 |
| 2. 第 5 节编码 | **接受。** 双方应共用唯一的 `rtl/common/cpu_control_pkg.sv`，不得分别维护不同数值的同义编码。 |
| 3. ID 控制寄存后用于 EX，EX 元数据反馈 | **接受。** `alu_ctrl`、`alu_src_a_sel`、`alu_src_b_sel` 与其他 ID 控制进入 ID/EX；Datapath 同步反馈 `rs1_e/rs2_e`、`uses_rs1_e/uses_rs2_e`、`branch_type_e/jump_e`。 |
| 4. EX 分支、前递及门控优先级 | **接受。** EX 比较使用前递后的 rs1/rs2；MEM 非 Load 前递优先于 WB；重定向优先于 load-use；复位 > flush > enable > 保持。 |
| 5. 同步低有效复位 | **接受候选基线。** Datapath 计划在上升沿使用同步低有效复位；需与系统顶层及另外两方保持一致。 |
| 6. PC 复位地址 | **建议采用 `32'h0000_0000`，待三方最终确认。** 建议实现为参数 `RESET_PC`，默认值为零。 |
| 7. LW→消费者停一拍的实际存储器时序 | **逻辑方案接受，真实时序待验证。** 目标是 Load 在 MEM 发起/完成固定延迟访问，Load 数据与 rd/valid/wb_sel 配对进入 WB，使停顿后的消费者在 EX 通过 `FWD_WB` 获得正确数据。需在 SRAM wrapper 确定后用边沿表和测试证明。 |
| 8. WB→ID 同周期同址读取处理 | **接受并计划实现显式 WB→ID bypass。** 当 `valid_w && regwrite_w && rd_w!=0` 且读地址等于 `rd_w` 时，ID 读数据选择最终 `wb_data`。 |
| 9. 同步 IMEM 暂停和重定向的返回处理 | **待存储器接口冻结后实现。** Datapath 将保存请求 PC/valid；暂停时不得覆盖 IF/ID，重定向后旧路径返回必须失效。若固定一周期方案无法满足，需要双方升级接口，不能在 Datapath 内暗自假设。 |
| 10. RV32I 范围、非法/NOP 策略 | **接受。** 实现 C1 第 9 节列出的 37 条 RV32I 指令；暂不实现 M/Zmmul、CSR、特权、压缩和原子扩展。第一版建议非法指令、FENCE、ECALL、EBREAK按安全 NOP，且不得产生任何架构副作用。 |
| 11. 地址对齐及未支持访存情况 | **建议第一版不实现未对齐半字/字访问。** LB/LBU/SB 可访问任意字节地址；LH/LHU/SH 要求 2 字节对齐；LW/SW 要求 4 字节对齐。当前接口没有异常反馈，测试程序不得产生不支持的访问。CNN 张量基地址继续要求 4 字节对齐。 |
| 12. 已有公共 package 或接口冲突 | **当前未发现已有 RTL package 冲突。** 项目尚未提供 Datapath RTL；后续创建共享 package 前需由双方确认文件归属和版本。 |

## 3. Datapath 对 Control 的端口承诺

### 3.1 Datapath 输出给 Control

Datapath 将按 C1 输出：

- ID 级：`instr_d`、`rs1_d`、`rs2_d`、`valid_d`。
- EX 级：`rd_e`、`rs1_e`、`rs2_e`、`uses_rs1_e`、`uses_rs2_e`、`memread_e`、`branch_type_e`、`jump_e`、`cmp_eq_e`、`cmp_lt_e`、`cmp_ltu_e`、`valid_e`。
- MEM 级：`rd_m`、`regwrite_m`、`memread_m`、`valid_m`。
- WB 级：`rd_w`、`regwrite_w`、`valid_w`。
- 基线未实现乘法器，`mul_busy` 固定为 0。

所有带 d/e/m/w 后缀的信息保证属于对应流水级的同一条指令。无效级、复位、气泡或被冲刷指令不会产生 Store、寄存器写回或重定向等副作用。

### 3.2 Datapath 接收 Control 输出

Datapath 将接收 C1 的 22 个 Control 输出，并按以下方式处理：

- `pc_sel`、`fwd_a`、`fwd_b`、`fwd_store` 为当前 EX/重定向相关的即时选择。
- ID 译码控制先写入 ID/EX，然后随对应指令向后传递。
- `pc_en` 控制 PC；`if_id_en/if_id_flush` 控制 IF/ID；`id_ex_flush` 负责气泡和年轻指令冲刷。
- 实际寄存器写使能必须与 `valid_w` 相与并排除 `rd_w=0`。
- 实际 SRAM/MMIO 写使能必须与 `valid_m` 相与，避免错误路径 Store 生效。

## 4. 前递、暂停和跳转实现约定

1. EX 操作数先进行前递，再由 `alu_src_a_sel/alu_src_b_sel` 选择 ALU 输入。
2. 分支比较直接使用前递后的 rs1/rs2，不使用已经选择立即数的 ALU B 输入。
3. Store 地址使用前递后的 rs1 加 S 型立即数；Store 数据由 `fwd_store` 选择前递后的 rs2。
4. JAL/JALR 写回值为该指令的 `PC+4`；JALR 目标最低位清零。
5. 前递优先级为有效 MEM 非 Load > 有效 WB > ID/EX 原值。
6. load-use 时保持 PC 和 IF/ID、清空 ID/EX；EX 中旧 Load 正常进入 MEM，MEM/WB 正常推进。
7. EX 重定向时更新目标 PC，并冲刷 IF/ID 与 ID/EX；当前 EX 中的 Branch/JAL/JALR 自身仍进入后级。

## 5. 存储器时序临时约定与待确认项

当前先接受 C1 的“固定时延、无 ready/stall 端口”基线，但以下内容必须在实现完整 Datapath 顶层前冻结：

| 项目 | Datapath 建议 | 状态 |
|---|---|---|
| PC 复位地址 | `32'h0000_0000` | 待三方确认 |
| IMEM 读延迟 | 固定 1 周期同步读 | 待确认 |
| Data SRAM CPU 读延迟 | 固定 1 周期同步读 | 待确认 |
| Data SRAM 写完成 | `valid_m && memwrite_m` 对应的接受沿只写一次 | 待 wrapper 定义 |
| MMIO 读写等待 | 第一版无额外等待 | 待确认 |
| 可变延迟支持 | 第一版不支持；需要时升级 C1 | 暂不实现 |

在 wrapper 未确定前，Datapath 侧不承诺 C1 中 LW→消费者只停一拍已经通过真实同步存储器验证。

## 6. CNN/MMIO 边界说明

- CNN 9 个固定 32 位端口继续按原 SoC 规格执行，不增加 Control 直连端口。
- CPU 使用普通 LW/SW 访问 CNN MMIO。
- `CONTROL.start` 与 `CONTROL.soft_reset` 由 Datapath 产生单周期脉冲。
- `STATUS` 为只读输入，写操作不改变其状态。
- CNN 的 DMA/memory master 属于 CNN 模块，连接 Data SRAM B 口；Datapath 负责 CPU 使用的 A 口及 MMIO 路由。
- CNN MMIO 偏移接受 `0x00~0x20` 的现有表，但完整 `CNN_MMIO_BASE` 尚需三方冻结。

## 7. Datapath 侧计划回传的文件

接口冻结并开始实现后，Datapath 侧计划回传：

- `rtl/common/cpu_control_pkg.sv`
- `rtl/cpu_datapath/cpu_datapath.sv`
- PC、寄存器堆、立即数生成器、ALU、四组流水寄存器、LSU 和 CNN 寄存器组 RTL
- `docs/memory_timing_contract.md`
- Control—Datapath 显式命名端口连接样例，不使用 `.*`
- 单元测试、集成测试、Verilator 命令和测试日志
- 接口差异表与尚未验证项目清单

没有真实 Control RTL 时，只会使用明确标注为 test-only 的 stub；stub 测试不会报告成真实 CPU 联调通过。

## 8. 需要 Control 负责人回复确认的事项

请 Control 负责人确认以下内容：

- [ ] 接受 Datapath 对 C1 的原则确认及上述保留项。
- [ ] 接受 `RESET_PC=32'h0000_0000` 的建议，或提供最终值。
- [ ] 同意双方共用唯一的 `cpu_control_pkg.sv`。
- [ ] 同意第一版非法指令、FENCE、ECALL、EBREAK按安全 NOP。
- [ ] 同意未对齐访问的第一版限制。
- [ ] 与 SoC/CNN 负责人共同确定 IMEM/Data SRAM 的精确时序。
- [ ] 与 SoC/CNN 负责人共同确定 `CNN_MMIO_BASE`。

上述事项完成后，双方可将 C1/D1 的状态更新为“接口双方已确认”。“接口已确认”与“真实 RTL 已联调”分别记录，不能互相替代。

## 9. 变更规则

后续若修改端口、编码、流水级、复位或存储器采样时序，双方必须同步更新 C1、D1、共享 package 和相关 RTL，并记录变更原因与影响。只修改一方文件时，不得继续沿用相同接口版本号。
