# NVDLA 小图适配结果

来源运行：`D:\code\FPGA1\cpu_control (2)\cpu_control\build\runs\20261012_145608_nvdla_small`。已核对适配源码 SHA256、PASS 标记、无故障状态和读写活动。

本次使用真实 NVDLA nv_small 与本工程 banked SRAM。测试端驱动 CPU 风格的 MMIO/A 口；不包含 UART 输入或 CPU 执行指令，不是完整人脸识别网络。

本次运行的编译耗时：**514.787 秒**。这是该次编译记录，不包含此前环境准备和失败排查。每个用例独立复位，硬件时间包含装载、配置、运算、读回校验，按 100 MHz 计算。

| 小测试 | 电脑执行仿真时间 | 硬件时间（全程） | 结果 |
|---|---:|---:|---|
| dc_1x1x8_1x1x8x1_int8_0 | 5.288 s | 86.30 us | PASS |
| dc_6x8x192_3x3x192x32_int8_0 | 63.138 s | 1403.25 us | PASS |
| pdp_8x8x64_2x2_int8 | 4.291 s | 128.10 us | PASS |

- [dc_1x1x8_1x1x8x1_int8_0 全程](dc_1x1x8_1x1x8x1_int8_0/overview.png) · [首次写回](dc_1x1x8_1x1x8x1_int8_0/first_write.png) · [GTKWave 会话](dc_1x1x8_1x1x8x1_int8_0/control.gtkw)
- [dc_6x8x192_3x3x192x32_int8_0 全程](dc_6x8x192_3x3x192x32_int8_0/overview.png) · [首次写回](dc_6x8x192_3x3x192x32_int8_0/first_write.png) · [GTKWave 会话](dc_6x8x192_3x3x192x32_int8_0/control.gtkw)
- [pdp_8x8x64_2x2_int8 全程](pdp_8x8x64_2x2_int8/overview.png) · [首次写回](pdp_8x8x64_2x2_int8/first_write.png) · [GTKWave 会话](pdp_8x8x64_2x2_int8/control.gtkw)

打开各子目录 `open_wave.cmd` 可用工程自带 GTKWave 观察。蓝色为读请求/响应，黄色为写回请求/响应，绿色为完成中断。`phase`：1 装载、2 配置、3 等完成、4 读回校验、5 结束。

详细接线、信号方向、状态编码、构建步骤和未覆盖范围见 [适配说明](../../docs/nvdla_small_integration.md)。每项的原始日志、输出字节、地址映射与寄存器命令也已保留。
