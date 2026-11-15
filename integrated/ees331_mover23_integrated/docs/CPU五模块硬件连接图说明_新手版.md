# CPU 五模块硬件连接图说明（新手版）

日期：2026-10-04  
依据：[译码单元与执行单元合并建议](译码执行单元合并建议.md)  
状态：目标硬件连接说明；当前生产 RTL 尚未重构成这五个独立顶层文件

> 本版把原来的 `decode_issue_unit` 和 `execute_unit` 合并为 `decode_execute_unit`。合并模块内部仍保留 `ID/EX` 流水寄存器，因此 CPU 仍是 IF、ID、EX、MEM、WB 五级流水。减少的是总图中的模块和外部连线，不是删除一个流水级。

---

## 1. 五个 CPU 功能模块

| 顺序 | 模块 | 中文名称 | 主要职责 |
|---:|---|---|---|
| 1 | `fetch_unit` | 取指单元 | PC、同步取指、IF/ID |
| 2 | `decode_execute_unit` | 译码与执行单元 | 译码、寄存器堆、ID/EX、前递选择、ALU、比较和跳转判断 |
| 3 | `memory_access_unit` | 访存单元 | EX/MEM、Data SRAM、CNN MMIO、M 级读数据 |
| 4 | `writeback_unit` | 写回单元 | MEM/WB、最终写回选择和寄存器堆写使能 |
| 5 | `pipeline_control_unit` | 流水控制单元 | 冒险、暂停、冲刷和前递控制 |

另外保留一个 `cpu_core` 集成壳。它只负责实例化、参数传递和接线，不算第六个功能模块。

CPU 外部有：

- 同步指令存储器 `imem_rom`；
- 双口 `Data SRAM`；
- `CNN MMIO` 寄存器；
- SRAM B 口仲裁器、图像输入和 CNN memory master，这些没有进入 CPU 五模块内部。

---

## 2. 三组线怎么理解

本文把每个模块的输入和输出统一分成三组。

### 2.1 数据线

数据线搬运真正要处理的内容，例如：

- 32 bit 指令；
- 寄存器操作数；
- 立即数；
- ALU 结果；
- SRAM/MMIO 读写数据；
- 最终写回数据。

### 2.2 信号线

信号线包含控制和状态，例如：

- `clk`、`rst_n`；
- `valid`；
- 读写使能；
- ALU、写回和前递选择；
- 暂停、冲刷和跳转重定向。

### 2.3 地址/编号线

地址/编号线指出“访问哪里”或“选择哪个寄存器”，例如：

- PC、PC+4、分支和跳转目标；
- IMEM、Data SRAM、CNN MMIO 地址；
- `rs1`、`rs2`、`rd` 等 5 bit 寄存器编号。

### 2.4 位宽统计规则

- `[31:0]` 表示 32 bit；
- `[4:0]` 表示 5 bit；
- 没有方括号的普通控制信号通常是 1 bit；
- 同一根输出同时送给两个对象叫作扇出，端口位宽只计算一次；
- “小计”是多个独立信号位宽的加法，不代表一定要写成一根匿名大总线。

---

## 3. 整体连接顺序

```text
同步 IMEM
   ↕
1. fetch_unit
   ↓ D级指令、PC和valid
2. decode_execute_unit
   ↓ E级结果和访存控制
3. memory_access_unit ↔ Data SRAM / CNN MMIO
   ↓ M级写回候选
4. writeback_unit
   └────────→ 返回 decode_execute_unit 的寄存器堆和EX前递

5. pipeline_control_unit
   ├─ 观察 D/E/M/W 状态
   ├─ 控制 fetch_unit 的PC、保持和冲刷
   └─ 控制 decode_execute_unit 的ID/EX冲刷和前递选择
```

原来 `decode_issue_unit → execute_unit` 的 201 bit 外部连接现在位于 `decode_execute_unit` 内部，不再穿过 `cpu_core` 顶层。

---

## 4. 模块 1：`fetch_unit`（取指单元）

### 4.1 它做什么

`fetch_unit` 根据 PC 从同步 IMEM 取出指令，并把指令、指令地址和 PC+4 保存到 IF/ID。

内部包含：

- PC 寄存器；
- PC+4 加法器；
- Next-PC 选择器；
- Fetch Adapter；
- IF/ID 流水寄存器。

