# FPGA1 源码隔离与端口对齐核验

核验日期：2026-10-08。用户要求：把 `D:\QQ\FPGA1.zip` 源码加入项目，隔离保存，不改用户部分，只做端口对齐。

## 本次实际处理

检查发现同一压缩包已经导入 `partners/cnn/FPGA1/`，系统顶层已有连接。因此本次复用已有导入和接线，不重复解压覆盖，不修改任何 RTL、测试脚本或编译清单；新增本说明和本次验证结果，并在交付入口补充链接。

- 压缩包 SHA256：`3c3e6b390c8ade24e65a8864db3dc962c92b2411f8391b8cc9ceceaf3b6b016c`。
- `rtl/`、`tb/`、`scripts/`、`docs/`、`examples/`、`README.md`、`requirements.txt` 共 93 个文件均已在独立目录中，与包内文件逐字节一致，其中包括 25 个原始 SystemVerilog 源文件。
- 包内 `.deps/`、`.git/`、旧 `build/`、嵌套构建日志和原包 `.gitignore` 不属于本次源码导入范围。
- 对项目 `rtl/`、`partners/datapath/`、`partners/cnn/FPGA1/`、`tb/`、`scripts/` 的 233 个现有文件核对操作前后 SHA256，全部不变（排除 Python 自动缓存）。这包含用户 Control C1、生产 Datapath、当前 SRAM 和顶层。

[文件哈希与隔离核验结果](../build/runs/20261008_174055_957077_fpga1_isolation/result.json)

## 隔离边界与编译入口

| 位置 | 职责 |
|---|---|
| `partners/cnn/FPGA1/rtl/` | 原包 CNN 实现，保留原样 |
| `rtl/cpu_control/` | 用户 Control C1，保持原样 |
| `partners/datapath/delivery/rtl/cpu_datapath/` | 生产 Datapath，保持原样 |
| `rtl/soc/face_soc_top.sv` | 现有板级六模块顶层，完成外部端口连接 |
| `rtl/soc/face_soc_cnn_top.sv` | 现有计算侧测试入口 |
| `rtl/compat/tensor_operator_engine.sv` | 已有 XSim 语法等价副本，原文件仍保存在原包目录 |
| `rtl/filelists/system_cnn.f` | 从项目根目录解析的系统编译清单，共 51 个源文件 |

系统使用上述清单选取源文件，不递归编译整个 `partners/`。其中 24 个 CNN 原始 SV 直接参与编译，`tensor_operator_engine` 使用现有兼容副本，仅将 `pool_sample` 的声明初始化拆成声明和连续赋值；本次核验确认无其他差异。同名原版和兼容版不能同时编译。

## 已对齐的外部端口

方向以 CNN 为参照。具体接线见 [板级顶层](../rtl/soc/face_soc_top.sv)。

| CNN 端口 | 方向 / 位宽 | 对端及顶层连线 |
|---|---|---|
| `clk`、`rst_n` | 输入，各 1 位 | `clock_unit` 提供的同名时钟、低有效复位 |
| `mmio_addr`、`mmio_wdata` | 输入，各 32 位 | `cpu_core.mmio_addr/mmio_wdata`，顶层 `cnn_mmio_addr/cnn_mmio_wdata` |
| `mmio_re`、`mmio_we` | 输入，各 1 位 | `cpu_core.mmio_re/mmio_we`，顶层 `cnn_mmio_re/cnn_mmio_we` |
| `mmio_rdata`、`mmio_ready` | 输出，32 / 1 位 | 返回 `cpu_core.mmio_rdata/mmio_ready`，顶层 `cnn_mmio_rdata/cnn_mmio_ready` |
| `mem_addr`、`mem_wdata` | 输出，各 32 位 | 直接连接 `datasram` 同名输入 |
| `mem_read`、`mem_write` | 输出，各 1 位 | 直接连接 `datasram` 同名输入 |
| `mem_rdata`、`mem_ready` | 输入，32 / 1 位 | 直接来自 `datasram` 同名输出 |

`CNN_MMIO_BASE` 同时传给 CPU 地址译码和 CNN 的 `BASE_ADDR`，默认 `0x4000_0000`。CNN 控制通过普通 MMIO 读写完成，不给 Control C1 增加 STATUS/CONTROL 硬件端口。

CNN 原生访存为 66 位请求、33 位返回；请求保持到 `mem_ready` 表示完成，读返回时数据必须有效。CNN 的字节写由自身 `accelerator_mem_if` 执行整字读改写。该接口直接连接当前 `datasram`，不经过 CPU，也不增设外置 SRAM 仲裁器或适配器。

图像桥另用 `io_mem_*` 70/35 位接口，保留 `error`；与 CNN 的竞争由现有 `datasram` 内部处理。CNN 原生接口没有 `error` 端口，现有 `cnn_mem_fault` 在系统侧锁存并送 LED，故障后需系统复位。此次未改变这些既有行为。

## 本次验证

| 命令 | 结果 |
|---|---|
| `python scripts/run_cnn_integration.py` | `tb_cnn_native_memory`、`tb_cpu_cnn_integration`、`tb_soc_uart` 三项 PASS |
| `python scripts/audit_soc_sources.py` | CNN 25 个 SV、Datapath 12 个 SV 与各自原包一致；兼容差异、六模块边界、51 个编译源核验 PASS |
| `python -m unittest discover -s tb -p test_uart_image_transfer.py` | 7 项 PASS |

[本次 XSim 结果](../build/runs/20261008_174057_139031_cnn_integration/result.json)；同目录保留本次编译日志、三项仿真日志和 VCD。[本次原始源码审计](../build/runs/20261008_174116_090697_soc_source_audit/result.json)。

XSim 对 `tb_soc_uart.sv:56` 的任务参数 `len` 给出一条敏感性警告 `43-4328`；仿真未报错，三项均完成 PASS 检查。

验证范围是 RTL 连接、访存握手、CPU/CNN 小任务联动和 UART 仿真，不代表已完成 FPGA 上板、时序收敛或完整人脸识别模型验收。
