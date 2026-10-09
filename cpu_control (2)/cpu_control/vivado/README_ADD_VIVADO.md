# 在 Vivado 中运行 ADD 全信号仿真

这套入口不使用 Python。测试平台是纯 Verilog 文件，生产 CPU 代码继续以 SystemVerilog 编译。

## 1. 为什么生产代码仍是 `.sv`

现有 CPU 使用了 `package`、`logic`、`always_comb`、`always_ff` 和结构体等 SystemVerilog 语法。Vivado 原生支持这些语法。强行改成旧式 Verilog-2001 会改变公共 package、端口类型和大量 RTL，不符合“内容架构不变”的要求。

因此文件分工为：

```text
tb/integration/tb_add_vivado.v   纯 Verilog 测试平台
rtl/**/*.sv                      本方正式 SystemVerilog Control
partners/datapath/**/*.sv        负责人正式 SystemVerilog Datapath/存储器
vivado/run_add_all_signals.tcl   Vivado 建工程、运行仿真、加入波形
```

Python 只曾用于自动画 PNG；Vivado 硬件仿真本身从来不依赖 Python。

## 2. 一条命令打开并运行

在项目根目录打开命令提示符或 PowerShell：

```powershell
D:\vivado\2026.1\Vivado\bin\vivado.bat -mode gui -source vivado\run_add_all_signals.tcl
```

脚本会自动：

1. 建立 `build/vivado_add_all_signals/` 仿真工程；
2. 加入真实 Control、生产 Datapath、IMEM、双口 Data SRAM、B 口仲裁和 CNN MMIO；
3. 编译 `tb_add_vivado.v`；
4. 运行 `ADD x6,x1,x2`；
5. 在 Vivado 波形窗口按 IF、ID、流水控制、EX、MEM、WB 分组加入全部讲解信号；
6. 保存 `add_all_signals.wcfg`。

如果 FPGA 型号不是默认的 `xc7a35tcpg236-1`，可以把实际型号作为第一个 Tcl 参数：

```powershell
D:\vivado\2026.1\Vivado\bin\vivado.bat -mode gui -source vivado\run_add_all_signals.tcl -tclargs 你的FPGA型号
```

行为仿真不依赖具体 FPGA 型号；真正综合和生成 bitstream 时必须改成开发板的实际型号。

## 3. Vivado 中应看到的结果

Tcl Console 应出现：

```text
VIVADO_ADD_RESULT x1=1 x2=2 x6=3 rf_writes=1 dmem_reads=0 dmem_writes=0 mmio_reads=0 mmio_writes=0
PASS: Vivado Verilog testbench + real Control + production Datapath ADD
```

波形末尾应看到：

```text
alu_a_e=1
alu_b_e=2
alu_result_e=3
alu_result_m=3
wb_data_w=3
rd_w=6
rf_we=1
x6_value=3
```

`x1_value`、`x2_value`、`x6_value` 只是测试平台只读观察线，不进入综合后的 CPU 硬件。

## 4. 在 Vivado GUI 内手动运行

也可以先打开 Vivado，然后在 Tcl Console 中执行：

```tcl
cd D:/cpu_control
source vivado/run_add_all_signals.tcl
```

波形配置保存在：

```text
build/vivado_add_all_signals/add_all_signals.wcfg
```
