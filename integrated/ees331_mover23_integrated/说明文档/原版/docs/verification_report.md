# CPU_CONTROL C1 验证报告

更新日期：2026-09-14。状态：**D1 对齐后的 Control 组合功能、C1 显式连接与 test-only stub 时序测试通过；真实 Datapath 直连尚未验证。** Datapath 原则接受 C1，公共地址/系统复位/真实存储时序仍待三方冻结；未提供生产 Datapath/CNN，无法报告真实系统或人脸识别结果。

## D1 对齐后的本次完整回归

命令：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。

Vivado XSim 2026.1 实际编译、展开、仿真及绘图通过：**1,244 个场景，30,463 项检查，0 失败**，包含 1,000 条随机译码及 128 个约束随机前递状态。编译/展开日志未发现 WARNING/ERROR。四张新 PNG 已打开检查；本次没有重跑历史的种子 2026、pytest、C 语法检查或负向测试，以下历史结果不可当成本次新增测试的证据。

| 本次新增场景 | 结果 |
|---|---|
| pipeline_D1_safe_NOP | FENCE/ECALL/EBREAK、非法 MUL/Store/JALR 连续执行后 x5=9、x6=10，仅两次合法寄存器提交，Store/重定向/停顿均为零 |
| stub_D1_RESET_PC_parameter | 参数为 0x40 时从对应指令取指，AUIPC x5=0x40、消费者 x6=0x41，不执行零地址指令；运行中复位仅在上升沿回到 0x40 并清空有效位 |

实际证据：[result.json](../../../build/runs/20260914_124846_374213_all_seed1/result.json)、[编译日志](../../../build/runs/20260914_124846_374213_all_seed1/compile.log)、[仿真日志](../../../build/runs/20260914_124846_374213_all_seed1/simulation.log)、[VCD](../../../build/runs/20260914_124846_374213_all_seed1/waves/cpu_control.vcd)、[本次波形目录](../../../build/runs/20260914_124846_374213_all_seed1/figures)。

本次没有改变生产 Control 行为或接口编码；RESET_PC 参数属于 stub/接线样例。新增验证仍是 test-only 模型，不能证明 D1 建议的同步 IMEM/SRAM wrapper 已兼容。详细差异见 [D1 对齐记录](control_reply_to_D1.md)。

## 工具与执行方式

实际工具：Vivado Simulator 2026.1（SW Build 6511674）、Python 3.11.9、matplotlib 3.10.8。C 语法检查使用已有 MinGW GCC 9.5.0（安装目录名含 10.0.0，版本以工具输出为准）。pytest 版本见 verification_manifest.json。

Icarus/vvp/Verilator 没有在本机找到，未运行对应后端或 lint。没有下载、安装系统工具；XSim 所需 DLL/Tcl/Java 环境由 Python 启动器在子进程内设置。当前 XSim 编译/展开日志没有 WARNING/ERROR；这不替代 lint、综合锁存器检查或物理时序分析。

## 历史基线完整回归（2026-09-13）

| 运行 | 命令参数 | 用例数 | 检查数 | 随机译码 | 随机前递 | 失败 |
|---|---|---:|---:|---:|---:|---:|
| [种子 1 结果](../../../build/runs/20260913_111134_231003_all_seed1/result.json) | --test all --seed 1 --random-cases 1000 --waves --plot --lint | 1,242 | 30,394 | 1,000 | 128 | 0 |
| [种子 2026 结果](../../../build/runs/20260913_111347_519716_all_seed2026/result.json) | --test all --seed 2026 --random-cases 5000 --waves | 5,242 | 134,394 | 5,000 | 128 | 0 |

命令前缀为 `python scripts/run_tests.py`。用例数是 begin_case 场景计数；check 数是逐信号比较次数；不是语句覆盖率或独立 ISA 指令条数。定向译码 55 行=37 条要求指令+ECALL/EBREAK/FENCE 三个项目 NOP+15 个非法编码。每行核对 14 个控制字段和 illegal_d，并执行不变量检查。

