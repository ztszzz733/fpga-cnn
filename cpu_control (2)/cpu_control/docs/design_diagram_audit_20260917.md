# 对用户所给架构图的设计核查（2026-09-17）

核查对象：本轮对话中的“Face-Recognition SoC — CNN Owner I/O Contract Revision”图，以及当前工程的生产 RTL、验证模型、驱动和接口文档。图片未作为本地原始文件归档；本报告依据对话中可见的图中文字与连接关系。原始设计输入、生产 RTL 和其他负责人的模块均未修改。

## 1. 判断

**CPU_CONTROL 已按图中的功能划分及已确认 C1 接口实现，现有验证未发现 Control 行为偏离；但当前工程不能认定为整张图的严格完整实现。**

原因有三类：

1. 图是功能架构图，当前接口按 C1 细化，端口名称、比较标志和部分辅助信号并非逐字照图。
2. 生产 Datapath、CNN、MMIO 寄存器硬件和 DMA 未出现在当前工程，不能用 test-only stub 替代验收。
3. 图左下角的完整人脸识别软件流程尚未实现；现有软件仅为单层 CNN 启动/轮询示例。

用户职责是 CPU_CONTROL，缺少其他负责人的生产模块不等于本方 Control 应自行补写这些模块。M 已正式接受 C1 v1.0，本方确认不是待办；三方共同归档及系统参数冻结仍未完成。

## 2. 逐功能块对照

| 图中要求 | 当前依据 | 判断及验证边界 |
|---|---|---|
| PC / Branch Control：PC 选择、写使能、重定向及年轻指令 flush | [branch_control.sv](../rtl/cpu_control/branch_control.sv)、[pipeline_control.sv](../rtl/cpu_control/pipeline_control.sv) | 已实现；EX 分支/JAL/JALR 决策，重定向清 IF/ID 与 ID/EX。目标地址和 JALR bit0 清零由 Datapath 完成，stub 已验证 |
| Hazard / Forward：RAW、load-use、A/B 前递 | [hazard_unit.sv](../rtl/cpu_control/hazard_unit.sv) | 已实现；MEM 非 Load 优先于 WB，valid/源使用/x0 限定，Load 数据依赖插一拍气泡；另有 EX Store 数据前递 |
| Main Decoder：寄存器写、访存、ALU 源、结果源 | [main_decoder.sv](../rtl/cpu_control/main_decoder.sv) | 已实现 D 级译码；类型、立即数和源使用等字段比图更详细 |
| ALU Decoder：funct3/funct7 到 4-bit ALUCtrl | [alu_decoder.sv](../rtl/cpu_control/alu_decoder.sv) | 已实现；检查完整 funct7，支持当前 37 条 RV32I 基线指令；M/CSR 等扩展未实现，图没有明确要求这些扩展 |
| Control Output / Pipeline Gating Matrix | [cpu_control.sv](../rtl/cpu_control/cpu_control.sv)、[pipeline_control.sv](../rtl/cpu_control/pipeline_control.sv) | 已实现；复位 > EX redirect > load-use > 正常；Control 组合逻辑，D 控制经 Datapath 流水后使用，前递为当前 EX 即时选择 |
| CNN Driver Control：配置后 start，轮询 done | [cnn_driver_example.c](../sw/drivers/cnn_driver_example.c) | 软件示例符合配置顺序；先写七个参数寄存器、再写 start，轮询 STATUS 并检查 error/超时。不应把图中此框解释为 Control 直接连接 STATUS 的硬件 FSM |
| 32-bit Harvard 五级 Datapath | [control_datapath_stub.sv](../tb/models/control_datapath_stub.sv)、[cpu_control_link_example.sv](../tb/integration/cpu_control_link_example.sv) | 只有测试模型：独立 IMEM/Data 数组和 F/D/E/M/W 行为。没有真实 Datapath；实际寄存器堆、ALU、LSU、流水寄存器、同步存储 wrapper 未验收 |
| CPU A / CNN B 双口 Data SRAM、DMA request/response | 生产 RTL 无对应模块；[memory_timing_contract.md](memory_timing_contract.md) 记录条件 | 未实现/未验证；stub 没有 CNN B 口、DMA、gnt/rvalid/rdata 或双口冲突模型 |
| 9 个 32-bit CNN 寄存器及固定 owner 端口 | 驱动结构体和 [cpu_control_interface.md](cpu_control_interface.md) | 偏移和软件布局符合；没有九寄存器硬件 bank 或 CNN owner 顶层，不能声称物理端口已接通 |
| CNN Scheduler / 地址计数器 / Loop Controller / Local SRAM / PE / Post-process / Output Buffer / Status Encoder | 当前生产 RTL 无 CNN 文件 | 未实现/未验证，属于 CNN 负责人范围 |
| 全局 clk/rst_n | Control 有 clk/rst_n，流水状态在 stub 上升沿同步复位 | CPU 侧契约已确认；Control 的 clk 不存状态。CNN 和全局分发复位未共同验收 |

