# 本次结果：Post×2，缩减算子并扩容共享 BRAM

K3×2、K1×6、Post×2、Add×1、Pad×1，共 12 个；DW7 不实例化。生产默认共享 tile RAM 为 **392 KiB**，即原 32 KiB 加上回收的 360 KiB。

## 实际资源统计

| 版本 | LUT | 寄存器 | BRAM36 等效 | DSP | 共享 RAM |
|---|---:|---:|---:|---:|---:|
| 原 23 算子 | 71101 | 46017 | 137.5 | 61 | 32 KiB |
| 缩减算子、未回填共享 RAM | 35326 | 25830 | 47 | 33 | 32 KiB |
| 本次实际配置 | 49053 | 34978 | 137.0 | 33 | 392 KiB |

统计为同型号 Z7020、Vivado 2025.2 综合后的整套 SoC。原版引用随集成包提供的真实综合报告；两份缩减版报告为本次运行。完整证据在 evidence/。回填共享缓存会增加页表逻辑，所以最终 LUT 以最后一行为准。资源数量检查通过，未进行布局布线或上板时序验证。

## 一图完整网络验证通过

129 个任务全部开始并完成；19365452 字节中间输出逐字节匹配独立整数参考。CPU 配置、图片提交、算子计算、tile RAM 换页、MOVER/DDR 读写、CPU fence、结果取回、缓冲区护栏与批次复位均经过实际 RTL。

按约定跳过原 DW7 及其关联 Post，末尾 PW 和 Post 保留原参数，在 7×7 上运算。最终为 UINT8/HWC、7×7×128，**6272 字节**，见 full_outputs.bin。此网络变体不等价于原 128 字节嵌入，不包含识别精度验证。

输出 SHA256：`8971dac0e8b2df60698e060a5e066b416213e8a71553161f66b037e613718485`。

图片提交到 DDR 结果可见的周期数：248676566；按 100 MHz 绘图参考换算为 2486.766 ms。这是模拟周期换算，不是电脑仿真用时或板上实测频率。

PS GP0 和 DDR 是外部环境模型，软 CPU、CNN、片上 RAM、MOVER 为生产 RTL；执行内存只预装模型和填充值，中间参考结果不注入执行内存。

## 打开波形

- `open_full.cmd`：完整一图，CPU、CNN、内存和 MOVER，以及全部 12 个算子状态。
- `open_full_cpu_config.cmd`：复位到 CPU 配置及输入提交。
- `open_full_operator_detail.cmd`：首个 K1 任务开始后的 128 拍细节，可横移查看请求、等待、MAC 和输出。
- `open_small.cmd`：已完成的小规模 8 任务回归。

CPU 配置和算子细节是从完整记录按真实时间戳裁出的独立小文件，打开更快；完整状态 FST 约 96 MB，首次加载可能需要几十秒。

各行有 K3_0、K1_0、POST_0 等实例名称。`IDLE_NO_TASK` 表示没有持有任务；其他名称是该实例实际 FSM。拿到任务后可能在等数据，不能把整段有色区都当成乘加。缩放过远时密集变化会显示成纯色，请先打开细节视图或放大。

末尾任务计数回到零，是测试在取回结果后执行了批次复位；此前会达到 129。最终 RAM 分块前后的整机数值、周期、任务事件和结果时刻完全一致。

## 代码和复现

`source/` 包含本次生产 RTL 清单中的源码、CPU 固件、测试平台和一图数据；`production_changes.patch` 对照修改前备份。当前工作目录仍在 `D:/code/FPGA1/integrated/ees331_mover23_integrated`。入口 `rtl/soc/ees331/face_soc_ees331_mover_top.sv`，清单 `rtl/filelists/system_ees331_reduced.f`。

本机完整仿真脚本 `simulation/scripts/run_reduced_soc.py` 通过 WSL 运行，依赖已安装的 Verilator、C++ 编译器和 zlib。综合脚本 `simulation/scripts/run_reduced_synth.py 401408` 通过 Windows Python 调用 Vivado。移到其他机器时需要调整工具路径；Vivado 本身及工具链不包含在交付包中。
