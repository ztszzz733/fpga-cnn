# CPU_CONTROL P1 对齐验证报告

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## 2026-09-28 B1接口审计补充

生产Control已对照双口SRAM与B口仲裁方案完成静态审计，结论为无需修改生产RTL：B口、仲裁器、CNN MMIO寄存器组和35位返回均在Control边界之外。过期的stub注释和当前接口说明已经改正，详见[B1审计](control_B1_alignment_review_20260928.md)。

改正后已按统一命令重新运行完整回归。Vivado XSim 2026.1编译、展开、仿真和绘图成功：1,244个场景、30,463项检查、0失败，1,000条随机译码全部执行；7个生产Control/package文件的哈希与既有清单完全一致。证据见[result.json](../build/runs/20260928_215503_605664_7528_all_seed1/result.json)、[编译日志](../build/runs/20260928_215503_605664_7528_all_seed1/compile.log)、[仿真日志](../build/runs/20260928_215503_605664_7528_all_seed1/simulation.log)和[完整VCD](../build/runs/20260928_215503_605664_7528_all_seed1/waves/cpu_control.vcd)。

本轮没有修改或验证B口仲裁器、双口SRAM、CNN memory master及实体FPGA；这些模块仍需等待对应负责人按B1说明交付后进行联调。

## 2026-09-17 晚间：收到生产 Datapath 并完成有限程序联跑

已收到 `D:\QQ\face_recognition_soc_datapath_complete.zip`，48 个 C1 接口的名称/方向/位宽匹配。只编译对方兼容共享 package 一次，连接本方真实 Control 与对方生产 Datapath；双方生产 RTL 哈希未变化。Vivado XSim 2026.1 的两个独立新构建均通过：

- 单条 ADD：1 + 2 = 3，最终 x6=3，寄存器只写一次，数据存储器读写、MMIO 读写、暂停及重定向均为 0。
- 对方混合程序使用真实 Control：117 个运行周期、1 次 load-use 暂停、10 次重定向、17 次数据读、10 次数据写、1 次 MMIO 读和 1 次写；原有结果与事务检查通过。

本轮证据：[result.json](../build/runs/20260917_212107_968626_real_datapath_review/result.json)、[ADD 日志](../build/runs/20260917_212107_968626_real_datapath_review/add/simulation.log)、[混合程序日志](../build/runs/20260917_212107_968626_real_datapath_review/mixed/simulation.log)、[新 ADD 中文波形](../build/runs/20260917_212107_968626_real_datapath_review/add/figures/add_real_datapath_cn.png)。范围、首次测试模型展开失败与仅副本适配、共享包条件及图中尚未实现项详见 [对接核查](datapath_connection_review_20260917.md)。

存储器仍用同步模型，CNN MMIO 用 stub；真实 CNN、共享 SRAM B 口、实体存储器/FPGA、完整人脸识别软件和三方系统联调均未运行。兼容包新哈希及实际 SRAM/MMIO 提交边沿仍需共同归档。本轮不是原 1,000 随机译码完整回归的替代。

下文的“Datapath 未提供”及旧模型限制属于当时运行记录；现状以上述晚间记录为准，不能把新旧运行的波形和范围混用。

## 2026-09-14 指定指令阶段测试补充

新增 `--test instruction --stage fetch|decode|execute|memory|writeback|all --instruction ...`。生产 Control RTL 未修改；改动位于运行脚本、testbench、波形配置和 test-only Datapath stub。多条指定指令逐条独立复位，使用安全代表机器码经过 F/D/E/M/W；检查对应阶段的有效位、完整控制字、目标寄存器、跳转 PC 选择、未知值和最终副作用。阶段结果仍是 Control + stub 验证，不是生产 Datapath 联调。

- 全部 55 个表内项目执行 `stage=all`：1,265 项检查、0 失败，见 [阶段结果](../build/runs/20260914_173349_674396_29280_instruction_seed1/result.json)。其中包括 37 条已实现指令、3 个安全 NOP 和 15 个非法/不支持编码。
- 修改后的规定完整回归：1,244 场景、30,463 项检查、0 失败，见 [最新完整结果](../build/runs/20260914_173505_950453_12400_all_seed1/result.json)。
- 绘图解析测试：12 项通过。六种阶段均已实际运行并生成对应信号组图片。
- test-only stub 补充了对齐的 LB/LH/LW/LBU/LHU 和 SB/SH/SW 行为，用于阶段观测；真实 LSU、存储器边沿协议和异常反馈仍未验证。