## 3. 图上信号与实际接口

| 图上的名称/画法 | 当前实际信号/行为 | 差异性质 |
|---|---|---|
| PCSrc[1:0] | pc_sel[1:0]：00=PC+4、01=Branch/JAL、10=JALR | 名称不同、功能对应 |
| PCWrite / IFIDWrite | pc_en / if_id_en | 名称不同、功能对应 |
| FlushIFID / FlushIDEX | if_id_flush / id_ex_flush | 名称不同、功能对应 |
| StallIF / StallID | load-use 时 pc_en=0、if_id_en=0，同时 id_ex_flush=1 | 无独立 Stall 输出，用使能表达保持；不能省略 ID/EX 插气泡 |
| FwdA / FwdB | fwd_a / fwd_b；另有 fwd_store | C1 细化 Store 数据路径；前递先于 ALUSrc 和分支比较 |
| ALUSrc、RegWrite、MemR/W | alu_src_a_sel/b_sel、regwrite_d、memread_d、memwrite_d | D 级译码输出，须随指令流水；不能直接拿当前 D 级输出控制另一条 EX/MEM 指令 |
| ResultSrc[1:0] | wb_sel_d[1:0]：ALU / Load / PC+4 | 名称不同、功能对应 |
| ALU Z/LT 回送 | cmp_eq_e / cmp_lt_e / cmp_ltu_e | 比较接口细化为相等、带符号小于、无符号小于；由 Datapath 比较前递后的寄存器值产生，并非只使用普通 ALU 当前运算标志 |
| funct7[5] | ALU decoder 输入完整 funct7[6:0] | 合法性检查细化，避免仅凭 bit5 接受非法/M 扩展编码 |
| 图上简略流水元数据 | valid_d/e/m/w、EX rs/uses/branch/jump、memread_m 等 | C1 明确同一指令的阶段归属；当前顶层 26 输入、22 输出，共 48 个端口 |

以上属于已确认 C1 的接口细化。若“严格”指图上端口名称和线条必须一模一样，当前工程不是这种逐字复制；不能为追求图面一致而擅自改变已冻结 ABI。

## 4. CNN 九寄存器与软件流程

驱动使用九个 uint32_t 字段，STATUS 为 volatile const；布局有 offsetof/sizeof 静态断言。软件 const 只能限制 C 写法，真正只读仍须由硬件地址译码保证。

| 偏移 | 图中寄存器 | 当前软件 |
|---|---|---|
| 0x00 | CONTROL：bit0=start、bit1=reset | 启动时仅写一次 1；未提供 soft_reset 调用流程 |
| 0x04 | STATUS：bit0=busy、bit1=done、bit2=error | 位定义一致，检查 busy/error/done |
| 0x08 | INPUT_ADDR | 一致 |
| 0x0C | OUTPUT_ADDR | 一致 |
| 0x10 | WEIGHT_ADDR | 一致 |
| 0x14 | BIAS_ADDR | 一致 |
| 0x18 | IMAGE_SIZE：[31:16]height、[15:0]width | 打包一致 |
| 0x1C | CHANNELS：[31:16]out_ch、[15:0]in_ch | 打包一致 |
| 0x20 | CNN_PARAM：kernel/stride/padding/quant_shift | 接受调用者预打包参数；精确位域尚待 Z 冻结 |

图底部明确要求 start 是脉冲、done 粘滞到下一次 start/reset。当前代码只保证一次 CONTROL 写入，**不能证明硬件产生单周期脉冲，或 CNN 正确清除/保持 done**。图中 CONTROL 的 RW 标签不能单独证明可以保持 start=1，须结合底部脉冲说明落实寄存器语义。P1/驱动仍保留 Z 侧行为待冻结记录，属于图上目标尚未完成共同确认与硬件验证。