### 4.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 同步 IMEM | `imem_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `pipeline_control_unit` | `pc_sel[1:0]`、`pc_en`、`if_id_en`、`if_id_flush` | 5 |
| **信号线小计** |  |  | **7** |
| 地址线 | `decode_execute_unit` | `branch_target_e[31:0]`、`jalr_target_e[31:0]` | 64 |
| **地址线小计** |  |  | **64** |

输入唯一端口合计：`32 + 7 + 64 = 103 bit`。

### 4.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_execute_unit` | `instr_d[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | 同步 IMEM | `imem_re` | 1 |
| 信号线 | `decode_execute_unit`、`pipeline_control_unit` | `valid_d` | 1 |
| **信号线小计** |  |  | **2** |
| 地址线 | 同步 IMEM | `imem_addr[31:0]` | 32 |
| 地址线 | `decode_execute_unit` | `pc_d[31:0]`、`pc4_d[31:0]` | 64 |
| **地址线小计** |  |  | **96** |

输出唯一端口合计：`32 + 2 + 96 = 130 bit`。

`valid_d` 同时送给译码执行单元和流水控制单元，但仍然只是一根 1 bit 输出。

### 4.4 本模块信号线明细

| 方向 | 信号 | 位宽 | 来源或对象 | 新手理解 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | SoC 时钟硬件 | 上升沿更新 PC、取指状态和 IF/ID |
| 输入 | `rst_n` | 1 | SoC 复位硬件 | 低电平时复位取指状态 |
| 输入 | `pc_sel` | 2 | `pipeline_control_unit` | 选择 PC+4、Branch/JAL 或 JALR 目标 |
| 输入 | `pc_en` | 1 | `pipeline_control_unit` | 是否允许 PC 更新 |
| 输入 | `if_id_en` | 1 | `pipeline_control_unit` | 是否允许 IF/ID 接收新内容 |
| 输入 | `if_id_flush` | 1 | `pipeline_control_unit` | 清除 IF/ID 中的错误路径指令 |
| 输出 | `imem_re` | 1 | 同步 IMEM | 发出取指读请求 |
| 输出 | `valid_d` | 1 | `decode_execute_unit`、`pipeline_control_unit` | D 级内容是否有效 |

---

## 5. 模块 2：`decode_execute_unit`（译码与执行单元）

### 5.1 为什么合并

原译码单元和执行单元之间需要传递 201 bit 的 E 级数据、地址/编号和控制信号。合并后，这组连接全部放在模块内部，总图不再绘制这条宽连接。

### 5.2 内部仍有两个逻辑区域

