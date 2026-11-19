> **2026-11-19 当前开发入口：[简化四算子CNN](simple_cnn/README.md)。两套K3＋两套K1，软件直接下发，不使用原硬件调度器。下文为原moon基线说明，旧PLAN/ROM不能驱动新CNN。**

# EES331 两 bank、软件规划读段版本

本工程从 `ees331_bank4_100/build_k1x4_post` 独立复制并适配。旧工程及其构建目录保持原状。本轮仅修改代码和验证功能，没有启动新的 Vivado 综合、布局布线或上板操作，不能据此宣称 100 MHz 已达标。

可编辑图：[顶层连线图（draw.io，三页）](docs/diagrams/EES331_两bank_软件规划访存_顶层连线图.drawio)，[预览与说明](docs/diagrams/README.md)。

## 保留的功能与配置

- 两个 K3、四个 PW8、两个 Post、Add、Pad，共 10 个执行单元，单元掩码 `0x3FF`。
- 共享缓存由四 bank 改为两 bank，每 bank 196 KiB，总容量仍为 392 KiB（401,408 字节），392 个 1 KiB 页。
- ARM FreeRTOS 从 SD 读取 `PLAN.BIN`、配置任务、上传模型/图片、读取和保存结果；保留 RISC-V 邮箱固件和 DDR 分区。
- 保留缓存刷新、失效、只读保护、DMA、错误恢复、请求取消与排空。
- DW7 及其后 Post 继续沿用此前基线的关闭配置，本轮没有新增删除网络任务。
- 板级顶层 `face_soc_ees331_mover_top.sv` 逐字节不变。构建必须使用 `k1_units.txt` 的 `K1_UNITS=4`；顶层默认参数不能替代工程配置。
- K3 内部供四个空间 MAC 通道使用的 input banks 保留；它们不是本次减少的共享缓存 bank。

## 软件规划协议

每任务仍为 20 个 32-bit 字：前 16 字为命令，后 4 字为依赖等元数据。新版 K3 的字段如下，其他操作保持原含义。

| 字索引，0-based | 内容 |
|---|---|
| 4 | 输入行字节数 `width * in_channels` |
| 5 | 每输出通道权重字节数，普通 K3 为 `9 * in_channels`，depthwise 为 9 |
| 11 bit 31 | 软件读计划版本 1 标志，必须置位 |
| 11 bit 8 / 9 | 输入 / 权重使用 32-bit 读取；未置位表示字节读取 |
| 11 bit 10 | 在本地 RAM 中缓存整层权重 |
| 11 bit 0 | 原 depthwise 标志 |
| 12 / 15 | 输入 / 权重张量总字节数 |
| 13 / 14 | 保留，由调度器写入帧标签和帧槽号 |

`planned_schema.py` 和 `prepare_plan.py` 负责提前计算参数；`k3_plan.h` 和 `schedule.c` 校验形状、范围、对齐、缓存容量和帧分区。现有双图 `fixture/PLAN.BIN` 已转换；模型、图片、任务依赖、DDR 分区、参考中间结果和最终结果不变。

首版采用整段整字或整段字节模式，不在运行中自动扩宽。RGB 等不满足整字条件的段使用字节模式。可能增加片上访存次数，性能需看回归周期；没有把每次读取变成 ARM RPC。

## 硬件改动

`self_conv_spatial4_engine.sv` 直接接收软件读参数，保留输出侧的设置计算与原 MAC、tile、halo 和权重复用数据路径。旧 K3 的通用字缓存、自动扩宽和带地址标签的预取路径从本版本移除。

`planned_read_adapter.sv` 以连续通道加载或权重加载为一段。段首寄存地址、宽度、次数；按计数发出最多四个有序未完成读取，返回 FIFO 按顺序供算子消费。地址数据、响应有效位寄存后再推进算子，不做逐请求的 32-bit 地址标签匹配，也不保留旧路径的运行时回退分支。`clear` 是与共享缓存协同的取消屏障，屏障结束前外部必须处理完旧 epoch 的回复。

共享缓存使用 `tile_local_ram_bank2.sv`，实际仲裁和返回流水宽度均为两路；页槽按 0/1 bank 交错分配。原 `tile_local_ram_bank4.sv` 仅是未加入 filelist 的基线参考文件。

## 功能验证命令

在本工程目录执行，使用本机已有 Python、Verilator Native 和 MSVC。

```powershell
D:\python\python.exe arm_schedule/check_pager.py
D:\python\python.exe arm_schedule/check_planned_reads.py
D:\python\python.exe arm_schedule/check_k3_plans.py
D:\python\python.exe arm_schedule/simulate.py
D:\python\python.exe arm_schedule/plot_waveforms.py arm_schedule/simulation_bank2
D:\python\python.exe audit.py
```

`check_pager.py` 验证两个物理 bank 的实际并发、四客户端冲突与数据顺序、512 次流式读、401 页脏淘汰、替换回绕、部分页刷新、失效重装、取消、AXI 错误恢复和只读保护。

`check_planned_reads.py` 验证读段长度、字节/整字模式、FIFO/背压、有序回复、读写切换、零延迟写完成、取消屏障、非法段和错误恢复，以及 C 软件计划校验。

`check_k3_plans.py` 对普通及 depthwise K3、stride 1/2、奇数通道、非对齐地址、部分 tile、halo 和权重复用执行独立标量卷积参考比较。

完整双图使用真实板级 RISC-V ROM/CPU、CNN、两 bank 缓存和 Mover RTL，公共 ARM 调度 C 逻辑在原生环境执行，PS/DDR 为带等待的模型。它不等同于 ARM 内核运行 FreeRTOS 的板上测试。仿真中的 100 MHz 为时间换算目标，不是时序签核。

结果和源码适用性见 `verification.json`；RTL 差异见 `RTL_changes.patch`。未来综合需重新检查 Slice 打包与 10 ns 下布线后的建立、保持、脉宽、未约束路径和路由状态，不能沿用旧版本的 bitstream 或时序结论。

## GitHub 交付说明（2026-11-19）

本目录是本次最新版合并工程的独立快照，包含完整受测 RTL、RISC-V ROM、ARM FreeRTOS 调度源码、两图测试数据、回归结果、波形和三页 draw.io 图。旧分支中的 `cpu_control (2)/cpu_control` 为历史工程入口。

RTL、ROM、调度 C/C++ 源码及测试数据按本地受测字节上传，`source_sha256.json`、`verification.json` 和 `upload_manifest.json` 可用于核验。未上传编译缓存、工具安装目录和生成的 Vivado/Vitis 工程；本版本没有经过综合、布局布线或实板验证，也没有可用的新 bitstream/BOOT.BIN。

仿真脚本默认采用原机器的 Verilator/MSVC 路径；在其他机器复现时，应按安装位置调整工具路径，完整仿真支持 `--toolchain`、`--msvc` 参数。Vitis 构建也需要本机 SDK 和本版本后续生成的 XSA。

`audit.py` 是与前版比较的原始审计脚本，依赖同级 `ees331_bank4_100` 历史工程；仅克隆本目录时不可直接运行。已完成的审计结果保存在 `verification.json`，与前版的 RTL 差异保存在 `RTL_changes.patch`。独立读取 `source_sha256.json` 即可校验本目录 RTL，无需历史工程。
