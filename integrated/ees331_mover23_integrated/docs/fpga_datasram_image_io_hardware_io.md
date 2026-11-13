# 新手版 FPGA Data SRAM 与图像 I/O 硬件接线清单

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## 1. 先说最重要的结论

第一版 FPGA 系统使用下面这条路线：

```text
电脑发送图片
    ↓ uart_rx
图像输入输出硬件
    ↓ Data SRAM B口
Data SRAM 保存图片
    ↓ Data SRAM A口
CPU读取图片并处理
    ↓ Data SRAM A口
CPU把结果写回Data SRAM
    ↓ Data SRAM B口
图像输入输出硬件读取结果
    ↓ uart_tx
电脑收到结果
```

需要特别区分：

- `uart_rx` 和 `uart_tx` 是 FPGA 芯片对外的真实引脚。
- `a_addr`、`a_wdata`、`a_rdata` 等是 FPGA 芯片内部连接 CPU 和 Data SRAM 的线。
- `b_addr`、`b_wdata`、`b_rdata` 等是 FPGA 芯片内部连接外部图像桥/CNN 和 Data SRAM 的线。
- Data SRAM 自己不会直接输出“人员编号”。它只输出 32 位存储数据。人员编号必须先写进 SRAM 结果区，再由 `uart_tx` 发给电脑。

第一版建议输入 `64×64` 灰度图，每个像素 1 字节，一张图片正好 4096 字节。当前先验证图片是否正确进入 SRAM、CPU 是否能正确读取、结果是否能正确发回；这一步不是完整人脸识别。

## 2. “A口”和“B口”是什么

Data SRAM 使用双口存储器，相当于同一间仓库有两个门：

| SRAM 端口 | 固定使用者 | 主要用途 |
|---|---|---|
| A 口 | CPU | CPU 使用 Load/Store 指令读写数据 |
| B 口 | 图像输入输出硬件或 CNN | 输入图片、CNN 读写特征、输出结果 |

A、B 两口访问的是同一份 SRAM 内容。CPU 从 A 口写入地址 `0x2000` 的值，B 口之后也能从地址 `0x2000` 读到它。

B 口有两个可能的使用者，所以不能把它们的线直接接在一起：

- 装载图片、发送结果时，由 `image_io_bridge` 使用 B 口。
- CNN 计算时，由 `cnn_accelerator` 使用 B 口。
- `sram_b_arbiter` 负责决定当前把谁接到 B 口。

## 3. 硬件清单

### 3.1 FPGA 内部硬件

| 硬件模块 | 中文名称 | 做什么 |
|---|---|---|
| `fpga_face_top` | FPGA 系统顶层 | 把所有硬件连接起来，并引出板级引脚 |
| `imem_rom` | 固定指令存储器 | 保存 CPU 上电后自动执行的程序 |
| `cpu_core` | CPU 核心 | 执行固定程序，通过 A 口读写 Data SRAM |
| `data_sram_tdp` | 双口 Data SRAM | 保存图片、结果、特征、权重和普通数据 |
| `image_io_bridge` | 图像输入输出硬件 | 接收 UART 图片、写 SRAM、读结果、发送 UART |
| `sram_b_arbiter` | SRAM B 口选择器 | 在图像桥和 CNN 之间选择一个 B 口使用者 |
| `cnn_accelerator` | CNN 加速器 | 后续读取图像并写回 CNN 计算结果 |

当前已经有 CPU Control 和生产 Datapath。`imem_rom`、实体双口 SRAM、图像桥、B 口选择器和真实 CNN 仍需要实现。

### 3.2 FPGA 外部硬件

| 外部硬件 | 与 FPGA 的连接 |
|---|---|
| 板载晶振 | 提供 `sys_clk` |
| 复位按键/复位芯片 | 提供 `rst_n_in` |
| USB-UART | 向 FPGA 的 `uart_rx` 发送图片，从 `uart_tx` 接收结果 |
| 三个 LED | 显示 ready、busy、error |
| 电脑 | 通过 USB-UART 发送图片文件和接收结果 |

---

## 4. `fpga_face_top`：板子上真正看到的 I/O