```text
┌──────────────── decode_execute_unit ────────────────┐
│                                                     │
│ D区：                                               │
│ 指令译码 → 寄存器堆读取 → 立即数生成                │
│                         │                           │
│                       ID/EX                         │
│                  （必须保留的寄存器）               │
│                         │                           │
│ E区：                                               │
│ 前递选择 → ALU输入选择 → ALU/比较 → 分支跳转判断    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

合并没有删除 ID/EX，也没有把 D 和 E 变成同一拍组合路径。

### 5.3 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `fetch_unit` | `instr_d[31:0]` | 32 |
| 数据线 | `memory_access_unit` | `mem_forward_m[31:0]` | 32 |
| 数据线 | `writeback_unit` | `wb_data_w[31:0]` | 32 |
| **数据线小计** |  |  | **96** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `fetch_unit` | `valid_d` | 1 |
| 信号线 | `pipeline_control_unit` | `id_ex_flush`、`fwd_a[1:0]`、`fwd_b[1:0]`、`fwd_store[1:0]` | 7 |
| 信号线 | `writeback_unit` | `rf_we_w` | 1 |
| **信号线小计** |  |  | **11** |
| 地址/编号线 | `fetch_unit` | `pc_d[31:0]`、`pc4_d[31:0]` | 64 |
| 地址/编号线 | `writeback_unit` | `rd_w[4:0]` | 5 |
| **地址/编号线小计** |  |  | **69** |

输入唯一端口合计：`96 + 11 + 69 = 176 bit`。

`wb_data_w` 进入合并模块后在内部同时连接：

- 寄存器堆写数据口；
- EX 级 WB 前递选择器。

因此不再需要从 `writeback_unit` 分别拉两条同名数据线到两个模块。

### 5.4 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `alu_result_e[31:0]`、`store_data_e[31:0]` | 64 |
| **数据线小计** |  |  | **64** |
| 信号线 | `memory_access_unit`、`pipeline_control_unit` | `valid_e`、`memread_e` | 2 |
| 信号线 | `memory_access_unit` | `regwrite_e`、`memwrite_e`、`load_type_e[2:0]`、`store_type_e[1:0]`、`wb_sel_e[1:0]` | 9 |
| 信号线 | `pipeline_control_unit` | `uses_rs1_d`、`uses_rs2_d`、`uses_rs1_e`、`uses_rs2_e` | 4 |
| 信号线 | `pipeline_control_unit` | `redirect`、`redirect_sel[1:0]` | 3 |
| **信号线小计** |  |  | **18** |
| 地址/编号线 | `memory_access_unit` | `pc4_e[31:0]` | 32 |
| 地址/编号线 | `memory_access_unit`、`pipeline_control_unit` | `rd_e[4:0]` | 5 |
| 地址/编号线 | `fetch_unit` | `branch_target_e[31:0]`、`jalr_target_e[31:0]` | 64 |
| 地址/编号线 | `pipeline_control_unit` | `rs1_d[4:0]`、`rs2_d[4:0]`、`rs1_e[4:0]`、`rs2_e[4:0]` | 20 |
| **地址/编号线小计** |  |  | **121** |

输出唯一端口合计：`64 + 18 + 121 = 203 bit`。

注意：

- `valid_e` 和 `memread_e` 同时送给访存单元与流水控制单元，各只计算一次；
- `rd_e` 同时送给访存单元与流水控制单元，也只计算一次；
- 原 `decode_issue_unit → execute_unit` 的 201 bit 连接没有消失，而是变成合并模块内部的 ID/EX 输出。

### 5.5 本模块信号线明细

#### 输入信号线

| 信号 | 位宽 | 来源 | 新手理解 |
|---|---:|---|---|
| `clk` | 1 | SoC 时钟硬件 | 更新寄存器堆和 ID/EX |
| `rst_n` | 1 | SoC 复位硬件 | 复位寄存器堆、ID/EX，并限制副作用 |
| `valid_d` | 1 | `fetch_unit` | D 级指令是否有效 |
| `id_ex_flush` | 1 | `pipeline_control_unit` | 清空 ID/EX，向 E 级插入 bubble |
| `fwd_a` | 2 | `pipeline_control_unit` | rs1 的 EX 前递来源选择 |
| `fwd_b` | 2 | `pipeline_control_unit` | rs2 的 EX 前递来源选择 |
| `fwd_store` | 2 | `pipeline_control_unit` | Store 写数据的前递来源选择 |
| `rf_we_w` | 1 | `writeback_unit` | 允许 W 级结果写入寄存器堆 |

#### 输出信号线

| 信号 | 位宽 | 输出对象 | 新手理解 |
|---|---:|---|---|
| `valid_e` | 1 | `memory_access_unit`、`pipeline_control_unit` | E 级内容是否有效 |
| `uses_rs1_d` | 1 | `pipeline_control_unit` | D 级是否真正使用 rs1 |
| `uses_rs2_d` | 1 | `pipeline_control_unit` | D 级是否真正使用 rs2 |
| `uses_rs1_e` | 1 | `pipeline_control_unit` | E 级是否真正使用 rs1 |
| `uses_rs2_e` | 1 | `pipeline_control_unit` | E 级是否真正使用 rs2 |
| `regwrite_e` | 1 | `memory_access_unit` | 后续是否写寄存器 |
| `memread_e` | 1 | `memory_access_unit`、`pipeline_control_unit` | 是否为 Load |
| `memwrite_e` | 1 | `memory_access_unit` | 是否为 Store |
| `load_type_e` | 3 | `memory_access_unit` | Load 类型和扩展方式 |
| `store_type_e` | 2 | `memory_access_unit` | Store 字节宽度 |
| `wb_sel_e` | 2 | `memory_access_unit` | 后续写回来源 |
| `redirect` | 1 | `pipeline_control_unit` | 是否需要改变取指路线 |
| `redirect_sel` | 2 | `pipeline_control_unit` | 选择 Branch/JAL 或 JALR 目标 |

### 5.6 模块内部但不再画到顶层的信号

以下信号仍然存在，只是不再作为两个顶层模块之间的端口：

| 内部线组 | 信号 | 合计位宽 |
|---|---|---:|
| 数据线 | `rd1_e[31:0]`、`rd2_e[31:0]`、`imm_e[31:0]` | 96 |
| 信号线 | `valid_e`、源使用标志、ALU 选择、访存类型、写回选择、分支和跳转类型 | 26 |
| 地址/编号线 | `pc_e[31:0]`、`pc4_e[31:0]`、`rs1_e[4:0]`、`rs2_e[4:0]`、`rd_e[4:0]` | 79 |
| 合计 | 原 Decode→Execute 内部连接 | **201** |

---

## 6. 模块 3：`memory_access_unit`（访存单元）

### 6.1 它做什么

`memory_access_unit` 接收 E 级结果，完成地址译码和 Load/Store 处理，并决定访问 Data SRAM 还是 CNN MMIO。

内部包含：

- EX/MEM 流水寄存器；
- E/M 地址译码；
- LSU；
- Data SRAM 请求生成；
- CNN MMIO 路由；
- M 级读数据和前递值选择。

### 6.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_execute_unit` | `alu_result_e[31:0]`、`store_data_e[31:0]` | 64 |
| 数据线 | Data SRAM A 口 | `dmem_rdata[31:0]` | 32 |
| 数据线 | CNN MMIO | `mmio_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **128** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `decode_execute_unit` | `valid_e`、`regwrite_e`、`memread_e`、`memwrite_e`、`load_type_e[2:0]`、`store_type_e[1:0]`、`wb_sel_e[1:0]` | 11 |
| 信号线 | CNN MMIO | `mmio_ready` | 1 |
| **信号线小计** |  |  | **14** |
| 地址/编号线 | `decode_execute_unit` | `pc4_e[31:0]`、`rd_e[4:0]` | 37 |
| **地址/编号线小计** |  |  | **37** |

输入唯一端口合计：`128 + 14 + 37 = 179 bit`。

`alu_result_e` 对普通指令是 ALU 结果，对 Load/Store 又会被解释成访存地址。为了让模块两端分类一致，CPU 内部 `decode_execute_unit → memory_access_unit` 边界把它归入数据线；经过地址译码后形成的 `dmem_addr`、`mmio_addr` 才归入外部地址线。

### 6.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_execute_unit` | `mem_forward_m[31:0]` | 32 |
| 数据线 | `writeback_unit` | `read_data_m[31:0]`、`alu_result_m[31:0]` | 64 |
| 数据线 | Data SRAM A 口 | `dmem_wdata[31:0]` | 32 |
| 数据线 | CNN MMIO | `mmio_wdata[31:0]` | 32 |
| **数据线小计** |  |  | **160** |
| 信号线 | `writeback_unit`、`pipeline_control_unit` | `valid_m`、`regwrite_m` | 2 |
| 信号线 | `pipeline_control_unit` | `memread_m` | 1 |
| 信号线 | `writeback_unit` | `wb_sel_m[1:0]` | 2 |
| 信号线 | Data SRAM A 口 | `dmem_wstrb[3:0]`、`dmem_re`、`dmem_we` | 6 |
| 信号线 | CNN MMIO | `mmio_re`、`mmio_we` | 2 |
| **信号线小计** |  |  | **13** |
| 地址/编号线 | `writeback_unit` | `pc4_m[31:0]` | 32 |
| 地址/编号线 | `writeback_unit`、`pipeline_control_unit` | `rd_m[4:0]` | 5 |
| 地址/编号线 | Data SRAM A 口 | `dmem_addr[31:0]` | 32 |
| 地址/编号线 | CNN MMIO | `mmio_addr[31:0]` | 32 |
| **地址/编号线小计** |  |  | **101** |

