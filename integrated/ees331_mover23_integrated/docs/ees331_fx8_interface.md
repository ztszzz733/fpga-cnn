# EES-331：FX8 图像桥接入说明

当前交付范围按用户最新要求限定为**代码修改与仿真**。本文的接线、XDC、工程创建和综合入口作为后续参考草案保留，不属于已完成的板级验证；本次不继续上板、布局布线或时序签核。

本次新增 `face_soc_neureka_fx8_top`，使用 EES-331 的 J7 扩展连接器。板上 100 MHz 时钟经四分频产生 25 MHz 接口时钟。RX、TX 各为独立 8 位总线，均有 valid/ready 握手。每方向物理峰值为 25 MB/s，协议、对端存储器、CRC 检查、SRAM 仲裁会降低实际图像有效吞吐；目前没有上板实测值。

## 六模块结构与改动边界

```text
clock_unit ──100 MHz── CPU / IMEM / SRAM / CNN / 图像桥
                          │                │
                          └──原 MMIO───────┘
外部控制器/存储控制器
        ⇅ J7：8 位 RX + 8 位 TX + ready/valid + 时钟 + 复位
image_bridge_fx8
  ├─ fx8_link：25 MHz 链路、RX 512 字节 FIFO、TX 32 字节 FIFO
  └─ image_load_stream：描述符、请求/响应、CRC、32 位打包
        ⇅ 原 io_mem_* 端口
datasram_banked ⇄ CPU / CNN
```

顶层仍然直接实例化六个模块：`clock_unit`、`image_bridge_fx8`、`cpu_core_autoload`、`imem_rom`、`datasram_banked`、`neureka_pipeline_cnn_top`。图像桥内部的 FIFO 和协议引擎不增加 SoC 平级模块。

| 部分 | UART 入口 | 新 FX8 入口 |
|---|---|---|
| 对外连接 | UART RX/TX | 8 位 RX、8 位 TX、4 根握手、时钟、复位，共 22 根信号线及地 |
| 图像桥接收 | 串行字节 | 并行字节、跨时钟 FIFO |
| 图像写 SRAM | 每字节一次授权 | 合并成对齐 32 位写入；首尾不足一字时用 byte enable |
| CPU 加载控制 | 0x40/0x44，三线握手 | 相同 |
| SRAM 描述符 | 0x60 起五个字 | 相同 |
| CNN、CPU、SRAM 内部接口 | 现有接口 | 相同，无新增连接 |
| 帧间并行 | 输入/输出 A/B 缓冲、CPU 协作轮询 | 保留；同一份四帧 C 固件可用 |
| CNN 内部 | Neureka/Vicuna、分块双缓冲 | 保留 |

旧 `face_soc_neureka_pipeline_top` 及 UART 图像桥未被替换，选择新 top 才启用 FX8。不要同时选两个板级 top。该接口负责外部存储读取，TX 目前发送读取命令，不会自动把 CNN 结果回传给对端。

## J7 接线

来源：用户提供的《EES331_UserManual_v1.0_1220》印刷页 6、28–29、35–37；默认 PL bank34 为 3.3 V。下表方向均以 EES-331 FPGA 为参照。

| 信号 | 方向 | J7 脚号（按位 0→7） | FPGA 封装脚（按位 0→7） |
|---|---|---|---|
| fx8_rx_data[7:0] | 输入 | 17、18、19、20、22、23、24、25 | J15、K15、J16、J17、L16、L17、M17、N17 |
| fx8_tx_data[7:0] | 输出 | 26、27、28、29、30、31、32、33 | N18、M15、M16、J18、K18、J21、J22、J20 |
| fx8_rx_ready | 输出 | 34 | K21 |
| fx8_rx_valid | 输入 | 35 | L21 |
| fx8_tx_ready | 输入 | 36 | L22 |
| fx8_tx_valid | 输出 | 37 | K19 |
| fx8_clk | 输出 | 38 | K20 |
| fx8_reset_n | 输出，低有效 | 40 | L19 |
| GND | 公共参考地 | 77、78、79、80 | 板上地 |

J7-21 的 K16 是带 PUDC_B 功能的引脚，本方案避开；J7-39 不使用。J7 的电源脚不是数据信号。对接板需要匹配 3.3 V I/O 电平并共地，线束/转接板按连接器实际脚位核对，不能把差分命名里的 P/N 当成两端可以互换的位序。

板级公共脚：100 MHz `sys_clk=M19`；按键 S1 `rst_n_in=L18`，板上有上拉，按下为低；`led_ready/led_busy/led_error` 分别接 LED0/1/2 的 V4/U6/U5，高电平点亮。busy 沿用原语义，表示图像桥忙。

原先的 21 根接口信号之外，补上了一根复位输出。`fx8_reset_n` 在 FPGA 系统复位或桥故障时拉低，链路时钟域同步释放。对端必须清空请求解析状态和待发字节，禁止在复位期间发送；应在自己的接收逻辑中同步复位释放。接口时钟在系统复位时可能停低，桥故障后仍持续输出。

## 电气时序与握手

1. EES-331 提供 `fx8_clk`；对端不得再驱动这根线。
2. 每个上升沿，某方向同时为 `valid=1 && ready=1` 时，恰好传输一个字节。发送方在未被接收前必须保持 data 和 valid，不得只打一拍脉冲后丢弃字节。
3. 对端在时钟边沿后更新信号，在下一接收上升沿前满足建立/保持时间。两个方向独立握手；RX 指对端→FPGA。
4. 复位释放后，对端等待接口恢复，FPGA 在 CPU 提交描述符后主动发起读取。对端不可主动发送不属于当前请求的数据。

