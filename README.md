# 简化 CNN 图像加速器

**MobileFaceNet 新版本已放在 [mobilefacenet/](mobilefacenet/README.md)**：保留9个MMIO，新增Normal/DW3/DW7、ReLU6、Residual Add、128维输出和ONNX导出/逐层Golden验证。运行 `python mobilefacenet/scripts/verify_all.py` 可执行完整验证。原CNN版本在下文，两个版本独立编译。

本工程只包含 **CNN 加速器本体和 9 个 MMIO 寄存器**。没有 CPU、指令 ROM、完整 SoC、外设或软件驱动。Testbench 中的 MMIO 访问任务仅用于模拟未来 CPU 的寄存器读写。

RTL 使用 Verilog-2001，文件位于 `rtl/`；测试平台使用 SystemVerilog，位于 `tb/`。顶层为 `cnn_accelerator_top`，只暴露时钟/复位、32 位 MMIO 和简单 32 位 RAM Master 接口。

## 运行仿真

需要 Python 3.9+、Icarus Verilog（`iverilog` / `vvp`，参见[官方安装说明](https://steveicarus.github.io/iverilog/usage/installation.html)）。本机脚本能找到已有 OSS CAD Suite；其他电脑可加入 PATH 或指定工具路径：

```powershell
python scripts/run_tests.py

# 单独运行一个阶段
python scripts/run_tests.py accelerator_regs
python scripts/run_tests.py relu_unit
python scripts/run_tests.py quantizer
python scripts/run_tests.py mac_unit
python scripts/run_tests.py maxpool_unit
python scripts/run_tests.py buffers
python scripts/run_tests.py address_generator
python scripts/run_tests.py accelerator_mem_if
python scripts/run_tests.py cnn_controller
python scripts/run_tests.py top_smoke
python scripts/run_tests.py cnn_accelerator

# 指定工具位置
python scripts/run_tests.py --iverilog C:/iverilog/bin/iverilog.exe --vvp C:/iverilog/bin/vvp.exe

# 可选：Yosys 展开、过程转换、结构检查
python scripts/check_structure.py
```

完整回归自动生成确定性输入和 Python Golden Result，包含完整 224×224 RGB 图像。完整用例比小模块测试耗时更长。编译失败、断言失败或缺少 PASS 标记都会使脚本非零退出。

## 查看波形

如果 GTKWave 窗口没有显示，可以直接生成 PNG 波形图（本机已安装 Pillow）：

```powershell
python scripts/view_wave.py --image
```

然后打开 `build/wave_overview.png` 看完整过程，或打开 `build/wave_mac_detail.png` 看累加放大图。这些图由真实 VCD 信号转换，保留实际时序。

在工程根目录运行以下命令，会仿真小规模卷积并打开 GTKWave，自动选好 19 个关键信号：

```powershell
python scripts/view_wave.py
```

波形文件为 `build/top_smoke.vcd`，信号布局为 `build/top_smoke.gtkw`。输入 1…9、权重全 1，最终输出为 45。详细时间点与信号说明见[波形查看指南](docs/waveforms.md)。

只生成波形，不启动查看器：

```powershell
python scripts/run_tests.py top_smoke --waves
```

完整 224×224 测试也支持 `python scripts/run_tests.py cnn_accelerator --waves`，输出 `build/cnn.vcd`；它运行更久、波形文件也大，建议先看小例子。普通 `python scripts/run_tests.py` 不默认导出波形。

## 文档和文件

| 内容 | 位置 |
|---|---|
| 总体结构、MMIO、RAM 协议、数据布局、复位和限制 | [接口与集成说明](docs/architecture.md) |
| 每个模块的接口、独立 Testbench、测试数据和预期输出 | [分阶段开发与测试](docs/module_tests.md) |
| 实际验证结果 | [验证报告](docs/verification.md) |
| 顶层完整代码 | [cnn_accelerator_top.v](rtl/cnn_accelerator_top.v) |
| 仅 RTL 的文件清单，供后续工程集成 | [files.f](rtl/files.f)（从工程根目录使用） |
| 独立软件参考模型和数据生成器 | [generate_vectors.py](scripts/generate_vectors.py) |
| 端到端 Testbench | [tb_cnn_accelerator.sv](tb/tb_cnn_accelerator.sv) |
| 模拟 Data RAM | [model_data_ram.sv](tb/model_data_ram.sv) |
| 生成的输入 / Golden 数据 / 用例参数 | `build/vectors/*.memh`、`*.golden.hex`、`manifest.json` |
| 每个模块的真实仿真日志 | `build/tb_*.log` |

## 首版实现选择

- 固定 3×3 卷积，stride 1–15、padding 0–15；宽高和通道数由寄存器配置。
- 一个有符号 INT8 乘法器和一个 INT32 累加器；加法溢出按二进制补码回绕。
- 输入和权重各缓存一个输入通道的 9 个样本；不缓存整幅图像。
- 可选 INT32 ReLU、2×2/stride=2 MaxPool、算术右移和 INT8 饱和量化。
- 小端 HWC 激活布局，权重布局 `[OC][KY][KX][IC]`。
- 字节写回采用读改写；输出首地址无需 4 字节对齐，相邻字节得到保留。
- 不支持原地输出；参数错误在访问 RAM 前报告。

该版本优先保证功能、模块边界和握手正确。未做 FPGA 器件映射、时序约束或性能承诺。
