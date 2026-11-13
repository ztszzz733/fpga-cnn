# CPU 外部 ADDR / DATA / CONTROL 三组总线设计说明（新手版）

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## 1. 先给结论

CPU 外部连接可以统一画成三种线组：

```text
ADDR     地址线组
DATA     数据线组
CONTROL  控制和状态线组
```

但这里的“三条总线”是**三类线束**，不是三根单 bit 电线，也不是把所有外设接到同一根共享物理总线上。

当前系统建议保留四套独立接口：

1. `I-BUS`：`fetch_unit` 与同步 IMEM 之间的只读指令总线；
2. `SRAM-A BUS`：`memory_access_unit` 与 Data SRAM A 口之间的 CPU 数据总线；
3. `MMIO BUS`：`memory_access_unit` 与 CNN MMIO 寄存器之间的控制寄存器总线；
4. `SRAM-B BUS`：CNN、图像输入、仲裁器与 Data SRAM B 口之间的共享数据搬运总线。

每一套接口都在图上画成 ADDR、DATA、CONTROL 三条粗线组。

> 不建议现在把 IMEM、Data SRAM A 口和 CNN MMIO 强行合成一根共享总线。当前 CPU 可以同时取下一条指令，并让流水线中的其他指令访问数据或 MMIO；一根共享总线会产生争用，而当前 C1/Datapath 没有为这种争用提供统一的全流水暂停接口。

---

## 2. 整体硬件连接

```text
                                  ┌─────────────────┐
                     I-BUS        │   同步 IMEM     │
┌──────────────┐   ADDR ─────────→│  指令存储器     │
│ fetch_unit   │   DATA ←─────────│                 │
│ CPU取指模块  │   CTRL ─────────→│                 │
└──────────────┘                  └─────────────────┘

┌──────────────────────┐          ┌─────────────────┐
│ memory_access_unit   │ SRAM-A   │ Data SRAM A口   │
│ CPU访存模块          │ ADDR ───→│ CPU专用         │
│                      │ DATA ←──→│                 │
│                      │ CTRL ───→│                 │
│                      │          └─────────────────┘
│                      │
│                      │ MMIO     ┌─────────────────┐
│                      │ ADDR ───→│ cnn_mmio_regs   │
│                      │ DATA ←──→│ CNN寄存器从设备  │
│                      │ CTRL ←──→│                 │
└──────────────────────┘          └────────┬────────┘
                                           │ 配置/状态
                                           ↕
                                  ┌─────────────────┐
                                  │ cnn_accelerator │
                                  │ CNN计算模块      │
                                  └────────┬────────┘
                                           │ cnn_mem_* 70/35
                                           ↕
┌────────────────┐                ┌─────────────────┐
│ image_io_bridge│── io_mem_* ───→│ sram_b_arbiter  │
└────────────────┘       70/35    └────────┬────────┘
                                           │ b_* 70/35
                                           ↕
                                  ┌─────────────────┐
                                  │ Data SRAM B口   │
                                  │ 图像/CNN共享    │
                                  └─────────────────┘
```

CPU 使用 Data SRAM A 口；CNN 和图像输入通过仲裁器使用 B 口。CPU 与 CNN 不会争用同一个 SRAM 物理端口。

---

## 3. 三组线的基本定义

### 3.1 ADDR 地址线组

ADDR 告诉从设备“访问哪里”。

本系统地址均为：

```text
32 bit 字节地址
```

例如 `0x0000_0004` 表示从基址开始偏移 4 字节的位置。

### 3.2 DATA 数据线组

DATA 搬运真正的数据，分为两个方向：

```text
写数据：主设备 → 从设备
读数据：从设备 → 主设备
```

虽然硬件图可以把它们合并画成一条双向 DATA 粗线，但 SystemVerilog 中应使用两根独立的单向信号：

```text
wdata[31:0]  主设备输出
rdata[31:0]  从设备输出
```

不建议在 FPGA 内部使用 `inout` 三态数据总线。

### 3.3 CONTROL 控制和状态线组

CONTROL 告诉双方：

- 当前有没有请求；
- 是读还是写；
- 哪些字节有效；
- 请求是否被接受；
- 返回数据是否有效；
- 本次访问是否出错。

不同接口的时序不同，所以 CONTROL 中包含的信号也不同。