种子 1 同参数多次运行的 vectors.txt SHA-256 都为 `1f0de2548733c6889f1ab176637d8a327a89ec3f81bf8d208172d18837e2c030`，刺激可复现。黄金向量由独立 CSV 提供，随机生成仅变动合法模板的非控制位，不调用 RTL 生成期望。

## 历史基线功能计数与需求对应

以下计数取最终种子 1 的 tb_summary.json；前递统计来自定向+约束随机组合样例，不包含 stub 内的每次前递。

| 功能 | 实际计数 |
|---|---:|
| A/MEM，A/WB 前递 | 4，4 |
| B/MEM，B/WB 前递 | 3，5 |
| Store/MEM，Store/WB 选择 | 3，5 |
| 定向 load-use 命中 | 7 |
| 人为不可消费 MEM Load 组合被识别 | 2 |
| BEQ/BNE/BLT/BGE/BLTU/BGEU | 每种 taken=1，not-taken=1，另有比较差异检查 |

| 需求 | 测试 ID/场景 | 实际结果与边界 |
|---|---|---|
| 37 指令全部字段、立即数类型 | decode_vector_0..36 | PASS；不等于完整 ISA 合规 |
| 项目 NOP 与非法 opcode/funct/M/shift/CSR/FENCE.I | decode_vector_37..54 | PASS；非法=安全字 0+内部标志，无 trap |
| MEM/WB、双源不同级、优先级、x0、无效级 | forward_0..15、random_forward_0..127 | PASS |
| MEM Load 不前递地址/不选旧 WB | forward_10/11 | PASS，检测 unready，未宣称可执行该输入状态 |
| rs1/rs2、SW 数据/地址、Branch/JALR 依赖及假相关 | load_use_0..15 | PASS；7 次真实暂停条件 |
| 连续 Load-use、数据与周期 | pipeline_load_use | PASS；LW=42，ADD=49，仅 1 stall，E 气泡/M 前进/WB 前递 |
| LW→SW | pipeline_load_store | PASS；写 91，仅 1 stall/1 Store |
| 最新同名写入、ALU→SW、WB→ID 可见 | pipeline_forward_store_and_WB_ID | PASS；Store 与 x6 都为 11 |
| 六种分支两结果，signed/unsigned 不同 | branch_*、signed_unsigned_differ | PASS |
| D/E 分支级别与有效性 | D_branch_does_not_control_E、invalid_E_branch | PASS |
| EX JAL/JALR 与 valid | jump_1/2 | PASS |
| 错误路径不提交 | pipeline_branch_flush | PASS；x7=0、Store=0、仅目标 x8 提交 |
| JAL 链接和目标消费者 | pipeline_JAL_link | PASS；x5=x6=4，错误 Store=0 |
| ALU→Branch 双源前递 | pipeline_ALU_branch_forward | PASS；A/B=MEM，目标写回，错误 Store=0 |
| ALU→JALR、最低位清零、链接 | pipeline_JALR_forward_mask | PASS；17→16，链接=8，错误路径无副作用 |
| 门控 reset > redirect > stall | reset_safety / arb_* | PASS；独立仲裁器强制双请求 |
| flush 高于 enable、运行中复位 | stub_flush_over_enable / runtime_reset_* | PASS；仅 TB 注入，生产模块无 force/层级依赖 |
| 支持域无 X/Z、reserved 输出、互斥、valid 限定 | invariants / step_link | PASS；未知非法输入域不声称已覆盖 |
| CNN 软件涉及的 LW/SW 与分支 | 译码、load-use/branch 场景 | PASS Control 部分；真实 MMIO 脉冲/STATUS 未测试 |

主 TB 还有约束随机前递状态，固定 xorshift32 种子，排除 MEM Load 尚未就绪的合法消费者；两个不合法组合另作显式定向负条件识别。

## 历史脚本、解析器与其他检查（2026-09-13）

