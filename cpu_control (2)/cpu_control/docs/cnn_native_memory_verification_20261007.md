# CNN 直接接入 CPU 存储子系统验证

> 历史验证记录：本文所测的是 2026-10-07 的结构，不是当前板级顶层。2026-10-08 已改为六个平级大模块，仲裁进入 datasram，并实现 UART 与 clock_unit。当前结果见 [六模块验证记录](soc_six_module_verification_20261008.md)，当前接线见 [顶层小白说明](../SoC顶层连线与总体IO说明_小白版.md)。

2026-10-07。按用户要求删除独立适配器，验证当前原生 mem_* 接入版本。

## 实现变化

- 删除 rtl/soc/cnn_memory_adapter.sv、顶层实例和清单条目；不是把旧模块改名。
- face_soc_cpu_memory_top 和 datapath_memory_subsystem 新增原生 mem_* 端口及 NATIVE_CNN_MEMORY 参数。
- 既有存储子系统内部处理读 pending、完成 ready、字节使能和故障锁存；内部 B1 仲裁接口及 error 保留。
- face_soc_cnn_top 启用原生模式，CNN mem_* 直接接 CPU 子系统。历史 B1 模式默认仍为 0，未启用的接口不会发请求。
- Control、Datapath 流水线和 CNN 计算 RTL 未修改。C 驱动协议不变。

## 本次通过结果

| 验证 | 结果 | 本次目录 |
|---|---|---|
| 原生 CNN 存储接口单元测试 | PASS | build/runs/20261007_213641_808370_cnn_integration/ |
| 真实 CPU + CNN 联调 | PASS | 同上 |
| 历史 B1 存储与旧顶层展开 | 30 checks，PASS | build/runs/20261007_213652_011117_partner_datapath_b1/ |

每次目录包含本次 result.json、编译/仿真日志和 VCD；没有用上个版本的波形代替。Control RTL 未改，本次不重复其已通过的全量随机回归；真实 Control 和 Datapath 已随新顶层重新编译及运行。

原生存储测试直接实例化真实 datapath_memory_subsystem、sram_b_arbiter 和 data_sram_tdp，验证连续写、连续读、读后立即写、读响应前不提前 ready、不重复请求、图像桥已有读请求时 CNN 等待、读写越界、未对齐、A/B 写冲突、同时读写非法请求、读 pending 中复位及故障后复位恢复。

CPU 联调仍由真实 CPU 执行指令：写任务表、读回 MMIO、启动两次卷积，分别读到 0xA5A511A5 和 0xA5A513A5（17、19），保护字节不变；并发 CPU A口/图像 B口访问通过；非法描述符和软复位通过。完整测试共 3 次 START、32 次 CNN 读、2 次 CNN 写和 214 次图像侧写。

## 重现

```powershell
python scripts/run_cnn_integration.py
python scripts/run_partner_datapath_b1_tests.py
```

RTL 编译清单现在有 51 个文件，不包含 cnn_memory_adapter。新存储测试为 tb/integration/tb_cnn_native_memory.sv，替代已删除的 tb_cnn_memory_adapter.sv。

限制仍包括：尚未验证完整人脸模型、所有算子依赖链、UART、FPGA 资源/布局布线/时序/上板；C 驱动未编译运行。SRAM fault 为系统诊断输出，需 CPU 超时处理及整体复位；没有新增 CPU 软件可读故障寄存器。任务区跨拍读改写仍需软件保证所有权。

[新版连接图](SoC芯片封装与内部IO层级连接图.md) · [小白说明](CNN实际代码整合修改说明_小白版.md)
