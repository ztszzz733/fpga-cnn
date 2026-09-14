# 验证报告

验证日期：2026-09-11。工程范围仅为 CNN 加速器和 9 个 MMIO 寄存器。

## 最终结果

**11 个 Testbench 全部通过。** 完整端到端验证包含 16 组不同参数 / 数据、一次复位后重复运行，共 17 次 Golden 对比、50,468 个输出字节；9 个非法配置检查及软复位排空 / 重启检查也全部通过。

完整 224×224 RGB 用例已真实运行 RTL 仿真，并非仅验证软件模型或缩小图像：IC=3、OC=1、kernel=3、stride=1、padding=1、shift=8、ReLU=1、Pool=0，输出 224×224×1，共 **50,176 字节全部匹配**。

## 工具与检查

| 项目 | 实际使用 / 结果 |
|---|---|
| RTL 仿真 | 本机 OSS CAD Suite 中的 Icarus Verilog 14.0 devel，`s20260301-361-g2efe188b5-dirty` |
| Testbench 编译 | `-g2012 -Wall`；最终日志无编译警告 |
| 纯 Verilog-2001 RTL 编译 | `-g2001 -Wall -s cnn_accelerator_top -c rtl/files.f`，退出码 0 |
| 软件参考模型 | Python 3.11；仅标准库；确定性随机种子 20260911 |
| RTL 结构检查 | Yosys 0.68+48，`ff5817c34-dirty`；hierarchy / proc / opt / check -assert / stat 通过 |
| 组合锁存器 | 无推导出的组合锁存器 |
| Yosys 检查结论 | `Found and reported 0 problems.` |

Yosys 的结构检查不是目标 FPGA 的布局布线或时序验证，没有据此宣称器件资源使用率、最高频率或板上可用性。

## 逐阶段结果

| 阶段 | Testbench | 结果 / 日志 |
|---|---|---|
| 1–2 MMIO 寄存器 | tb_accelerator_regs | [PASS](../build/tb_accelerator_regs.log) |
| 3 ReLU | tb_relu_unit | [PASS](../build/tb_relu_unit.log) |
| 4 Quantizer | tb_quantizer | [PASS](../build/tb_quantizer.log) |
| 5 MAC / Accumulator | tb_mac_unit | [PASS，包含 65,536 种乘法组合](../build/tb_mac_unit.log) |
| 6 MaxPool | tb_maxpool_unit | [PASS](../build/tb_maxpool_unit.log) |
| 7 Buffers | tb_buffers | [PASS](../build/tb_buffers.log) |
| 8 Address Generator | tb_address_generator | [PASS](../build/tb_address_generator.log) |
| 9 Memory Interface | tb_accelerator_mem_if | [PASS](../build/tb_accelerator_mem_if.log) |
| 10 Controller FSM | tb_cnn_controller | [PASS](../build/tb_cnn_controller.log) |
| 11 顶层首次端到端 | tb_top_smoke | [PASS，手算结果 45](../build/tb_top_smoke.log) |
| 12 完整端到端 | tb_cnn_accelerator | [PASS](../build/tb_cnn_accelerator.log) |
| RTL 结构 | Yosys | [0 problems](../build/structure.log) |

## Golden 用例

| 用例 | 输出字节数 | 重点 | 结果 |
|---|---:|---|---|
| sanity | 1 | 1…9 与全 1 卷积，输出 45 | PASS |
| rgb_signed | 60 | RGB、多输出通道、有符号量化 | PASS |
| relu_saturation | 32 | ReLU、INT8 饱和边界 | PASS |
| negative_pool | 8 | 全负数 INT32 池化；输出 -41,-55,-46,-64,-48,-57,-37,-59 | PASS |
| stride_pool | 4 | stride=2，后接 Pool | PASS |
| padding_two | 20 | 小图与 padding=2 | PASS |
| shift_255 | 2 | 8 位最大移位量，输出 0,-1 | PASS |
| int32_wrap | 2 | INT32 回绕，输出 -128,127 | PASS |
| pool_odd_drop | 1 | 奇数卷积尺寸的池化边缘丢弃 | PASS |
| random_0 | 105 | 确定性随机参数 / 数据组合 | PASS |
| random_1 | 24 | 确定性随机参数 / 数据组合 | PASS |
| random_2 | 2 | 确定性随机参数 / 数据组合 | PASS |
| random_3 | 18 | 确定性随机参数 / 数据组合 | PASS |
| random_4 | 3 | 确定性随机参数 / 数据组合 | PASS |
| random_5 | 9 | 确定性随机参数 / 数据组合 | PASS |
| rgb_224 | 50,176 | 完整 224×224 RGB | PASS |
| sanity，再次运行 | 1 | 错误 / 软复位后的重启，无硬复位 | PASS |

每例完整参数和前 16 个预期数值见 [manifest.json](../build/vectors/manifest.json)。逐字节测试数据和预期输出位于 `build/vectors/`。

## 时序、地址和恢复检查

- 对 0、3、5 个等待周期配置进行了仿真，覆盖立即完成与背压。
- RAM 模型断言：请求在等待中稳定；地址已对齐、已知且不越界；读写互斥。
- 验证全部四个 INT8 字节 lane 的读取 / 符号扩展，以及整字和字节写。
- 每次有效端到端计算检查整个 RAM：输出区域与 Golden 匹配，所有非输出字节与启动前快照一致。
- 输出首地址不对齐；输出首尾字里的相邻字节得到保留。写提交次数恰好等于预期输出字节数。
- 检查 BUSY 期间写配置无效、START 不重复触发、DONE 保持、旧 DONE/ERROR 不跨越 RESET 重新置位。
- 非法 kernel、stride、尺寸、通道数、Bias 对齐、输出重叠、地址越界、空池化和保留位共 9 类配置，均 STATUS=4 且不访问 RAM。
- 验证取消读、取消读改写的读阶段、排空已经呈现的字节 / 整字写；端到端 RESET 后停止新请求，随后可正常重启。

## 复现与日志摘录

从工程根目录运行：

```powershell
python scripts/run_tests.py
python scripts/check_structure.py
```

完整测试的实际末尾日志：

```text
CASE PASS rgb_224: 50176 bytes, 12821034 cycles
CASE START sanity
CASE PASS sanity: 1 bytes, 174 cycles
PASS tb_cnn_accelerator (17 golden runs, 9 invalid configs, soft reset/restart)
```

这里的 cycle 数包含 Testbench 的 MMIO 配置后控制操作、轮询和 DONE 保持观察开销，不是 FPGA 实测性能。首次完整仿真曾达到旧脚本的 600 秒运行上限；此后分离配置尺寸计算与逐样本寻址、保留实时日志，并重新完成上述最终验证。当前脚本每项默认上限 1800 秒，可用 `--timeout` 调整；超时或断言失败不会标记为通过。

后续仍需针对具体 FPGA 做器件映射、时序约束、面积与板上验证；当前不支持原地输出，也不含共享 RAM 仲裁。完整集成约定见[接口说明](architecture.md)。
