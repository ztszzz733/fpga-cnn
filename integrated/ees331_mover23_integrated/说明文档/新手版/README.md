# 项目从哪里开始

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../../docs/uart_image_bridge_protocol.md)、[本次验证](../../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## 先做这一件事

打开 PowerShell，复制下面两行执行：

```powershell
cd D:\cpu_control
python scripts/run_tests.py --plot
```

这台电脑的工具已配置好。命令结束后，最后一行以 **PASS** 开头就是本次流程通过。`--plot` 只表示同时生成图片，其他设置用默认值。

不知道怎样打开窗口、找结果或处理错误，就按 [测试教程](test.md) 的四步操作。

## 推荐阅读顺序

1. [测试教程](test.md)：先亲手跑通一次。
2. [硬件接口与完整指令说明](硬件接口与完整指令说明.md)：查看你负责的硬件、逐模块 IO、指定指令测试方法和 37 条完整指令流程。
3. [代码阅读说明](代码阅读说明.md)：知道每个模块负责什么。
4. [等待与跳转说明](等待与跳转说明.md)：结合例子理解控制行为。
5. [本次对接说明](本次对接说明.md)：了解当前进度。

需要查别的内容，打开 [全部说明目录](../README.md)。

## 测试通过代表什么

目前通过的是控制模块和简化测试模型的验证。真实的数据通路、存储器和 CNN 还没有接入验证，不能把结果理解成整个识别系统已经完成。实际记录见 [测试结果说明](测试结果说明.md)。

---

[对应原版](../原版/README.md) · [全部说明目录](../README.md)
