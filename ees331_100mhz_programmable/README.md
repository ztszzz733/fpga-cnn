# EES331 可编程 SoC · 100 MHz

这是带 ARM 程序装载器的整机版本。ARM 可通过 GP0 装载用户编译的 RV32I 程序，RISC-V 程序可调用 CNN。顶层为 `face_soc_ees331_simple_top`，目标器件为 `xc7z020clg484-1`，分页缓存为 192 KiB（两块 96 KiB bank）。

Vivado 2026.1 参考构建在 100 MHz 完成了综合、布局和布线。布线后建立时序 WNS 为 **−2.001 ns**，保持时序 WHS 为 **+0.028 ns**。最差路径从分页缓存页有效位到突发写状态寄存器。

## 从源码运行综合

安装 Python 3.8 或更新版本和带 Zynq-7000 器件支持的 Vivado 2026.1。在本目录执行下列命令，将 Vivado 路径换成实际安装位置。指定一个尚不存在的构建目录。

```powershell
py -3 .\build.py D:\fpga\ees331_run --vivado "C:\Xilinx\Vivado\2026.1\bin\vivado.bat"
```

Vivado 已加入 PATH 时可以省略 `--vivado`。生成的工程入口为输出目录中的 `project/ees331_ddr.xpr`，综合报告在 `synth/`。如需继续布局和布线，在命令末尾加 `--implement`。时序未通过时，布线报告保存在 `impl/timing_summary.rpt`。

`runtime_program/` 包含 ARM 串口装载器、RV32I 用户程序构建工具、三角函数与矩阵示例及主机串口工具。运行 `python runtime_program/build_user.py --help` 可查看交叉编译器配置。
