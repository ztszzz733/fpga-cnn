# Data SRAM A/B 口与 FPGA 联动新手教程

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## 1. 先记住最重要的一句话

**Data SRAM 是 FPGA 芯片内部的一块共享数据仓库；A 口固定给 CPU，B 口由图像输入输出模块和 CNN 分时使用。A、B 口访问的是同一份数据，不是两块不同的内存。**

可以把双口 SRAM 想成一间有两扇门的仓库：

| SRAM 端口 | 固定使用者 | 主要用途 |
|---|---|---|
| A 口 | CPU | CPU 执行 Load/Store 指令时读写数据 |
| B 口 | 图像输入输出硬件或 CNN | 输入图片、CNN 读写特征和权重、输出结果 |

CPU 从 A 口向地址 `0x2000` 写入数据后，图像桥或 CNN 从 B 口读取 `0x2000`，看到的是同一个数据。

## 2. 整体硬件结构

```text
                              FPGA 芯片内部
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  固定程序                                                      │
│  imem_rom ──────→ cpu_core                                     │
│                       │                                        │
│                       │ Load/Store                             │
│                       ▼                                        │
│                 Data SRAM A口                                  │
│                       │                                        │
│                       ├──── 同一份 Data SRAM 数据 ────┐        │
│                       │                               │        │
│                 Data SRAM B口 ◀───────────────────────┘        │
│                       ▲                                        │
│                       │                                        │
│                sram_b_arbiter                                  │
│                  ▲          ▲                                  │
│                  │          │                                  │
│       image_io_bridge     cnn_accelerator                      │
│            ▲   │                                               │
└────────────│───│───────────────────────────────────────────────┘
             │   │
          uart_rx uart_tx
             │   │
             电脑
```

这里的“端口”不是开发板上的插孔，而是 FPGA 内部 RTL 模块之间的一组信号线。

真正需要连接到 FPGA 外部管脚的通常只有：

- `sys_clk`：板载晶振时钟；
- `rst_n_in`：复位输入；
- `uart_rx`：电脑向 FPGA 发送图片；
- `uart_tx`：FPGA 向电脑发送结果；
- `led_ready/led_busy/led_error`：可选的状态指示灯。

`a_addr`、`a_rdata`、`b_addr`、`b_rdata` 等 SRAM 信号都位于 FPGA 芯片内部，不需要分配外部引脚。

## 3. 为什么需要两个端口

如果 SRAM 只有一个口，CPU、CNN 和图像输入输出模块都必须排队使用它。True Dual-Port SRAM，也就是真双口存储器，可以让 A、B 两口在满足冲突规则的情况下同时访问同一块存储阵列。

例如：

```text
同一个周期：
CPU 通过 A 口读取地址 0x0100
CNN 通过 B 口读取地址 0x3000
```

两个地址不同，因此可以并行完成。

双口不等于完全没有限制。两个端口如果在同一个周期写同一个地址，结果可能由具体 FPGA 器件和 BRAM 模式决定，因此本项目要求上层协议主动避免这种情况。

## 4. SRAM A 口：CPU 专用

CPU 继续使用现有 `dmem_*` 接口，不需要修改 Control。顶层把这些信号直接接到 SRAM A 口：

```text
CPU                         Data SRAM A口

dmem_addr    ─────────────▶ a_addr
dmem_wdata   ─────────────▶ a_wdata
dmem_wstrb   ─────────────▶ a_wstrb
dmem_re      ─────────────▶ a_re
dmem_we      ─────────────▶ a_we
dmem_rdata   ◀───────────── a_rdata
```

### 4.1 A 口信号作用

| SRAM 信号 | CPU 信号 | 位宽 | 方向（相对 SRAM） | 作用 |
|---|---|---:|---|---|
| `a_addr` | `dmem_addr` | 32 | 输入 | CPU 要访问的字节地址 |
| `a_wdata` | `dmem_wdata` | 32 | 输入 | CPU 要写入的 32 位数据 |
| `a_wstrb` | `dmem_wstrb` | 4 | 输入 | 32 位数据中哪些字节真正写入 |
| `a_re` | `dmem_re` | 1 | 输入 | 为 1 表示 CPU 发起读请求 |
| `a_we` | `dmem_we` | 1 | 输入 | 为 1 表示 CPU 发起写请求 |
| `a_rdata` | `dmem_rdata` | 32 | 输出 | SRAM 返回给 CPU 的 32 位数据 |