`constraints/ees331_fx8_timing.xdc` 给出的首版对端时序契约为：返回数据/ready 的时钟到输出加往返走线延迟 1–12 ns；对端接收的建立预算不大于 6 ns、保持预算不大于 2 ns。这是**设计假设**，不是手册给出的外部器件参数。需要用实际控制器与转接板数据修订，再完成全系统布局布线与时序签核。

RTL 综合分支使用 BUFG 和 ODDR 输出时钟；普通功能仿真用等价时钟波形。FIFO 使用 Gray 指针和两级同步器，约束限制指针传输延迟/位间偏斜，不对所有跨域路径一概设置 false path。

## 对端协议

协议保留原 UART 主动读取格式，传输介质改成带握手的字节流。所有多字节整数均为 little-endian。每次只允许一个未完成的请求，默认每包最多 256 个载荷字节。

| 字节 | FPGA→对端请求（固定 16 字节） | 对端→FPGA 回复（16+N 字节） |
|---|---|---|
| 0–3 | ASCII `IMIO` | ASCII `IMOR` |
| 4 | 2：读取 | 0：成功 |
| 5 | 包序号 tag | 原样返回 tag |
| 6–7 | 本次长度 N，1–256 | 原样返回 N |
| 8–11 | 外部源地址 | 原样返回源地址 |
| 12… | 请求 CRC32，4 字节 | N 字节载荷 |
| 12+N…15+N | — | 回复 CRC32，4 字节 |

CRC32 使用 reflected polynomial `0xedb88320`，初始值 `0xffffffff`，末尾取反。请求 CRC 覆盖前 12 字节；回复 CRC 覆盖前 12+N 字节。图像描述符还包含整批载荷 CRC，跨包持续累计。

对端实现流程：接收并检查 16 字节请求 → 从指定外部地址读取 N 字节 → 生成回复头和 CRC → 按 ready/valid 发完回复 → 等待下一请求。若外部读取失败，可以返回相同长度、非零状态并提供正确包 CRC；FPGA 会拒绝该批次并进入故障状态。实际控制板应使用并口/FIFO/DMA或 FPGA 逻辑完成字节握手，不能假设普通 MCU 软件 GPIO 轮询能跑满 25 MHz。

外部裸 Flash、SD 卡、SDRAM 的原生协议与本接口不同，需要对端存储控制器。具体器件未指定，因此没有为未知存储器编写 SPI/SD/DDR 控制器。

## 装载、流水与错误

CPU 仍写五字描述符 `{0x31444c49, source, destination, byte_count, payload_crc32}`，再通过原 0x40/0x44 触发和确认。CPU 使用同一份 `cnn_frames.h`，帧槽必须在计算、结果消费完后释放；输入 A/B 和 CNN 内部 tile A/B 是两组不同缓冲区。

```text
外部加载帧 n+1 → RX FIFO → 包 CRC → 拼成 32 位 → 空闲输入缓冲
                                      与以下工作重叠
已就绪帧 n    → Neureka 分块卷积 ⇄ 中间双缓冲 ⇄ Vicuna → 输出缓冲
CPU           → 轮询调度 / 处理已完成结果 / 准备后续描述符
```

包 CRC 通过前不会写入该包的载荷。整帧 CRC 失败时，载荷可能已经写入空闲帧缓冲，但该帧不会提交给 CNN。所有桥故障锁存，CPU 确认完成后也不自动恢复；需系统复位，FIFO 和对端同时清空。超时计数使用 100 MHz 系统时钟，默认 1 秒，适用于发送阻塞、接收无进展、SRAM 阻塞等阶段。TX FIFO 能容纳整个读取命令，因此对端完全不接收命令通常体现为等待回复超时（错误 3）。

错误码沿用原桥：1 参数非法；3 回复超时；4 包头/状态/tag/地址/长度不符；5 包 CRC；6 SRAM 写错误；7 SRAM 写等待超时；8 整批 CRC；9 非法状态；10 描述符地址非法；11 描述符超时；12 描述符读错误；13 描述符 magic 错误；新增 14 表示请求字节流发送阻塞。内部 `error_code` 用于调试，CPU 仍接收原有错误握手，不新增 MMIO 地址。

## 编译与验证入口

在 `cpu_control` 目录运行：

```powershell
python scripts/run_fx8.py
python scripts/neureka_fx8_sources.py
python scripts/run_fx8.py --real-cores
```

`run_fx8.py` 默认使用真实主 CPU、桥、SRAM、mailbox 和 tile 调度器，CNN 运算使用明确标注的测试模型。`--real-cores` 使用固定版本的真实 Neureka/Vicuna 源码，不允许模型替代。生成生产 filelist 及运行真实内核，需要本地 `third_party` 依赖完整；当前 `fpga-cnn-moon` 镜像中已有依赖。

生产清单 `rtl/filelists/system_neureka_fx8.f` 不包含测试运算模型。后续板级工作的草案入口为 `scripts/create_fx8_project.tcl` 和 `scripts/run_fx8_synth.py`，当前不作为已验证交付入口。工程创建脚本选择 top `face_soc_neureka_fx8_top`，器件 `xc7z020clg484-1`，现有同名目录会拒绝覆盖。

该脚本不自动生成 bitstream。上板前仍需设置应用 IMEM 初始化文件，并安排权重、配置表等 SRAM 数据的启动初始化；四帧测试里的 `$readmemh` 预装载属于 testbench，不会自动成为板上 SRAM 初始化。此次没有改变原 CPU 启动方式或引入可写 IMEM。

本次实测结果和限制见 [FX8 验证记录](fx8_verification_20261022.md)。
