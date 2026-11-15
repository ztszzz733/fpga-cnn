# 接口变更记录

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

旧版资料保留在“说明文档/原版”。以下入口以当前六模块版本为准，旧版本不作为当前板级接线依据。

## 本次变更

| 日期 | 变化 | 不变部分 |
|---|---|---|
| 2026-10-08 | SRAM 原生 CNN 完成时序、内部 B 仲裁；六模块顶层；UART 和时钟复位 RTL | Control C1、CPU Datapath 十二个模块、原始 FPGA1 RTL |
| 2026-10-07（历史） | 删除独立 CNN 适配器，暂时把时序逻辑放进旧存储 wrapper | 该 wrapper 现不在板级编译路径 |

详见 [修改说明](CNN实际代码整合修改说明_小白版.md)和 [验证记录](soc_six_module_verification_20261008.md)。

[早期 C1 接口变更原文](../说明文档/原版/docs/interface_change_log.md) · [新手改动记录](../说明文档/新手版/项目改动记录.md)。

