# CPU＋CNN＋存储顶层仿真记录（2026-11-11）

## 结论与版本

在隔离工作目录 `D:\FPGA\system_sim_20261111` 完成了真实 CPU、23 客户端 CNN、缓存/DDR 桥、新 `download_ram` CPU 本地 RAM 的顶层 RTL 仿真。四种样例均 PASS；新 `tile_dma_system` 与真实 CPU 下载执行另行 PASS。**新 DATA MOVER／tile RAM 尚未接到真实 CNN 的顶层访存端口**，因此不能宣称新存储路线完成 CPU＋CNN 端到端联调。

CPU Control、Datapath、`cpu_core` 来自 11 月 9 日合并快照，关键文件与已抓取的 `origin/moon` `e298f0c6a45ddefc0a562814289157a46a9d2c34` 一致。CNN 算术流文件与已抓取的 `origin/zhang` `264883efcfa61259537195aaaafd323062c81a79` 一致；SoC 使用合并快照的 `face_soc_ees331_top #(.POOL23(1))` 配置：K3×4、K1×12、Post×4、Add/DW7/Pad 各一。该配置使用 `fixed_schedule_compact`、128 KiB CNN cache、64 MiB 逻辑 DDR 窗口。PS7 与外部 DDR 用 AXI 仿真模型代替；测试没有真实 PS 软件、开发板或器件 DDR。

## 实测结果

| 场景 | 图数/任务 | 逐字节核对 | 周期 | 跨图计算重叠周期 | 结果 |
|---|---:|---:|---:|---:|---|
| 短行 tile | 1 / 3 | 48 | 30,196 | 0 | PASS |
| 8×8×32 tile | 1 / 3 | 12,288 | 451,539 | 0 | PASS |
| 同一 8×8×32 tile 复制到独立 DDR 工作区 | 4 / 12 | 49,152 | 1,010,221 | 157,791 | PASS |
| 原四图 7×7 合成诊断图，六类算子 | 4 / 44 | 28,812 | 239,333 | 1,975 | PASS |

四图六类算子场景还检查了只读模型区、16 个工作槽的尾部保护、最终 DDR 输出、任务启动/完成不重复，以及 CPU 命令响应。最终输出 SHA-256 为 `d961e0eb6f303e1f4e49a9792e92778ba2d4f5b4ee6600976d3417ee6f9d08f0`，与原始样例清单相同。23 个算子实例全部参与编译和连接，实际任务使用了 15 个实例：K3 四个、K1 四个、Post 四个、Add/DW7/Pad 各一个；其余 8 个 K1 实例没有被这组小图调度到。四图样例的峰值同时活跃图数为 4。

测试固件在原 mailbox 程序启动前执行一次 CPU RAM 写入、读回、比较；四种场景均观察到 CPU RAM 读写各一次并通过比较，随后原程序正常完成全部命令。原 mailbox 固件本身不访问 CPU 本地 RAM，这一点是增加测试固件探针后才获得的覆盖。

新存储链路独立复测：`tile_dma_system` 两种 tile 共 12 组、40 行、105,893 周期 PASS，含真实 `tile_row_dma`、`data_mover`、`tile_local_ram` 与模拟 DDR；计算端输出仍由测试数据写入，并非 CNN 算子。真实 Control＋Datapath＋可下载 IMEM/CPU RAM 的独立测试也 PASS，覆盖程序下载、`.data/.bss`、字节访存与两次重启。

## 为仿真所做的小改动

所有改动均在隔离目录；没有修改原 `D:\FPGA\11.9` 工程、`origin/moon`、`origin/zhang`，也没有修改存储工作树的 RTL。

1. 在隔离副本的 `rtl/cnn_ddr/datasram_ddr_subsystem.sv` 中，以 `storage_v2/rtl/download_ram.sv` 实例替换原 CPU RAM 数组，参数仍为 16 KiB、基址 0、同步一拍 CPU 端口；暂将 loader 端保持无效。`rtl/filelists/system_ees331.f` 增加该源码。
2. 新增测试专用的 23 客户端观察顶层、C++ 检查器与固件 RAM 探针。探针只改测试 ROM：将原首条指令移至空闲 ROM 区，先做一次 0x100 地址的写读比较，然后跳回原固件第 2 条指令。生产 CPU/CNN 算术 RTL 和原固件文件未改。
3. 转换现有 tile 样例为紧凑调度器的 18 字元数据；额外制作四帧独立工作区样例，并将历史四图 11 步合成诊断图转换为新顶层输入格式。转换只作用于测试数据。
4. 本机 VS/CMake 自检最初报 `C1902 Program Database Manager mismatch`；在隔离副本的 `scripts/bootstrap_verilator_native.py` 中指定自检使用 Release 配置后完成编译。实际仿真程序设 180 秒进程超时和 2,000 万周期内部看门狗。本次没有发生卡死或超时。

## 尚未验证、下一步接线

- 新 `data_mover`／`tile_local_ram` 的单计算端口与现有 CNN 的 23 路 cache 请求协议不同。需要确定 23 路仲裁/适配、逐 tile 地址与任务映射、缓存与搬运器的边界，以及它们共用 HP0 时的 AXI 仲裁或替换方案，之后才能在同一生产顶层做新存储路径端到端仿真。
- 六类算子四图测试是 7×7 合成诊断图、11 步模板；tile 测试是 3 步模板。没有在这条 DDR/cache＋CPU 顶层执行完整 131 步 MobileFaceNet 或实际人脸识别，也未覆盖全部 23 个实例的任务运行。
- 此次是 RTL 仿真，没有重新综合、布局布线或上板。11 月 9 日的原 23 客户端配置综合报告为 88,758 LUT / XC7Z020 可用 53,200，已超额；本次 CPU RAM 替换后的资源数尚未重测，仿真 PASS 不表示可放入 XC7Z020。

## 复现与证据

使用本机 Python 3.13、Verilator 5.050、Visual Studio 2022。工作目录：`D:\FPGA\system_sim_20261111`。

```powershell
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/prepare_pool23_soc.py
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/run_pool23_soc.py short_row_2x2x2
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/run_pool23_soc.py tile_8x8x32
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/run_pool23_soc.py tile_8x8x32_four_frames
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/run_pool23_soc.py four_frame_all_ops
```

每个场景的 `build/pool23_soc/<场景>/result.json`、`metrics.json`、`simulation.log`、`outputs.bin` 和编译日志都保存在隔离目录。新存储链路独立复测证据在原存储工作树的 `storage_v2/build/tile_dma_system/` 与 `storage_v2/build/cpu_download/`。