### 4.1 输入端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 小白解释 |
|---|---:|---|---|---|
| `sys_clk` | 1 | 板载晶振 | FPGA 内部全部同步硬件 | 整个系统按这个节拍工作 |
| `rst_n_in` | 1 | 复位按键/芯片 | FPGA 内部复位电路 | 拉低时系统回到初始状态 |
| `uart_rx` | 1 | USB-UART TX | `image_io_bridge` | 电脑逐位发送图片数据的输入线 |

### 4.2 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 小白解释 |
|---|---:|---|---|---|
| `uart_tx` | 1 | `image_io_bridge` | USB-UART RX | FPGA逐位发送结果给电脑的输出线 |
| `led_ready` | 1 | `image_io_bridge` | 板载 LED | 亮起表示可以发送下一张图片 |
| `led_busy` | 1 | 系统状态逻辑 | 板载 LED | 亮起表示正在接收、处理或发送 |
| `led_error` | 1 | 错误状态逻辑 | 板载 LED | 亮起表示 CRC、地址或 CNN 出错 |

第一版不需要把 32 位 SRAM 数据线引到 FPGA 管脚。32 位 SRAM 数据线全部位于 FPGA 内部，最终结果通过一根 `uart_tx` 串行输出。

---

## 5. `imem_rom`：固定程序接线

CPU 的程序在生成 bitstream 时已经放进 `imem_rom`。上电后 CPU 自动取指，不需要电脑再下载程序。

### 5.1 输入端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `imem_addr` | 32 | `cpu_core` | `imem_rom` | CPU 要读取的指令地址 |
| `imem_re` | 1 | `cpu_core` | `imem_rom` | 1 表示 CPU 正在请求一条指令 |

### 5.2 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `imem_rdata` | 32 | `imem_rom` | `cpu_core` | 固定一周期后返回的 32 位指令 |

IMEM 与 Data SRAM 是两个不同存储器。图片不能写进 IMEM，CPU 指令也不从 Data SRAM 读取。

---

## 6. `cpu_core` 与 Data SRAM A 口

CPU 继续使用现有 `dmem_*` 接口，不修改 CPU Control。

### 6.1 CPU 输出到 SRAM A 口

| CPU 信号 | SRAM 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---|---:|---|---|---|
| `dmem_addr` | `a_addr` | 32 | `cpu_core` | `data_sram_tdp` | CPU 要访问的字节地址 |
| `dmem_wdata` | `a_wdata` | 32 | `cpu_core` | `data_sram_tdp` | CPU 要写入的 32 位数据 |
| `dmem_wstrb` | `a_wstrb` | 4 | `cpu_core` | `data_sram_tdp` | 哪些字节真的写入 |
| `dmem_re` | `a_re` | 1 | `cpu_core` | `data_sram_tdp` | 1 表示 CPU 要读 SRAM |
| `dmem_we` | `a_we` | 1 | `cpu_core` | `data_sram_tdp` | 1 表示 CPU 要写 SRAM |

这五类信号加起来共有 70 bit：

```text
32 地址 + 32 写数据 + 4 字节使能 + 1 读使能 + 1 写使能 = 70 bit
```

### 6.2 SRAM A 口返回给 CPU

| SRAM 信号 | CPU 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---|---:|---|---|---|
| `a_rdata` | `dmem_rdata` | 32 | `data_sram_tdp` | `cpu_core` | CPU 读取到的 32 位数据 |

### 6.3 简单例子

CPU 要把 `0x12345678` 写进地址 `0x00002000`：

```text
a_addr  = 0x00002000
a_wdata = 0x12345678
a_wstrb = 1111
a_re    = 0
a_we    = 1
```

CPU 之后读取同一地址：

```text
a_addr = 0x00002000
a_re   = 1
a_we   = 0
```

固定一周期后：

```text
a_rdata = 0x12345678
```

---

## 7. `image_io_bridge`：图片输入和结果输出

`image_io_bridge` 一边连接 UART，一边通过仲裁器连接 SRAM B 口。

### 7.1 板级输入输出

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `uart_rx` | 1 | USB-UART | `image_io_bridge` |
| 输出 | `uart_tx` | 1 | `image_io_bridge` | USB-UART |

