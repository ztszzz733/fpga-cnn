# EES331 4 bank 缓存侧独立交付

日期：2026-11-15。共同对照为 `bank1_ref/`（已有命中流水、缺页期间服务驻留页的单 bank 版本）；候选为 `optimized/`。两者来自同一 GitHub `zhang` 分支提交 `695c5a9de38f4d9408530c1c1877661f93129ffb`，并包含先前 `cnn_paged_mover.patch`。本报告衡量的是**在先前单 bank 优化基础上，4 bank 缓存侧的增量效果**。

## 改动与接口

- `rtl/cnn_ddr/cnn_paged_mover.sv`：保留 392 个 1 KiB 全相联页槽；按 bank 轮转分配物理槽。每 bank 独立仲裁一个 32 位计算请求，持有请求者标签和返回流水。每客户端的页槽命中寄存器加速驻留页访问；页表查找和轮转仲裁用平衡树，避免长优先链。缺页只锁定目标槽，其余驻留页继续服务。
- `storage_v2/rtl/tile_local_ram_bank4.sv`：把现有 392 KiB RAM 分成 96/96/100/100 KiB 四个计算 bank，各保留一条计算口和一条 DMA 口；对 DATA MOVER 仍呈现单条 32 位线性 DMA 接口。物理本地地址范围依次为 `0x00000–0x17FFF`、`0x18000–0x2FFFF`、`0x30000–0x48FFF`、`0x49000–0x61FFF`。相同字的计算/DMA 冲突沿用计算优先、DMA 背压语义。
- `rtl/filelists/system_ees331_reduced.f`：登记新增 RAM 适配模块。`storage_v2/rtl/data_mover.sv` 未改动，SHA256 与 `bank1_ref/` 一致：`4E252CC931020236EE159DE8E6B69A42329C36FCFEDFAA54EF24B0F2A603D216`。本侧没有新增 DSP 运算或 BRAM 容量。

生产 RTL 补丁是 `bank4_changes.patch`，相对于 `bank1_ref/`，仅包含以上三个文件；已用 `git apply --check` 验证可应用。对接规则仍见 `BANK4_DATA_MOVER_HANDOFF.md`。

## 同条件仿真

Verilator 5.050，同一 RTL 之外的测试程序、仿真 DDR 模型、输入与期望输出。周期为仿真时钟周期；100 MHz 只用于参考吞吐换算，**不代表板级已满足该频率**。

| 场景 | 单 bank 参考 | 4 bank 候选 | 说明 |
|---|---:|---:|---|
| 四客户端独立驻留页，合计 2048 次 32 位写 | 2051 周期 | 1536 周期 | 减少 25.11%，吞吐 1.335 倍 |
| 四客户端独立驻留页，合计 2048 次 32 位读 | 2051 周期 | 1536 周期 | 减少 25.11%，吞吐 1.335 倍 |
| 同拍实际接收的独立页请求峰值 | 1 笔 | 4 笔 | 读、写阶段各有 512 个四笔接收周期 |
| 单客户端驻留页 512 次读 | 1536 周期 | 1536 周期 | 单客户端循环速度保持一致 |
| 四客户端共享同一页 2048 次读 | 2050 周期 | 2050 周期 | 同 bank 仍受单计算口限制 |
| 单帧真实 CPU/CNN/DDR，3 个任务 | 336539 周期 | 336439 周期 | 少 100 周期，输出一致 |
| 四帧真实 CPU/CNN/DDR，12 个任务 | 685168 周期 | 645255 周期 | 少 39913 周期（5.83%），1.062 倍 |
| 3 槽反复换页与错误恢复压力测试 | 40800 周期 | 40931 周期 | 增加 131 周期（0.32%） |

独立页读写测试先为每客户端预热一页；每阶段 512 次/客户端。4 bank 候选在四个 bank 各接收一笔的周期之后，仍因客户端每次等待回复再发下一笔而存在空拍，因此持续吞吐约为每拍 1.333 笔 32 位请求，而不是每拍 4 笔。按 100 MHz 仿真参考时钟换算，独立页读/写为约 `399.4→533.3 MB/s`。独立页测试的 DDR 总读写量两版同为 5120/5120 字节；清刷后逐字节校验一致。

四帧夹具完成 12 个任务、校验 49152 字节中间结果，DDR 读取 68608 字节、写入 53248 字节，两版完全相同；输出 SHA256 均为 `c0e899fefd789691c2bc87d204ac6b8546f4f86bca7a8b926f90542304bb121b`。四帧输入到 DDR 结果可见的延迟为 `326604→308779`、`331799→314004`、`611684→572748`、`616854→576786` 周期。单帧输出 SHA256 两版也一致。RAM 专项仿真覆盖四端口同拍、首末字、bank 边界、线性 DMA、同字冲突重试和越界；换页回归覆盖脏页写回、字节使能、清刷、失效、取消、突发错误与恢复。

