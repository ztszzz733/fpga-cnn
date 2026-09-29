# 三任务输入输出接口波形

## 按硬件图只看主要连线

```powershell
python mobilefacenet/scripts/diagram_wave.py --open
```

使用已完成的三任务仿真，生成包含图中 37 根主要信号及第一行 clk（共 38 根）的 [diagram.vcd](../build/interface_wave/diagram.vcd) 和 [diagram.gtkw](../build/interface_wave/diagram.gtkw)。同一条连线两端的别名只显示一份，具体对应关系见 [图中连线与精简波形对应](../build/interface_wave/diagram_signals.md)。

## 完整接口视图

在项目根目录运行：

```powershell
python mobilefacenet/scripts/interface_wave.py --open
```

用当前 RTL 执行三个连续任务：1×1 普通卷积 → 3×3 DW 卷积 → 3×3 普通卷积。每个后续任务使用前一个任务写回 RAM 的结果。

默认打开全部信号，包括用户指定的 MMIO、队列、任务读取器、FIFO、卷积控制、缓存、阵列和输出接口。原始波形保留实际 RTL 层级；信号分组对应框图功能。

生成文件位于 `mobilefacenet/build/interface_wave/`：

- [interfaces.vcd](../build/interface_wave/interfaces.vcd)：原始仿真波形。
- [all.gtkw](../build/interface_wave/all.gtkw)：预先选好全部信号的 GTKWave 配置。
- [guide.md](../build/interface_wave/guide.md)：本次任务时间、各视图说明和信号读取方法。
- [signals.csv](../build/interface_wave/signals.csv)：全部选中信号的层级路径和位宽。
- [comparison.csv](../build/interface_wave/comparison.csv)：39 次结果写回与参考值的对照。
- [result.json](../build/interface_wave/result.json)：检查结果和任务时间。

## 正确值对照

**按运行步骤看“这一步哪些信号应是什么值”时，使用 [分步骤波形对照](../build/interface_wave/step_checklist.md)。** 其中包含时刻、沿前/沿后、操作、信号正确值和步骤含义；[时间顺序总表](../build/interface_wave/chronological_steps.md) 可从启动一直顺着看到结束。

生成步骤对照：`python mobilefacenet/scripts/interface_wave_steps.py`。它会先验证现有仿真波形，再生成主表及全部缓冲写入明细。

运行仿真后，再运行：

```powershell
python mobilefacenet/scripts/interface_wave_reference.py
```

打开 [三任务波形正确值对照](../build/interface_wave/reference.md)，可以逐项核对任务配置、完整输入/权重/偏置、量化前后结果、FIFO 数量变化、分块配置和 39 次写回。时间注明采样沿前或沿后，数据缓存和任务读取器分别列出。

配套 CSV 提供全部读取、缓冲写入及有效 PE 分块结果的预期值。预期值通过独立的标量卷积计算生成，再与 VCD 中的真实信号比较；检查结果保存在 `reference_result.json`，逐项预期/实际值在 `wave_checks.csv`。

分模块查看时，使用 `--view mmio`、`queue`、`reader_fifo`、`control`、`cache` 或 `array_output`。例如：

```powershell
python mobilefacenet/scripts/interface_wave.py --open --view reader_fifo
```

同名 `rsp_data/cmd_addr` 按读取器和缓存的实际路径区分。`quant_shift` 是 `clp[19:12]` 的观察别名；输出选择的 row/col 与装载索引复用同一组寄存器，在相应视图中重复展示。`sums` 保留完整 2048 位总线，另外提供四个 PE 结果的十进制观察别名。

测试会检查任务顺序、24 个任务读取字、39 个写回值与地址、DONE 状态，以及全部 16384 字节 RAM 内容。仿真时钟周期 10 ns，仅表示当前测试的周期关系。
