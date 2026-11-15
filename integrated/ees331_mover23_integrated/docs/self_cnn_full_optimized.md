# 完整 MobileFaceNet 四图：算子数量调整对比

原配置 **K3×4、K1×2**；候选 **K3×2、K1×4**。Post / Add / DW7 / Pad 均各一套。两轮使用同一份四图数据、固定网络模板、输入节奏和 SRAM 参数，并分别取得真实 RTL PASS。

原配置 **1,138,093,351 拍**，候选 **653,428,459 拍**。候选周期减少 **484,664,892 拍（42.59%）**，批次吞吐加速 **1.742×**。 这比较的是同一四图批次端到端周期；不是串行到并行的加速，也不是将短图比例套到全网。

| 配置 | K3 | K1 | 四图实际周期 | 条件时间 ms @100MHz | 条件吞吐 图/s @100MHz |
|---|---:|---:|---:|---:|---:|
| 原配置 | 4 | 2 | 1,138,093,351 | 11380.934 | 0.351 |
| 候选 | 2 | 4 | 653,428,459 | 6534.285 | 0.612 |

**100MHz 仅用于算术换算，尚无新的全设计布局布线或时序达标证据。** 主机仿真耗时与硬件周期分别记录，编译优化造成的主机加速不当作硬件性能提升。

## 实测图与计数

- [周期比较](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/cycle_comparison.png>)、[同轴四图流水前后对比](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/timeline_comparison.png>)、[算子池忙碌与仲裁](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/pool_comparison.png>)。
- [周期 CSV](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/cycle_comparison.csv>)、[各池 CSV](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/pool_comparison.csv>)、[逐层 CSV](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/layer_comparison.csv>)。
- [候选 MAC 同拍采样](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/candidate_mac_detail.png>)、[候选跨类工作采样](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/candidate_pipeline_detail.png>)；`open_candidate_mac_detail.cmd` / `open_candidate_pipeline_detail.cmd` 打开候选实际 VCD，会话各含10根物理信号且不重复。横轴是采样窗口相对时间，未记录全局起点，不能当作网络从零开始。
- [候选可编辑架构图](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/architecture.drawio>) 沿用完整网络图，只调整 K3 / K1 数量，保留 **16 MiB 仿真容量**表述。 已有实际 GTKWave / Tcl 验证 **PASS**：两个候选会话均显示10根唯一信号，本次生成已重新核对当前 `.gtkw` 与 VCD 的 SHA256。详见 [GTKWave 验证证据](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/gtkwave_validation.json>) 和 [波形核验记录](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/wave_views.json>)。 报告生成本身不启动 GTKWave。

| 算子池 | 实例数 原→候选 | 平均忙碌率 原→候选 | 仲裁等待 实例·拍 原→候选 | 等同类资源 帧·拍 原→候选 |
|---|---:|---:|---:|---:|
| 3×3 / DW3 | 4→2 | 4.51%→15.67% | 2,093,347→1,330,157 | 0→60,854,648 |
| 1×1 | 2→4 | 97.81%→85.25% | 2,842,460→4,840,688 | 2,016,986,427→0 |
| DW7 | 1→1 | 0.01%→0.02% | 192→165 | 0→0 |
| Post | 1→1 | 6.08%→10.60% | 710,420→738,556 | 3,495,305→6,573,919 |
| Add | 1→1 | 0.91%→1.59% | 92,380→134,110 | 0→0 |
| Pad | 1→1 | 0.87%→1.52% | 184,848→173,578 | 0→0 |

1×1 的累计同类资源等待从 2,016,986,427 变为 0 帧·拍；3×3/DW3 从 0 变为 60,854,648 帧·拍。这些真实计数用于判断增加 K1、减少 K3 后等待是否转移，最终收益以总周期实测为准。

平均忙碌率 = 同类 active 总和 /（实例数 × 本轮总周期）。仲裁等待只计 `valid && !ready`，不包含正常 SRAM 响应延迟、逐字节请求的固定开销。排队是各图累计的帧·拍，不能除总周期当作批次占比；有空闲池仍未启动的计数还包含槽释放和调度扫描。任务条 busy 跨度不等同于每拍都在 MAC。

## 相同算术与结果证明

两轮分别完成 **524 个任务、935,241,728 次标量 MAC、77,349,168 个输出字节校验**，各 524 次分配/释放及四份外部读取确认。四图输出逐值完全相同，并与独立整数 golden 相同；合计 512 字节 SHA256：`80351fb04be5c55bc45d6e6fcadaef6680b20d0532d15f7bb5bf5c661416a44f`。

算术 RTL、bai SRAM 及核心调度/租约/固定模板展开 RTL 的记录哈希必须逐一相同，否则脚本拒绝生成本报告。实际中间写请求逐字节比较 golden，后续真实 SRAM 读响应核对；最终结果、只读区和尾部保护经 SRAM 端口读取。没有用软件数值替代算子运行，也不声称所有中间数据都额外完整回读。

结果为每图 128 个 UINT8 量化分量，采用跨图固定的首图诊断尺度。整数 golden 一致不代表与 FP32 逐值相同，也不代表人脸识别精度验证。

