# NVDLA 小图适配说明

> 2026-10-13 新增联合 SoC 入口：原 RV32I CPU 已通过 CNN 命令寄存器控制 NVDLA 和 Vicuna 2，三项小测试通过。见 [联合接入说明](hybrid_soc_integration.md)。下文仍描述此前独立 NVDLA 适配测试；不能把其 host 驱动流程与新版 CPU 固件测试混淆。

本次目标：把真实开源 NVDLA 接到本工程的 CPU MMIO 和 banked DATASRAM 接口，先验证小尺寸计算、握手、写回结果。采用独立入口，保留已有 NEureka 版本。不运行大图，不据此声称性能提升。

**2026-10-12 验证结果：三项小测试全部 PASS，均通过官方 CRC32 校验。** 正式结果来自 `build/runs/20261012_145608_nvdla_small`；存储桥短测试 PASS，六模块 SoC 展开检查 PASS。波形和具体耗时见 `deliverables/nvdla_small/README.md`。

## 实际接入结构

```
CPU 的 MMIO → CSB 适配器 → NVDLA 原生配置寄存器
                                  │
                         官方卷积 / SDP / PDP
                                  │ 64 位主存接口
                              存储适配桥
                                  │ 2 路 32 位客户端
                         现有 datasram_banked
```

CNN 封装为 `rtl/nvdla/nvdla_cnn_top.sv`。`rtl/nvdla/face_soc_nvdla_top.sv` 提供 CPU、CNN、DATASRAM、IMEM、IMAGE_BRIDGE、CLOCK 六模块接线入口。适配器放在 CNN 内部，顶层模块数量不增加。

本次功能仿真使用 `nvdla_small_harness`：测试程序代替 CPU 发 MMIO 请求，通过 SRAM 的 CPU A 口装入特征和权重；NVDLA 从真实 `datasram_banked` 读取并写回，再由 A 口读回校验。**这不是 UART → CPU 指令执行 → CNN 的完整 SoC 仿真**。六模块入口另做编译展开检查，原有 CPU、UART 和 IMEM RTL 不改。

## 采用的官方版本

- 仓库：https://github.com/nvdla/hw
- 分支来源：master；固定提交 `1a65f1f5b48268accaa47c95f95c2601918be095`。
- 配置：`nv_small`，INT8，atomic C=8、K=8，主存接口 64 位；包含卷积、SDP、PDP。
- 本地依赖：`third_party/nvdla`，保持官方计算 RTL；许可证见该目录 `LICENSE`。
- 官方 vcp/eperl 生成裁剪后的 RTL。checked-in CFGROM RTL 缺少地址头文件时，从同提交的 `NVDLA_CFGROM.rdl` 提取顺序寄存器地址，不替换卷积或池化逻辑。

依赖目录不纳入本工程 Git。新机器可先 `git clone https://github.com/nvdla/hw.git third_party/nvdla`，然后在该目录 `git checkout 1a65f1f5b48268accaa47c95f95c2601918be095`。本机使用已配置的项目网络代理。

## 接口变化

| 接口 | 方向 | 含义 |
|---|---|---|
| `mmio_addr[31:0]` | CPU → CNN | 字节地址，默认配置范围 0x40000000–0x4003FFFF |
| `mmio_wdata[31:0]`、`mmio_we` | CPU → CNN | 写 NVDLA 配置寄存器 |
| `mmio_re` | CPU → CNN | 读寄存器，包括完成状态 |
| `mmio_rdata[31:0]`、`mmio_ready` | CNN → CPU | 读回值/本次事务完成；写入也等待 NVDLA 确认 |
| `cnn_valid[0]`、`cnn_addr[31:0]` | CNN → SRAM | 32 位读取请求和地址；两次读拼成一个 64 位返回 |
| `cnn_valid[1]`、`cnn_addr[63:32]`、`cnn_wdata[63:32]` | CNN → SRAM | 写回请求、地址、数据 |
| `cnn_byte[1]` | CNN → SRAM | 完整 4 字节用整字写，部分掩码用逐字节写，保留其余字节 |
| `cnn_ready[i]` | SRAM → CNN | 本周期能接受客户端 i 的请求，需要与 valid 同时为 1 |
| `cnn_response[i]`、`cnn_rdata` | SRAM → CNN | 已接受事务的完成响应；读事务同时返回数据 |
| `irq` | NVDLA → 封装观察点 | 未屏蔽的引擎完成中断；本版 CPU 通过寄存器轮询完成 |
| `fault` | 适配器/SRAM → 观察点 | 非法地址、突发最后一拍不匹配或 SRAM 故障；需复位恢复 |

CSB 内部是 16 位**字地址**，适配器将 MMIO 偏移右移两位。原 CNN MMIO 窗口只有 4 KB，NVDLA 六模块入口将其扩大为 256 KB。例如 GLB 完成状态的 CPU 地址为 `0x4000100C`，SDP_0 完成为 bit0，PDP_0 完成为 bit4。

原来 11 路 SRAM 客户端的接口形状保留，本版只占用客户端 0（读）和 1（写），其余客户端关闭。桥的读写方向各允许一笔突发在途，能同时推进读和写，但没有实现高带宽多 outstanding/乱序返回。它是功能适配基线，不是 NVDLA 的最佳存储架构。

## 小测试做了什么