输出唯一端口合计：`160 + 13 + 101 = 274 bit`。

### 6.4 本模块信号线明细

#### 输入信号线

| 信号 | 位宽 | 来源 | 新手理解 |
|---|---:|---|---|
| `clk` | 1 | SoC 时钟硬件 | 更新 EX/MEM |
| `rst_n` | 1 | SoC 复位硬件 | 复位 EX/MEM，禁止复位期间写副作用 |
| `valid_e` | 1 | `decode_execute_unit` | E 级内容是否有效 |
| `regwrite_e` | 1 | `decode_execute_unit` | 后续是否写寄存器 |
| `memread_e` | 1 | `decode_execute_unit` | 是否执行 Load |
| `memwrite_e` | 1 | `decode_execute_unit` | 是否执行 Store |
| `load_type_e` | 3 | `decode_execute_unit` | Load 类型 |
| `store_type_e` | 2 | `decode_execute_unit` | Store 类型 |
| `wb_sel_e` | 2 | `decode_execute_unit` | 写回来源 |
| `mmio_ready` | 1 | CNN MMIO | MMIO 访问是否就绪 |

#### 输出信号线

| 信号 | 位宽 | 输出对象 | 新手理解 |
|---|---:|---|---|
| `valid_m` | 1 | `writeback_unit`、`pipeline_control_unit` | M 级是否有效 |
| `regwrite_m` | 1 | `writeback_unit`、`pipeline_control_unit` | M 级是否会写寄存器 |
| `memread_m` | 1 | `pipeline_control_unit` | M 级是否为 Load，防止错误前递 |
| `wb_sel_m` | 2 | `writeback_unit` | W 级写回来源选择 |
| `dmem_wstrb` | 4 | Data SRAM A 口 | 四个字节通道写使能 |
| `dmem_re` | 1 | Data SRAM A 口 | SRAM 读请求 |
| `dmem_we` | 1 | Data SRAM A 口 | SRAM 写请求 |
| `mmio_re` | 1 | CNN MMIO | MMIO 读请求 |
| `mmio_we` | 1 | CNN MMIO | MMIO 写请求 |