CPU 到 SRAM 的请求线共 70 bit：

```text
32 位地址 + 32 位写数据 + 4 位字节使能 + 1 位读使能 + 1 位写使能
= 70 bit
```

### 4.2 CPU 写入示例

CPU 要把 `0x12345678` 写入地址 `0x00002000`：

```text
a_addr  = 0x00002000
a_wdata = 0x12345678
a_wstrb = 4'b1111
a_re    = 0
a_we    = 1
```

在有效时钟上升沿，SRAM 完成这次写入。

### 4.3 CPU 读取示例

CPU 之后读取地址 `0x00002000`：

```text
a_addr = 0x00002000
a_re   = 1
a_we   = 0
```

当前设计要求 A 口采用固定一周期同步读：

```text
时钟沿 N：SRAM 接收地址和读请求
N 到 N+1：SRAM 内部读取数据，a_rdata 在这个周期内变为有效值
时钟沿 N+1：CPU 后级保存读出的数据
```

如果该地址保存的是 `0x12345678`，那么在约定的返回时间内：

```text
a_rdata = 0x12345678
```

### 4.4 为什么 A 口没有 `ready` 或 `rvalid`

当前 CPU 接口没有 Data SRAM 的等待或应答输入。CPU 默认 SRAM 一定按照固定时序工作：请求在 EX→MEM 上升沿被接受，Load 数据在随后的 MEM 周期稳定，并在 MEM→WB 上升沿保存。

因此，实体 SRAM wrapper 必须满足这一周期约定，不能擅自改成两周期或不确定延迟。如果以后需要更慢或可变延迟的存储器，必须升级 CPU 接口和流水线暂停控制。

## 5. `a_wstrb`：控制写入哪些字节

SRAM 数据宽度是 32 bit，也就是 4 个字节：

```text
a_wdata[31:24]  a_wdata[23:16]  a_wdata[15:8]  a_wdata[7:0]
    字节3            字节2           字节1          字节0
```

`a_wstrb` 的每一位控制一个字节：

| `a_wstrb` | 实际写入内容 |
|---|---|
| `4'b0001` | 只写最低字节，即 `a_wdata[7:0]` |
| `4'b0010` | 只写第二个字节 |
| `4'b0100` | 只写第三个字节 |
| `4'b1000` | 只写最高字节 |
| `4'b0011` | 写低 16 位 |
| `4'b1100` | 写高 16 位 |
| `4'b1111` | 32 位全部写入 |
| `4'b0000` | 不写入任何字节 |

所以：

- `SB` 通常只有一个字节写使能为 1；
- `SH` 通常有两个连续的字节写使能为 1；
- `SW` 通常为 `4'b1111`。

字节写使能保证 CPU 修改一个字节时，不会破坏同一个 32 位字中的其他字节。

## 6. 字节地址和 SRAM 内部地址

当前计划的 Data SRAM 参数为：

```text
容量：256 KiB
数据宽度：32 bit，即每个存储字为 4 字节
字节地址范围：0x00000000～0x0003FFFF
存储字数量：65,536 个 32-bit word
```

CPU、图像桥和 CNN 使用的都是 32 位字节地址。BRAM 内部每个位置保存 4 字节，因此 wrapper 通常使用：

```text
内部字地址 = addr[17:2]
```

最低两位 `addr[1:0]` 表示 32 位字中的字节位置：

| `addr[1:0]` | 字节位置 |
|---|---|
| `2'b00` | 第 0 字节，数据位 `[7:0]` |
| `2'b01` | 第 1 字节，数据位 `[15:8]` |
| `2'b10` | 第 2 字节，数据位 `[23:16]` |
| `2'b11` | 第 3 字节，数据位 `[31:24]` |

例如，字节地址 `0x1000～0x1003` 都属于同一个 32 位存储字；下一个 32 位字从地址 `0x1004` 开始。

## 7. SRAM B 口：图像桥和 CNN 共用

B 口有两个可能的请求者：

```text
image_io_bridge ─┐
                 ├─▶ sram_b_arbiter ─▶ Data SRAM B口
cnn_accelerator ─┘
```

图像桥与 CNN 的输出不能直接并联。假设图像桥要求访问 `0x1000`，CNN 同时要求访问 `0x3000`，一根 `b_addr` 信号不可能同时表达两个地址。因此必须通过 `sram_b_arbiter` 选择本周期由谁使用 B 口。

### 7.1 B 口请求信号

