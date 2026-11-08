# 当前23算子CNN资源统计

**结论：尚未取得完整CNN总数。** 已测22个算子的独立报告相加为48,869 LUT（器件容量91.86%）、30,189 FF（28.37%）、112 BRAM Tile（80%）、49 DSP（22.27%）；未计入DW7和控制/仲裁。不能再用只统计卷积的42,200 LUT判断“资源充足”。这是分模块相加，不是整体映射后的资源下限或精确总量。

本次没有修改功能RTL、没有重跑图片仿真。所有综合进程已结束；失败记录与日志保留。首要确定阻塞是leases.hold和use_owners当前存储写法无法推断RAM；其次还有若干模块受本机内存/限时约束未完成。先改可综合的任务表结构、再衡量算子数量，比继续直接扩容更合适。


生成时间：2026-10-25T18:04:11.760057。Vivado 2025.2，器件XC7Z020-CLG484-1，10ns时钟约束，仅综合，未布局布线。

## 统计范围

与完整15图PASS的参数一致：K3×4（每核4空间MAC）、K1×12（PW8）、Post×4、Add/DW7/Pad各1，15图片上下文、2048任务容量、60缓冲槽。复用卷积单核报告前已核对当前源文件哈希；其余模块此次逐个综合。未修改功能RTL或重新跑全网仿真。

整体顶层为self_fixed_network_top。第一次整体综合触发电脑可用物理内存低于1.5GiB的保护，终止该任务及其子进程，状态MEMORY_GUARD，不是整体综合PASS。随后逐模块统计。**下表是独立综合结果按实例数相加，不能当作整体布局布线的精确数值。** 顶层常量传播、端口裁剪及跨层优化会改变数量；保留的调试计数器也计入单核。

共享64MiB SRAM仅在综合临时副本中把datasram_tdp_bank存储体标为黑盒，保留原23客户端仲裁、地址宽度和接口。算子内部RAM照常计入。没有把64MiB偷偷缩小成片内RAM，也没有实现DDR控制器。当前已验证入口不含CPU、IMEM、UART、板级时钟；仓库旧SoC入口没有接入这个23算子顶层，不能冒充整机资源。

## 完整模块清单

| 模块 | 数量 | LUT合计 | FF合计 | BRAM Tile合计 | DSP合计 | 结果 |
|---|---:|---:|---:|---:|---:|---|
| 3×3 / DW3卷积 | 4 | 9,800 | 6,500 | 40 | 0 | PASS |
| 1×1 PW8卷积 | 12 | 32,400 | 18,636 | 60 | 0 | PASS |
| 后处理（GROUP_BYTES=16） | 4 | 4,996 | 3,808 | 10 | 32 | PASS |
| 残差Add（GROUP_BYTES=16） | 1 | 1,229 | 944 | 2 | 8 | PASS |
| DW7（8通道） | 1 | 未取得 | 未取得 | 未取得 | 未取得 | TIMEOUT |
| 补边Pad | 1 | 444 | 301 | 0 | 9 | PASS |
| 4-bank / 23客户端存储仲裁 | 1 | 未取得 | 未取得 | 未取得 | 未取得 | MEMORY_GUARD |
| 任务调度器（2048项） | 1 | 未取得 | 未取得 | 未取得 | 未取得 | MEMORY_GUARD |
| 缓冲区生命周期管理（60槽） | 1 | 未取得 | 未取得 | 未取得 | 未取得 | FAIL |
| 结果交接（60槽） | 1 | 未取得 | 未取得 | 未取得 | 未取得 | MEMORY_GUARD |
| 固定网络模板展开（512步） | 1 | 未取得 | 未取得 | 未取得 | 未取得 | MEMORY_GUARD |
| **已测模块算术合计** | — | 48,869 | 30,189 | 112 | 49 | 非整体综合总量 |
| **其中已测算子小计** | — | 48,869 | 30,189 | 112 | 49 | 未完成算子不计入 |
| **XC7Z020容量** | — | 53,200 | 106,400 | 140 | 220 | 器件报告 |

BRAM Tile按36Kb块等效计，0.5表示一个18Kb块。LUT、FF、BRAM、DSP是不同资源，不能彼此直接相加。

状态说明：PASS仅表示该模块综合和报告生成完成，不代表整机可放置或10ns时序通过；MEMORY_GUARD表示电脑可用物理内存低于1.5GiB而中止，不是FPGA资源超限判定；TIMEOUT表示480秒内未完成；FAIL表示工具给出具体综合错误。超时/保护时终止该运行的进程树，没有把未完成报告作为成功数值。

