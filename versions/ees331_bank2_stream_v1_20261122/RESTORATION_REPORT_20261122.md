# 2 bank 连续读写恢复版：功能与整机资源报告

日期：2026-11-22。基于 GitHub `zhang@b165edc176e14a51c57f4937a7681cd510974c68`，最终可审阅源码位于 `project/`。基准源码、两项 DMA 中间版本和每轮综合证据均独立保留。发布版本：`ees331-bank2-stream-v1-20261122`，目标分支 `bai-datasram`。

## 已实施

1. DMA↔bank：本地请求与响应分开计数，最多四笔有序在途；同步暂存与寄存输出保留。填页连续写入、写回连续读取，完成前等待所有本地响应及返回寄存器排空。
2. bank→DDR：当前数据被接收的同拍同步读取下一拍数据；遇背压保持输出，16 拍 burst 可以连续发送。
3. CNN↔bank：每单元四槽有序读缓冲，只在算子报告的连续地址范围内提前读取；读写切换或中止时排空旧请求。每单元增加两项输出写队列，外部写在途最多四笔。任务完成等待所有排队及已接受写入返回响应。

最终返回路径额外寄存地址匹配结果与数据，避免地址判断直接进入算子完成控制。K3/K1 的计算流水、K1 单输出通道、K3×2＋K1×2、392 KiB、2 bank、单 MOVER 和单 HP0 均按当前简化版配置；没有新增 DDR 下一页预取或全局 392 位预取标记。引擎旧 READ_AHEAD 参数仍为 0，新的四笔读取由独立桥接器和 read_beats 边界信号实现。

生产修改共 5 个文件：

- `source/storage_v2/rtl/data_mover.sv`
- `simple_cnn/rtl/simple_k3_engine.sv`
- `simple_cnn/rtl/simple_k1_engine.sv`
- `simple_cnn/rtl/simple_mem_bridge.sv`
- `simple_cnn/rtl/cnn_simple_top.sv`

## 整机 PL 综合

Vivado 2025.2，xc7z020clg484-1，完整 `face_soc_ees331_simple_top`；包含 CPU、ROM、16 KiB 数据 RAM、CNN、分页器、共享 RAM、DMA、控制桥及复位。PS 硬核以外部 AXI 接口接入，无未解析黑盒。全部版本使用同一份 ROM、同一 10 ns 时钟约束，以及 rebuilt、no_iobuf、max_bram_cascade_height=1。

| 版本 | LUT | FF | BRAM Tile | DSP | 综合 WNS/ns |
|---|---:|---:|---:|---:|---:|
| baseline | 26,451 | 21,911 | 118 | 16 | -0.685 |
| stage1_local_stream | 26,529 | 21,878 | 118 | 16 | -0.685 |
| stage2_axi_stream | 27,032 | 21,986 | 118 | 16 | -0.357 |
| stage3_cnn_stream | 28,652 | 22,408 | 118 | 16 | -0.078 |

最终使用 **28,652 LUT**，比基准增加 **2,201**；LUT 上限 53,200，剩余 24,548。BRAM 上限 140、使用118，剩余22；DSP上限220、使用16。各阶段资源均未超限。最终综合 WNS **-0.078 ns**，仍未完成 100 MHz 时序收敛。外部 AXI 端口尚无输入/输出延迟预算，没有布局布线或上板结果。

第三阶段首次候选的 WNS 为 −1.210 ns，原始报告和当时源码哈希保留于 `evidence/synthesis/initial_stage3/`；最终交付采用补充返回寄存后的 `evidence/synthesis/final/`。

## 仿真结果

同一 Verilator 5.050 / g++ 原生工具链；数值参考由测试程序独立计算。性能均为相同测试条件下的仿真拍数，没有换算为实板性能。

| 1 KiB 搬运，DDR无压力、本地1拍应答 | 基准 | 阶段1 | 阶段2及最终DMA |
|---|---:|---:|---:|
| 填页周期 | 1,211 | 467 | 467 |
| 写回周期 | 1,059 | 579 | 459 |
| 最长本地连续接收 | 1 | 32 | 32 |
| 最长DDR写连续接收 | 1 | 1 | 16 |

DMA 同条件每版82项均PASS，包括双方向、随机背压、1/2/5/9拍响应、两个bank边界、首末页、字节护栏、非法命令、AXI/本地错误、超时排空和恢复。阶段1、2另分别通过原有392 KiB两bank分页器回归，覆盖401页脏淘汰、替换回绕、字节写、fence、invalidate、取消、错误恢复和并发驻留页访问。

- CNN：160个数值任务、4个非法描述符、4个中止/重启单元均PASS，另有12项K1地址区间检查PASS。基准 **305,228拍** → 最终 **202,092拍**，减少 **33.79%**。使用同一支持每客户端四笔有序在途的测试模型；相较上游单笔模型，随机数调用时序有所变化，因此与上游旧报告305,843拍不直接比较。
- 专用桥接器10组PASS：零/延迟回复、四笔读取、读写切换、写队列、背压、保持请求时中止、迟到回复和重启。
- **真实 CNN＋2 bank 缓存＋DMA＋DDR 模型集成**：两批，每批四个并发算子，共8任务，覆盖普通K3、DW3、K1、非对齐/奇数通道及两批数据复用。经fence后全部输出逐字节匹配独立参考，输出FNV64为 `9d45ac45582e4ae6`，两版DDR读/写同为32768/14336字节。
- 集成工作区间（从提交任务至fence后DDR结果可见，累加两批）：**83,550拍 → 37,745拍**，减少 **54.82%**；实际外部在途峰值4→16。这是小任务夹具，不能推断112×112整图、完整网络或五图性能。

本轮没有运行旧ROM/ARM调度的完整CPU软件整机仿真。该简化版的MMIO不兼容、缺少Post/Add/Pad的边界仍在，完整网络集成需另行适配。

## 运行控制与交付

仿真硬上限30秒，编译外层上限240秒；综合硬上限420秒，每20秒记录日志字节及进程树CPU活动，连续90秒日志与CPU均无进展即终止进程树。本轮各项运行均正常结束，没有触发停滞/超时中断。

- 最终源码：[project](project/)，源码哈希清单：[source_manifest.json](project/source_manifest.json)。
- 最终整机证据：[资源](evidence/synthesis/final/utilization.rpt)、[层级](evidence/synthesis/final/hierarchy.rpt)、[时序](evidence/synthesis/final/timing.rpt)、[最差路径](evidence/synthesis/final/paths.rpt)、[网表](evidence/synthesis/final/soc_synth.dcp)。
- [机器可读结果](RESTORATION_RESULTS.json)、[生产RTL差异](restore_streaming.patch)。
- 原始测试记录均在 `evidence/simulation/<版本>/<测试>/`；限时入口为 `scripts/run_bounded.py`，编译入口为 `scripts/build_test.py`。
