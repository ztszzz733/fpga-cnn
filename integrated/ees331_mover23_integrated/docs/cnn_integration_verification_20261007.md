# CPU / FPGA1 CNN 实际整合验证记录

> 历史验证记录：本文所测的是 2026-10-07 的结构，不是当前板级顶层。2026-10-08 已改为六个平级大模块，仲裁进入 datasram，并实现 UART 与 clock_unit。当前结果见 [六模块验证记录](soc_six_module_verification_20261008.md)，当前接线见 [顶层小白说明](../SoC顶层连线与总体IO说明_小白版.md)。

> 历史记录：本页对应最初“独立适配器”版本，其模块和测试现已删除/替换。最新用户要求已落实为 CNN 直接接 CPU 存储子系统，见 [新版验证](cnn_native_memory_verification_20261007.md)。下列旧结果仅用于追溯，不作为新版本验收结果。

日期：2026-10-07，工具：Vivado XSim 2026.1。测试使用本次独立目录中的日志和 VCD，没有复用交付包内旧仿真结果。

## 验证结论

真实 Control、生产 Datapath、实际 FPGA1 CNN、双口 SRAM RTL 和 B 口仲裁器的最小队列联调通过。CPU 流水线和 C1 保留，修改集中于两个存储 wrapper、新增系统顶层与访存适配器。CNN 原始 25 个 SV 文件及 files.f 与 ZIP 逐字节一致。

| 测试 | 结果 | 本次运行目录 |
|---|---|---|
| CPU/CNN 联调与适配器 | 两个 testbench 均 PASS | `build/runs/20261007_210516_830295_cnn_integration/` |
| Control 全量回归 | 1244 cases、30463 checks、0 failures；随机指令 1000 | `build/runs/20261007_205904_168992_9700_all_seed1/` |
| 原 B1 存储检查与旧顶层展开 | 30 checks，PASS | `build/runs/20261007_210144_145360_partner_datapath_b1/` |

这些目录相对工程根目录。每个目录有独立 `result.json`；Control 目录另有本次绘图，CNN 目录有两个本次 VCD。Control 报告中的 `real_datapath: NOT_RUN` 仅指该 Control 测试入口，真实 Datapath 验证在本页第一行所列独立运行中完成。

## CPU/CNN 实测内容

测试平台只预置指令 ROM 和初始空 SRAM。任务数据、任务表和启动配置均由真实 CPU 执行 RV32I 指令写入；没有用测试平台替 CPU 直接驱动 CNN 的 MMIO。

- CPU 读回 QUEUE_BASE=`0x800`、TASK_COUNT=`1`，保留槽写入后读回零。
- SB、SH 和未对齐 SW 不产生 CNN MMIO 写操作，原队列地址不变。
- 第一次计算 `7*2+3`，CPU 读回并保存 `0xA5A511A5`。
- 第二次把输入改为 8，CPU 再次启动并保存 `0xA5A513A5`；周围字节未被覆盖。
- CPU 在 CNN 运行时向不重叠的 SRAM A 口区域写入 `0x12345678`，结果正确。
- 模拟图像主设备持续向另一区域写 B 口，共完成 214 次；CNN 完成 32 次读和 2 次写，未报冲突或故障。
- CPU 共发出 3 次队列 START：前两次有效，第三次故意用描述符版本 2（非法），读到 STATUS=4；随后写 CONTROL=2，读到 STATUS=0。
- 仿真在 3860 ns 正常结束，testbench 有独立超时保护。

最后通过标记：

```text
PASS tb_cpu_cnn_integration CPU queue/readback, 17->19, guards, concurrent A/B, invalid descriptor, soft reset; starts=3 cnn_reads=32 cnn_writes=2 io_writes=214
```

## 适配器检查

独立 testbench 注入 grant 等待与读响应等待，检查读 grant 不提前产生 mem_ready、等待响应时不重复请求、数据返回时正确完成；覆盖读后立即写、连续写、写错误、读错误、非法同时读写、等待中复位。

错误时必须不确认成功并锁存 fault，整体复位后恢复。本测试中的延迟由 B1 响应驱动器注入；整合测试中的真实 SRAM 是同步一拍读取，不能把两者混称为已经测过各种真实 RAM IP 延迟。

## 源码与工具兼容

`partners/cnn/FPGA1/rtl/` 的 26 个文件（25 SV 加 files.f）逐字节核对 ZIP，没有修改。`rtl/compat/tensor_operator_engine.sv` 与原文件只有一处等价差异：

```systemverilog
// Original declaration rejected by XSim 2026.1:
// wire signed [31:0] pool_next,pool_sample=rsp_data;
wire signed [31:0] pool_next, pool_sample;
assign pool_sample = rsp_data;
```

`system_cnn.f` 已只选兼容副本，不会重复编译同名模块。最终联调 compile.log 没有 WARNING、CRITICAL 或 ERROR。

开发过程中发现并修正了 XSim net 声明兼容、Windows Tcl 文件路径转义，以及测试误用支持的 MatMul 编号作为非法编号的问题。失败运行目录保留用于追溯，以表格中的最后成功运行作为验收依据。

## 尚未覆盖

没有进行完整 MobileFaceNet 模型/人脸识别准确率验证、复杂多任务依赖链与所有算子的系统级回归、真实 UART 图像桥接入、目标 FPGA 综合/资源检查/布局布线/时序/上板。本次未编译执行 C 驱动；真实 CPU 仿真运行的是 testbench 生成的 RV32I 机器指令，C 文件为对应队列协议的软件调用示例。

物理共享 RAM 默认 256 KiB，全模型是否适配该容量仍需规划。B 口固定 CNN 优先不是任意流量下的公平仲裁。`cnn_mem_fault` 为系统诊断输出，没有新增 CPU 可读故障寄存器，也没有伪造 CNN error 输入。任务区域所有权必须由软件和图像桥共同遵守。

## 重现命令

```powershell
python scripts/run_cnn_integration.py
python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot
python scripts/run_partner_datapath_b1_tests.py
```

[小白版修改说明](CNN实际代码整合修改说明_小白版.md) · [当前连接图](SoC芯片封装与内部IO层级连接图.md)
