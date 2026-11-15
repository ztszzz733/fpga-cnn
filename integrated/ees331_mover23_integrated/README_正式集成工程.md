# FPGA CPU＋CNN＋存储正式集成工作目录

本目录建立于 2026-11-11，用作以后统一开展 CPU、CNN、存储接线和验证的工作副本。原来源目录保持不变。现已增加**真实 CPU＋23 路 CNN＋新 DATA MOVER/tile RAM 的独立顶层**，并通过 RTL 仿真；XC7Z020 整机综合 LUT 超额，尚不能作为可上板验收版本。

## 目录

| 路径 | 内容与来源 |
|---|---|
| `rtl/`、`partners/`、`firmware/`、`scripts/`、`tb/`、`docs/`、`constraints/`、`vivado/` 等 | 完整复制 `D:\FPGA\11.9\cpu_control (2)\cpu_control` 的 2026-11-09 CPU＋CNN 工程；历史 `build/`、`deliverables/` 等文件也保留。 |
| `storage_v2/` | 完整复制 `D:\FPGA\fpga-cnn-bai-datasram-storage\cpu_control (2)\cpu_control\storage_v2`；包括新 IMEM/CPU RAM、DATA MOVER、tile RAM、加载器、测试、报告和既有构建证据。 |
| `simulation/` | 完整复制并本地化 `D:\FPGA\system_sim_20261111` 的顶层仿真副本、脚本、输入样例和结果；其 `rtl/`、`partners/`、`firmware/` 是测试专用源码快照，与本目录根部生产基线分开。 |

## 当前使用入口

- 旧缓存基线：`rtl/soc/ees331/face_soc_ees331_top.sv`，编译清单 `rtl/filelists/system_ees331.f`；它仍使用原 CNN cache＋DDR 桥。`simulation/` 内有该路径的对照测试，报告为 `simulation/SYSTEM_SIM_REPORT_20261111.md`。
- 新存储功能顶层：`rtl/soc/ees331/face_soc_ees331_mover_top.sv`，编译清单 `rtl/filelists/system_ees331_mover23.f`，默认 23 客户端。`rtl/cnn_ddr/cnn_paged_mover.sv` 把真实 CNN 请求适配到 `storage_v2/rtl/tile_local_ram.sv`，并调用 `storage_v2/rtl/data_mover.sv` 经 HP0 访问 DDR。新路径没有同时实例化旧 cache，不需要两套 AXI 主设备仲裁。详见 `docs/storage_mover23_integration_report_20261111.md` 与接口约定。
- `storage_v2/rtl/tile_row_dma.sv` 仍作为独立的显式逐行搬运候选模块；新顶层目前采用透明按需分页。CPU `download_ram` 的运行端口已接，下载端口和可下载 IMEM 仍待系统集成。

## 仿真复现

在 `simulation/` 中运行：

```powershell
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/prepare_pool23_soc.py
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/run_mover23_soc.py four_frame_all_ops
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/test_mover23_faults.py
```

2026-11-11 在**本目录**新路径四图六类算子测试 PASS：44 个任务、28,812 字节逐字节检查，342,441 周期；新旧路径最终输出逐字节相同。新路径结果在 `simulation/build/mover23_soc/`，故障恢复测试在 `simulation/build/mover23_faults/`。旧路径在本目录重跑的对照结果位于 `simulation/build/pool23_soc_formal/four_frame_all_ops/`；复制过来的 `simulation/build/pool23_soc/` 含旧绝对路径的 CMake 缓存。`scripts/check_ees331_wiring.py` 对旧顶层通过了 128 根连线检查，新顶层通过 Verilator 展开、真实顶层仿真和 Vivado 综合。

`storage_v2/scripts/run_native.py` 在本目录改用 `storage_v2/build/formal_runs/`，避免复制过来的 CMake 缓存引用旧路径；其本地编译器自检指定 Release 配置。本目录重新运行 `tile_dma_system`（12 组、40 行）和 `cpu` 下载执行测试，均 PASS。上述两处仅调整验证脚本/构建配置，不改变存储 RTL。

本目录目前是普通文件夹，未初始化为新的 Git 仓库，也未提交或推送。下一轮生产集成应以根部工程为修改对象，在 `simulation/` 保留对应测试版本和结果。
