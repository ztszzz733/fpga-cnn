# EES331 4 bank 缓存侧版本

日期：2026-11-15。此目录以 `zhang` 分支提交 `695c5a9de38f4d9408530c1c1877661f93129ffb` 的集成工程为基础，叠加先前的单 bank 命中流水优化及本轮 4 bank 缓存侧修改。提交目标为 `bai-datasram`。

## 代码范围

- `rtl/cnn_ddr/cnn_paged_mover.sv`：四个 bank 分别仲裁计算请求、保持请求者标签并返回响应；保留 392 个 1 KiB 页槽、单个缺页搬运引擎。
- `storage_v2/rtl/tile_local_ram_bank4.sv`：把原有 392 KiB 本地 RAM 组织为 96/96/100/100 KiB 四个 bank；对 DATA MOVER 维持一条 32 位线性 DMA 接口。
- `rtl/filelists/system_ees331_reduced.f`：登记新增 RAM 模块。

`storage_v2/rtl/data_mover.sv` 未改动。这次提交没有合入另一侧的 DATA MOVER 优化，也没有新增 DSP 或 BRAM 容量。

## 验证结果

本轮数据以已有命中流水的单 bank 版本为对照，均为相同仿真条件下的周期数：

| 场景 | 单 bank | 4 bank | 结果 |
|---|---:|---:|---|
| 四客户端独立驻留页，2048 次读 | 2051 | 1536 | 减少 25.11% |
| 四客户端独立驻留页，2048 次写 | 2051 | 1536 | 减少 25.11% |
| 单客户端驻留页，512 次读 | 1536 | 1536 | 持平 |
| 四帧、12 个真实 CPU/CNN/DDR 任务 | 685168 | 645255 | 减少 5.83%；结果一致 |

完整 PL 顶层 Vivado 2025.2 综合：4 bank 为 LUT 57516、FF 38283、BRAM36 等效 137、DSP 24；相对单 bank 增加 LUT 2536、FF 1029，BRAM 和 DSP 不变。目标器件 LUT 上限 53200，4 bank 当前超出 4316；10 ns 约束下综合后 WNS 为 -27.282 ns。**这是已通过功能仿真的候选版本，尚不能据此认定可上板或达到 100 MHz。**

详细测试条件、输出校验和资源说明见 `docs/bank4/BANK4_RESULT.md`；与 DATA MOVER 并行开发的接口约定见 `docs/bank4/BANK4_DATA_MOVER_HANDOFF.md`。这两份报告中的 `bank1_ref/`、`optimized/` 和 `mover_side/` 指测试时的本地工作目录，并非本仓库目录。

仓库原有 `MANIFEST_SHA256.txt` 是导入的 `zhang` 工程包历史清单；本次变更的精确文件哈希另见 `BANK4_SHA256.txt`。