## 当前还不能给出的数字

未完成模块：DW7（8通道）、4-bank / 23客户端存储仲裁、任务调度器（2048项）、缓冲区生命周期管理（60槽）、结果交接（60槽）、固定网络模板展开（512步）。这些项不能填0。上述已测合计不是全SoC总量，也不证明100MHz上板能过时序。

## 大任务容量的额外代价

以下是源码声明容量，不是最终映射LUT/FF数量：

| 表/数组 | 当前规模 | 声明容量 |
|---|---:|---:|
| leases.hold任务保持表 | 2048×2048 bit | 512 KiB |
| leases.pending活动槽保持掩码 | 60×2048 bit | 15 KiB（122,880 bit） |
| dispatch.commands | 2048×512 bit | 128 KiB |
| fixed_program.cmds | 512×512 bit | 32 KiB |
| fixed_program.holds | 512×512 bit | 32 KiB |

这批设计为有限多图仿真保留了较大的可编程任务表。异步读取、宽掩码和并行比较可能映射成分布式RAM、寄存器和大量选择逻辑，不能假设会自动成为紧凑BRAM。尤其pending还逐槽并行检查整个任务完成掩码。进一步优化应优先考虑稀疏依赖编号/消费者计数、较小循环任务窗口、同步BRAM任务表，而不是直接复制更多算子；这些改动本次没有实施。

64MiB实验共享存储与器件全部140个36Kb块的630KiB原始容量相差约104倍；630KiB还包含奇偶位，且不能全部留给共享存储。现有实验布局需外部存储及控制器，或重新规划片内分块/复用容量，不能据本表宣称直接上板。

## 可追溯报告

- 3×3 / DW3卷积：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_155929_013040_self_cnn_synth/result.json>)；[资源报告](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_155929_013040_self_cnn_synth/utilization.rpt>)
- 1×1 PW8卷积：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261024_012253_161051_self_cnn_synth/result.json>)；[资源报告](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261024_012253_161051_self_cnn_synth/utilization.rpt>)
- 后处理（GROUP_BYTES=16）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174414_589056_pool_resources_post/result.json>)；[资源报告](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174414_589056_pool_resources_post/utilization.rpt>)
- 残差Add（GROUP_BYTES=16）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174506_017163_pool_resources_add/result.json>)；[资源报告](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174506_017163_pool_resources_add/utilization.rpt>)
- DW7（8通道）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174624_483215_pool_resources_dw7/result.json>)；[日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174624_483215_pool_resources_dw7/process.log>)
- 补边Pad：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175428_174033_pool_resources_pad/result.json>)；[资源报告](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175428_174033_pool_resources_pad/utilization.rpt>)
- 4-bank / 23客户端存储仲裁：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175608_695778_pool_resources_fabric/result.json>)；[日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175608_695778_pool_resources_fabric/process.log>)
- 任务调度器（2048项）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175659_663862_pool_resources_dispatch/result.json>)；[日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175659_663862_pool_resources_dispatch/process.log>)
- 缓冲区生命周期管理（60槽）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175800_617034_pool_resources_leases/result.json>)；[日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175800_617034_pool_resources_leases/process.log>)

```text
ERROR: [Synth 8-3391] Unable to infer a block/distributed RAM for 'hold_reg' because the memory pattern used is not supported. Failed to dissolve the memory into bits because the number of bits (4194304) is too large. Use 'set_param synth.elaboration.rodinMoreOptions {rt::set_parameter dissolveMemorySizeLimit 4194304}' to allow the memory to be dissolved into individual bits
ERROR: [Synth 8-3391] Unable to infer a block/distributed RAM for 'use_owners_reg' because the memory pattern used is not supported. Failed to dissolve the memory into bits because the number of bits (67584) is too large. Use 'set_param synth.elaboration.rodinMoreOptions {rt::set_parameter dissolveMemorySizeLimit 67584}' to allow the memory to be dissolved into individual bits
ERROR: [Common 17-69] Command failed: Synthesis failed - please see the console or run log file for details
```

- 结果交接（60槽）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175823_028191_pool_resources_results/result.json>)；[日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_175823_028191_pool_resources_results/process.log>)
- 固定网络模板展开（512步）：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_180208_206018_pool_resources_programmer/result.json>)；[日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_180208_206018_pool_resources_programmer/process.log>)

- 整体综合中止记录：[result.json](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261025_174301_396810_pool_resources_full/result.json>)。
- summary.json保存参数、每项资源、报告哈希与原始结果路径。