---

## 7. 模块 4：`writeback_unit`（写回单元）

### 7.1 它做什么

`writeback_unit` 保存 MEM/WB 状态，在 ALU 结果、Load/MMIO 数据和 PC+4 中选择最终写回值。

### 7.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `read_data_m[31:0]`、`alu_result_m[31:0]` | 64 |
| **数据线小计** |  |  | **64** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `memory_access_unit` | `valid_m`、`regwrite_m`、`wb_sel_m[1:0]` | 4 |
| **信号线小计** |  |  | **6** |
| 地址/编号线 | `memory_access_unit` | `pc4_m[31:0]`、`rd_m[4:0]` | 37 |
| **地址/编号线小计** |  |  | **37** |

输入唯一端口合计：`64 + 6 + 37 = 107 bit`。

### 7.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_execute_unit` | `wb_data_w[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | `pipeline_control_unit` | `valid_w`、`regwrite_w` | 2 |
| 信号线 | `decode_execute_unit` | `rf_we_w` | 1 |
| **信号线小计** |  |  | **3** |
| 地址/编号线 | `decode_execute_unit`、`pipeline_control_unit` | `rd_w[4:0]` | 5 |
| **地址/编号线小计** |  |  | **5** |

输出唯一端口合计：`32 + 3 + 5 = 40 bit`。

### 7.4 本模块信号线明细

| 方向 | 信号 | 位宽 | 来源或对象 | 新手理解 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | SoC 时钟硬件 | 更新 MEM/WB |
| 输入 | `rst_n` | 1 | SoC 复位硬件 | 复位 MEM/WB |
| 输入 | `valid_m` | 1 | `memory_access_unit` | M 级内容是否有效 |
| 输入 | `regwrite_m` | 1 | `memory_access_unit` | 当前指令是否允许写寄存器 |
| 输入 | `wb_sel_m` | 2 | `memory_access_unit` | 选择 ALU、读数据或 PC+4 |
| 输出 | `valid_w` | 1 | `pipeline_control_unit` | W 级内容是否有效 |
| 输出 | `regwrite_w` | 1 | `pipeline_control_unit` | W 级是否具有写寄存器语义 |
| 输出 | `rf_we_w` | 1 | `decode_execute_unit` | 最终寄存器堆写使能 |

最终写使能仍为：

```text
rf_we_w = valid_w && regwrite_w && (rd_w != 0)
```

---

## 8. 模块 5：`pipeline_control_unit`（流水控制单元）

### 8.1 它做什么

`pipeline_control_unit` 是“交通指挥员”。它不搬运 32 bit 运算数据，只观察 D/E/M/W 的寄存器编号和状态，然后决定暂停、冲刷和前递。

