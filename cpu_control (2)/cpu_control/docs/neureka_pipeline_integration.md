# Neureka + Vicuna 分块双缓冲接入

本次实现最初约定的两级流水：Neureka 卷积 → Vicuna 可编程后处理。A/B 两块缓冲位于现有共享 SRAM。没有加入跨层融合、逐像素直通或新阵列架构。当前是新入口下的 RTL 实现，端到端验证状态见本文末尾，不能据此宣称上板通过。

## 工程入口与兼容范围

- SoC 顶层：`rtl/neureka_pipeline/face_soc_neureka_pipeline_top.sv`。
- CNN 顶层：`rtl/neureka_pipeline/neureka_pipeline_cnn_top.sv`，端口与原 `hybrid_cnn_top` 完全相同。
- 文件清单：`rtl/filelists/system_neureka_pipeline.f`。从项目根目录解析，路径包含空格时由构建脚本生成带引号的 XSim project。
- 主 CPU Control、生产 Datapath、IMEM、四银行 DATASRAM、图像桥与 clock_unit 保持原文件。板外仍是原 UART、时钟、复位和 LED 接口，SoC 内仍有六个平级模块。
- 原 hybrid/NVDLA 和独立 Neureka 入口保留，旧 filelist 不变。使用新入口时不混编旧 CNN 顶层。
- **硬件端口兼容不等于旧卷积命令兼容**。原 NVDLA CSB 配置和旧 opcode 队列不能原样执行；主 CPU 固件需要发送下述 Neureka tile 描述符。CPU 本身和其 MMIO 译码不需要改。
- 11 路 SRAM 客户端分配：0–8 为 Neureka HCI 桥，9 为描述符/配置读取，10 为 Vicuna。仲裁仍由原 datasram_banked 完成。没有新增外部缓存端口。

## 执行链与所有权

```text
串行：N(tile0) → V(tile0) → N(tile1) → V(tile1) → ...
流水：N(tile0,A) → N(tile1,B) → 等待/复用 A → N(tile2,A) → ...
                    V(tile0,A) → V(tile1,B) → V(tile2,A) → ...
```

每个槽位依次 FREE → FILL → READY → DRAIN → FREE。Neureka 的既有适配器等全部写回响应排空才报告 done，随后消费者才能读取；Vicuna 完成程序且存储状态 IDLE、向量待写寄存器清零后才释放槽位。两级按 tile 编号顺序运行，奇偶 tile 固定对应 A/B。消费者慢时生产者等待，生产者慢时消费者等待，均不能覆盖未消费数据。

每块有自己的 24 字 Neureka 原生配置。调度器将配置拷入内部寄存器，并把输出指针（word 2）替换为当前缓冲区。Vicuna 得到该槽地址、最终输出地址、有效字节数和程序模式。调度器通过已有 Vicuna 寄存器接口依次写参数并启动，等待 busy 确认，避免上一任务残留的 done 提前释放新任务。

默认贯穿两级的数据布局为 HWC。示例按输出行分块，3×3 卷积的输入必须多覆盖两行 halo；输入起点为原图的对应行，而输入行跨度仍是整幅输入的跨度。每块完成全部输入通道归约并量化后才送后处理，不把部分和当作最终 INT8 结果。

## MMIO 协议

CPU 仍只访问原邮箱范围（CNN_BASE 默认 0x40000000）：

| 外层偏移 | 含义 |
|---|---|
| 0x00 | 目标寄存器地址 |
| 0x04 | 写入数据 |
| 0x08 | 命令：1 写、2 读 |
| 0x0c | bit0 busy、bit1 done、bit2 error |
| 0x10 | 读回值 |
| 0x14 | 已完成邮箱事务数 |

下表是**经邮箱访问**的内部调度器寄存器，地址为 CNN_BASE + 偏移：