### 3.4 `clk` 和 `rst_n` 是否属于总线

本文把 `clk` 和 `rst_n` 视为 SoC 公共系统线，不计入 ADDR/DATA/CONTROL 接口位宽。

它们的来源和去向是：

| 信号 | 位宽 | 来源 | 去向 |
|---|---:|---|---|
| `clk` | 1 | SoC 时钟硬件 | CPU、IMEM、Data SRAM、MMIO、仲裁器、CNN |
| `rst_n` | 1 | SoC 复位硬件 | CPU、IMEM、Data SRAM、MMIO、仲裁器、CNN |

---

## 4. 哪些 CPU 内部模块直接使用外部总线

五个 CPU 功能模块中，只有两个模块直接连接外部总线。

| CPU 内部模块 | 是否直接连接外部总线 | 连接对象 | 作用 |
|---|---|---|---|
| `fetch_unit` | 是 | 同步 IMEM | 提供取指地址，接收指令 |
| `decode_execute_unit` | 否 | 无 | 译码、读寄存器、计算 ALU 结果和访存地址 |
| `memory_access_unit` | 是 | Data SRAM A 口、CNN MMIO | 发出数据读写和 MMIO 访问 |
| `writeback_unit` | 否 | 无 | 从访存单元接收 Load/MMIO 数据并写回寄存器堆 |
| `pipeline_control_unit` | 否 | 无 | 控制暂停、冲刷和前递，不直接读取外部数据 |

因此，数据获取路径不是“所有 CPU 模块一起连存储器”，而是：

```text
IMEM数据：IMEM → fetch_unit → decode_execute_unit

SRAM/MMIO数据：
Data SRAM或MMIO → memory_access_unit → writeback_unit
                                  └→ decode_execute_unit（M级前递）
```

---

## 5. I-BUS：CPU 与同步 IMEM

### 5.1 主设备和从设备

| 角色 | 模块 |
|---|---|
| 总线主设备 | CPU 内部 `fetch_unit` |
| 总线从设备 | CPU 外部 `imem_rom` |

主设备决定读哪个地址，从设备返回该地址的指令。

### 5.2 ADDR 地址线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `imem_addr[31:0]` | 32 | `fetch_unit` | `imem_rom` | 要读取的指令字节地址 |

ADDR 合计：32 bit，方向为 CPU → IMEM。

### 5.3 DATA 数据线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `imem_rdata[31:0]` | 32 | `imem_rom` | `fetch_unit` | 返回的一条 RV32I 指令 |

DATA 合计：32 bit，方向为 IMEM → CPU。

IMEM 是只读指令存储器，因此没有 `imem_wdata`。

### 5.4 CONTROL 控制线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `imem_re` | 1 | `fetch_unit` | `imem_rom` | 为 1 时发出指令读请求 |

CONTROL 合计：1 bit，方向为 CPU → IMEM。

当前 IMEM 是固定一周期同步返回，没有独立的 `ready`、`rvalid` 或 `error`。

### 5.5 请求和返回位宽

```text
CPU → IMEM 请求：ADDR 32 + CONTROL 1 = 33 bit
IMEM → CPU 返回：DATA 32 = 32 bit
```

### 5.6 CPU 如何取得一条指令

用新手语言说明：

1. `fetch_unit` 中的 PC 保存当前指令地址；
2. `fetch_unit` 把 PC 放到 `imem_addr`；
3. `fetch_unit` 拉高 `imem_re`；
4. IMEM 在上升沿接受地址；
5. 固定一个周期后，IMEM 把指令放到 `imem_rdata`；
6. Fetch Adapter 把返回指令和原请求 PC 配对；
7. IF/ID 保存 `instr_d`、`pc_d`、`pc4_d`；
8. `decode_execute_unit` 在下一阶段接收并译码。

### 5.7 为什么 IMEM 可以与 Data SRAM 使用相同基址

当前 CPU 是 Harvard 结构：I-BUS 和 SRAM-A BUS 是两套独立线。

因此：

```text
imem_addr = 0x0000_0000
dmem_addr = 0x0000_0000
```

不会冲突。前者访问指令存储器，后者访问数据存储器。

---

## 6. SRAM-A BUS：CPU 与 Data SRAM A 口

### 6.1 主设备和从设备