### 8.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 无 | 无 | 0 |
| **数据线小计** |  |  | **0** |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `fetch_unit` | `valid_d` | 1 |
| 信号线 | `decode_execute_unit` | `uses_rs1_d`、`uses_rs2_d`、`valid_e`、`uses_rs1_e`、`uses_rs2_e`、`memread_e`、`redirect`、`redirect_sel[1:0]` | 9 |
| 信号线 | `memory_access_unit` | `valid_m`、`regwrite_m`、`memread_m` | 3 |
| 信号线 | `writeback_unit` | `valid_w`、`regwrite_w` | 2 |
| **信号线小计** |  |  | **16** |
| 地址/编号线 | `decode_execute_unit` | `rs1_d[4:0]`、`rs2_d[4:0]`、`rs1_e[4:0]`、`rs2_e[4:0]`、`rd_e[4:0]` | 25 |
| 地址/编号线 | `memory_access_unit` | `rd_m[4:0]` | 5 |
| 地址/编号线 | `writeback_unit` | `rd_w[4:0]` | 5 |
| **地址/编号线小计** |  |  | **35** |

输入唯一端口合计：`0 + 16 + 35 = 51 bit`。

### 8.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 无 | 无 | 0 |
| **数据线小计** |  |  | **0** |
| 信号线 | `fetch_unit` | `pc_sel[1:0]`、`pc_en`、`if_id_en`、`if_id_flush` | 5 |
| 信号线 | `decode_execute_unit` | `id_ex_flush`、`fwd_a[1:0]`、`fwd_b[1:0]`、`fwd_store[1:0]` | 7 |
| **信号线小计** |  |  | **12** |
| 地址/编号线 | 无 | 无 | 0 |
| **地址/编号线小计** |  |  | **0** |

输出唯一端口合计：12 bit。

### 8.4 本模块信号线明细

#### 输入信号线

| 信号 | 位宽 | 来源 | 新手理解 |
|---|---:|---|---|
| `rst_n` | 1 | SoC 复位硬件 | 复位期间输出安全控制 |
| `valid_d` | 1 | `fetch_unit` | D 级是否有效 |
| `uses_rs1_d` | 1 | `decode_execute_unit` | D 级是否使用 rs1 |
| `uses_rs2_d` | 1 | `decode_execute_unit` | D 级是否使用 rs2 |
| `valid_e` | 1 | `decode_execute_unit` | E 级是否有效 |
| `uses_rs1_e` | 1 | `decode_execute_unit` | E 级是否使用 rs1 |
| `uses_rs2_e` | 1 | `decode_execute_unit` | E 级是否使用 rs2 |
| `memread_e` | 1 | `decode_execute_unit` | E 级是否为 Load |
| `redirect` | 1 | `decode_execute_unit` | E 级是否要求改变取指路线 |
| `redirect_sel` | 2 | `decode_execute_unit` | 目标地址类型 |
| `valid_m` | 1 | `memory_access_unit` | M 级是否有效 |
| `regwrite_m` | 1 | `memory_access_unit` | M 级是否会写寄存器 |
| `memread_m` | 1 | `memory_access_unit` | M 级是否为 Load |
| `valid_w` | 1 | `writeback_unit` | W 级是否有效 |
| `regwrite_w` | 1 | `writeback_unit` | W 级是否会写寄存器 |

#### 输出信号线

| 信号 | 位宽 | 输出对象 | 新手理解 |
|---|---:|---|---|
| `pc_sel` | 2 | `fetch_unit` | 下一 PC 来源选择 |
| `pc_en` | 1 | `fetch_unit` | PC 写使能 |
| `if_id_en` | 1 | `fetch_unit` | IF/ID 写使能 |
| `if_id_flush` | 1 | `fetch_unit` | 清空 IF/ID |
| `id_ex_flush` | 1 | `decode_execute_unit` | 清空内部 ID/EX，插入 bubble |
| `fwd_a` | 2 | `decode_execute_unit` | EX 的 rs1 前递选择 |
| `fwd_b` | 2 | `decode_execute_unit` | EX 的 rs2 前递选择 |
| `fwd_store` | 2 | `decode_execute_unit` | Store 数据前递选择 |

控制优先级继续保持：

```text
复位 > EX重定向 > load-use暂停 > 正常推进
```

