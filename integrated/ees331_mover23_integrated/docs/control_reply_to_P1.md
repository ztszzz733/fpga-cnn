# M（CPU_CONTROL）对项目协作需求 P1 的正式确认

文档编号：CPU-CTRL-ACK-P1；日期：2026-09-14；交付版本：Control v1.0（C1 端口/编码不变）。依据：[FACE-SOC-COORD-P1 v0.1 原文](inputs/FACE-SOC-COORD-P1.md)、[D1 原文](inputs/CPU-DP-IF-D1.md)。本回复记录用户授权的 Control 侧确认，可交付 Datapath/Z 负责人；尚未向外发送。

## 1. 按 P1 §5.3 回复

| 要求 | M / Control 侧正式回复 |
|---|---|
| C1：接受 / 有差异 | **接受。Control 侧正式确认 CPU-CD-IF-C1 作为 Control—Datapath v1.0 开发基线。** 冻结本方 48 个端口、方向、位宽、编码、流水级归属及现有控制规则；不再将 M 侧确认列为待办。D1 已记录 Datapath 原则接受，P1 请求正式冻结；三方 S-01 总表仍需共同回签归档，不代填对方签字。 |
| D1：接受 / 有差异 | **接受 D1 的接口条目及其保留条件，无新增端口/编码差异。** 第 2 节 12 项逐项处理见 [D1 当前回复](control_reply_to_D1.md)。实际存储时序仍按条件验收。 |
| rst_n 时序 | **确认 CPU 流水状态采用上升沿同步、低有效 rst_n。** Control 自身完全组合，clk 不用于存储状态；rst_n 拉低时组合输出立即变安全，Datapath 在上升沿清状态。这与同步流水复位一致，不把 Control 改成时序模块。全局复位分发及 CNN 侧确认仍属 S-03。 |
| PC 复位地址 | **Control 侧接受 RESET_PC=32'h0000_0000，建议 Datapath 保留 RESET_PC 参数。** PC 由 Datapath 持有，不添加 Control 地址端口；S-02 最终系统值待共同归档。 |
| Control RTL 交付物 | 已有可编译真实 RTL：共享 package + 6 个 Control 模块，详见第 3 节。 |
| 尚未解决问题 | S-01～S-10 的共同冻结记录、真实 Datapath 顶层/存储 wrapper、Z 侧 CNN 外部协议和真实联调，详见第 5 节。 |

## 2. 按 P1 §5.1 确认控制规则

- 编码唯一来源为 `rtl/common/cpu_control_pkg.sv`。Control 交付此基准，双方工程集成时只编译同一个物理文件一次。Datapath M1 的 package 内容未提供，本次不能声称已完成跨工程逐字比较；请用下列 SHA-256 核对，若仅注释不同也需确认后合并为一个共享文件，禁止独立修改数值。
- package SHA-256：`fc0f6cf155299a43b2d44b527d087d726bf4a3f974377a1d7301492cefed0a3c`。
- 控制优先级确认：**复位 > EX 重定向/flush > load-use 暂停 > 正常推进**。流水寄存器采用复位 > flush > enable > 保持。load-use 仅保持 PC/IF-ID、清空 ID/EX，旧 EX 指令及 M/W 正常前进。
- 第一版非法指令、FENCE、ECALL、EBREAK 均输出安全零控制，无寄存器写、访存或跳转副作用；不实现 trap。FENCE 的简化仅适用于当前固定、有序访存假设。
- 37 条 RV32I 指令与 `uses_rs1/uses_rs2` 见 [译码表](decode_table.csv)。不支持 M/Zmmul、CSR、特权、压缩/原子扩展，`mul_busy` 固定为 0 是已明确约定的未支持扩展输入。
- `valid_d/e/m/w` 分级限定；真正的 WB 写使能、SRAM/MMIO 写使能还须由 Datapath 使用对应级 valid 门控。

## 3. 按 P1 §5.2 交付

生产编译清单：[rtl/filelists/cpu_control.f](../rtl/filelists/cpu_control.f)。所有路径相对工程根目录，按下表顺序以 SystemVerilog 编译；只有这 7 个文件属于 Control 生产依赖，不需要 stub 或 testbench。

| 顺序 | 文件 | 作用 |
|---|---|---|
| 1 | `rtl/common/cpu_control_pkg.sv` | 唯一共享编码和 decode_t |
| 2 | `rtl/cpu_control/main_decoder.sv` | 主译码 |
| 3 | `rtl/cpu_control/alu_decoder.sv` | ALU 运算及 funct 合法性 |
| 4 | `rtl/cpu_control/hazard_unit.sv` | 前递与 load-use |
| 5 | `rtl/cpu_control/branch_control.sv` | EX 分支/跳转判断 |
| 6 | `rtl/cpu_control/pipeline_control.sv` | 优先级及流水门控 |
| 7 | `rtl/cpu_control/cpu_control.sv` | 48 端口真实组合顶层 |