交付核对另已通过：[alignment_checks.json](../build/runs/20260914_155026_886660_all_seed1/alignment_checks.json)。48 端口表与 RTL 的方向/位宽一致；7 文件生产清单与回归使用的生产源顺序一致，单独编译并展开 cpu_control 成功（[独立编译日志](../build/runs/20260914_155026_886660_all_seed1/production_only/compile.log)）；44 个受保护原始输入/RTL/TB/归档文件哈希未改变，P1 归档与桌面源文件逐字节一致。

2026-09-14：**Control v1.0 / C1 本方正式确认后的完整回归 PASS：1,244 场景、30,463 检查、0 失败。** 生产 Control 和 test-only stub 均未修改，重新运行验证交付基准。真实 Datapath/CNN 未提供，真实直连未运行。

命令：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。使用 Vivado XSim 2026.1，编译、展开、仿真和绘图成功，命令退出 0；编译/展开日志未发现 WARNING/ERROR。

| 验证范围 | 本次结果 |
|---|---|
| RV32I 与 uses_rs1/uses_rs2 | 55 条定向译码向量（含 37 条支持指令）+ 1,000 条随机合法编码变体 |
| 前递 | 16 个定向状态 + 128 个约束随机状态；MEM 非 Load 优先 WB、valid/源使用/x0 门控、MEM Load 遮挡旧 WB |
| load-use | 16 个定向状态，7 次真依赖命中；程序 LW→ADD 和 LW→SW 各暂停一次 |
| 分支/跳转 | 六类分支各跳/不跳，JAL/JALR、前递比较、JALR bit0 清零、PC+4 链接与错路冲刷 |
| 安全行为 | 无效级、副作用、运行中同步复位、flush 优先、仲裁器 reset > redirect > stall、非法/FENCE/ECALL/EBREAK 连续执行 |
| 接口样例 | 真实 Control 与 test-only stub 的 48 端口显式命名连接；不等于生产 Datapath 已接入 |

本次证据：[result.json](../build/runs/20260914_155026_886660_all_seed1/result.json)、[编译日志](../build/runs/20260914_155026_886660_all_seed1/compile.log)、[仿真日志](../build/runs/20260914_155026_886660_all_seed1/simulation.log)、[TB 汇总](../build/runs/20260914_155026_886660_all_seed1/tb_summary.json)、[完整 VCD](../build/runs/20260914_155026_886660_all_seed1/waves/cpu_control.vcd)。源文件哈希见 [verification_manifest.json](verification_manifest.json)。

四张本次新生成的图均已打开检查，标签和总线值可读，暂停/前递/冲刷变化与检查结果相符；未用历史图片替代。

| 场景 | 本次图片 |
|---|---|
| decode | [PNG](../build/runs/20260914_155026_886660_all_seed1/figures/decode.png) |
| forwarding | [PNG](../build/runs/20260914_155026_886660_all_seed1/figures/forwarding.png) |
| load_use | [PNG](../build/runs/20260914_155026_886660_all_seed1/figures/load_use.png) |
| branch_flush | [PNG](../build/runs/20260914_155026_886660_all_seed1/figures/branch_flush.png) |

本次没有重跑历史的其他种子、pytest、C 语法检查或负向脚本测试。未运行 Verilator lint、综合、FPGA 时序、板级测试、真实 SRAM/MMIO/CNN。stub 仅实现对齐 LW/SW 数据行为；字节/半字类型只验证 Control 译码。同步 IMEM 返回、生产 LSU、CNN 端口及 memory master 均待对应负责人交付后验证。

接口确认与系统验证分开记录：M 已正式接受 C1 v1.0；RESET_PC/全局复位/公共地址/真实存储时序以及 Z 侧协议仍需按 [P1 回复的 S-01～S-10 表](control_reply_to_P1.md) 完成共同冻结。

历史证据保留在 [旧验证报告](../说明文档/原版/docs/verification_report.md)。docs/figures 内仍为有 provenance 标注的历史图，当前报告直接链接本次 run 目录。
