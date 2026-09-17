# 验证记录与范围

2026-09-17阵列版本的最新记录见[8×8实测报告](../reports/systolic8/README.md)，设计与复现方式见[阵列说明](systolic8.md)。以下保留2026-09-15串行任务队列版本的历史记录。

验证日期：2026-09-15，包含RAM任务队列改版。本机实际使用 Icarus Verilog / VVP、Python 3.11、NumPy、ONNX 及 Yosys 执行。复现命令：

```powershell
python mobilefacenet/scripts/verify_all.py
```

最终机器可读报告在 `mobilefacenet/build/verification.json`。每次运行先标记 running，只有全部命令成功并逐字节检查最终输出后才写 passed。`build/` 是可重新生成的仿真产物，不属于 RTL 源码。

## 已通过的检查

| 验证层级 | 内容 | 通过标准 |
|---|---|---|
| 模块级 | 17 个 RTL testbench，包含基础模块联合测试、描述符FIFO、描述符读取器与队列顶层测试 | 编译/仿真退出0，存在 PASS，无断言失败 |
| 独立算子 | 15个整层用例：Conv3、stride、Conv1、DW3/7、DW stride/padding、ADD、ReLU/ReLU6、移位255、累加溢出、COPY、FINAL | 每一个实际 RAM 输出字节等于独立 Python 结果 |
| 残差块 | 4层：1×1扩展、DW3、1×1投影、ADD | 连续执行，不注入中间 Golden，保留残差输入 |
| 多层 RGB | 112×112×3 开始的15个任务，降采样到7×7，GDC7、Conv1到128、FINAL | 每层比对通过，最终写回恰好128字节 |
| ONNX 集成 | 未训练ONNX测试图，经BN融合、激活融合、Gemm→Conv1、活跃张量内存规划后生成9个硬件任务 | 导出参数进入真实RTL，9层输出逐字节一致，最终128字节一致 |
| RAM任务队列 | 同一9层测试链分别使用1、3、4条任务暂存容量；ONNX导出的9层再以队列执行，共36次逐层比对 | 每条队列只提交一次START，按序取描述符并执行，各层与最终128字节均一致 |
| 软件参考 | 7个 Python 自检查 | BN融合对比独立ONNX浮点执行器、手算算子、残差活跃性、任务描述符布局与RAM打包，以及不支持的算子/尺度与任务表地址错误拒绝 |
| 协议/异常 | MMIO锁、重复START、14种非法参数、RESET取消与重启、RAM等待稳定、相邻字节保护 | 非法参数零RAM访问；正确状态；未越界写入 |
| 队列异常 | 空队列、未对齐/地址回绕、错误版本/保留位/嵌套队列、任务表覆盖、第二任务失败、忙时START、取任务与写结果阶段RESET | 队列入口非法时零RAM访问；非法任务不写结果、不执行后续任务；复位排空后可重新启动 |
| 结构 | Yosys hierarchy/proc/opt/check -assert | 展开与结构检查通过；未进行器件映射或时序收敛 |

两套集成链分别保存 `synthetic112.rtl.log`、`onnx_fixture.rtl.log` 与对应 `*.rtl_features.bin`；报告保存最终数据 SHA-256，便于复查。普通回归日志中的 `tb_mobilefacenet.log` 会由最近一次运行覆盖，使用完整验证脚本可以保留两个场景。

队列另保存 `queue_depth1.log`、`queue_depth3.log`、`queue_depth4.log`、`onnx_queue.log` 和对应 `*.features.bin`。前三套最终输出相同；ONNX队列输出与同一ONNX测试图的原逐层MMIO输出相同。队列接口和复现命令见[任务队列说明](task_queue.md)。另已单独运行 `custom_wave.py`，用户现有输入的9次MAC及最终RAM结果54全部通过，原单算子波形实验保持兼容。

## Python Golden 的独立性

参考模型使用 NumPy CHW 滑动窗口和张量求和，未读取 RTL 的地址、累加器或计数器。先在 INT64 求和，再明确回绕到 INT32，执行算术右移、激活与饱和。

测试程序预装输入、权重、Bias；原模式由 MMIO 启动每一层，队列模式额外预装任务表并只启动整条队列一次。期望数据在单独的 golden 数组，**不会写入 DUT RAM 的层间激活区**。每层结束后比对整个输出区，还扫描 RAM 其他地址，检查没有意外覆盖。集成 RAM 对事务插入3周期等待；独立 Memory IF 测试插入5周期等待。

首个合法任务故意再写一次 START，检查拒绝重复启动并保留 ERROR，因此该任务最终 STATUS 预期为6；其余正常任务为2。不是首层计算失败。下一次合法 START 会清除旧 ERROR。

## 112×112 测试链

该链使用固定种子测试权重、较少通道，以在串行参考架构上快速检查完整空间尺寸和层间访存。它不是训练过的 MobileFaceNet 网络，也不宣称与某一论文网络的全部层数/通道一致。

```text
RGB 3×112×112
  Conv3 stride2 → 2×56×56
  DW3 stride2   → 2×28×28
  Conv1         → 4×28×28
  DW3 stride2   → 4×14×14
  Conv1         → 4×14×14
  DW3 stride2   → 4×7×7
  COPY 保存残差
  Conv1         → 8×7×7
  DW3           → 8×7×7
  Conv1         → 4×7×7
  ADD 残差      → 4×7×7
  Conv1         → 8×7×7
  DW7           → 8×1×1
  Conv1         → 128×1×1
  FINAL_OUTPUT  → OUTPUT_ADDR 的128字节
```

固定任务中第一个112×112普通卷积输出6272字节，测试统计1600318周期；最后FINAL复制128字节，统计1600周期。该统计包含测试平台的轮询/收尾开销，不是性能规格或频率承诺。

## 仍需真实模型完成的验证

目前未获得用户的 ONNX / PyTorch 模型及预处理输入，因此没有真实训练权重的逐层推理比对、识别准确率或余弦相似度结果。提供模型后，先运行导入器检查，再用实际预处理数据导出整数 Golden 并运行相同通用 testbench。

一些 MobileFaceNet 实现使用 PReLU，例如[公开实现中的网络定义](https://github.com/sirius-ai/MobileFaceNet_TF/blob/master/nets/MobileFaceNet.py)。当前按需求实现 ReLU/ReLU6，不把其他激活自动替换。BN融合遵循[ONNX BatchNormalization 推理公式](https://onnx.ai/onnx/operators/onnx__BatchNormalization.html)。ONNX 兼容性检查以本版硬件限制为准。

本版默认scale=1/16、权重按层选择2的幂尺度，仅提供部署基线。真实模型可能需要校准、不同层间尺度、per-channel requantization、PReLU或末端归一化等扩展；这些不能通过一张波形或测试权重的PASS代替验证。

## 集成限制

- 输出缓冲不可与仍读取的输入/权重/Bias重叠。导出器已经按最后使用位置复用RAM并保护残差。
- RAM没有byte-enable，INT8写使用读改写；外部不能同时修改相同32位字。没有完整SoC缓存一致性处理。
- RAM接口没有error或timeout输入；如果外部永远不给ready，加速器会持续等待。RESET也必须排空已呈现的事务。
- 输入与权重各49字节，采用分块窗口，未实现3/7行复用；地址计算中的可变乘除法和每字节写回适合功能基线，尚未做资源/时序优化。
- 波形用于定位时序，逐层自检查用于验证结果。VVP是执行文件，VCD才是波形文件。