| 官方用例 | 内容 | 校验 |
|---|---|---|
| `dc_1x1x8_1x1x8x1_int8_0` | 1×1 空间、8 输入通道的最小卷积 | 官方输出 CRC32 `8f68a2ae` |
| `dc_6x8x192_3x3x192x32_int8_0` | 6×8 空间、192 输入通道、32 输出通道、3×3 卷积及 SDP 输出 | 官方输出 CRC32 `ee3e1e0c` |
| `pdp_8x8x64_2x2_int8` | 8×8 空间、64 通道、2×2 池化 | 官方输出 CRC32 `33d91a71` |

三项分别独立复位运行，**不是串联成同一网络**。官方特征/权重字节和算术配置保持不变，仅将高地址内存区域映射到本地 256 KB SRAM。每项 `memory_map.json` 记录地址变化，`commands.txt` 记录实际寄存器命令，`output.bin` 保存硬件写回后读出的内容。官方数据是已排布的特征张量，不是直接 RGB 图片文件。

单独桥测试覆盖：部分字节掩码、两拍突发、读写 ID、读返回/写完成的反压保持、跨 SRAM 边界故障。六模块入口检查只说明 RTL 能展开，不表示已经运行完整 CPU 固件。

## 怎样看波形

交付目录 `deliverables/nvdla_small` 中，每个用例有 `overview.png`、`first_write.png`、`control.vcd`、`control.gtkw` 和 `open_wave.cmd`。双击 `open_wave.cmd` 用工程自带 GTKWave 打开。

建议按下面顺序看：

1. `phase=1`：测试程序装入特征和权重；`host_we` 是写入 SRAM，不是 UART。
2. `phase=2`：MMIO 配置；`mmio_we/re` 发请求，`mmio_ready` 表示已确认。
3. `phase=3`：等待算子完成。`cnn_valid[0] && cnn_ready[0]` 表示 SRAM 接受一个读请求，`cnn_response[0]` 表示对应读完成。`read_beats` 每交给 NVDLA 一个完整 64 位数据递增一次。
4. `cnn_valid[1] && cnn_ready[1]` 表示 SRAM 接受一次写回，`cnn_response[1]` 表示写响应。`write_beats` 表示已完成的 64 位写拍数；首次递增比第一笔 32 位/字节写稍晚。
5. `irq=1` 后检查完成状态，再进入 `phase=4` 读回并校验 CRC；`phase=5` 为测试通过后的结束区间。`fault` 全程应为 0。

`config_state`：0 空闲、1 发 CSB、2 等应答、3 返回 CPU 完成。
`read_state`：0 空闲、1 发 SRAM 读、2 等 SRAM、3 返回 NVDLA。
`write_state`：0 等地址、1 等写数据、2 发 SRAM 写、3 等响应、4 完成本拍、5 返回写完成。

这些是接口状态，不能把 `read_state`/`write_state` 或一个 valid 拉高直接解释成所有 MAC 正在运算。PNG 从本次真实 RTL 控制端口采样的 VCD 绘制，图中子位用于区分读写客户端；GTKWave 中总线只出现一次。

时间轴假设 100 MHz，每周期 10 ns。`metrics.json` 中 `hardware_ns_at_100MHz` 包含装载、配置、计算、读回的硬件仿真周期；实际电脑运行时间见总目录 `result.json` 的 `compile_seconds` 和各测试 `simulation_seconds`，两者不要混淆。

## 复跑和下一步

本机在 WSL Ubuntu-22.04 下运行：

使用 Verilator 5.38 做 RTL 功能仿真，**必须保留官方 RAM 模型的 `#delay`**：默认 `--timing --timescale-override 1ns/1ps`，C++ 驱动按 100 MHz 推进时钟，并执行两次时钟边沿之间的定时事件。这不是布局布线后的门级延迟仿真。

首次排查时，忽略 RAM 延迟的版本能完成任务，但 6×8 多通道卷积和 8×8 池化的 CRC 错误；相同构建条件下，官方原始 AXIResponder 测试平台也复现了卷积 CRC 差异。保持输入、算术配置、适配 RTL 和官方计算 RTL 不变，恢复 RAM 延迟后，两项均匹配官方预期。不要把此前的 ERROR 运行目录当作正式结果，也不要为了减少编译时间改回 `--no-timing`。`--no-timed-ram` 仅供复现这一诊断问题。

```powershell
wsl -d Ubuntu-22.04 -- python3 '/mnt/d/code/FPGA1/cpu_control (2)/cpu_control/scripts/run_nvdla_small.py'
wsl -d Ubuntu-22.04 -- python3 '/mnt/d/code/FPGA1/cpu_control (2)/cpu_control/scripts/run_nvdla_small.py' --reuse
wsl -d Ubuntu-22.04 -- python3 '/mnt/d/code/FPGA1/cpu_control (2)/cpu_control/scripts/check_nvdla_adapters.py'
```

首次生成/编译一次；`--reuse` 必须匹配已编译适配 RTL 和测试驱动的哈希。每次产生独立运行目录。编译上限 900 秒，每个小测试电脑执行上限 120 秒，同时有 2,000,000 周期保护。缓存位于工程根下 `.nvdla_build/nv_small`，不放易清理的 Linux 临时目录。

旧 NEureka 描述符/固件不能直接用于 NVDLA。后续需要编写或移植 CPU 的 NVDLA 寄存器驱动，将张量排布、权重排布、寄存器表装入运行流程，再接入 UART 全链路；目前不宣称通用模型编译器、人脸识别网络或多帧并行已完成。

后续多个相同算子的自动分配也尚未实现。优先保持 NVDLA 内部稳定，在 CNN 封装内部增加独立算子和软件调度，用共享 SRAM 和完成标志衔接；内存带宽验证通过后，再考虑更深的多算子流水。