| 角色 | 模块 |
|---|---|
| 总线主设备 | CPU 内部 `memory_access_unit` |
| 总线从设备 | CPU 外部 `data_sram_tdp.A` |

CPU A 口是专用端口，不经过 B 口仲裁器。

### 6.2 ADDR 地址线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `dmem_addr[31:0]` | 32 | `memory_access_unit` | Data SRAM A 口 | Load/Store 字节地址 |

ADDR 合计：32 bit，方向为 CPU → SRAM。

### 6.3 DATA 数据线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `dmem_wdata[31:0]` | 32 | `memory_access_unit` | Data SRAM A 口 | Store 写数据 |
| `dmem_rdata[31:0]` | 32 | Data SRAM A 口 | `memory_access_unit` | Load 返回的 32 bit 存储字 |

DATA 有两个方向：

```text
CPU → SRAM：32 bit 写数据
SRAM → CPU：32 bit 读数据
```

物理信号合计为 64 bit，但任何一次事务只按读或写使用对应方向。

### 6.4 CONTROL 控制线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `dmem_wstrb[3:0]` | 4 | `memory_access_unit` | Data SRAM A 口 | 四个写字节 lane 的使能 |
| `dmem_re` | 1 | `memory_access_unit` | Data SRAM A 口 | 读请求 |
| `dmem_we` | 1 | `memory_access_unit` | Data SRAM A 口 | 写请求 |

CONTROL 合计：6 bit，方向为 CPU → SRAM。

当前 A 口没有独立 `ready` 和 `error` 返回。

### 6.5 请求和返回位宽

```text
CPU → SRAM A请求：
ADDR 32 + DATA写 32 + CONTROL 6 = 70 bit

SRAM A → CPU返回：
DATA读 32 = 32 bit
```

### 6.6 CPU 如何执行 Load

以 `lw x5, 0(x1)` 为例：

1. `decode_execute_unit` 从寄存器堆读出 `x1`；
2. ALU 计算 `x1 + 立即数`，得到 `alu_result_e`；
3. `memory_access_unit` 判断地址落在 Data SRAM 范围；
4. 它把地址放到 `dmem_addr`，拉高 `dmem_re`；
5. SRAM 在 E→M 接受沿保存读地址；
6. M 级期间，SRAM 将 32 bit 存储字放到 `dmem_rdata`；
7. LSU 根据 LB/LH/LW/LBU/LHU 类型抽取和扩展数据；
8. `read_data_m` 进入 `writeback_unit`；
9. W 级把结果写入 `x5`。

紧邻 Load 的下一条指令如果马上使用 `x5`，`pipeline_control_unit` 会插入一拍 bubble。

### 6.7 CPU 如何执行 Store

以 `sw x5, 0(x1)` 为例：

1. ALU 计算 Store 地址；
2. Store 前递选择器取得最新的 `x5` 数据；
3. LSU 根据地址低位形成 `dmem_wdata` 和 `dmem_wstrb`；
4. `memory_access_unit` 输出 `dmem_addr`、`dmem_wdata`，并拉高 `dmem_we`；
5. SRAM 在 E→M 接受沿写入被 `dmem_wstrb` 选中的字节；
6. Store 没有 `dmem_rdata` 写回。

---

## 7. MMIO BUS：CPU 与 CNN MMIO 寄存器

### 7.1 主设备和从设备

| 角色 | 模块 |
|---|---|
| 总线主设备 | CPU 内部 `memory_access_unit` |
| 总线从设备 | CPU 外部 `cnn_mmio_regs` |

MMIO 的作用是配置和查看 CNN，不用于直接搬运整幅图像、权重或卷积结果。

### 7.2 ADDR 地址线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `mmio_addr[31:0]` | 32 | `memory_access_unit` | `cnn_mmio_regs` | 要访问的 CNN 寄存器地址 |

ADDR 合计：32 bit，方向为 CPU → MMIO。

### 7.3 DATA 数据线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `mmio_wdata[31:0]` | 32 | `memory_access_unit` | `cnn_mmio_regs` | CPU 写入的寄存器数据 |
| `mmio_rdata[31:0]` | 32 | `cnn_mmio_regs` | `memory_access_unit` | MMIO 返回的寄存器数据 |

DATA 物理信号合计为 64 bit，分为 32 bit 写方向和 32 bit 读方向。