### 7.2 图像桥输出到 B 口选择器

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `io_mem_req` | 1 | `image_io_bridge` | `sram_b_arbiter` | 1 表示要访问 SRAM |
| `io_mem_we` | 1 | `image_io_bridge` | `sram_b_arbiter` | 1=写图片，0=读结果 |
| `io_mem_addr` | 32 | `image_io_bridge` | `sram_b_arbiter` | SRAM 字节地址 |
| `io_mem_wdata` | 32 | `image_io_bridge` | `sram_b_arbiter` | 四个像素字节打包后的数据 |
| `io_mem_be` | 4 | `image_io_bridge` | `sram_b_arbiter` | 哪些字节有效 |

同样一共是 70 bit。

### 7.3 B 口选择器返回给图像桥

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 小白解释 |
|---|---:|---|---|---|
| `io_mem_gnt` | 1 | `sram_b_arbiter` | `image_io_bridge` | 这一次请求已经被 SRAM 接受 |
| `io_mem_rvalid` | 1 | `sram_b_arbiter` | `image_io_bridge` | 现在的读数据有效 |
| `io_mem_rdata` | 32 | `sram_b_arbiter` | `image_io_bridge` | 从 SRAM 读出的结果数据 |
| `io_mem_error` | 1 | `sram_b_arbiter` | `image_io_bridge` | 地址或访问方式错误 |

返回线一共 35 bit：

```text
1 接受 + 1 数据有效 + 32 读数据 + 1 错误 = 35 bit
```

图像桥收到 UART 图片时做的是“写 SRAM”，所以主要使用 `io_mem_addr/io_mem_wdata/io_mem_be`。发送结果时做的是“读 SRAM”，所以主要使用 `io_mem_addr/io_mem_rdata/io_mem_rvalid`。

---

## 8. `cnn_accelerator`：CNN 与 SRAM B 口

CNN 使用与图像桥相同形式的请求线，但信号名前缀为 `cnn_`。

### 8.1 CNN 输出到 B 口选择器

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `cnn_mem_req` | 1 | `cnn_accelerator` | `sram_b_arbiter` | CNN 请求访问 SRAM |
| `cnn_mem_we` | 1 | `cnn_accelerator` | `sram_b_arbiter` | 1=写结果，0=读输入/权重 |
| `cnn_mem_addr` | 32 | `cnn_accelerator` | `sram_b_arbiter` | SRAM 字节地址 |
| `cnn_mem_wdata` | 32 | `cnn_accelerator` | `sram_b_arbiter` | CNN 要写回的数据 |
| `cnn_mem_be` | 4 | `cnn_accelerator` | `sram_b_arbiter` | 字节写使能 |

### 8.2 B 口选择器返回给 CNN

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `cnn_mem_gnt` | 1 | `sram_b_arbiter` | `cnn_accelerator` | CNN 请求已接受 |
| `cnn_mem_rvalid` | 1 | `sram_b_arbiter` | `cnn_accelerator` | CNN 读数据有效 |
| `cnn_mem_rdata` | 32 | `sram_b_arbiter` | `cnn_accelerator` | 输入、权重或 bias 数据 |
| `cnn_mem_error` | 1 | `sram_b_arbiter` | `cnn_accelerator` | 访问错误 |

真实 CNN 目前还没有接入，因此这些是必须由 CNN 负责人最终确认并实现的接口。

---

## 9. `sram_b_arbiter`：为什么需要 B 口选择器

图像桥和 CNN 都想使用 SRAM B 口。如果把两组输出直接连在一起，会产生两个硬件同时驱动一根线的问题，RTL 会多驱动，硬件行为也不确定。

`sram_b_arbiter` 的作用可以理解为一个电子选择开关：

```text
图像桥请求 ─┐
             ├─ B口选择器 ─→ SRAM B口
CNN请求 ─────┘
```

第一版选择规则：

1. 如果上一个 SRAM 读请求还没有返回，就先等返回，不接新请求。
2. CNN 和图像桥同时请求时，先服务 CNN。
3. 只有 CNN 没请求时，才服务图像桥。
4. 一次读请求是谁发出的，返回的读数据就只送回给谁。