| 信号 | 位宽 | 作用 |
|---|---:|---|
| `b_req` | 1 | 为 1 表示存在一次访问请求 |
| `b_we` | 1 | `1=写`，`0=读` |
| `b_addr` | 32 | 本次访问的字节地址 |
| `b_wdata` | 32 | 本次要写入的数据 |
| `b_be` | 4 | 哪几个字节允许写入 |

B 口请求线也是 70 bit：

```text
1 位请求 + 1 位读写方向 + 32 位地址 + 32 位写数据 + 4 位字节使能
= 70 bit
```

### 7.2 B 口返回信号

| 信号 | 位宽 | 作用 |
|---|---:|---|
| `b_gnt` | 1 | SRAM 已经接受本次请求 |
| `b_rvalid` | 1 | 当前 `b_rdata` 是有效的读返回数据 |
| `b_rdata` | 32 | 从 SRAM 读出的数据 |
| `b_error` | 1 | 地址越界、未对齐或访问方式错误 |

B 口返回线共 35 bit：

```text
1 位请求接受 + 1 位读数据有效 + 32 位读数据 + 1 位错误
= 35 bit
```

### 7.3 `b_gnt` 和 `b_rvalid` 的区别

这是 B 口最容易混淆的两个信号：

- `b_gnt=1` 表示：“你的请求我已经接收了。”
- `b_rvalid=1` 表示：“你请求读取的数据现在已经出来了。”

它们不一定在同一个周期出现。

一次典型的 B 口读取过程：

```text
周期 0：主设备给出 b_req=1、b_we=0、b_addr
接受沿：b_gnt=1，SRAM 接受请求，主设备可以撤销请求
周期 1：b_rvalid=1，b_rdata 是读出的有效数据
```

一次典型的 B 口写入请求：

```text
b_req   = 1
b_we    = 1
b_addr  = 写入地址
b_wdata = 写入数据
b_be    = 字节写使能
```

当 `b_req && b_gnt && b_we` 成立时，这次写请求被接受。

## 8. B 口仲裁器的作用

第一版仲裁规则为：

```text
如果存在尚未返回的 B 口读请求：
    不接受新请求，等待 b_rvalid
    把返回数据送给原来的请求者

否则，如果 CNN 正在请求：
    选择 CNN

否则，如果图像桥正在请求：
    选择 image_io_bridge

否则：
    B 口空闲
```

同时请求时，CNN 为固定高优先级。但正常系统流程应从工作阶段上避免竞争：

| 工作阶段 | B 口使用者 | 主要行为 |
|---|---|---|
| `LOAD` | `image_io_bridge` | 把电脑发来的图像写入 SRAM |
| `READY` | 无或图像桥 | 等待 CPU 确认，不覆盖输入区 |
| `PROCESS` | `cnn_accelerator` | 读取输入和权重，写回计算结果 |
| `DUMP` | `image_io_bridge` | 读取结果并通过 UART 发给电脑 |
| `ERROR` | 无 | 禁止继续写入，等待恢复或复位 |

### 8.1 为什么仲裁器必须记住读请求者

假设：

```text
周期 0：图像桥请求读取地址 0x2000
周期 0：SRAM 接受请求
周期 1：SRAM 返回数据
```

数据返回时，当前地址和请求线可能已经变化。因此仲裁器必须在读请求被接受时保存：

```text
read_owner_q = image_io_bridge
```

当 `b_rvalid=1` 时，只向图像桥返回：

```text
io_mem_rvalid = 1
io_mem_rdata  = b_rdata
```

CNN 此时必须看到：

```text
cnn_mem_rvalid = 0
```

如果不保存请求者，返回数据就可能被送错模块。

## 9. A、B 口并行和冲突规则

True Dual-Port BRAM 允许两个端口独立访问，但同地址冲突必须由系统避免。

| A 口操作 | B 口操作 | 是否允许 | 说明 |
|---|---|---|---|
| 读地址 X | 读不同地址 Y | 允许 | 两口正常并行 |
| 写地址 X | 读不同地址 Y | 允许 | 两口正常并行 |
| 写地址 X | 写不同地址 Y | 允许 | 两口正常并行 |
| 读地址 X | 读同一地址 X | 可允许 | 需要确认 FPGA BRAM 的具体模式 |
| 写地址 X | 读同一地址 X | 第一版禁止 | 由邮箱和所有权协议避免 |
| 写地址 X | 写同一地址 X | 严格禁止 | 应通过仿真断言报错 |