---

## 9. CPU 外部模块 1：同步指令存储器 `imem_rom`

### 9.1 功能

同步 IMEM 保存程序。`fetch_unit` 给出地址和读请求，IMEM 在固定一个周期后返回 32 bit 指令。

### 9.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 无 | 无 | 0 |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `fetch_unit` | `imem_re` | 1 |
| **信号线小计** |  |  | **3** |
| 地址线 | `fetch_unit` | `imem_addr[31:0]` | 32 |
| **地址线小计** |  |  | **32** |

### 9.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `fetch_unit` | `imem_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | 无 | 无 | 0 |
| 地址线 | 无 | 无 | 0 |

### 9.4 信号线明细

| 方向 | 信号 | 位宽 | 来源或对象 | 含义 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | SoC 时钟硬件 | 同步返回指令 |
| 输入 | `rst_n` | 1 | SoC 复位硬件 | 复位时返回安全 NOP |
| 输入 | `imem_re` | 1 | `fetch_unit` | 接受取指请求 |

当前接口按固定一周期返回，因此没有 `imem_ready`。

---

## 10. CPU 外部模块 2：双口 `Data SRAM`

### 10.1 功能和边界

CPU 只直接使用 Data SRAM A 口。B 口由 CPU 外部 `sram_b_arbiter` 在图像输入和 CNN memory master 之间仲裁。

下面只统计公共时钟/复位和 CPU A 口；不把 B 口混入 CPU 五模块接线。

### 10.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `dmem_wdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `memory_access_unit` | `dmem_wstrb[3:0]`、`dmem_re`、`dmem_we` | 6 |
| **信号线小计** |  |  | **8** |
| 地址线 | `memory_access_unit` | `dmem_addr[31:0]` | 32 |
| **地址线小计** |  |  | **32** |

CPU 专用 A 口请求本身仍是 70 bit：

```text
dmem_addr 32 + dmem_wdata 32 + dmem_wstrb 4 + dmem_re 1 + dmem_we 1 = 70
```

公共 `clk`、`rst_n` 不计入 70 bit A 口请求。

### 10.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `dmem_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | 无（A 口没有独立 ready/error） | 无 | 0 |
| 地址线 | 无 | 无 | 0 |

### 10.4 A 口信号线明细

| 方向 | 信号 | 位宽 | 来源或对象 | 含义 |
|---|---|---:|---|---|
| 输入 | `dmem_wstrb` | 4 | `memory_access_unit` | 四个写字节使能 |
| 输入 | `dmem_re` | 1 | `memory_access_unit` | SRAM 读请求 |
| 输入 | `dmem_we` | 1 | `memory_access_unit` | SRAM 写请求 |

B 口继续保持 70 bit 请求和 35 bit 返回，`error` 不得删除；它不经过 `pipeline_control_unit`。

---

## 11. CPU 外部模块 3：`CNN MMIO`

### 11.1 功能和边界

CNN MMIO 是 CPU 用来配置和观察 CNN 的存储器映射寄存器。从 CPU 看，它是一组地址、读写数据和控制信号；它不是 CNN 数据搬运主端口。

### 11.2 完整输入：三组线及来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `mmio_wdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `memory_access_unit` | `mmio_re`、`mmio_we` | 2 |
| **信号线小计** |  |  | **4** |
| 地址线 | `memory_access_unit` | `mmio_addr[31:0]` | 32 |
| **地址线小计** |  |  | **32** |

CPU 到 MMIO 的专用访问接口是 66 bit：

```text
mmio_addr 32 + mmio_wdata 32 + mmio_re 1 + mmio_we 1 = 66
```

公共 `clk`、`rst_n` 不计入 66 bit CPU 访问接口。

### 11.3 完整输出：三组线及对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `mmio_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | `memory_access_unit` | `mmio_ready` | 1 |
| **信号线小计** |  |  | **1** |
| 地址线 | 无 | 无 | 0 |

### 11.4 CPU 侧信号线明细

| 方向 | 信号 | 位宽 | 来源或对象 | 含义 |
|---|---|---:|---|---|
| 输入 | `mmio_re` | 1 | `memory_access_unit` | CPU 请求读取 CNN 寄存器 |
| 输入 | `mmio_we` | 1 | `memory_access_unit` | CPU 请求写入 CNN 寄存器 |
| 输出 | `mmio_ready` | 1 | `memory_access_unit` | 合法 MMIO 访问已经就绪 |