### 9.1 选择器输出到 SRAM B 口

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `b_req` | 1 | `sram_b_arbiter` | `data_sram_tdp` | 访问请求 |
| `b_we` | 1 | `sram_b_arbiter` | `data_sram_tdp` | 1=写，0=读 |
| `b_addr` | 32 | `sram_b_arbiter` | `data_sram_tdp` | 字节地址 |
| `b_wdata` | 32 | `sram_b_arbiter` | `data_sram_tdp` | 写数据 |
| `b_be` | 4 | `sram_b_arbiter` | `data_sram_tdp` | 字节写使能 |

### 9.2 SRAM B 口返回给选择器

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 小白解释 |
|---|---:|---|---|---|
| `b_gnt` | 1 | `data_sram_tdp` | `sram_b_arbiter` | SRAM 已接受请求 |
| `b_rvalid` | 1 | `data_sram_tdp` | `sram_b_arbiter` | 返回的数据现在有效 |
| `b_rdata` | 32 | `data_sram_tdp` | `sram_b_arbiter` | SRAM 读出的 32 位数据 |
| `b_error` | 1 | `data_sram_tdp` | `sram_b_arbiter` | 地址越界或请求错误 |

`sram_b_arbiter` 必须记住每个读请求来自图像桥还是 CNN，否则下一周期读数据返回时不知道该送给谁。

---

## 10. `data_sram_tdp`：完整 I/O

### 10.1 公共输入

| 信号 | 位宽 | 来源硬件 | 去向硬件 | 作用 |
|---|---:|---|---|---|
| `clk` | 1 | 系统时钟 | `data_sram_tdp` | A/B 口同步读写时钟 |
| `rst_n` | 1 | 系统复位 | `data_sram_tdp` | 清除返回有效等控制状态，不要求清空全部 SRAM |

### 10.2 A 口输入和输出

| 方向（相对 SRAM） | 信号 | 位宽 | 来源/去向 |
|---|---|---:|---|
| 输入 | `a_addr` | 32 | 来自 CPU `dmem_addr` |
| 输入 | `a_wdata` | 32 | 来自 CPU `dmem_wdata` |
| 输入 | `a_wstrb` | 4 | 来自 CPU `dmem_wstrb` |
| 输入 | `a_re` | 1 | 来自 CPU `dmem_re` |
| 输入 | `a_we` | 1 | 来自 CPU `dmem_we` |
| 输出 | `a_rdata` | 32 | 返回 CPU `dmem_rdata` |

### 10.3 B 口输入和输出

| 方向（相对 SRAM） | 信号 | 位宽 | 来源/去向 |
|---|---|---:|---|
| 输入 | `b_req` | 1 | 来自 `sram_b_arbiter` |
| 输入 | `b_we` | 1 | 来自 `sram_b_arbiter` |
| 输入 | `b_addr` | 32 | 来自 `sram_b_arbiter` |
| 输入 | `b_wdata` | 32 | 来自 `sram_b_arbiter` |
| 输入 | `b_be` | 4 | 来自 `sram_b_arbiter` |
| 输出 | `b_gnt` | 1 | 返回 `sram_b_arbiter` |
| 输出 | `b_rvalid` | 1 | 返回 `sram_b_arbiter` |
| 输出 | `b_rdata` | 32 | 返回 `sram_b_arbiter` |
| 输出 | `b_error` | 1 | 返回 `sram_b_arbiter` |

### 10.4 地址怎么换成 SRAM 内部位置

当前计划的 Data SRAM 范围：

```text
0x00000000 ～ 0x0003FFFF，共 256 KiB
```

CPU、图像桥和 CNN 使用的都是“字节地址”。SRAM 数据宽度是 32 bit，也就是每个字 4 字节，所以 wrapper 内部使用：

```text
内部字地址 = addr[17:2]
```

低两位 `addr[1:0]` 表示一个 32 位字中的第几个字节。

---

## 11. 图像在 SRAM 里怎么放

第一版使用：

```text
宽度：64
高度：64
通道：1（灰度）
每像素：signed int8，1字节
总大小：64×64×1 = 4096字节
起始地址：0x00001000
结束地址：0x00001FFF
```

四个连续像素放进一个 32 位字：

| SRAM 地址 | 32 位数据中的位置 |
|---:|---|
| `0x1000` | `[7:0]=像素0`、`[15:8]=像素1`、`[23:16]=像素2`、`[31:24]=像素3` |
| `0x1004` | 像素4、5、6、7 |
| `...` | 中间像素 |
| `0x1FFC` | 最后四个像素 |