| 检查 | 实际证据 |
|---|---|
| --test decode --seed 2，中文含空格结果路径 | [实际结果](../../../build/中文%20路径/20260913_111050_834589_decode_seed2/result.json)，PASS |
| --test load_use --waves --plot | [实际结果](../../../build/runs/20260913_111050_833586_load_use_seed1/result.json)，PASS |
| --test branch --waves --plot | [实际结果](../../../build/runs/20260913_111050_834589_branch_seed1/result.json)，PASS |
| 绘图轻量测试 | `python -m pytest -q tests/test_plot_waveforms.py`：12 passed；含多 timescale、X/Z、别名、常量、初始值、窗口继承/错误与缺失信号 |
| C 示例 | GCC `-std=c11 -Wall -Wextra -Werror -fsyntax-only`，退出 0；不等于目标交叉编译或 CNN 功能通过 |
| 不支持 mul_busy、继续收集模式 | [预期失败结果](../../../build/runs/20260913_111347_512713_reset_seed1/result.json)：34 检查、1 故意失败，脚本退出 1 |
| 全局周期超时 | [预期失败结果](../../../build/runs/20260913_111347_514714_decode_seed1/result.json)：MAX_CYCLES=2，cycle=3 TIMEOUT，脚本退出 1 |

子集入口回归在最终新增的 stub 优先级检查之前执行；最终完整回归包含该新增检查。负向结果不是产品功能失败，而是确认脚本不会误报成功。

## 图片和源 VCD

四张交付 PNG/SVG 已更新为 2026-09-14 D1 对齐后种子 1 运行的新产物，均已打开视觉检查。字标签可读、总线按离散区间显示、波形变化与周期检查一致。源文件：[本次 VCD](../../../build/runs/20260914_124846_374213_all_seed1/waves/cpu_control.vcd)。副本及哈希来源记录在 [figures/provenance.json](figures/provenance.json)。新增 D1 场景在原场景之后执行，下面四个窗口数值与历史基线相同，但源 VCD 为本次新文件。

| 场景 | 实际窗口（ns） | 图 |
|---|---|---|
| decode | 30.001..112.501 | [PNG](figures/decode.png) / [SVG](figures/decode.svg) |
| forwarding | 10582.501..10642.501 | [PNG](figures/forwarding.png) / [SVG](figures/forwarding.svg) |
| load_use | 12530.001..12600.001 | [PNG](figures/load_use.png) / [SVG](figures/load_use.svg) |
| branch_flush | 12920.001..13000.001 | [PNG](figures/branch_flush.png) / [SVG](figures/branch_flush.svg) |

图片展示短窗口；整次运行数据保存在 VCD。XSim 不导出未打包 imem/dmem/regs 数组，日志仅给信息提示，数据结果通过 TB scoreboard 检查；绘图所需标量与 packed 总线均存在。未用合成 fixture 代替交付波形。

## 未验证与接口状态

- 真实 cpu_datapath 未提供：真实命名/采样行为兼容性、真实 CPU 程序、真实 SRAM wrapper、CNN 双口 DMA、CNN 寄存器行为和识别结果均未运行。
- D1 原则接受 C1 端口/编码、安全 NOP 和逻辑控制方案；系统复位、RESET_PC、CNN_MMIO_BASE 及 IMEM/Data SRAM/MMIO 精确时序尚未三方冻结。
- FENCE 简化仅适用于当前有序无未完成访存假设；没有标准 trap、CSR、M 扩展、压缩/原子指令或可变延迟握手。
- Control 验证了所有 Load/Store 类型编码；stub 只做对齐 LW/SW，未验证字节拼接、符号扩展/未对齐异常的生产 LSU。
- Verilator lint、Icarus 后端实际执行、Linux 模拟器、FPGA 综合/资源/时序均未执行。不报告行覆盖、toggle coverage、无锁存器综合证明或完整 ISA 合规率。

收到真实 Datapath 后，按 [连接清单](datapath_connection_checklist.md) 接入并跑真实程序，才可在明确验证范围内更新兼容结论。