### 7.4 CONTROL 控制和状态线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `mmio_re` | 1 | `memory_access_unit` | `cnn_mmio_regs` | MMIO 读请求 |
| `mmio_we` | 1 | `memory_access_unit` | `cnn_mmio_regs` | MMIO 写请求 |
| `mmio_ready` | 1 | `cnn_mmio_regs` | `memory_access_unit` | 合法访问在本周期已经就绪 |

CONTROL 物理信号合计为 3 bit：

```text
CPU → MMIO：2 bit
MMIO → CPU：1 bit
```

### 7.5 请求和返回位宽

```text
CPU → MMIO请求：
ADDR 32 + DATA写 32 + CONTROL(re/we) 2 = 66 bit

MMIO → CPU返回：
DATA读 32 + CONTROL(ready) 1 = 33 bit
```

### 7.6 MMIO 地址表

MMIO 基址为 `0x4000_0000`，窗口为 4 KiB。

| 地址 | 寄存器 | 方向 | 含义 |
|---:|---|---|---|
| `0x4000_0000` | `CONTROL` | CPU→CNN | start、soft_reset 脉冲 |
| `0x4000_0004` | `STATUS` | CNN→CPU | busy、done、error |
| `0x4000_0008` | `INPUT_ADDR` | CPU→CNN | 输入特征首地址 |
| `0x4000_000C` | `OUTPUT_ADDR` | CPU→CNN | 输出特征或分数首地址 |
| `0x4000_0010` | `WEIGHT_ADDR` | CPU→CNN | 权重首地址 |
| `0x4000_0014` | `BIAS_ADDR` | CPU→CNN | bias 首地址 |
| `0x4000_0018` | `IMAGE_SIZE` | CPU→CNN | 高16位高度，低16位宽度 |
| `0x4000_001C` | `CHANNELS` | CPU→CNN | 高16位输出通道，低16位输入通道 |
| `0x4000_0020` | `CNN_PARAM` | CPU→CNN | 卷积、步长、padding、量化等参数 |

### 7.7 CPU 如何写 CNN 配置

以写 `INPUT_ADDR` 为例：

1. CPU 程序执行一条 `sw`；
2. `decode_execute_unit` 计算地址 `0x4000_0008`；
3. `memory_access_unit` 判断它属于 CNN MMIO；
4. M 级输出 `mmio_addr=0x4000_0008`；
5. 要写入的 SRAM 地址放到 `mmio_wdata`；
6. `mmio_we=1`；
7. `cnn_mmio_regs` 在上升沿保存 `INPUT_ADDR`；
8. 合法访问同时满足 `mmio_ready=1`。

### 7.8 CPU 如何读取 CNN 状态

1. CPU 程序对 `0x4000_0004` 执行 `lw`；
2. `memory_access_unit` 输出 `mmio_addr` 和 `mmio_re`；
3. `cnn_mmio_regs` 把 `STATUS` 放到 `mmio_rdata`；
4. `mmio_ready=1` 表示返回有效；
5. 数据经过 `memory_access_unit` 和 `writeback_unit` 写回 CPU 寄存器；
6. 软件检查 `busy`、`done`、`error`。

当前 STATUS 定义：

| 位 | 名称 | 含义 |
|---:|---|---|
| `[0]` | `busy` | CNN 正在运行或等待最后存储事务完成 |
| `[1]` | `done` | 本次任务成功完成 |
| `[2]` | `error` | 参数、地址、SRAM或内部运算发生错误 |

---

## 8. CNN MMIO 与 CNN 计算模块之间的三组线

CPU 通过 MMIO 写寄存器后，`cnn_mmio_regs` 把这些寄存器直接送给 `cnn_accelerator`。

这不是 CPU 总线的延长，而是 MMIO 寄存器到 CNN 的本地配置接口。