假设电脑依次发送四个像素字节 `11 22 33 44`，图像桥写 SRAM 时：

```text
b_addr  = 0x00001000
b_wdata = 0x44332211
b_be    = 1111
b_we    = 1
b_req   = 1
```

这是小端排列：最低地址的 `0x11` 放在最低 8 位。

---

## 12. 结果在 SRAM 里怎么放

第一阶段先不输出人脸编号，而是输出容易验证的图片统计值：

| SRAM 地址 | 内容 | 谁写入 | 谁读出 |
|---:|---|---|---|
| `0x2000` | `pixel_count`，应为 4096 | CPU A 口 | 图像桥 B 口 |
| `0x2004` | 所有像素累加值 `sum` | CPU A 口 | 图像桥 B 口 |
| `0x2008` | 所有像素异或值 `xor_value` | CPU A 口 | 图像桥 B 口 |
| `0x200C` | `status`，0 表示成功 | CPU A 口 | 图像桥 B 口 |

图像桥从 B 口读取这四个 32 位字，再通过 `uart_tx` 逐字节发给电脑。

接入真实 CNN 后，可以把结果区改为：

| 输出方式 | SRAM 中保存的内容 | FPGA 对外输出 |
|---|---|---|
| 分类 | `result_id` 和 `score` | 通过 `uart_tx` 输出，或可选 32 位并行端口 |
| embedding | N 个 int8/int16 特征 | 通过 `uart_tx` 输出整个向量 |
| 图像回读 | 原始图像或输出特征图 | 通过 `uart_tx` 输出全部字节 |

---

## 13. 一张图片完整经过哪些硬件

### 第一步：电脑发送图片

电脑把图片文件转换为 4096 个 signed int8 像素，通过 USB-UART 发送。FPGA 从 `uart_rx` 收到数据。

### 第二步：图像桥写入 SRAM

`image_io_bridge` 每收齐四个像素就组成一个 32 位字，通过 `io_mem_*` 请求写入。

### 第三步：B 口选择器接通图像桥

此时 CNN 不工作，`sram_b_arbiter` 把图像桥的地址和数据送到 `b_*`。

### 第四步：SRAM 保存图像

图像写入 `0x1000～0x1FFF`。全部写完并且 CRC 正确后，图像桥在邮箱中写 `FRAME_READY=1`。

### 第五步：CPU 读取并处理

固定程序通过 A 口轮询 `FRAME_READY`，然后从 `0x1000～0x1FFF` 读取图像，计算统计值，并写入 `0x2000～0x200C`。

### 第六步：图像桥读取结果

图像桥通过 B 口读取 `0x2000～0x200C`。

### 第七步：电脑收到结果

图像桥把结果打包，通过 `uart_tx` 发给电脑。电脑比较 FPGA 结果和本地计算结果。

---

## 14. 全部硬件的合并线束（唯一组号）

同一对硬件之间的多个信号在图上可以画成一根粗线，在线旁写组号和总位宽。粗线只是画图方式，不表示这些信号在 RTL 中短接。

### 14.1 全部线组

| 组号 | 一根线束（箭头方向） | 总位宽 | 包含信号 |
|---|---|---:|---|
| 001 | 板载晶振 → `fpga_face_top` | 1 | `sys_clk` |
| 002 | 复位硬件 → `fpga_face_top` | 1 | `rst_n_in` |
| 003 | USB-UART → `image_io_bridge` | 1 | `uart_rx` |
| 004 | `image_io_bridge` → USB-UART | 1 | `uart_tx` |
| 005 | `image_io_bridge`/状态逻辑 → LED | 3 | `led_ready`、`led_busy`、`led_error` |
| 006 | `cpu_core` → `imem_rom` | 33 | `imem_addr`、`imem_re` |
| 007 | `imem_rom` → `cpu_core` | 32 | `imem_rdata` |
| 008 | `cpu_core` → `data_sram_tdp` A 口 | 70 | `a_addr`、`a_wdata`、`a_wstrb`、`a_re`、`a_we` |
| 009 | `data_sram_tdp` A 口 → `cpu_core` | 32 | `a_rdata` |
| 010 | `image_io_bridge` → `sram_b_arbiter` | 70 | `io_mem_req`、`io_mem_we`、`io_mem_addr`、`io_mem_wdata`、`io_mem_be` |
| 011 | `sram_b_arbiter` → `image_io_bridge` | 35 | `io_mem_gnt`、`io_mem_rvalid`、`io_mem_rdata`、`io_mem_error` |
| 012 | `cnn_accelerator` → `sram_b_arbiter` | 70 | `cnn_mem_req`、`cnn_mem_we`、`cnn_mem_addr`、`cnn_mem_wdata`、`cnn_mem_be` |
| 013 | `sram_b_arbiter` → `cnn_accelerator` | 35 | `cnn_mem_gnt`、`cnn_mem_rvalid`、`cnn_mem_rdata`、`cnn_mem_error` |
| 014 | `sram_b_arbiter` → `data_sram_tdp` B 口 | 70 | `b_req`、`b_we`、`b_addr`、`b_wdata`、`b_be` |
| 015 | `data_sram_tdp` B 口 → `sram_b_arbiter` | 35 | `b_gnt`、`b_rvalid`、`b_rdata`、`b_error` |

