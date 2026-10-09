# SoC 顶层连线与总体 I/O 说明（小白版）

更新：2026-10-08。本文是当前六模块接线依据，替代旧图中的“CPU 存储子系统 + 外部仲裁器”。

## 1. 先看结论

**芯片内的六个大模块就是 cpu_core、cnn、datasram、IEM、image_bridge、clock_unit。**
CPU 是执行程序的人，IEM 是程序书，datasram 是大家共用的数据仓库。CNN 去仓库拿数据，不是去 CPU 里面拿数据。

你说的 IEM 在代码里叫 IMEM，实际模块名是 `imem_rom`。它和 datasram 都在 CPU 外面，与 CPU 平级；不是藏在 cpu_core 里面的两块存储器。

![六模块横向连接图](docs/figures/soc_cpu_mem_io.png)

[可放大 SVG](docs/figures/soc_cpu_mem_io.svg) · [修改说明](docs/CNN实际代码整合修改说明_小白版.md) · [UART 协议](docs/uart_image_bridge_protocol.md)

| 图上名称 | 实际模块 / 顶层实例 | 职责 |
|---|---|---|
| cpu_core | cpu_core / u_cpu_core | 内含原 cpu_control + cpu_datapath，取指、执行、访存和访问 CNN 寄存器 |
| cnn | mobilefacenet_accelerator_top / u_cnn | 原始 FPGA1 CNN；accelerator_regs 接 CPU，accelerator_mem_if 接 datasram |
| datasram | datasram / u_datasram | 共享双口存储器；A 给 CPU，B 给 CNN 和图像桥，仲裁和读写完成逻辑全部在内部 |
| IEM | imem_rom / u_imem | 同步读指令 ROM，保存 CPU 固件 |
| image_bridge | image_bridge / u_image_bridge | 真实 UART 收发、CRC32、分块写 SRAM、读回 SRAM、错误回包 |
| clock_unit | clock_unit / u_clock_unit | 系统时钟直通，外部低有效复位异步拉低、经过 3 个时钟沿同步释放 |

真正板级顶层是 `rtl/soc/face_soc_top.sv`，直接实例化上面六个模块。顶层只是把线接起来，不是第七个功能模块。
`face_soc_cnn_top.sv` 仅是保留给 CPU/CNN 仿真的四模块测试入口；不能把它当成当前板级顶层。

**没有独立适配器，也没有独立的系统 B 口仲裁模块。** 仲裁功能没有消失，而是直接写在 datasram 内部。
CNN 原包内部也有一个 `accelerator_mem_arbiter`，用于 CNN 内部计算单元之间的选择，和系统共享 SRAM 的仲裁不是一回事，保留不动。

## 2. 看懂三组线

- 地址线：告诉对方“访问哪里”。本工程地址都是 32 位字节地址，地址加 1 表示下一个字节。
- 数据线：告诉对方“写什么 / 读到了什么”。32 位数据等于 4 个字节；写数据和读数据是两组不同的线。
- 信号线：告诉对方“读还是写、哪些字节有效、完成没有、出错没有”。下面逐根列出具体名字。

表中 `[31:0]` 是 32 根并行线，不是串口；`[3:0]` 是 4 根；没有括号的控制信号都是 1 根。箭头表示谁输出、谁输入，不表示同一根电线双向驱动。时钟和复位是公共信号，另列，不重复算入每条接口。

## 3. ① cpu_core 与 IEM：读程序

| 线组 | 具体信号 | 位宽 | 来源 → 去向 | 用途 |
|---|---|---:|---|---|
| 地址 | imem_addr[31:0] | 32 | cpu_core → IEM | 指令地址 |
| 数据 | imem_rdata[31:0] | 32 | IEM → cpu_core | 返回一条指令 |
| 信号 | imem_re | 1 | cpu_core → IEM | 读指令使能 |