建议在仿真中检查两个端口没有同时写或读写冲突：

```systemverilog
assert (!(a_we && b_req && b_gnt &&
          (a_addr[31:2] == b_addr[31:2])));
```

这里比较 `addr[31:2]`，是因为低两位属于同一个 32 位字中的字节位置。

## 10. 图片怎样通过 B 口进入 SRAM

UART 一次只传输 1 bit，SRAM 一次处理 32 bit，所以不能直接这样连接：

```text
uart_rx → SRAM 数据端口
```

正确路径是：

```text
uart_rx
   ↓
UART 接收和波特率采样
   ↓
数据包解析、尺寸检查、长度检查和 CRC 检查
   ↓
image_io_bridge 每收齐 4 个像素组成一个 32 位字
   ↓
sram_b_arbiter
   ↓
Data SRAM B口
```

第一阶段输入规格为：

```text
图像大小：64×64
通道数：1，灰度
每个像素：signed int8，1 字节
总大小：4096 字节
起始地址：0x00001000
结束地址：0x00001FFF
```

假设电脑依次发送四个像素字节：

```text
11 22 33 44
```

图像桥按小端顺序形成：

```text
b_addr  = 0x00001000
b_wdata = 0x44332211
b_be    = 4'b1111
b_we    = 1
b_req   = 1
```

写入后的字节关系是：

```text
地址 0x1000 = 0x11，对应 word[7:0]
地址 0x1001 = 0x22，对应 word[15:8]
地址 0x1002 = 0x33，对应 word[23:16]
地址 0x1003 = 0x44，对应 word[31:24]
```

下一组四个像素写入地址 `0x1004`。

## 11. CPU 和 CNN 如何联动

CPU 与 CNN 之间有两条不同的通路，不能把它们混为一谈。

### 11.1 控制通路：MMIO

CPU 通过 CNN MMIO 寄存器告诉 CNN：

- 输入图像放在哪里；
- 输出结果写到哪里；
- 权重和 bias 放在哪里；
- 图像尺寸和通道数；
- 什么时候启动；
- 当前是否完成或发生错误。

路径为：

```text
CPU → CNN MMIO 寄存器组 → CNN 控制状态机
```

MMIO 负责传递命令和少量参数，不负责搬运整张图片。

### 11.2 数据通路：SRAM B 口

CNN 真正读取图像、权重和特征图，以及写回计算结果，走的是：

```text
CNN DMA/memory master
        ↓
sram_b_arbiter
        ↓
Data SRAM B口
```

所以可以简单记成：

> MMIO 负责传命令，SRAM B 口负责传大量数据。

### 11.3 一次 CNN 任务的典型流程

```text
1. 图像桥通过 B 口把图片写到 0x1000
2. 图像桥设置 SRAM 邮箱中的 FRAME_READY=1
3. CPU 通过 A 口发现 FRAME_READY
4. CPU 通过 MMIO 写入 INPUT_ADDR、OUTPUT_ADDR 等参数
5. CPU 通过 MMIO 产生 start 启动脉冲
6. CNN 通过 B 口读取输入图像和权重
7. CNN 完成计算并通过 B 口把结果写到输出区
8. CNN 设置 done 状态
9. CPU 通过 MMIO 发现任务完成
10. 图像桥通过 B 口读取输出区
11. 图像桥通过 uart_tx 把结果发送给电脑
```

## 12. 第一阶段 FPGA 联调流程

在接入真实 CNN 之前，建议先用 CPU 计算简单统计值，验证整条 SRAM 数据链。

### 12.1 完整过程

1. FPGA 上电，固定程序已经存放在 `imem_rom` 中。
2. CPU 开始运行，通过 A 口轮询邮箱中的 `FRAME_READY`。
3. 电脑通过 USB-UART 发送一张 64×64 灰度图。
4. `image_io_bridge` 检查包头、尺寸、长度和 CRC。
5. 图像桥每收到 4 个像素，通过 B 口写入一个 32 位字。
6. 完整图像写入 `0x1000～0x1FFF` 后，图像桥设置 `FRAME_READY=1`。
7. CPU 通过 A 口读取图像。
8. CPU 计算 `pixel_count`、`sum` 和 `xor_value`。
9. CPU 通过 A 口把结果写入 `0x2000～0x200C`。
10. 图像桥通过 B 口读取结果。
11. 图像桥通过 `uart_tx` 把结果发回电脑。
12. 电脑将 FPGA 返回值与本地参考计算结果比较。