### 8.1 ADDR 配置地址线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `INPUT_ADDR[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 输入数据首地址 |
| `OUTPUT_ADDR[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 输出数据首地址 |
| `WEIGHT_ADDR[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 权重首地址 |
| `BIAS_ADDR[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | bias 首地址 |

ADDR 配置线合计：128 bit，方向为 MMIO → CNN。

这四个地址都必须：

- 4 字节对齐；
- 落在 Data SRAM `0x0000_0000～0x0003_FFFF`；
- 被 CNN 在合法 start 时锁存。

### 8.2 DATA 配置/状态线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `IMAGE_SIZE[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 图像高度和宽度 |
| `CHANNELS[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 输入和输出通道数 |
| `CNN_PARAM[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 当前层参数 |
| `STATUS[31:0]` | 32 | `cnn_accelerator` | `cnn_mmio_regs` | busy、done、error 等状态 |

方向统计：

```text
MMIO → CNN：96 bit
CNN → MMIO：32 bit
```

### 8.3 CONTROL 控制线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `CONTROL[31:0]` | 32 | `cnn_mmio_regs` | `cnn_accelerator` | 控制寄存器输出 |

其中当前有效控制位为：

| 位 | 名称 | 行为 |
|---:|---|---|
| `[0]` | `start` | CPU 写 1 产生一个系统周期启动脉冲 |
| `[1]` | `soft_reset` | CPU 写 1 产生一个系统周期软复位脉冲 |
| `[31:2]` | 保留 | 保持 0 |

CNN 收到合法 `start` 时应一次性锁存所有地址和参数，运行期间不能依赖 CPU 一直保持配置不变。

---

## 9. SRAM-B BUS：CNN 通过仲裁器访问 Data SRAM

CNN 不通过 CPU 的 `memory_access_unit` 搬运张量。CNN 自己是一个存储器主设备，通过 B 口总线读取输入、权重、bias，并写回结果。

### 9.1 CNN 到仲裁器的请求

#### ADDR 地址线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `cnn_mem_addr[31:0]` | 32 | `cnn_accelerator` | `sram_b_arbiter` | SRAM 字节地址 |

#### DATA 数据线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `cnn_mem_wdata[31:0]` | 32 | `cnn_accelerator` | `sram_b_arbiter` | CNN 写回数据 |

#### CONTROL 控制线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `cnn_mem_req` | 1 | `cnn_accelerator` | `sram_b_arbiter` | 请求有效，保持到授权 |
| `cnn_mem_we` | 1 | `cnn_accelerator` | `sram_b_arbiter` | 1=写，0=读 |
| `cnn_mem_be[3:0]` | 4 | `cnn_accelerator` | `sram_b_arbiter` | 四个字节 lane 使能 |

请求方向合计：

```text
ADDR 32 + DATA 32 + CONTROL 6 = 70 bit
```

### 9.2 仲裁器返回 CNN

#### ADDR 地址线组

返回方向没有地址线，合计 0 bit。

#### DATA 数据线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `cnn_mem_rdata[31:0]` | 32 | `sram_b_arbiter` | `cnn_accelerator` | CNN 读返回数据 |

#### CONTROL 控制和状态线组

| 信号 | 位宽 | 来源 | 去向 | 含义 |
|---|---:|---|---|---|
| `cnn_mem_gnt` | 1 | `sram_b_arbiter` | `cnn_accelerator` | 本周期接受请求 |
| `cnn_mem_rvalid` | 1 | `sram_b_arbiter` | `cnn_accelerator` | 当前读返回数据有效 |
| `cnn_mem_error` | 1 | `sram_b_arbiter` | `cnn_accelerator` | 地址、对齐、冲突或访问错误 |

返回方向合计：

```text
DATA 32 + CONTROL 3 = 35 bit
```

`cnn_mem_error` 是正式接口的一部分，不得把返回方向缩成 34 bit。

### 9.3 仲裁器到物理 SRAM B 口

仲裁器选择 CNN 或图像输入请求，然后用同样的三组线访问物理 B 口。

请求方向：

| 线组 | 信号 | 位宽 | 来源 | 去向 |
|---|---|---:|---|---|
| ADDR | `b_addr[31:0]` | 32 | `sram_b_arbiter` | Data SRAM B 口 |
| DATA | `b_wdata[31:0]` | 32 | `sram_b_arbiter` | Data SRAM B 口 |
| CONTROL | `b_req`、`b_we`、`b_be[3:0]` | 6 | `sram_b_arbiter` | Data SRAM B 口 |

返回方向：

| 线组 | 信号 | 位宽 | 来源 | 去向 |
|---|---|---:|---|---|
| DATA | `b_rdata[31:0]` | 32 | Data SRAM B 口 | `sram_b_arbiter` |
| CONTROL | `b_gnt`、`b_rvalid`、`b_error` | 3 | Data SRAM B 口 | `sram_b_arbiter` |

图像输入主设备使用对应的 `io_mem_*` 70/35 bit 接口，格式与 CNN 相同。

### 9.4 CNN 如何读取 SRAM 数据

1. CNN 把地址放到 `cnn_mem_addr`；
2. 设置 `cnn_mem_we=0`、`cnn_mem_be=0`；
3. 拉高 `cnn_mem_req`，并保持地址和控制不变；
4. 仲裁器选中 CNN 后返回 `cnn_mem_gnt=1`；
5. `req && gnt` 成立的上升沿表示读请求被接受；
6. CNN 撤销当前请求，并等待返回；
7. 固定一个周期后，`cnn_mem_rvalid=1`；
8. 若 `cnn_mem_error=0`，`cnn_mem_rdata` 是有效数据；
9. 若 `cnn_mem_error=1`，CNN 应终止当前任务并置 `STATUS.error`。

### 9.5 CNN 如何写回 SRAM 数据

1. CNN 给出 `cnn_mem_addr` 和 `cnn_mem_wdata`；
2. 设置 `cnn_mem_we=1`；
3. 用 `cnn_mem_be` 选择有效写字节；
4. 拉高 `cnn_mem_req`；
5. `cnn_mem_req && cnn_mem_gnt && cnn_mem_we` 成立的上升沿是写接受沿；
6. 若同周期 `cnn_mem_error=0`，写入成功；
7. 写事务不产生 `cnn_mem_rvalid`；
8. 最后一笔结果写成功以前，CNN 不得提前置 `done`。

---

## 10. CPU 配置 CNN、CNN 获取数据的完整流程

### 第一步：图像进入 Data SRAM

```text
外部图像数据
 → image_io_bridge
 → io_mem_* 三组线
 → sram_b_arbiter
 → Data SRAM B口
```

### 第二步：CPU 写 CNN 配置

CPU 通过 MMIO BUS 依次写入：

```text
INPUT_ADDR
OUTPUT_ADDR
WEIGHT_ADDR
BIAS_ADDR
IMAGE_SIZE
CHANNELS
CNN_PARAM
```

这些寄存器告诉 CNN 数据位于 Data SRAM 的什么位置，以及应执行什么运算。

### 第三步：CPU 启动 CNN

CPU 向 `CONTROL[0]` 写 1，`cnn_mmio_regs` 产生一个周期的 `start` 脉冲。

### 第四步：CNN 锁存配置

CNN 在 start 周期一次性锁存四个地址和三个参数，然后置 `STATUS.busy=1`。

### 第五步：CNN 读取输入、权重和 bias

CNN 通过 `cnn_mem_*` 70/35 bit 总线向仲裁器发请求，仲裁器再访问 Data SRAM B 口。

### 第六步：CNN 写回结果

CNN 把结果写入 `OUTPUT_ADDR` 指定的 SRAM 区域。最后一笔写成功后才能清 `busy` 并置 `done`。

### 第七步：CPU 查询结果

CPU 通过 MMIO BUS 读取 `STATUS`：

- `busy=1`：继续等待；
- `done=1`：结果已经写入 SRAM；
- `error=1`：任务失败。

### 第八步：CPU 读取 CNN 输出

CPU 使用 SRAM-A BUS，从 `OUTPUT_ADDR` 指定的位置读取分类分数或输出特征。

所以数据实际流向是：

```text
CPU通过MMIO配置CNN
CNN通过SRAM-B BUS搬运和计算数据
CPU再通过SRAM-A BUS读取结果
```

CNN 的大数据不经过 MMIO BUS。

---

## 11. 地址空间

| 地址空间 | 默认范围 | 接口 | 使用者 |
|---|---|---|---|
| IMEM | `0x0000_0000～0x0000_FFFF` | I-BUS | `fetch_unit` |
| Data SRAM | `0x0000_0000～0x0003_FFFF` | SRAM-A/B BUS | CPU、CNN、图像输入 |
| CNN MMIO | `0x4000_0000～0x4000_0FFF` | MMIO BUS | CPU |

IMEM 和 Data SRAM 地址范围可以重叠，因为它们位于两套独立总线上。

CNN 的 `INPUT_ADDR`、`OUTPUT_ADDR`、`WEIGHT_ADDR` 和 `BIAS_ADDR` 都是 Data SRAM 地址，不是 IMEM 地址，也不是 MMIO 地址。

---

## 12. 为什么现在不建议做一根统一共享总线

### 12.1 取指和数据访问需要并行

五级流水中，IF 级可能正在读取下一条指令，同时 E/M 级正在进行 Load、Store 或 MMIO。

如果所有访问共用一根地址线，就必须新增仲裁和暂停机制，否则同一周期无法同时表示两个地址。

### 12.2 SRAM 和 MMIO 当前可能在不同流水级产生请求

当前生产 Datapath 中：

- SRAM 请求在 E 级形成并于 E→M 接受；
- CNN MMIO 请求在 M 级形成；
- 不同指令可能让 SRAM 请求和 MMIO 请求出现在同一周期。

因此不能在 CPU 外部简单用一个 MUX 把两者硬并成一根总线而不处理冲突。

### 12.3 当前 CPU 没有通用总线等待接口

当前外部接口没有完整的统一：

```text
req / gnt / rvalid / error / pipeline_stall
```

如果将来要改成 AXI、AHB、OBI、Wishbone 或自定义统一总线，必须同时设计：

- 请求保持规则；
- 接受和返回握手；
- 总线忙时的全流水暂停；
- 读写顺序；
- MMIO 不可重复副作用；
- 异常和错误返回；
- IF 与数据访问仲裁；
- 对现有 load-use、分支冲刷和同步存储时序的重新验证。

这会改变当前接口契约，不再只是画图分组。

---

## 13. 画硬件图时怎么画

每套接口画三条粗线，在线旁边列出具体信号。

### 13.1 I-BUS

```text
ADDR[32]    imem_addr
DATA[32]    imem_rdata
CONTROL[1]  imem_re
```

### 13.2 SRAM-A BUS

```text
ADDR[32]       dmem_addr
DATA[32→]      dmem_wdata
DATA[32←]      dmem_rdata
CONTROL[6→]    dmem_wstrb[3:0], dmem_re, dmem_we
```

### 13.3 MMIO BUS

```text
ADDR[32]       mmio_addr
DATA[32→]      mmio_wdata
DATA[32←]      mmio_rdata
CONTROL[2→]    mmio_re, mmio_we
CONTROL[1←]    mmio_ready
```

### 13.4 CNN SRAM-B BUS

```text
ADDR[32→]      cnn_mem_addr
DATA[32→]      cnn_mem_wdata
DATA[32←]      cnn_mem_rdata
CONTROL[6→]    req, we, be[3:0]
CONTROL[3←]    gnt, rvalid, error
```

箭头必须保留，因为 DATA 和 CONTROL 都包含两个方向，不能只写一个总位宽而不说明方向。

---

## 14. 总线总表

| 接口 | 主设备 | 从设备 | ADDR | DATA 主→从 | DATA 从→主 | CONTROL 主→从 | CONTROL 从→主 |
|---|---|---|---:|---:|---:|---:|---:|
| I-BUS | `fetch_unit` | `imem_rom` | 32 | 0 | 32 | 1 | 0 |
| SRAM-A BUS | `memory_access_unit` | Data SRAM A | 32 | 32 | 32 | 6 | 0 |
| MMIO BUS | `memory_access_unit` | `cnn_mmio_regs` | 32 | 32 | 32 | 2 | 1 |
| CNN→Arbiter | `cnn_accelerator` | `sram_b_arbiter` | 32 | 32 | 32 | 6 | 3 |
| Arbiter→SRAM-B | `sram_b_arbiter` | Data SRAM B | 32 | 32 | 32 | 6 | 3 |

公共 `clk`、`rst_n` 不计入表中的总线位宽。

---

## 15. 一句话总结

> CPU 外部不是一根所有设备共享的总线，而是多套点对点接口；每套接口都可以在硬件图中统一分成 ADDR、DATA、CONTROL 三条线组。`fetch_unit` 通过 I-BUS 获取指令，`memory_access_unit` 通过 SRAM-A BUS 获取普通数据、通过 MMIO BUS 配置和读取 CNN，CNN 再通过带仲裁和错误返回的 SRAM-B BUS 自主搬运 Data SRAM 中的大数据。