MMIO_BASE 由调用者传入，图没有给出完整基地址，当前未选址不构成已知地址偏差。DMA 地址和数据通路是九寄存器之外的独立接口，当前未实现。

驱动无 DB_ADDR、RESULT_ID、SCORE，符合图的接口限制。不过图左下四步流程只落实了第二步的单层调用部分：图片/权重/bias/数据库装载、网络层调度与输入输出缓冲交换、最终 embedding 读取、normalize + cosine similarity + argmax 均无完整实现。注释让调用者交换地址，不能作为已经实现多层调度的证据。当前也没有 RV32 目标编译/链接或该驱动在 CPU 上运行的验证。

## 5. 存储时序限制

当前 C1 没有 IMEM/MEM ready，也没有支持任意存储延迟的全流水保持机制。load-use 一拍成立需要 Load 数据在 M→W 沿前有效并正确进入 WB。真实同步 BRAM 若直到该沿才接受 M 地址，同沿不能获得新的读值，此时需要 wrapper 满足既有边沿契约或共同升级接口。

本轮模型是数组读取；图只说明 Harvard 和双口分工，未定义存储接受/返回沿，所以这一项应判为“待验证”，不能直接判为严格符合或已经不符合。

## 6. 本轮实际验证

默认 python 命中 DevEco 的 Python 3.8.10，规定入口在 argparse.BooleanOptionalAction 处退出，尚未开始 RTL 仿真。改用本机 py -3.11（Python 3.11.9）执行同一脚本后正常完成；未修改脚本或全局 Python 配置。

| 实际运行 | 结果 | 本轮证据 |
|---|---|---|
| py -3.11 scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot | PASS；1,244 场景、30,463 检查、0 失败；1,000 随机译码、128 随机前递状态 | [result.json](../build/runs/20260917_172556_764470_25128_all_seed1/result.json)、[compile.log](../build/runs/20260917_172556_764470_25128_all_seed1/compile.log)、[simulation.log](../build/runs/20260917_172556_764470_25128_all_seed1/simulation.log) |
| 同脚本 --test instruction --stage all --instruction 指定 CSV 中全部 55 个名字 --seed 1 --waves --plot | PASS；55 场景、1,265 检查、0 失败；含 37 条基线指令、3 个安全 NOP、15 个非法/不支持样例 | [result.json](../build/runs/20260917_172640_450856_15404_instruction_seed1/result.json) |

使用 Vivado XSim 2026.1；完整回归 compile.log 未检出 WARNING/ERROR/CRITICAL。两次均使用新的独立 build/runs 目录，生成本轮 VCD 与 PNG/SVG，没有使用历史波形代替。本轮已打开检查 [load-use](../build/runs/20260917_172556_764470_25128_all_seed1/figures/load_use.png) 与 [branch flush](../build/runs/20260917_172556_764470_25128_all_seed1/figures/branch_flush.png) 图，保持/插泡/WB 前递及错路冲刷可见。

两次测试的 real_datapath 均为 NOT_RUN: not provided。未运行生产 Datapath/CNN/MMIO/DMA、综合、FPGA 时序或上板测试；本轮未执行 C 编译。阶段测试是安全代表样例，不等于所有操作数/指令序列的完整 ISA 合规验证。

## 7. 发现的文档问题与接入条件

- [memory_timing_contract.md](memory_timing_contract.md) 尾部仍说 stub 只支持 LW/SW，且对齐约束不扩展其范围；当前 stub 已包含 LB/LH/LW/LBU/LHU 和 SB/SH/SW，应更新该现行描述。
- [verification_report.md](verification_report.md) 顶部已记录字节/半字模型补充，尾部又保留“字节/半字只验证译码”的旧限制，阅读时容易误判当前能力。本轮结果以第 6 节的新运行证据为准。
- 要完成图的系统级验收，需要其他负责人交付真实 Datapath/共享 package/同步存储 wrapper、九寄存器硬件 bank、CNN 顶层和独立 memory master；共同确认全局复位、系统地址、start/done 时序、CNN_PARAM 与数据格式，再验证 CPU 配置—启动—DMA—完成—读取结果流程。
- 要实现图左下的最终识别流程，还需要完整 CPU 软件和目标工具链；当前 RV32I 无硬件乘法不直接违背此图，但 embedding 相似度运算必须落实可运行的软件乘法或正式扩展方案。

本次只新增核查报告与仿真运行产物，保留上述现行文档问题供后续修订，没有改动冻结的 Control 实现。