### 12.2 第一阶段结果区

| SRAM 地址 | 内容 | 写入方 | 读取方 |
|---:|---|---|---|
| `0x2000` | `pixel_count`，应为 4096 | CPU A 口 | 图像桥 B 口 |
| `0x2004` | 所有像素累加值 `sum` | CPU A 口 | 图像桥 B 口 |
| `0x2008` | 所有像素异或值 `xor_value` | CPU A 口 | 图像桥 B 口 |
| `0x200C` | `status`，0 表示成功 | CPU A 口 | 图像桥 B 口 |

这一步可以证明下面的完整闭环确实工作：

```text
电脑 → UART → 图像桥 → B口 → SRAM → A口 → CPU
CPU → A口 → SRAM → B口 → 图像桥 → UART → 电脑
```

它验证的是数据通路，不代表完整人脸识别已经完成。

## 13. SRAM 邮箱的作用

CPU、图像桥和 CNN 运行速度不同，需要一小块共享状态区告诉对方“数据准备好了”或“结果完成了”。建议使用 SRAM 前 256 字节作为邮箱：

| 偏移 | 名称 | 主要写入方 | 含义 |
|---:|---|---|---|
| `0x00` | `FRAME_READY` | 图像桥设置、CPU 清除 | 完整有效图像已经写入 |
| `0x04` | `FRAME_ID` | 图像桥 | 当前帧编号 |
| `0x08` | `IMAGE_ADDR` | 图像桥 | 图像起始地址，默认 `0x1000` |
| `0x14` | `PAYLOAD_BYTES` | 图像桥 | 图像数据字节数 |
| `0x20` | `RESULT_READY` | CPU/CNN 流程 | 结果已经可以读取 |
| `0x24` | `RESULT_ADDR` | CPU | 结果起始地址，默认 `0x2000` |
| `0x28` | `RESULT_BYTES` | CPU | 结果长度 |
| `0x30` | `RESULT_STATUS` | CPU | 成功或错误码 |

每个字段必须明确唯一的写入者。例如，当 `FRAME_READY=1` 且 CPU 尚未处理时，图像桥不能覆盖输入图像区。

## 14. FPGA 中的 SRAM 最终是什么硬件

虽然模块名称是 `Data SRAM`，在 FPGA 内部通常使用厂商的 Block RAM，而不是在芯片外再接一块 SRAM：

```text
SystemVerilog 存储数组或厂商 BRAM IP
                 ↓ 综合
FPGA 内部 True Dual-Port Block RAM
```

目标 wrapper 需要满足：

- 数据宽度为 32 bit；
- 存储深度为 65,536 个 32 位字；
- 总容量为 256 KiB；
- A、B 两个真实端口；
- 每个端口支持字节写使能；
- 固定一周期同步读取；
- 明确定义同地址访问模式；
- 可按需要使用初始化文件装载固定数据或权重。

复位时通常只清除控制状态，例如：

```text
b_rvalid
b_error
未完成读请求标志
仲裁器状态
```

复位不要求逐项清空整个 256 KiB 存储阵列。强行用复位循环清空大数组，可能导致综合器无法把它正确推导成 BRAM，或者消耗大量逻辑资源。

## 15. 时钟、复位和跨时钟域

建议 CPU、IMEM、Data SRAM、CNN 和 B 口仲裁器优先使用同一个系统时钟。

UART 输入是相对于系统时钟的异步信号，必须先经过同步和波特率采样逻辑，不能直接进入 SRAM 或系统状态机。

如果以后接入摄像头，摄像头通常有独立的 `cam_pclk`。摄像头数据进入 CPU/CNN 时钟域之前，需要异步 FIFO 或双时钟帧缓存，还要完成裁剪、缩放、颜色转换和 int8 量化。直接接摄像头不适合作为第一次 SRAM 上板测试。

外部按键复位还应考虑消抖和同步释放，避免不同模块在不同周期退出复位。

## 16. 顶层核心接线示意

下面只展示 CPU 与 Data SRAM 的主要关系，不是完整顶层：

