# 项目从哪里开始

本次提交说明：[2026-10-22 修改说明](docs/2026-10-22修改说明.md)。源码压缩包位于仓库根目录 `releases/2026-10-22/`。

## 2026-10-22 FX8 并行图像桥（代码与仿真）

新增 `face_soc_neureka_fx8_top`：8 位 RX/TX、25 MHz 握手、跨时钟 FIFO、包/整帧 CRC 和 32 位 SRAM 打包写。保留六模块内部接口、原 UART 入口和已有帧/分块双缓冲。同一 CPU C 固件通过四帧功能回归；计算模型与真实内核限制见 [验证记录](docs/fx8_verification_20261022.md)。用户当前不考虑上板，板级文件仅为参考草案。

- [实现与接口说明](docs/ees331_fx8_interface.md)
- 回归：`python scripts/run_fx8.py`
- 生产源码清单：`rtl/filelists/system_neureka_fx8.f`

## 2026-10-22 Neureka 连续帧调度

`face_soc_neureka_pipeline_top` 现通过 SRAM 描述符选择输入帧 A/B，保持六模块端口和连线。新增 CPU 协作式调度、独立输出 A/B 和 UART 连续四帧示例。主 CPU/桥/SRAM/调度 RTL 的并发回归通过，计算级行为模型不等于真实 Neureka/Vicuna 验收；真实核及上板限制见 [连续帧使用与验证说明](docs/neureka_continuous_frames.md)。

## NEureka 可编程卷积适配

新增隔离入口 `face_soc_neureka_top`（`rtl/filelists/system_neureka.f`）：把官方 NEureka RTL 接入原 CPU 的任务队列和四 bank DATASRAM，原通用 CNN 与固定 Sobel 流式入口均保留。顶层仍为六模块；排布转换、配置和 HCI 桥接都在 CNN 内部。当前为 SRAM 任务模式，不能直接替代此前 UART 逐像素流式入口。

- [适配与软件配置说明](docs/neureka_integration.md)
- [适配与功能验证说明](deliverables/neureka_benchmark/适配与验证说明.md)
- [架构、任务时间线与网页版说明](deliverables/neureka_benchmark/适配与验证说明.html)
- [可编辑 draw.io 架构图](deliverables/neureka_benchmark/neureka_architecture.drawio)
- [已通过功能验证的任务阶段波形](deliverables/neureka_benchmark/open_functional_tasks.cmd)（由真实任务事件生成，非总线逐拍转储）
- [开源版本、许可证与兼容补丁](third_party/NEUREKA_SOURCES.md)

已完成连续小图任务、桥接和顶层展开检查。2026-10-11 大图仿真也已通过：256×256 RGB、8 输出通道，卷积＋ReLU＋池化共 1,161,288 字节全部匹配。电脑执行仿真 8917.713 秒，硬件任务时间 101.60868 ms @100 MHz。本次复用已编译程序，重新编译耗时为 0；原始编译 793.346 秒。不提供具体加速倍数，也不代表完整人脸网络或 UART 加载闭环通过。

- [大图控制波形与阅读说明](deliverables/neureka_large_wave/波形阅读说明.md)
- [六个控制波形预览](deliverables/neureka_large_wave/index.html)
- [GTKWave 全程入口](deliverables/neureka_large_wave/open_01_overview.cmd)
- [卷积首次写回](deliverables/neureka_large_wave/open_04_conv_write.cmd)、[池化写回](deliverables/neureka_large_wave/open_05_pool_write.cmd)、[完成](deliverables/neureka_large_wave/open_06_complete.cmd)

## 2026-10-10 六张图片边接收边计算

新隔离入口 `face_soc_stream_top` 已完成 6 张 524×524 灰度图的 UART 引脚级仿真：固定双路 Sobel 卷积、幅值缩放、2×2 最大池化，全部 817452 字节特征写入 1 MiB DATASRAM 并逐字节验证。顶层仍是六模块。该入口使用专用固定流式卷积核，旧通用脉动阵列和 19 任务演示保留。