| 交付要求 | 文件及说明 |
|---|---|
| 完整顶层端口表、编码 | [cpu_control_interface.md](cpu_control_interface.md)，26 输入、22 输出 |
| Control 单元测试结果 | [verification_report.md](verification_report.md)、[verification_manifest.json](verification_manifest.json)，关联本次独立运行的日志与 VCD |
| 可复现验证 | `scripts/run_tests.py`、`scripts/plot_waveforms.py`、`scripts/wave_signals.json`、`scripts/requirements.txt`；`tb/filelists/cpu_control.f` 为完整仿真清单 |
| 联调定向序列及期望信号 | [control_datapath_directed_tests.md](control_datapath_directed_tests.md)、`tb/unit/tb_cpu_control.sv`、`tb/vectors/decode_cases.csv` |
| 显式接线样例 | `tb/integration/cpu_control_link_example.sv` 使用命名端口；内部 `control_datapath_stub` 仅用于验证。接真实 Datapath 须替换 stub 并连接其存储/CNN 端口。 |
| 存储边沿要求 | [memory_timing_contract.md](memory_timing_contract.md)，供 wrapper 实现者验收 |

## 4. C1 差异核对

| 核对项 | 本项目相对 C1 的结果 |
|---|---|
| 端口名、方向、位宽 | 无差异：48 端口，26 输入 / 22 输出 |
| package 编码 | 无差异，未修改 RTL；提供哈希供接收方核对 |
| D/E/M/W 归属及组合 Control | 无差异，所有跨级状态仍由 Datapath 持有 |
| 复位/重定向/暂停规则 | 无差异，本次将本方候选确认升级为正式开发承诺 |
| ready/stall、trap、CNN 直连端口 | C1 未定义这些端口，本次不新增；不通过常量隐藏任何应有的反馈端口 |
| 真实 Datapath 顶层是否一致 | 尚未收到源代码，未比较、未联调；不能以本方表格代替对方 RTL 核查 |

## 5. S-01～S-10 状态与后续责任

| 编号 | Control 侧意见 / 已完成部分 | 尚需共同确认或交付 |
|---|---|---|
| S-01 C1 v1.0 | M 正式接受并冻结本方 C1 开发基线 | 由协作方收齐共同冻结记录；P1/D1 不作为他方最终回签 |
| S-02 RESET_PC | M 接受默认 0，建议参数化；stub 已验证 | SoC/Datapath/CNN 共同记录最终启动地址、装载位置 |
| S-03 全局复位 | M 接受上升沿同步低有效；与所述 Datapath M1 一致 | Z/SoC 确认全局分发和 CNN 时序 |
| S-04 IMEM | 接受固定时延、无 ready/stall 的基线 | 容量/端口、请求接受沿、返回沿、PC/valid 配对、暂停缓存和错路返回失效 |
| S-05 Data SRAM | 接受 CPU A 口 / CNN B 口分工及 Load 一拍停顿的条件契约 | 容量、双口/冲突规则和 wrapper 实际边沿；Load 数据须按时与 WB 元数据配对 |
| S-06 CNN MMIO | 接受既有 0x00～0x20 寄存器偏移；软件基地址由调用者传入 | 三方给出完整基地址、地址范围和路由；未擅自选址 |
| S-07 CNN master | 接受由 Z 实现并使用 B 口 | Z 提供端口、请求/响应、字节使能、未完成请求数量、边沿时序 |
| S-08 CNN_PARAM | 软件使用确认后的参数值 | Z 冻结位域及合法值；Control 无 CNN 专用硬件状态机 |
| S-09 数据格式 | 遵守最后确认的对齐和装载规则 | Z 提供量化、位宽/符号、张量排列和测试向量，三方确认 |
| S-10 程序结束 | Control 安全 NOP 策略使 EBREAK 不充当硬件停止 | 共同选定测试结束判据/tohost 地址；本地 TB 完成条件不是系统规范 |

特别注意：同步 SRAM 若在 M→W 沿才接受 M 地址，则该沿不能同时捕获刚读出的新数据；不能仅写“固定一周期”就认定符合 C1。若无法满足现有边沿契约，需共同升级接口，不能静默延迟一拍。

Datapath M1 PASS 是 P1 中对方报告的进度，本项目未复测其模块。当前可开始 M2 的 Control 接线与定向验证准备；真实 CPU/CNN 联调须在收到相应 RTL 和时序契约后另行验收。Z 的 STATUS 粘滞位、busy 时 start、CNN_PARAM 及 memory master 未由 M 代确认。
