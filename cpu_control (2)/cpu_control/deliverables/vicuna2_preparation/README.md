# Vicuna 2 独立验证准备交付

> 更新：2026-10-12 WSL 已恢复，硬件模型已编译完成；工具链准备期间用户主动暂停以重启电脑。
> 最新断点见 [PAUSED.md](PAUSED.md)。下文“环境阻塞”是更早的历史状态，不能作为当前进度。

**当前状态：环境阻塞，未完成硬件验证。通过的 RTL 测试数为 0；没有仿真波形。**

本次目标是独立运行 CV32E40X 小控制核、标量浮点单元和 Vicuna 2，
证明同一份硬件可以执行不同算子程序。尚未接入项目主 CPU、NVDLA 或 DATASRAM。

## 已完成

- 下载官方测试工程及固定版本的控制核、向量核、浮点依赖。
- 下载 xPack RISC-V GCC 15.2.0-1 的 Linux 预编译工具链（压缩包约 413 MiB），
  SHA-256 与发布方 `.sha` 文件一致；未修改系统默认编译器。
- 复用现有 Verilator 5.038，补齐该版本官方 CMake 接口模板；GTKWave 可复用。
- 准备最小配置：128 位向量寄存器、64 位算术通路、32 位存储接口。
- 准备九个真实向量汇编程序及独立 Python 预期结果；脚本通过 Python 语法检查。
- 构建最多 2 个并发编译线程；每个测试最多 60 秒、200000 执行循环。

## 测试清单（全部 NOT_RUN）

| 程序 | 目标 |
|---|---|
| int32_residual | INT32 残差相加 |
| int32_mul | INT32 逐元素乘法 |
| int32_prelu | INT32 PReLU，系数 0.25，输入为 4 的倍数 |
| fp32_add | FP32 加法 |
| fp32_mul | FP32 乘法 |
| fp32_prelu | FP32 PReLU，显式测试浮点比较和选择 |
| fp16_add | FP16 加法 |
| fp16_mul | FP16 乘法 |
| int32_dot | INT32 向量乘法、求和和跨批次累加 |

每项有 19 个输入元素，包含正负数、零和非完整向量尾部。
各目录的 `test.S` 是待执行的程序；`expected.bin/expected.json` 是预期结果，
**不是仿真输出**。尚未用交叉编译器验证这些程序，也尚未验证浮点指令功能。

## 阻塞原因

WSL 多次返回：

```text
Wsl/Service/CreateInstance/CreateVm/HCS_E_CONNECTION_TIMEOUT
```

曾成功进入 Linux 源码准备阶段，但整仓复制遇到很慢的文件元数据处理；
已只中止该任务，改为在 Windows 端选择性准备实际需要的源码，准备成功。
之后 WSL 再次无法创建虚拟机。确认没有正在运行的 Linux 任务并清理启动状态后，
最后一次重试仍失败。因此未进入 RTL 编译，没有硬件周期数、仿真耗时或 PASS。
这也不代表 Vicuna 2 的 RTL/算子测试失败；它们还未被执行。

历史记录：

- `build/runs/20261012_164540_vicuna_small`：准备阶段中止，标为 `INTERRUPTED_PREPARATION`。
- `build/runs/20261012_170102_vicuna_small`：源码已准备，但沙箱内 Git 子模块状态读取失败。
- `build/runs/20261012_171019_vicuna_small`：选择性准备完成，标为 `PREPARED`。

## 恢复后运行

先使 Ubuntu-22.04 能正常启动，再运行本目录 `resume.cmd`。
它执行一次有上限的构建与九个小测试，不做大图仿真，也不自动重试 WSL。
源码、工具链压缩包和准备缓存均已保存，不必重新下载。

后续结果位于新的 `build/runs/<时间>_vicuna_small`；只有实际执行后逐字节匹配
预期数据，测试才能标为 PASS。浮点比较的上游实现仍需特别核对。

更多配置与边界见 `docs/vicuna2_small_validation.md`。
