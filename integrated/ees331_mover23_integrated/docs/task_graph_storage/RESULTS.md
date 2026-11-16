# 任务图存储路径阶段结果（2026-11-16）

## 功能

`simulation/scripts/run_task_graph_queue_test.ps1` 与 `simulation/scripts/run_task_graph_storage_test.ps1` 均通过。AXI3 压力模型覆盖 DDR 逻辑地址和显式本地地址混用、四 bank 同拍服务四个客户端、显式 LOAD/STORE、脏页同步与失效、DMA 中访问不同本地缓冲、DMA 中访问非相交的 DDR 驻留页、跨 4 KiB、尾字节、对齐/越界/只读、完成事件背压、AXI 读错、超时、迟到响应排空与恢复。测试日志由脚本生成在 `simulation/build/task_graph_storage_test/simulation.log`。

## 同条件综合资源

两个配置均从本目录同一份 RTL 与文件表综合，器件为 `xc7z020clg484-1`，Vivado 2025.2，时钟约束 10 ns，`-flatten_hierarchy rebuilt -no_iobuf`。`legacy` 是 392 KiB 原分页缓存加原始 MOVER；`plan` 是 64 KiB 分页缓存、328 KiB 显式本地窗口加同一原始 MOVER。

| 指标 | legacy | plan | 变化 |
|---|---:|---:|---:|
| Slice LUT | 57,516 | 48,205 | -9,311（-16.2%） |
| Slice FF | 38,283 | 31,748 | -6,535（-17.1%） |
| BRAM tile | 137 / 140 | 137 / 140 | 0 |
| DSP48E1 | 24 | 24 | 0 |
| 综合后 WNS，10 ns 约束 | -27.282 ns | -27.446 ns | -0.164 ns |

plan 的 LUT 占用 90.61%，legacy 为 108.11%；BRAM 两者均占 97.86%。WNS 是综合后估计，两者都未达到 10 ns，尚无布局布线后时序结论。两份报告的最差路径都起于 CNN 后处理、终于 CNN 计算引擎；这不能证明存储侧所有路径已经收敛。报告可用 `simulation/scripts/synth_task_graph_soc.tcl` 重建于 `simulation/build/task_graph_synth_legacy/` 与 `simulation/build/task_graph_synth_plan/`。

## 短场景性能

同一 AXI3 延迟/争用模型、同一 4 KiB LOAD 和 512 次本地读取：

| 执行方式 | 完成周期 |
|---|---:|
| 先 LOAD，后读取 | 3,816 |
| LOAD 与非冲突缓冲读取重叠 | 2,280 |

减少 1,536 周期，约 40.3%。这是同一新硬件上的存储短场景，只验证重叠能力；不能作为相对旧分页整机版本的网络加速比。混用地址的较长功能测试记录了 1 个明确的本地计算/DMA 重叠周期、3,123 个显式 DMA 忙周期、HP0 实际读 8,489 B/写 1,032 B（其中显式命令读 5,417 B/写 8 B）。

## 仍待整机验证

CNN 计划执行器尚未接入任务图命令与完成端口；软件的约 50 任务分支/汇合计划和两帧交错场景也尚未提供。因此没有同任务图的整网速度与整数结果比较。当前默认 64 KiB 分页缓存位于物理 bank 0；实际混用负载若大量使用 DDR 逻辑地址，缺页和 bank 冲突可能抵消本地窗口的收益。分区比例应以真实计划的访问轨迹复测。CPU 命令/事件寄存器地址和 PS DDR 保留区也需由相应接口方统一；RTL 当前默认 DDR 合法范围 16 MiB。