合计：CPU 发出 33 位，IEM 返回 32 位。没有写口、没有 ready、没有额外仲裁。
在时钟上升沿接收地址，沿后给出对应指令。取指等待与错路处理仍由原 Datapath 负责。

## 4. ② cpu_core 与 datasram：普通数据 A 口

| 线组 | 具体信号 | 位宽 | 来源 → 去向 | 用途 |
|---|---|---:|---|---|
| 地址 | dmem_addr[31:0] | 32 | cpu_core → datasram | 数据地址 |
| 数据 | dmem_wdata[31:0] | 32 | cpu_core → datasram | 待写数据 |
| 数据 | dmem_rdata[31:0] | 32 | datasram → cpu_core | 返回的整个 32 位字 |
| 信号 | dmem_re | 1 | cpu_core → datasram | 读使能 |
| 信号 | dmem_we | 1 | cpu_core → datasram | 写使能 |
| 信号 | dmem_wstrb[3:0] | 4 | cpu_core → datasram | 四个字节各自的写开关 |

合计：CPU 发出 70 位，datasram 返回 32 位。读、写不能同时拉高。
A 口不排队、不增加 ready/stall，保留原 CPU 所需的固定一拍同步读。CPU 字节/半字的选取与合法性检查仍在原 LSU；datasram 用地址选中整个字，用 wstrb 控制写入哪些字节。

## 5. ③ cpu_core 与 cnn：MMIO 控制口

| 线组 | 具体信号 | 位宽 | 来源 → 去向 | 用途 |
|---|---|---:|---|---|
| 地址 | mmio_addr[31:0] | 32 | cpu_core → cnn | CNN 寄存器地址 |
| 数据 | mmio_wdata[31:0] | 32 | cpu_core → cnn | 写寄存器的数据 |
| 数据 | mmio_rdata[31:0] | 32 | cnn → cpu_core | 读寄存器的数据 |
| 信号 | mmio_re | 1 | cpu_core → cnn | 读寄存器 |
| 信号 | mmio_we | 1 | cpu_core → cnn | 写寄存器 |
| 信号 | mmio_ready | 1 | cnn → cpu_core | 当前寄存器访问完成 |

合计：CPU 发出 66 位，CNN 返回 33 位。顶层把这些线命名为 `cnn_mmio_*`，不是增加了另一套端口。
直接接 CNN 内部 accelerator_regs，不经过 datasram，也不经过旧 cnn_mmio_regs。实际 FPGA1 MMIO 是零等待响应，与现有 CPU 匹配；不能擅自换成多拍 MMIO 外设。
默认基址 `0x40000000`；`+0x08` 是 QUEUE_BASE，`+0x18` 是 TASK_COUNT，启动 CONTROL 写 `0x3D`。STATUS 从 `+0x04` 读，没有额外 STATUS 硬件线。

## 6. ④ cnn 与 datasram：原生存储 B 口

| 线组 | 具体信号 | 位宽 | 来源 → 去向 | 用途 |
|---|---|---:|---|---|
| 地址 | mem_addr[31:0] | 32 | cnn → datasram | 对齐到 4 字节的访问地址 |
| 数据 | mem_wdata[31:0] | 32 | cnn → datasram | 待写的整个字 |
| 数据 | mem_rdata[31:0] | 32 | datasram → cnn | 返回的整个字 |
| 信号 | mem_read | 1 | cnn → datasram | 请求读，保持到 ready |
| 信号 | mem_write | 1 | cnn → datasram | 请求写，保持到 ready |
| 信号 | mem_ready | 1 | datasram → cnn | 本次成功读写完成 |

合计：CNN 发出 66 位，datasram 返回 33 位。这一组直接接 datasram，**不连 cpu_core，不经过 CPU 执行通路。**
没有 CNN 的 gnt/rvalid/be/error 端口，不给 CNN 虚构这些端口。CNN 字节写由其原有 accelerator_mem_if 先读整个字、修改目标字节、再写回整个字。

读时序例子（E0、E1 是相邻上升沿）：