## Vivado 2025.2 综合

器件 `xc7z020clg484-1`；相同 `synth_design` 及 10 ns 时钟约束。下表为**缓存+原 DATA MOVER 独立模块**的综合值，不能直接当作全 SoC 布局布线结果。

| 指标 | 单 bank 参考 | 4 bank 候选 | 差额 |
|---|---:|---:|---:|
| Slice LUT | 18487 | 21425 | +2938 |
| Slice FF | 11082 | 12190 | +1108 |
| RAMB36 等效 | 98 | 98 | 0 |
| DSP | 0 | 0 | 0 |
| 10 ns 综合后 WNS | -102.504 ns | -17.953 ns | 改善 84.551 ns，仍未满足 |

平衡页表查找与并行仲裁树将关键路径逻辑级数从单 bank 参考的 182 级降到 34 级。独立模块综合仍有 `-17.953 ns` 最差裕量，且该独立顶层有大量未约束的外部 AXI/CNN 端口；不能把仿真参考 100 MHz 当成可实现的板上频率。需要用完整 PL 顶层和正式约束做资源与布局布线验收。当前 4 bank 性能数字是**周期收益**，实际运行时间还取决于最终可达到的频率。

已补做**完整 PL 顶层**同条件综合：`face_soc_ees331_mover_top`、`POOL23=1`、外部 PS 接口、`-no_iobuf`，两版使用同一份 8 KiB 测试 ROM 初始化文件和 10 ns FCLK 约束。Vivado 综合成功，未出现 ROM 缺失关键告警。

| 完整 PL 指标 | 单 bank 参考 | 4 bank 候选 | 器件限额 |
|---|---:|---:|---:|
| Slice LUT | 54980 | 57516（+2536） | 53200 |
| Slice FF | 37254 | 38283（+1029） | 106400 |
| BRAM36 等效 | 137 | 137 | 140 |
| DSP | 24 | 24 | 220 |
| 10 ns 综合后 WNS | -59.494 ns | -27.282 ns | ≥0 ns |

单 bank 参考版已超出 LUT 限额 1780 个；4 bank 新增 2536 个，使候选共超出 4316 个。因此**不能把全部超限归因于 4 bank**。层级报告中 `u_datasram` 从 17292 增至 18809 LUT；`u_cnn` 从 34575 增至 35723 LUT，虽然 CNN 源码未修改。由于两版使用 `-flatten_hierarchy rebuilt`，跨模块逻辑重映射会改变层级归属，不能将层级差额逐项视为新增 RTL 的精确门数。结构上，增量主要来自四套计算口的 bank 仲裁、地址/数据选择、响应流水及 DMA 地址分发；页槽仍为 392 个，故 BRAM 数量没有增加。功能仿真通过，但当前综合结果**尚不能直接作为可上板版本**；仍未进行布局布线。完整 PL 原始报告分别在 `bank1_ref/build/small_soc_pl_synth/` 和 `optimized/build/small_soc_pl_synth/`。

## 集成边界与复现

本报告只验证 4 bank 缓存侧；`mover_side/candidate/` 的 DATA MOVER 改动尚未合入 `optimized/`。应在独立副本合并两份补丁，按交接文档验证 A/B/C/D 四组结果，尤其检查四帧吞吐、bank 冲突和最终资源/时序。当前可用夹具是单帧 3 任务、四帧 12 任务；未取得完整网络单帧 129 任务夹具，不能将短测收益外推到整图。

在本目录运行：

```powershell
.\run_bank4_ram_test.ps1
.\run_storage_bench.ps1 bank1_ref mixed
.\run_storage_bench.ps1 optimized mixed
.\run_storage_bench.ps1 bank1_ref pressure
.\run_storage_bench.ps1 optimized pressure
.\run_storage_bench.ps1 bank1_ref pager
.\run_storage_bench.ps1 optimized pager
.\run_small_soc.ps1 bank1_ref
.\run_small_soc.ps1 optimized
& 'D:/Xilinx/2025.2/Vivado/bin/vivado.bat' -mode batch -source synth_bank4.tcl -tclargs optimized
```

`run_small_soc.ps1` 的 FST 依赖替代处理仅移除波形记录；数值监控、CPU/CNN 请求、DDR 模型及校验仍为同一测试程序。Vivado 独立模块原始报告保存在各版本的 `build/bank4_synth/`。