| 偏移 | 含义 |
|---|---|
| 0x00 | 写 1 启动一批；故障后需系统复位 |
| 0x04 | bit0 busy、bit1 done、bit2 fault、bit3 rejected |
| 0x08 | 描述符表起始地址，4 字节对齐 |
| 0x0c | tile 数量，必须非零 |
| 0x10 / 0x14 | 缓冲 A / B 起点，4 字节对齐 |
| 0x18 | 每个缓冲区容量，非零且为 4 的倍数 |
| 0x1c | bit0=1 强制串行；0 为双缓冲流水 |
| 0x20 | 已完成后处理 tile 数 |
| 0x24 | 本批运行周期 |
| 0x28 | 卷积适配器与 Vicuna 同时 busy 的周期 |
| 0x2c | 错误码 |
| 0x30 | 已完成卷积 tile 数 |
| 0x34 | A 状态 bits1:0，B 状态 bits3:2 |

错误码：1 批参数/程序未加载/向量忙；2 配置指针非法；3 tile 长度或目的地址非法；4 Neureka 报错；5 Vicuna 报错；6 SRAM 或卷积写边界错误；7 整批超时。fault 锁定并取消 CNN 存储请求，恢复需系统复位。中途配置写会被拒绝并设置 rejected，不改正在使用的参数。流水期间不允许外部写 Vicuna 参数或程序；只读访问会在内部参数写期间短暂等待，外层 CPU 邮箱仍零等待。

Vicuna 地址仍为 CNN_BASE + 0x40000，程序 RAM 为 +0x41000 到 +0x44fff。程序必须在启动前完整加载；硬件 loaded 只表示至少写过一个程序字，并不校验程序完整性。普通独立向量任务可在流水空闲时运行。新 irq 表示流水批完成（含故障），独立向量任务通过其状态寄存器轮询。

每个 tile 描述符 16 字节，小端 4 个 uint32：

```c
{ native_config_address, final_output_address, valid_bytes, program_mode }
```

模式 0 的示例程序按 INT8 元素处理，count 即字节数。其他自定义程序必须遵守描述符中有效字节范围，不应直接把已有 FP32 程序的“元素个数”混作字节数。当前硬件不解析程序，也不为任意程序证明访存范围。

## 软件与内存约束

`sw/neureka_pipeline/neureka_pipeline.h` 提供邮箱、程序加载、批启动和带预算的轮询函数。软件超时不会释放缓冲区，因为硬件可能仍在运行。启动前保留所有输入、权重、配置、描述符、A/B 和最终输出内存，运行期间 CPU/图像桥不得覆盖。

硬件检查 A/B 互不重叠、不覆盖描述符表，配置指针/描述符/缓冲区/输出在 SRAM 范围内，单块有效长度不大于容量，最终输出不覆盖 A/B 或描述符。卷积写还在 SRAM 接口处检查当前槽边界。**原生配置的输入/权重/scale 跨度和所有 tile 之间的目的地址仍由软件保证正确**，不允许最终输出破坏以后要读的配置、输入、权重或程序源。硬件尚无通用张量地址规划器。

`python scripts/gen_neureka_pipeline.py firmware/neureka_pipeline_demo` 生成示例：15×9×3 → 13×7×5 的 3×3 卷积，再做 alpha=1/4 的 INT8 PReLU，四块输出行数 4/4/4/1，末块 35 字节。两块各 1 KiB 保留区，同一输入连续串行和流水各执行一次。CPU 固件使用真实 RV32I 指令，程序 RAM 由 CPU 经邮箱加载；输入 SRAM 在仿真中预装载，UART 保持空闲。示例不是完整 MobileFaceNet 或自动 UART 启动固件。

生成的 `cpu.hex` 是 IMEM 初始化内容；`sram.hex` 按 32 位小端字排列。`vector.bin` 和 `vector.S` 取自已归档的旧 hybrid 示例，仅复用程序字节，不复用历史测试输出。新 oracle 独立计算卷积和 PReLU 的 455 个字节。

## 构建与验证