### 14.2 每个硬件的输入/输出线组

| 硬件 | 输入线组 | 输出线组 |
|---|---|---|
| `fpga_face_top` | 001、002、003 | 004、005 |
| `imem_rom` | 006 | 007 |
| `cpu_core` | 007、009 | 006、008 |
| `image_io_bridge` | 003、011 | 004、005、010 |
| `sram_b_arbiter` | 010、012、015 | 011、013、014 |
| `data_sram_tdp` | 008、014 | 009、015 |
| `cnn_accelerator` | 013 | 012 |

时钟和复位进入各个时序模块的内部扇出没有在这张简化表中重复画很多根线。真正写 RTL 顶层时，`cpu_core`、`imem_rom`、`data_sram_tdp`、`image_io_bridge`、`sram_b_arbiter` 和 `cnn_accelerator` 都应连接同一系统时钟和同步后的复位。

---

## 15. 不能接错的地方

### 15.1 不要把 UART 直接接 SRAM

错误接法：

```text
uart_rx → SRAM data
```

正确接法：

```text
uart_rx → image_io_bridge → sram_b_arbiter → SRAM B口
```

UART 一次传 1 bit，SRAM 一次处理 32 bit，中间必须由图像桥完成接收、组字和地址计数。

### 15.2 不要把图像桥和 CNN 输出直接并联

两者都能输出地址和写数据，必须经过 `sram_b_arbiter`，否则会多驱动。

### 15.3 不要给 CPU A 口增加任意等待

当前 CPU 没有 Data SRAM `ready` 输入。A 口必须按照现有契约固定一周期返回读数据。

### 15.4 不要同时写同一个地址

CPU A 口与 B 口可以访问不同地址，但不能同周期写同一个 32 位字。邮箱协议和处理流程必须避免这种情况。

### 15.5 不要把当前结果说成人脸识别结果

第一阶段的 `pixel_count/sum/xor/status` 只是验证 SRAM 数据通路。真实人脸编号必须等 CNN、模型、权重、量化和最终输出格式完成后才能产生。

## 16. 第一阶段实际需要实现的最小集合

第一次上板可以暂时不接真实 CNN，只实现：

1. `imem_rom`：固定 CPU 程序。
2. `cpu_core`：现有真实 Control + 生产 Datapath。
3. `data_sram_tdp`：256 KiB 双口 SRAM。
4. `image_io_bridge`：UART 输入、输出和简单 CRC。
5. `sram_b_arbiter`：此时 CNN 请求固定为 0，也仍保留接口位置。
6. `fpga_face_top`：时钟、复位、UART 和 LED。

第一阶段通过标准：

- 电脑发送 64×64 灰度图。
- SRAM `0x1000～0x1FFF` 与原图字节完全一致。
- CPU 从 A 口读取全部 4096 字节。
- CPU 把统计结果写入 `0x2000～0x200C`。
- 电脑从 `uart_tx` 收到正确结果。
- 连续发送 100 张图片不丢帧、不覆盖、不出现 A/B 同地址写冲突。

达到这些条件后，再接 CNN stub 和真实 CNN，会比一开始同时调试所有模块容易定位问题。