## 应用候选配置与复现

候选真正的 RTL 例化参数是 `K3_UNITS=2`、`K1_UNITS=4`、`POST_UNITS=1`，DW7 / Add / Pad 各固定一套。`self_fixed_network_top` 与运行脚本默认仍保留 K3×4 / K1×2 以兼容历史入口；本候选由 `run_self_full.py --k3 2 --k1 4 --post 1` 显式选择，并将相同数量传给 RTL 和 C++ 校验器。仅查看默认参数不会得到本次候选配置。

选择四套 K1 的依据是该完整网络的 1×1 占 **93.42% MAC**，原 K1 池平均忙碌率 **97.807%**。本次固定流程四帧中，每帧至多推进一个当前任务，因此同时可用的 K1 任务最多四个；保留两套 K3 处理普通 3×3 / DW3 并维持跨图流水。此选择针对本次四图负载，收益由上面的完整 RTL 周期比较确认。

在项目根目录执行。若需重做匹配的四项小图 gate，可用：

```powershell
python scripts/run_self_full.py --k3 2 --k1 4 --post 1 --data build/self_full_small --modes overlap serial preloaded stress
```

已有匹配 gate `build/runs/20261023_194655_786340_self_full` 四项 PASS，可直接复用。使用当前候选编译缓存与同一四图完整数据的命令为：

```powershell
python scripts/run_self_full.py --k3 2 --k1 4 --post 1 --reuse --full --data build/self_full_data --gate build/runs/20261023_194655_786340_self_full --modes overlap
```

运行入口会核对编译缓存的源码/工具链签名，以及 gate 的相同可执行文件哈希、配置和四项 PASS；若重新编译改变签名或可执行文件，应改用新匹配 gate。上述是仿真复现与 RTL 参数应用说明，没有进行新的整机综合。

## 允许变化的构建 / 测试记录

- `scripts/bootstrap_verilator_native.py`：native simulator build/tool flags；`7ef06ffbcdc894ddb1b110185bd770b005fe35b5592286d5758e846ebb7d0a6d` → `4272ac509abf9b8d3a724dab62fb91edecf4a7fa77af48f37d46096564452182`。
- `tb/integration/self_full_main.cpp`：checker / profiling harness and matching operator-count constants；`44428445b6729a126a5da16a68955d8dd35a571ffd921a509b22d9a7263fcc5d` → `8704132a60fdf6dfe0f2f26d5e80ac150390a2dd4e237ec10bfd4b0167e1305a`。

构建 flags、Verilator 与运行脚本哈希、允许改变文件的前后哈希均写入 [comparison_config.json](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/comparison_config.json>)。上述允许项仅是构建/包装/校验范围，不能据此推导算法改变；受保护算术与存储哈希检查始终执行。

## 资源与存储边界

**没有新的完整 LUT 综合结果。** 六个卷积实例的类型分配变了，不能仅按实例总数宣称总 LUT 不变或符合 FPGA 容量。

已有独立单核 OOC 综合报告按本轮数量相加，**仅六个卷积核**的估算如下：

| 项目 | 原配置 | 候选 | 候选减原配置 |
|---|---:|---:|---:|
| LUT | 11,654 | 11,680 | +26 |
| FF | 9,002 | 8,974 | -28 |
| BRAM36 等效 | 29 | 22 | -7 |
| DSP48E1 | 0 | 0 | +0 |
| 声明的输入与权重局部缓存 KiB | 78 | 54 | -24 |

这不是新的整机综合，不包括 Post / Add / DW7 / Pad、控制、共享 SRAM 与仲裁；集成优化也可能改变相加结果。局部缓存减少不改变共享 SRAM 的 16 MiB 地址空间。单核源码和历史报告哈希已核验，详见 [资源证据](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/evidence/resources/resource_delta.json>)。

现有历史整体综合曾因 Post 参数 RAM 推断失败而未完成，DW7 权重 RAM 另有可能展开为寄存器的警告；本次没有重新完成整机综合或布局布线。

两轮均采用 **16 MiB 仿真 SRAM**；执行初值 **12,608,512 字节（12.024 MiB）**，四个复用工作区各 2,810,112 字节。这不代表 Zynq-7020 片内可容纳，仍需分块/外存和板级资源、时序验证。CPU/UART 固件集成与识别精度不在本次 PASS 范围。

## 原始证据与复现

- 原配置运行：`D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\runs\20261023_180539_292440_self_full`。
- 候选运行：`D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\runs\20261023_194836_645744_self_full`。
- 两轮数据 manifest SHA256：`5add2d08a16845ec1d058a5330880022fe62aa66a7f049db8cc2bd9310e4d1f1`。
- 原配置 / 候选 metrics、events、outputs、运行签名与日志保存在 [evidence](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_optimized/evidence>)；输入节奏均为 80 拍参数。
- 生成命令：`python scripts/compare_self_full.py --baseline "D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\runs\20261023_180539_292440_self_full" --candidate "D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\runs\20261023_194836_645744_self_full"`。
- 正式入口只接受不同运行、4/2→2/4 两种配置、完整网络 PASS；SELFTEST 输出固定隔离在 build 目录。