| 时刻 | datasram / CNN 行为 |
|---|---|
| E0 前 | CNN 保持地址和 mem_read=1；尚未采到 SRAM 数据，因此不能提前 ready |
| E0 | 若 B 口空闲，datasram 接单并读存储数组，记录“本次属于 CNN” |
| E0 后至 E1 前 | mem_rdata 是正确读数据，mem_ready=1；B 口不接受第二笔 |
| E1 | CNN 采样返回数据，datasram 清除在途标志；同一读请求不会重复接收 |

写操作在成功选中、地址合法且无冲突时给 ready，并在采样该 ready 的上升沿真正写入。
遇到非法地址、非对齐访问、非法同时读写、与 A 口冲突等错误，锁存 `cnn_mem_fault`，不假装成功，不返回假数据；CNN 可能一直等 ready，恢复要系统复位，不能只写 CNN 软复位。

## 7. ⑤ image_bridge 与 datasram：图像数据 B 口

| 线组 | 具体信号 | 位宽 | 来源 → 去向 | 用途 |
|---|---|---:|---|---|
| 地址 | io_mem_addr[31:0] | 32 | image_bridge → datasram | 对齐到 4 字节的地址 |
| 数据 | io_mem_wdata[31:0] | 32 | image_bridge → datasram | 待写数据 |
| 数据 | io_mem_rdata[31:0] | 32 | datasram → image_bridge | 读返回字 |
| 信号 | io_mem_req | 1 | image_bridge → datasram | 请求，未获准前保持地址和数据 |
| 信号 | io_mem_we | 1 | image_bridge → datasram | 1 写、0 读 |
| 信号 | io_mem_be[3:0] | 4 | image_bridge → datasram | 写时选择字节；读时必须为 0 |
| 信号 | io_mem_gnt | 1 | datasram → image_bridge | 请求被接收；写在这一沿完成 |
| 信号 | io_mem_rvalid | 1 | datasram → image_bridge | 读返回有效 |
| 信号 | io_mem_error | 1 | datasram → image_bridge | 写随 gnt、读随 rvalid 报错 |

合计：图像桥发出 70 位，datasram 返回 35 位，**error 保留**。
写时在 req && gnt 的上升沿一起检查 error；读时 gnt 只是接单，必须再等 rvalid。
UART 一次缓存最多 256 字节，CRC 和整段地址范围正确后才访问 SRAM；每次选择一个字节写入或从返回字中取一个字节。不是把 UART 8 位数据线直接连 RAM 32 位数据线。

## 8. 仲裁并入 datasram 后怎样工作

A 口始终属于 CPU。B 口空闲时 CNN 优先，其次图像桥；一个已接收的读必须返回后才让出 B 口。
这些选择、读返回归属和数据存储，都在 `rtl/soc/datasram.sv` 里，没有另外实例化 sram_b_arbiter 或 adapter。

同一个时钟沿，两口访问同一个 32 位字且至少一方写入，A 口优先，B 口报错；两口都读允许。不同字可以并行访问。
注意：“同一个字”包含其中四个字节，即便双方写不同字节，也按冲突处理。

**仲裁只解决“谁先用硬件端口”，不保证整帧图像或 CNN 的读改写是原子的。**
CPU / 电脑不要在 CNN 运行时修改它正在使用的图像、权重、描述符或输出区。建议先传完并校验、再用固件约定的 mailbox 通知 CPU 启动，CNN 完成后再读结果。mailbox 地址及完整人脸识别固件尚需项目约定，本次未凭空指定。
CNN 连续占 B 口可能使图像桥等待到超时；不要在 CNN 运算中持续发送 RAM 写入。

## 9. 公共时钟、复位与状态线