```text
python scripts/prepare_neureka_pipeline_deps.py
python scripts/neureka_pipeline_sources.py
python scripts/run_neureka_pipeline_control.py
python scripts/run_neureka_pipeline.py
```

第一步恢复原版本 Vicuna/CV32/FPU 依赖，不下载 NVDLA。Neureka 依赖沿用 `third_party/NEUREKA_SOURCES.md` 固定版本。依赖缺失时不要用占位计算模块替代。网络代理沿用项目 `network/proxy.psd1`，脚本不改变系统代理。

完整脚本使用 Windows 本机 XSim，独立 run 目录保存源码 SHA256、实际编译副本 SHA256、编译/展开/仿真日志和输入数据。由于上游语法兼容性，构建目录内移前了两处声明、去除了接口数组实参上的多余 modport；固定 128 位向量寄存器配置下，用等价常量数组替代 XSim 不能正确展开的可变长度切片。第三方原文件不改。采用上游 XSIM 宏和 relaxed enum 检查，不能把这当作完整 ISA 或形式验证。

## 当前边界

- pinned Neureka 的输入按无符号处理，示例限制在 0..127，权重和输出为有符号 INT8。负值 PReLU 输出不能未经处理直接作为下一层该 Neureka 的输入。CONF0 bit26 是 broadcast，不是 signed-input 开关。
- 仍需 SRAM 中转，四银行带宽和 Vicuna 的单请求存储口可能限制加速；双缓冲不保证每个形状都变快。
- 整批 watchdog 默认 50,000,000 周期；Vicuna 单任务仍使用原 200,000 周期限制，较大 tile 必须减小或另行分析预算。
- 旧的 FP32 程序顺序问题仍存在，本次仅以 INT8 路径验证流水，不扩展 FP32 可靠性结论。
- 保留 Neureka 的通用时钟门控/锁存存储实现；未完成指定 FPGA 型号的综合、时序收敛和上板测试，不能报 LUT/BRAM/DSP 或 MHz 指标。

## 本次结果

2026-10-19 本机运行：

1. `build/runs/20261019_212809_neureka_pipeline_control/result.json`：PASS。实际运行 scheduler RTL，计算级使用带延迟的握手模型；覆盖串行/流水、生产者或消费者较慢、7 字节尾块、无复位重启、忙时写拒绝、缓冲重叠、空批、配置越界、tile 超容量、存储故障、超时和未加载程序。模型测得串行 3551、流水 2372 周期，仅证明调度能重叠，不能视作真实 CNN 加速数据。
2. 通过文本签名检查，新旧 CNN 及六模块 SoC 的参数和端口声明完全一致。六个新增 Python 脚本通过语法检查，生成的四块有效长度为 140/140/140/35 字节。
3. `build/runs/20261019_213055_neureka_pipeline/`：真实 Neureka、CV32E40X、Vicuna、主 CPU 和 SRAM 已通过 XSim 编译、静态展开、模型生成；**运行未通过**。XSim 2026.1 在 0 ps、Iteration 0 的 CV32E40X alignment_buffer 内部出现 kernel exceptional condition。关闭优化后仍复现，后续在 `20261019_213325_neureka_pipeline` 尝试消除等价别名连接也未解决，该尝试未保留到正式源码/构建步骤。
4. `run_neureka_pipeline.py` 保留完整的串行/流水逐字节检验入口，崩溃会报告 FAIL，不会伪报 PASS。`run_neureka_pipeline_verilator.py` 提供不依赖旧缓存的另一入口；本机无可用 WSL/Verilator，因此此入口尚未执行。Linux/WSL 或已配置原生 Verilator+C++ 工具链后可运行 `python scripts/run_neureka_pipeline_verilator.py`。

因此本次交付状态是：**接入 RTL、双缓冲控制、驱动、示例固件和回归入口已实现；调度控制测试通过；真实核端到端数值正确性、真实加速比和 FPGA 综合/上板尚未验收。**
