# 简化四算子CNN（2026-11-19）

当前开发入口为本目录，基于moon提交`f26d4af`。删除旧硬件自动调度，保留K3×2和K1×2；软件点名指定单元，独立任务可并行。Post/Add/Pad/DW7不实例化。

这是先跑通、便于检查时序的简单基线。K3保留4空间MAC/拍和窗口/权重复用；K1保留8空间MAC/拍、单输出通道，关闭输入预取和外部连续读。每单元只有一笔外部访存在途。计算核心由moon已验证源码改造，前端与寄存访存桥重新实现。

## 已验证结果

| 项目 | 结果 |
|---|---:|
| 数值任务 | 160个PASS |
| 非法参数任务 | 4个PASS |
| 中止、迟到回复排空后重启 | 4个单元PASS |
| 第一组小任务至少两单元实际MAC重叠 | 4644拍 |
| 四单元同拍实际MAC | 161拍 |
| 实际观察到外部同时在途请求峰值 | 4笔 |
| CNN LUT | 10,399 |
| CNN FF | 9,346 |
| CNN BRAM36等效块 | 14 |
| CNN DSP | 16 |
| 10ns综合建立裕量WNS | +2.184ns |
| 10ns综合保持裕量WHS | +0.186ns |
| 建立/保持违例端点 | 0 / 0 |

器件XC7Z020-CLG484-1、Vivado2025.2，MAX_CHANNELS=512，CNN独立OOC综合，全部内部时钟端点受约束。最终综合用时 120.0 秒。CNN 单独布局布线使用相同的 10 ns 时钟，假定时钟源为 BUFGCTRL_X0Y0。建立裕量为 +0.589 ns，保持裕量为 +0.042 ns。外部接口尚缺时序预算，整机 100 MHz 仍需用 SoC 布局布线确认。[CNN 布线时序](evidence/routed/timing.rpt)

相较此前版本，本次同时减少算子数量、删除后处理和硬件调度，并降低K1输出通道并行度，不能把LUT下降解释为相同功能/吞吐的等价优化。

## 接口和构建入口

- [接口、寄存器、存储握手与使用边界](INTERFACE.md)
- [软件描述符助手和提交接口](software/cnn_simple.h)
- `cnn.f` / `rtl/cnn_simple_top.sv`：CNN独立入口。
- `soc.f` / `rtl/face_soc_ees331_simple_top.sv`：四客户端SoC接线版本，复用上级moon两bank存储。
- `build.sh`：使用保留在`D:/code/FPGA1/tools/verilator-wsl`的工具运行独立回归，可用VERILATOR_ROOT覆盖。
- `prepare_soc.py`：重建本机SoC连线清单和lint脚本。

**新MMIO与旧ROM/ARM schedule.c/PLAN.BIN不兼容。** 本轮没有更新完整启动软件，也没有跑整图或完整网络。SoC接线仅通过静态检查，旧存储树存在原有UNOPTFLAT警告，具体见`soc_lint.log`。不能直接沿用旧构建顶层、旧bitstream或旧BOOT.BIN。

软件负责选择空闲单元、管理依赖和缓冲区、准备/同步数据；CNN负责执行当前描述符、报告完成和错误。需要CPU/软件负责人按新接口对接。项目根build.tcl已改用simple_cnn/soc.f及新顶层，k1_units.txt固定为2，拒绝混用旧数量配置；本轮没有创建或运行整机Vivado工程。

## 波形与证据

- [GTKWave会话](small_control.gtkw)、[真实小回归VCD](small_control.vcd)：8条唯一控制信号，已用迁移后的GTKWave实际加载验证。
- [验证汇总](summary.json)、[任务回归记录](metrics.json)、[实际MAC事件](events.csv)。
- [最终综合资源](evidence/synthesis/utilization.rpt)、[层级资源](evidence/synthesis/hierarchy.rpt)、[时序](evidence/synthesis/timing.rpt)、[最差路径](evidence/synthesis/paths.rpt)。
- K3 两次分拍后，综合建立裕量达到 +0.203 ns。K1 随读请求记录末笔标记后达到 +0.286 ns，在已有准备周期内寄存地址区间的末端后达到 +2.184 ns。三次测量使用相同的 10 ns 约束。
- 在当前线性像素分组配置下，原 160 个数值任务和协议回归仍用 305,843 拍，记录的控制波形及 MAC 事件与基线逐字节一致。两套 K1 另通过 12 个地址越界、区间重叠或恰好相邻的检查。[边界验证](bounds_test.log)
- 相同的 CNN 独立布局布线设置下，建立余量从 +0.321 ns 变为 +0.589 ns。[改前布线](evidence/before_k1_fill/routed/timing.rpt) · [改后布线](evidence/routed/timing.rpt) · [改后最慢路径](evidence/routed/paths.rpt)

## 工程清理

按用户选择，移走并保留6处工具目录后，清理54个旧工程/实验缓存路径。项目根目录保留Git、moon_latest、tools和zonghe。旧工具的绝对路径已改变；本版脚本使用新路径。原有未提交README在测量目录作了单文件留档。

原moon的45份受测源码保持字节不变，作为CPU/存储接线基线；新CNN不使用其中旧调度器和其他算子。此前旧工程的跟踪文件删除体现为未提交工作区变更，Git历史仍在。没有自动提交或推送。