合法 CNN MMIO v1 访问仍要求同周期 `mmio_ready=1`。CONTROL、STATUS 和参数寄存器属于 MMIO 与 CNN 核心之间的连接，不回到 CPU 五模块。

---

## 12. 合并以后减少了哪些图中连线

### 12.1 完全移到模块内部的连接

原来的：

```text
decode_issue_unit ──201 bit──→ execute_unit
```

现在变成：

```text
decode_execute_unit 内部：Decode区 → ID/EX → Execute区
```

### 12.2 可以合并成一组箭头的连接

原来写回单元需要分别连接译码和执行：

```text
writeback_unit → decode_issue_unit
writeback_unit → execute_unit
```

现在统一为：

```text
writeback_unit → decode_execute_unit
```

原来流水控制单元也分别控制译码和执行：

```text
pipeline_control_unit → decode_issue_unit
pipeline_control_unit → execute_unit
```

现在统一为：

```text
pipeline_control_unit → decode_execute_unit
```

### 12.3 仍然必须保留的回路

| 回路 | 为什么不能删除 |
|---|---|
| `decode_execute_unit → fetch_unit` | 送 Branch/JAL/JALR 目标地址 |
| `memory_access_unit → decode_execute_unit` | M→EX 前递 |
| `writeback_unit → decode_execute_unit` | 寄存器写回和 WB→EX 前递 |
| `decode_execute_unit → pipeline_control_unit` | 送 D/E 相关状态和重定向 |
| `memory_access_unit → pipeline_control_unit` | 送 M 级前递状态 |
| `writeback_unit → pipeline_control_unit` | 送 W 级前递状态 |

---

## 13. 五个 CPU 模块位宽总表

以下按模块的唯一逻辑端口统计；扇出到多个对象的信号只计算一次。

| 模块 | 输入数据线 | 输入信号线 | 输入地址/编号线 | 输出数据线 | 输出信号线 | 输出地址/编号线 |
|---|---:|---:|---:|---:|---:|---:|
| `fetch_unit` | 32 | 7 | 64 | 32 | 2 | 96 |
| `decode_execute_unit` | 96 | 11 | 69 | 64 | 18 | 121 |
| `memory_access_unit` | 128 | 14 | 37 | 160 | 13 | 101 |
| `writeback_unit` | 64 | 6 | 37 | 32 | 3 | 5 |
| `pipeline_control_unit` | 0 | 16 | 35 | 0 | 12 | 0 |

这个表用于检查总图是否漏线。它不要求 RTL 把每组信号机械拼成一根匿名大总线。

---

## 14. 画图时的推荐方式

### 14.1 主模块排布

从左到右排列：

```text
fetch_unit → decode_execute_unit → memory_access_unit → writeback_unit
```

把 `pipeline_control_unit` 放在下方。

### 14.2 合并模块内部必须画出的内容

`decode_execute_unit` 大框内部至少画出：

```text
Decoder / RegFile / ImmGen → ID/EX → Forward MUX / ALU / Branch
```

其中 `ID/EX` 应使用明显的寄存器或流水边界符号，避免让人误解为 D 和 E 已合并为同一流水级。

### 14.3 连线规则

- 粗线：32 bit 数据束；
- 地址线：单独标出地址名称和位宽；
- 细线：控制/状态信号；
- 同一方向的同组线可以并成一条线束；
- 在线束旁边列出包含信号；
- 不把 `clk`、`rst_n` 混入存储器请求位宽；
- 扇出点要画清楚，不能误画成两个信号源。

---

## 15. 最后用一句话理解五个模块

1. `fetch_unit`：根据 PC 去 IMEM 取指令。
2. `decode_execute_unit`：看懂指令、读取操作数，经内部 ID/EX 后完成 ALU 和跳转判断。
3. `memory_access_unit`：访问 Data SRAM 或 CNN MMIO，并整理 M 级结果。
4. `writeback_unit`：选择最终结果并写回寄存器堆。
5. `pipeline_control_unit`：观察 D/E/M/W，指挥暂停、冲刷和前递。

最终结构是“五个功能模块、五级流水”。模块数和流水级数不是同一个概念。