- [六帧使用说明与实测](deliverables/stream_six_images/使用说明.md)
- [输入与实际输出图片](deliverables/stream_six_images/results.html)
- [接收计算重叠波形](deliverables/stream_six_images/open_all_modules.cmd)
- [六帧全程状态](deliverables/stream_six_images/open_all_frames.cmd)
- [新版 draw.io 图](deliverables/stream_six_images/soc_architecture.drawio)

运行：`scripts/run_stream_sim.ps1 -Waves`。以下章节是此前的通用多任务演示。

## 六模块状态、完整波形与 draw.io 图

新增六路顶层状态监测，仍保持六个模块实例。最新交付在 [信号与状态说明](deliverables/soc_top_view/信号与状态说明.md)，包含 61 根图中标注信号的功能、方向、位宽和有效条件。完整 GTKWave 视图已去重为 61 条轨迹，每根只出现一次，按输出端模块分组着色。

- [打开完整模块波形](deliverables/soc_top_view/open_all_modules.cmd)
- [查看六模块状态总览](deliverables/soc_top_view/open_module_states.cmd)
- [波形阅读指南](deliverables/soc_top_view/波形阅读指南.md)（[网页版](deliverables/soc_top_view/波形阅读指南.html)，按实际时间点逐步阅读）
- [可编辑 draw.io 架构与状态图](deliverables/soc_top_view/soc_architecture.drawio)

重新生成：`scripts/run_overlap_sim.ps1 -Cases overlap,observer_fault,restart -TopWaves`，随后把输出目录传给 `scripts/prepare_soc_top_view.py`，并运行 `scripts/draw_soc_top.py`。当前波形来自 20261009_222856_065280_overlap_integration；默认仿真 UART 已提高到 25 Mbps、每包 256 字节，正常、故障复位和原有恢复测试均通过。

UART 提速对照：`scripts/run_overlap_sim.ps1 -Cases uart_baseline,overlap -TopWaves`。旧参数可用 `-UartBaud 12500000 -ChunkBytes 64` 恢复；总图接口和 61 根去重信号不变。说明见 [UART 仿真提速](docs/uart_simulation_speed.md)。

## 2026-10-09 仿真架构：搬运计算重叠

本次新增六模块入口 `rtl/overlap/face_soc_overlap_top.sv` 和 `rtl/filelists/system_overlap.f`：保留原 CPU 和 8×8 PE 数量，在 CNN 内加入操作数双缓冲与独立写回，在 DATASRAM 内加入四存储体及多客户端仲裁。19 个任务通过真实 CPU/UART 全流程执行；旧入口继续保留。

设计、接口、复位和仿真用法见 [新架构说明](docs/overlap_soc_architecture.md)，本次实测见 [验收记录](docs/overlap_soc_verification.md)。运行 `scripts/run_overlap_sim.ps1 -Waves`，通过后可整理为 [GTKWave 会话](deliverables/gtkwave_overlap/open_gtkwave.cmd)。以下 2026-10-08 章节描述旧版入口。

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](docs/uart_image_bridge_protocol.md)、[本次验证](docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

旧版资料保留在“说明文档/原版”。以下入口以当前六模块版本为准，旧版本不作为当前板级接线依据。

## 直接使用

```powershell
python scripts/run_cnn_integration.py
python -m unittest discover -s tb -p test_uart_image_transfer.py
python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot
```

板级顶层选 `face_soc_top`；空 IMEM_INIT_FILE 不包含可运行固件，上板条件见顶层说明。

## 文档入口

- [CPU 数据流动说明（小白版）](CPU数据流动说明_小白版.md)
- [顶层逐根接线](SoC顶层连线与总体IO说明_小白版.md)
- [新手目录](说明文档/新手版/README.md)
- [按问题找文档](docs/README.md)
- [全部说明目录](说明文档/README.md)
- [CPU C1 接口](docs/cpu_control_interface.md)与 [M 正式回复 P1](docs/control_reply_to_P1.md)
- [历史原版](说明文档/原版/README.md)，保留早期 Control-only 阶段资料，不代表当前 CNN 接入状态

