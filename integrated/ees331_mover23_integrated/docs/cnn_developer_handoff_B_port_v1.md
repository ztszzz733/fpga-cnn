# CNN 负责人开发与对接说明（FPGA1 实际交付版）

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

2026-10-07 更新：独立 cnn_memory_adapter 已删除，CNN mem_* 直接接 CPU 存储子系统。本页替代 2026-09-28 对 CNN 原生端口的预设要求；系统 B1 的 70/35 位格式及 error 保留，转换由 CPU 集成侧完成。

## 当前结论

已接收 `FPGA1.zip`。CNN 顶层为 `mobilefacenet_accelerator_top`，其原始 25 份生产 RTL 已归档在 `partners/cnn/FPGA1/rtl/`。当前接线不要求 CNN 改成旧 CONTROL/STATUS 外部总线。

| 边界 | 当前实际协议 |
|---|---|
| MMIO | 请求 `addr32/wdata32/re/we`；返回 `rdata32/ready`；完整字节地址、对齐整字访问、组合 ready |
| RAM 主接口 | 请求 `addr32/wdata32/read/write`；返回 `rdata32/ready`；ready 表示完成，不表示只接收请求 |
| 系统适配 | `datapath_memory_subsystem` 内部 CNN 访存逻辑 将原生 66/33 位转换为 B1 70/35 位，然后进入 `sram_b_arbiter` |
| 任务配置 | QUEUE_BASE `+0x08`、TASK_COUNT `+0x18`、CONTROL `+0x00=0x3D` |
| 状态 | STATUS `+0x04`：BUSY bit0、DONE bit1、ERROR bit2；其余五槽保留 |
| 结果 | 存在共享 SRAM；没有额外 embedding、IRQ 或 STATUS 硬件输出 |

## 必须一起遵守的约定

1. CPU、CNN、CPU 存储子系统和 SRAM 使用同一个 clk；板级统一协调低有效复位。
2. B1 写操作 grant 时完成；读操作等待 rvalid。CNN 请求等待时必须稳定，连续事务不要求先拉低请求。
3. CNN 写是整字写，CPU 存储子系统写 be=1111、读 be=0000。INT8 的读改写由 CNN 内部完成。
4. CNN 运行期间，CPU/图像桥不得修改任务表、输入、权重和参数，不得读未完成输出；输出区域按整字保留，不能并发写相邻字节。
5. 原生 CNN 没有 error 输入。CPU 存储子系统保留 B1 错误并锁存 `cnn_mem_fault`，停止完成握手；软件超时后整体复位，不能将故障当作成功，也不能声称 STATUS[2] 自动报告 SRAM 故障。
6. 默认共享 SRAM 为 256 KiB；真实模型的权重和中间数据是否装得下，需另作容量规划。不能截断高位地址绕回 RAM。

## 已实现与仍需交接

新 CPU/CNN 集成顶层为 `rtl/soc/face_soc_cnn_top.sv`，编译清单为 `rtl/filelists/system_cnn.f`。旧 MMIO 寄存器仅在历史兼容模式实例化。

XSim 的兼容副本 `rtl/compat/tensor_operator_engine.sv` 只把一处 net 声明拆成声明和连续赋值；交付原件保持不变。

具体通过项见 [验证记录](cnn_native_memory_verification_20261007.md)。完整模型整数结果、板级 UART、综合资源/时序和上板仍待验收，不把小规模 RTL 联调当作完整人脸识别系统通过。

给新同学的步骤见 [小白版修改说明](CNN实际代码整合修改说明_小白版.md)；共同接线见 [SoC 邓庄连接图](SoC芯片封装与内部IO层级连接图.md)。旧版本备份在 `build/backups/before_cnn_20261007/docs/`。
