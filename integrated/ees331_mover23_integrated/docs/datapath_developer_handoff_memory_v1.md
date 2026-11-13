# Datapath 负责人存储与 CNN 接入交接（实际交付版）

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

2026-10-07 更新：独立 cnn_memory_adapter 已删除，CNN mem_* 直接接 CPU 存储子系统。CPU C1、流水线和 A/B 口基本结构保持原样；按实际 FPGA1 接口更新系统边界。

## 顶层选择

正式 CPU/CNN 仿真入口为 `face_soc_cnn_top`。它内部仍实例化 `face_soc_cpu_memory_top`，并选择 `EXTERNAL_CNN_MMIO=1` 和 `NATIVE_CNN_MEMORY=1`；该参数继续传给 `datapath_memory_subsystem`。

外接模式下，CPU 的 `mmio_*` 经新增 `cnn_mmio_*` 端口直达 CNN，返回读数据及 ready。旧 `cnn_mmio_regs` 不实例化，旧八组参数输出置零且在新顶层不连接；STATUS 输入在新顶层接零，仅为保留旧 wrapper 端口。

参数默认值 0 用于旧 ADD/B1 回归。沿用默认值并外接真实 CNN 会选错路径，因此新工程应直接选择 `face_soc_cnn_top`，不要手工拼接旧寄存器。

## 保留的存储结构

| 模块 | 当前作用 |
|---|---|
| `imem_rom` | 同步指令读取，默认 64 KiB，INIT_FILE 可预加载固件 |
| `data_sram_tdp` | 默认 256 KiB，CPU A 口同步读取、按字节使能写入 |
| `sram_b_arbiter` | CNN 优先、图像桥次之，读响应按请求所有者返回 |
| `datapath_memory_subsystem` 内部 CNN 访存逻辑 | 在既有模块内部处理 CNN 完成握手，接入原 B1 总线 |

仲裁器仍是固定 CNN 优先，不宣称对任意持续 CNN 流量有公平性保证。真实 FPGA1 请求间存在处理间隔，本次并发测试验证图像侧可取得进展；若将来换成连续饱和主设备，公平仲裁需单独设计。

A 口依旧没有等待信号。CPU 在 E 级末提交 SRAM 请求，M 级使用同步返回数据。CNN/MMIO 在 M 级零等待接受，实际 FPGA1 组合 ready 与现有 CPU 契约匹配。C1 组合控制、跨级状态归属和所有原 CPU 算术模块不变。

## 地址和驱动

默认 IMEM、Data SRAM 各从 0 开始但为不同存储器；CNN MMIO 为 `0x40000000`，合法对齐槽位到 `+0x20`。CPU 原有地址译码无需扩展。

`+0x08` 现在是队列地址，`+0x18` 是任务数，`CONTROL=0x3D` 启动。其余逐层配置移入 SRAM 的 32 字节任务表。只用 LW/SW 访问 MMIO，不支持 byte/halfword 配置。

CPU/图像桥与 CNN 使用不重叠的任务区域。RAM B 口同拍冲突会报错，但不能代替软件对跨拍读改写的所有权约束。

## 错误与复位

error 仍随 B1 的 35 位返回，未删除。CPU 存储子系统把 CNN 访存错误锁存为 `cnn_mem_fault`；CNN 原生不支持错误响应，所以停止确认该事务，等待系统恢复。CPU 有限轮询超时后不得复用缓冲区；整体复位清故障。CNN 软复位只负责 CNN 内部收尾，不能清CPU 存储子系统故障。

## 工程文件和验收

编译 `rtl/filelists/system_cnn.f`（路径相对根目录），顶层 `face_soc_cnn_top`。仅选择一份共享 package、一份 Control 和一份 CNN 同名模块；不能递归把所有原始/兼容/测试文件都加入综合。

测试入口：`python scripts/run_cnn_integration.py`；原 B1 检查：`python scripts/run_partner_datapath_b1_tests.py`。单元 B1 测试已补上新增外接端口的显式空接/零输入，继续检查历史模式。

[实际验证结果](cnn_native_memory_verification_20261007.md) · [新手步骤](CNN实际代码整合修改说明_小白版.md) · [共同连接图](SoC芯片封装与内部IO层级连接图.md)。板级图像桥、实际约束、BRAM 推断/资源和时序仍须目标 FPGA 综合验收。