```systemverilog
cpu_core u_cpu (
    .clk          (clk),
    .rst_n        (rst_n),
    .dmem_addr    (dmem_addr),
    .dmem_wdata   (dmem_wdata),
    .dmem_wstrb   (dmem_wstrb),
    .dmem_re      (dmem_re),
    .dmem_we      (dmem_we),
    .dmem_rdata   (dmem_rdata)
);

data_sram_tdp u_data_sram (
    .clk          (clk),
    .rst_n        (rst_n),

    .a_addr       (dmem_addr),
    .a_wdata      (dmem_wdata),
    .a_wstrb      (dmem_wstrb),
    .a_re         (dmem_re),
    .a_we         (dmem_we),
    .a_rdata      (dmem_rdata),

    .b_req        (b_req),
    .b_we         (b_we),
    .b_addr       (b_addr),
    .b_wdata      (b_wdata),
    .b_be         (b_be),
    .b_gnt        (b_gnt),
    .b_rvalid     (b_rvalid),
    .b_rdata      (b_rdata),
    .b_error      (b_error)
);
```

完整顶层还需要连接：

- `imem_rom`；
- CNN MMIO 寄存器组；
- `image_io_bridge`；
- `sram_b_arbiter`；
- `cnn_accelerator`；
- UART RX/TX；
- 时钟、复位和板级 LED。

## 17. 上板时怎样验证

### 17.1 仿真检查

- CRC 错误的 UART 包不能设置图像完成标志；
- 4096 个图像字节准确写入 `0x1000～0x1FFF`；
- A/B 口同地址写冲突断言不能触发；
- B 口每个读请求只产生一次 `rvalid`；
- 图像桥和 CNN 同时请求时只能有一个获得 `gnt`；
- 读返回只能送给原来的请求者；
- CPU 的 checksum 与电脑参考结果一致；
- UART 返回包的长度、帧号和 CRC 正确。

### 17.2 FPGA 上板检查

可以使用 ILA 依次观察：

1. `uart_rx` 是否正确收到数据包；
2. `io_mem_req/io_mem_gnt` 是否正确握手；
3. SRAM 地址 `0x1000`、中间地址和 `0x1FFC` 是否保存正确像素；
4. CPU A 口是否产生读请求，`a_rdata` 是否按时返回；
5. 结果区 `0x2000～0x200C` 是否被正确写入；
6. B 口是否正确读出结果；
7. `uart_tx` 返回值是否与电脑参考值相同；
8. 连续发送至少 100 帧，是否出现覆盖未处理帧或读返回错配。

## 18. 当前项目完成状态

当前已经确认：

- Control 与生产 Datapath 已经完成有限程序仿真；
- CPU 侧 `dmem_*` 接口已经存在；
- 生产 Datapath 在 EX→MEM 边沿提交 SRAM 读写请求；
- Load 数据需要在 MEM 周期稳定，并在 MEM→WB 边沿保存；
- 当前仿真使用同步存储模型；
- 真实 Control 与生产 Datapath 的 ADD 和混合程序仿真已经通过。

尚未完成或尚未进行实体板验证的部分：

- 可综合的真实双口 `data_sram_tdp`；
- B 口仲裁器；
- UART 图像输入输出桥；
- 真实 CNN 的 B 口 memory master；
- 具体开发板的 BRAM 容量检查；
- XDC/QSF 管脚、电压和时钟约束；
- 实体 FPGA 上固定一周期读取时序验证；
- A/B 口同地址访问的器件级模式验证；
- 完整人脸识别模型、权重、量化和结果格式验证。

因此，目前这是一套已经明确到接口和流程的上板方案，但不能表述为真实双口 SRAM、CNN 或完整 FPGA 人脸识别系统已经通过。

## 19. 最后用六句话总结

```text
A口 = CPU 专用的数据门。
B口 = 图像桥和 CNN 共享的数据门。
仲裁器 = B 口门卫，决定本次让谁访问，并把读结果送回正确的人。
MMIO = CPU 给 CNN 下命令、传少量参数和读取状态。
UART = FPGA 与电脑交换图片和结果的外部通道。
Data SRAM = CPU、图像桥和 CNN 交换大量数据的内部共享仓库。
```

## 20. 相关项目资料

- [新手版 FPGA Data SRAM 与图像 I/O 硬件接线清单](fpga_datasram_image_io_hardware_io.md)
- [技术版 FPGA Data SRAM 与图像 I/O 接线说明](fpga_datasram_image_io_wiring.md)
- [FPGA 固定固件与 Data SRAM 图像输入输出方案](fpga_fixed_firmware_image_io_plan.md)
- [固定 MEM 时序契约](memory_timing_contract.md)
- [Datapath 对接核查与报告影响](datapath_connection_review_20260917.md)