| 线组 | 具体信号 | 位宽 | 来源 → 去向 |
|---|---|---:|---|
| 信号 | clk | 1 | clock_unit → cpu_core、cnn、datasram、IEM、image_bridge |
| 信号 | rst_n | 1 | clock_unit → 同上五个模块 |
| 信号 | cnn_mem_fault | 1 | datasram → 顶层 LED 组合逻辑 |
| 信号 | bridge_ready | 1 | image_bridge → 顶层 LED 组合逻辑 |
| 信号 | bridge_busy | 1 | image_bridge → 顶层 LED 组合逻辑 |
| 信号 | bridge_error | 1 | image_bridge → 顶层 LED 组合逻辑 |

这里没有地址线和数据线。顶层仅三条组合赋值，不是单独状态模块：
`led_ready = bridge_ready && !cnn_mem_fault`；`led_busy = bridge_busy`；`led_error = bridge_error || cnn_mem_fault`。

bridge_ready 表示桥可收新包；busy 表示正在收包、访存或回复，**不是 CNN busy**。
bridge_error 对错误进行锁存，系统复位清除；普通 CRC/参数/范围错误回复后仍能继续接收。内存等待超时则停机到复位，防止迟到读数据混入下一包。

clock_unit 不倍频、不降频、不带 PLL。所有模块同频。外部 rst_n_in 拉低时内部复位立即拉低，释放需连续 3 个时钟上升沿；同步复位的模块在后续上升沿执行复位/恢复。按键机械去抖、电压和引脚约束需按实际板卡补齐。

## 10. 芯片封装总体 I/O：7 根数字信号

| 线组 | 顶层引脚 | 位宽 | 来源 → 去向 | 小白解释 |
|---|---|---:|---|---|
| 信号 | sys_clk | 1 | 板载晶振 → clock_unit | 外部时钟 |
| 信号 | rst_n_in | 1 | 板上复位按钮/复位电路 → clock_unit | 低有效复位 |
| 信号 | uart_rx | 1 | USB-UART TX → image_bridge | 电脑发来的串行数据 |
| 信号 | uart_tx | 1 | image_bridge → USB-UART RX | 返回给电脑的串行数据 |
| 信号 | led_ready | 1 | 顶层组合逻辑 → 板载 LED | 串口接收就绪 |
| 信号 | led_busy | 1 | 顶层组合逻辑 → 板载 LED | 图像桥忙 |
| 信号 | led_error | 1 | 顶层组合逻辑 → 板载 LED | 图像桥或 CNN 存储故障 |

封装没有并行地址线/数据线。UART 在一根线上按时间顺序传地址和数据，不能因此把 uart_rx 记成 32 位。
3 输入 + 4 输出 = 7 位，不包括电源、地、JTAG/下载专用脚。UART 两端必须共地并满足 FPGA I/O 电压，不能把 RS-232 正负电压直接接 FPGA；电源/地不是这里的 RTL 端口。LED 默认高电平有效，低有效开发板需在板卡约束/包装层适配。

## 11. 怎样编译、验证和上板

使用清单 `rtl/filelists/system_cnn.f`，板级顶层选 `face_soc_top`。不要把所有历史 SV 文件全选进去。
默认 CLOCK_HZ=50 MHz、BAUD=115200、IEM=64 KiB、SRAM=256 KiB；CLOCK_HZ 必须填实际输入时钟频率，UART 位周期用整数 CLOCK_HZ/BAUD。

CPU 程序由参数 `IMEM_INIT_FILE` 指定十六进制初始化文件。空文件参数不会自动生成可运行的人脸识别程序，UART 桥只访问 datasram，不负责写 IEM。SRAM 上电内容未定义，系统复位不清空它，固件必须初始化所需数据。

验证命令：

```powershell
python scripts/run_cnn_integration.py
python -m unittest discover -s tb -p test_uart_image_transfer.py
python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot
```

详细结果见 [六模块验证记录](docs/soc_six_module_verification_20261008.md)。
已验证的 RTL 仿真不等于已上板，也不等于完整人脸模型精度通过。尚需目标 FPGA 资源/BRAM 推断、布局布线时序、时钟/管脚约束、固件和真实串口实测。
