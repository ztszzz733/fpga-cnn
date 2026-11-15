# EES331：23 算子接入 DDR 的替代调度配置资源报告

日期：2026-11-09。整合分支：`bai-ees331-integration-20261109`（基于 `moon`，合入当时最新 `zhang`）。目标器件：`xc7z020clg484-1`，Vivado 2025.2。

**结论范围纠正：本报告不是原 15 帧、2048 任务、60 槽设计的资源报告。原设计的 `stream_buffer_leases` 综合失败，未产生可用的最终映射资源数；不能用下文紧凑调度配置的 88,758 LUT 等数值推断它的占用。**本报告只量化 23 算子与 DDR/cache 接入后的另一个 4 帧实现，用于判断该替代配置在 XC7Z020 上的容量风险。

## 配置与边界

本次综合的是 `face_soc_ees331_top` 的 `POOL23=1` 配置：4 个 K3 空间四路卷积、12 个 PW8、4 个 Post16、1 个 Add16、1 个 DW7、1 个 Pad，共 23 个 CNN 访存客户端。23 路均接到 `datasram_ddr_subsystem` 的共享 cache 和 AXI3 HP0 桥。cache 为 128 KiB；CNN 逻辑地址窗口设为 64 MiB，物理 DDR 基址为 `0x10000000`。CPU 保留 16 KiB 本地 RAM 和 8 KiB IMEM。

为避开 `zhang` 的 2048×2048 bit `stream_buffer_leases.hold` 无法综合的问题，23 路算子接入 `moon` 的 `fixed_schedule_compact`，综合路径不使用原大任务表。**这不是对原 15 帧、2048 任务、60 槽控制器的修复**：现接线仍为 4 帧、256 步模板、16 槽。原 15 图完整网络仿真曾在 64 MiB 仿真 SRAM 上通过；本次没有在 DDR/cache 路径上重做该测试，不能把旧结果移植为 DDR 版的功能结论。

原控制器已知的是 RTL 声明容量，而非最终 FPGA 占用：`hold` 为 2048×2048 bit，即 512 KiB；`pending` 为 60×2048 bit，即 15 KiB；`use_owners` 为 2048×33 bit，约 8.25 KiB。这些位可能映射到 BRAM、LUTRAM、FF 或被优化，原综合在映射前失败，无法从声明容量换算出可信的 LUT/BRAM/FF 数量。要回答原设计的资源问题，必须保持 15 帧等参数不变，修复其表结构或等价实现，再对同一 DDR 顶层重新综合。

Vivado 使用 `EES331_EXTERNAL_PS` 以端口表示 PS7 的 GP0/HP0，`-no_iobuf` 防止这些片内 AXI 信号被当成板级 I/O。报告统计完整 PL 侧 CPU、CNN、控制桥、cache、AXI 桥和本地存储；PS7 硬核、PS 端软件及真实 DDR 器件不占 PL LUT/BRAM，未包含在此数字中。固件 `program.mem` 已成功读入。综合未加板级时钟/接口时序约束，未布局布线。

## 整机 PL 资源

| 资源 | 综合用量 | XC7Z020 可用 | 使用率 | 结论 |
|---|---:|---:|---:|---|
| Slice LUT | 88,758 | 53,200 | 166.84% | 超出 35,558 |
| 其中逻辑 LUT | 71,754 | 53,200 | 134.88% | 单靠改善存储映射仍不够 |
| 其中 LUTRAM | 17,004 | 17,400 | 97.72% | 余量很小 |
| FF | 47,890 | 106,400 | 45.01% | 未超额 |
| BRAM tile（36 Kb 等效） | 133 | 140 | 95.00% | 仅余 7 tile |
| DSP48E1 | 61 | 220 | 27.73% | 未超额 |

最终 BRAM 由 79 个 RAMB36E1 和 108 个 RAMB18E1 组成，按 tile 折算为 133。Vivado 在映射前曾提示 BRAM 需求 337、器件可用 280（其内部 BRAM 计量单位），随后尝试用 LUTRAM 实现超出部分；因此最终 133 tile 不能解读为存储充足。`-no_iobuf` 下 IOB 使用为 0，不能据此推断板卡实际引脚情况。

| 层级 | LUT | FF | RAMB36 | RAMB18 | DSP |
|---|---:|---:|---:|---:|---:|
| CNN 与紧凑调度器 `u_cnn` | 79,438 | 42,109 | 47 | 108 | 61 |
| DDR/cache 子系统 `u_datasram` | 5,809 | 3,031 | 32 | 0 | 0 |
| CPU `u_cpu_core` | 2,349 | 1,739 | 0 | 0 | 0 |
| 图像控制桥 `u_image_bridge` | 1,175 | 979 | 0 | 0 | 0 |

分层数值来自 Vivado 分层报告；受层级重建、共享逻辑和显示取整影响，分层行不用于代替顶层汇总。CNN 内部较大的条目为 DW7 12,972 LUT（含 4,704 LUTRAM）、每个 PW8 约 2,700–2,800 LUT、每个 Post/Add 约 3,100–3,200 LUT，紧凑调度本体约 5,874 LUT。完整逐实例数值见原始分层报告。

## 结论与下一步

本配置**通过 RTL 展开和 Vivado 综合，但不能直接放进 XC7Z020**。逻辑 LUT 自身已超器件容量 18,554；即使把所有 LUTRAM 都改成 BRAM，当前逻辑规模仍过大。BRAM 已接近满额，片内存储重排也需要与算子数量一并考虑。下一轮应优先减少同时实例化的 PW8/Post 数量、复用计算单元，并检查 DW7/Post 的 LUTRAM 映射；之后再重新综合整机。仅减小 cache 容量不能解决逻辑 LUT 超额。

23 客户端共享的现有 cache 全局一次只处理一笔请求。即使未来资源缩到可放入器件，DDR 版吞吐也不能按原 4-bank SRAM 仿真的 15 图结果推算。要评估性能，还需对应的 DDR/cache 仿真与带板级约束的实现。本次没有进行功能仿真、布局布线或上板测试。

## 验证与原始证据

- 23 路与原 10 路配置均通过 Verilator 顶层 lint；`scripts/check_ees331_wiring.py` 对原图 128 个信号的命名和连接检查通过。
- Vivado `synth_design` 成功，0 个综合错误；日志确认 `program.mem` 成功读入。`test_compact_cnn.py` 未能运行：仓库脚本把 MSVC 路径固定为本机不存在的 `D:/visual studio2`，实际 Visual Studio 位于 `D:/VIsual Studio/visual studio 2022`。因此未把该测试记为通过；后续仿真阶段需要修正启动脚本的工具路径。
- [完整资源表](../build/pool23_pl_synth_corrected/utilization.rpt)、[分层资源表](../build/pool23_pl_synth_corrected/utilization_hierarchical.rpt)、[综合日志](../build/pool23_pl_synth_corrected/vivado_console.log)、[综合状态](../build/pool23_pl_synth_corrected/synth_status.txt)、[时序报告](../build/pool23_pl_synth_corrected/timing_summary.rpt) 和 [综合 checkpoint](../build/pool23_pl_synth_corrected/ees331_pool23_pl.dcp) 保存在本地 `build/pool23_pl_synth_corrected/`。时序报告缺少时钟约束，不能用于判断 50 MHz 是否达标。

复现脚本：[synth_ees331_pool23_pl.tcl](../scripts/synth_ees331_pool23_pl.tcl)。在不含括号的工作目录启动 Vivado；脚本会把 ROM 文件暂存到运行目录下的 `firmware/ees331_cpu/program.mem`，因为 Vivado Windows 并行子进程在带括号的当前目录会启动失败。首次综合因为 ROM 相对路径未找到而缺失 CPU，已作废；本报告只采用 `pool23_pl_synth_corrected`。
