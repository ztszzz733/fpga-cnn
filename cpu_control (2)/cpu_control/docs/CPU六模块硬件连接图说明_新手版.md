# CPU 六模块硬件连接图说明（新手版）

本文用于解释下列硬件参考图：

- 对话内嵌版本：[CPU 六模块硬件连接参考图](figures/cpu-six-module-reference.html)
- 浏览器直接打开版本：[CPU 六模块硬件连接参考图（Standalone）](figures/cpu-six-module-reference-standalone.html)

对应工程依据：

- [CPU 六模块重新划分方案](cpu_module_repartition_proposal.md)
- [CPU 六模块与外部硬件 I/O 清单](cpu_repartition_hardware_io.md)

> 重要说明：图中的六个模块是目标等价重划分方案。当前已经验证通过的是原来的真实 `cpu_control` 和生产 `cpu_datapath`，生产 RTL 还没有正式重构成这六个独立顶层文件。因此，本文是接线和画图基线，不是“六模块 RTL 已经完成”的声明。

---

## 1. 先理解图中的三组线

为了让总图不被几十根线塞满，图中把模块端口按用途分成三组。

### 1.1 数据线

数据线搬运真正要处理的内容，例如：

- 一条 32 bit 指令；
- 寄存器读出的 32 bit 操作数；
- 32 bit 立即数；
- ALU 运算结果；
- SRAM 或 MMIO 返回的 32 bit 数据；
- 最终写回寄存器堆的 32 bit 数据。

图中用**粗线**表示合并后的数据线束。

### 1.2 信号线

本文把控制信号和状态信号合称为“信号线”。它们通常不搬运计算数据，而是告诉模块“现在应该做什么”，例如：

- `clk`：什么时候更新寄存器；
- `rst_n`：是否处于复位；
- `valid_e`：E 级当前内容是否有效；
- `memread_e`：是否执行 Load；
- `pc_sel[1:0]`：下一条 PC 选择哪个来源；
- `fwd_a[1:0]`：ALU 的 A 输入从哪里前递。

图中用**细线**表示信号线，并在模块结尾逐项列出名称和位宽。

### 1.3 地址线

地址线指出“访问哪里”或“选择哪一个寄存器”，包括：

- PC、PC+4 和跳转目标地址；
- IMEM、Data SRAM、CNN MMIO 地址；
- `rs1`、`rs2`、`rd` 等 5 bit 寄存器编号。

本文把寄存器编号叫作“地址/编号线”。原因是 `rs1=5'd1` 的意思就是选择寄存器堆中的 `x1`，作用类似一个小型地址。

### 1.4 “总位宽”不是一根更宽的总线

例如某组包含三根独立的 32 bit 线：

```text
instr_d[31:0] + pc_d[31:0] + pc4_d[31:0]
```

这组线的合计位宽是：

```text
32 + 32 + 32 = 96 bit
```

这不代表硬件中真的存在一根名为“96 bit 总线”的端口。它只是画图时把三根相关线并在一起，方便阅读。实际写 RTL 时仍然可以保留三个独立端口。

同一根输出线如果同时接到两个模块，叫作**扇出**。本文统计模块端口位宽时只计算一次，不因为它有两个接收者就重复计算。

本文后面所有“来源”和“去向”都以当前正在介绍的模块为观察点：

- 输入来源：谁产生这根线，并把它送进当前模块；
- 输出对象：当前模块产生这根线后，把它送给谁；
- `SoC 时钟硬件`和`SoC 复位硬件`表示 CPU 外部的公共时钟、复位来源；
- 一根线有两个输出对象时，会在去向栏中同时列出两个模块，这不代表产生了两根不同的信号。

---

## 2. 整体连接顺序

CPU 主数据流从左向右：

```text
同步 IMEM
   ↓
1. fetch_unit
   ↓
2. decode_issue_unit
   ↓
3. execute_unit
   ↓
4. memory_access_unit ←→ Data SRAM / CNN MMIO
   ↓
5. writeback_unit
   └──────────────→ 返回 decode_issue_unit 的寄存器堆写口

6. pipeline_control_unit 位于下方，观察 D/E/M/W 各级状态，
   再向取指、译码和执行模块发送暂停、冲刷和前递选择信号。
```

这不是一条大家轮流使用的共享总线，而是模块之间的专用点对点连接。

---

## 3. 模块 1：`fetch_unit`（取指单元）

### 3.1 它做什么

`fetch_unit` 可以理解为“按照 PC 去指令存储器取任务单的人”。它内部包含：

- PC 寄存器；
- PC+4 加法；
- 下一 PC 选择器；
- 同步取指适配器；
- IF/ID 流水寄存器。

它是六个 CPU 模块中唯一直接连接同步 IMEM 的模块。

### 3.2 输入三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `imem_rdata[31:0]` |
| 信号线 | 7 bit | `clk`、`rst_n`、`pc_en`、`if_id_en`、`if_id_flush`、`pc_sel[1:0]` |
| 地址线 | 64 bit | `branch_target_e[31:0]`、`jalr_target_e[31:0]` |

输入合计为 `32 + 7 + 64 = 103 bit`。

输入的直观含义：

- 执行单元送来两个跳转候选地址；
- 流水控制单元决定 PC 是否更新、IF/ID 是否保持或清空；
- IMEM 返回一条 32 bit 指令。

### 3.3 输出三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `instr_d[31:0]` |
| 信号线 | 2 bit | `imem_re`、`valid_d` |
| 地址线 | 96 bit | `imem_addr[31:0]`、`pc_d[31:0]`、`pc4_d[31:0]` |

输出合计为 `32 + 2 + 96 = 130 bit`。

其中：

- `imem_addr` 告诉 IMEM 去哪里取指；
- `instr_d` 是进入 D 级的指令；
- `pc_d` 是这条指令自己的地址；
- `pc4_d` 是这条指令的顺序下一地址；
- `valid_d` 表示 IF/ID 中的这条指令是否真实有效。

### 3.4 本模块信号线清单

输入信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `clk` | 1 | 时钟上升沿到来时更新 PC、取指状态和 IF/ID |
| `rst_n` | 1 | 低电平时复位取指状态 |
| `pc_en` | 1 | 为 1 才允许 PC 更新 |
| `if_id_en` | 1 | 为 1 才允许 IF/ID 接收新内容 |
| `if_id_flush` | 1 | 为 1 时清掉 IF/ID 中的错误路径指令 |
| `pc_sel` | 2 | 选择 PC+4、Branch/JAL 目标或 JALR 目标 |

输出信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `imem_re` | 1 | 向 IMEM 发出读请求 |
| `valid_d` | 1 | D 级指令有效标志 |

### 3.5 完整输入：按三组线列出来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 同步 IMEM | `imem_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `pipeline_control_unit` | `pc_sel[1:0]`、`pc_en`、`if_id_en`、`if_id_flush` | 5 |
| **信号线小计** |  |  | **7** |
| 地址线 | `execute_unit` | `branch_target_e[31:0]`、`jalr_target_e[31:0]` | 64 |
| **地址线小计** |  |  | **64** |

### 3.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_issue_unit` | `instr_d[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | 同步 IMEM | `imem_re` | 1 |
| 信号线 | `decode_issue_unit`、`pipeline_control_unit` | `valid_d` | 1 |
| **信号线小计** |  |  | **2** |
| 地址线 | 同步 IMEM | `imem_addr[31:0]` | 32 |
| 地址线 | `decode_issue_unit` | `pc_d[31:0]`、`pc4_d[31:0]` | 64 |
| **地址线小计** |  |  | **96** |

`valid_d` 的输出对象有两个，但它仍然只是一根 1 bit 输出线。

---

## 4. 模块 2：`decode_issue_unit`（译码、寄存器堆与发射单元）

### 4.1 它做什么

这个模块可以理解为“看懂指令，并准备执行材料的人”。它内部包含：

- 主译码器；
- ALU 译码器；
- 安全译码逻辑；
- 32×32 bit 寄存器堆；
- 立即数生成器；
- ID/EX 流水寄存器。

它读取 `rs1` 和 `rs2`，生成立即数和控制字段，再把一整套 E 级输入保存在 ID/EX 中。

### 4.2 输入三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 64 bit | `instr_d[31:0]`、`wb_data_w[31:0]` |
| 信号线 | 5 bit | `clk`、`rst_n`、`valid_d`、`id_ex_flush`、`rf_we_w` |
| 地址/编号线 | 69 bit | `pc_d[31:0]`、`pc4_d[31:0]`、`rd_w[4:0]` |

输入合计为 `64 + 5 + 69 = 138 bit`。

这里有两条不同方向的工作：

- 前向工作：接收 D 级指令并准备 E 级输入；
- 回写工作：接收 W 级的 `rd_w` 和 `wb_data_w`，写回寄存器堆。

### 4.3 输出三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 96 bit | `rd1_e[31:0]`、`rd2_e[31:0]`、`imm_e[31:0]` |
| 信号线 | 28 bit | E 级控制/状态 26 bit，加 D 级源使用标志 2 bit |
| 地址/编号线 | 89 bit | `pc_e`、`pc4_e`、`rs1_e`、`rs2_e`、`rd_e`、`rs1_d`、`rs2_d` |

输出合计为 `96 + 28 + 89 = 213 bit`。

地址/编号线的具体组成：

| 信号 | 位宽 | 作用 |
|---|---:|---|
| `pc_e` | 32 | 当前 E 级指令地址 |
| `pc4_e` | 32 | 当前 E 级指令的 PC+4 |
| `rs1_e` | 5 | E 级源寄存器 1 编号 |
| `rs2_e` | 5 | E 级源寄存器 2 编号 |
| `rd_e` | 5 | E 级目的寄存器编号 |
| `rs1_d` | 5 | D 级源寄存器 1 编号，送流水控制单元 |
| `rs2_d` | 5 | D 级源寄存器 2 编号，送流水控制单元 |

### 4.4 本模块信号线清单

输入信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `clk` | 1 | 更新寄存器堆和 ID/EX |
| `rst_n` | 1 | 复位寄存器堆、ID/EX，并让译码输出保持安全值 |
| `valid_d` | 1 | D 级指令是否有效 |
| `id_ex_flush` | 1 | 清空 ID/EX，向 E 级插入一个 bubble |
| `rf_we_w` | 1 | 允许 W 级结果写入寄存器堆 |

输出信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `valid_e` | 1 | E 级内容是否有效 |
| `uses_rs1_e` | 1 | E 级指令是否真正使用 `rs1` |
| `uses_rs2_e` | 1 | E 级指令是否真正使用 `rs2` |
| `alu_ctrl_e` | 4 | ALU 具体执行加、减、与、或、移位等哪一种操作 |
| `alu_src_a_sel_e` | 2 | ALU A 输入选择寄存器、PC 或 0 |
| `alu_src_b_sel_e` | 2 | ALU B 输入选择寄存器或立即数 |
| `regwrite_e` | 1 | 这条指令最终是否需要写寄存器 |
| `memread_e` | 1 | 这条指令是否为 Load |
| `memwrite_e` | 1 | 这条指令是否为 Store |
| `load_type_e` | 3 | LB、LH、LW、LBU、LHU 等 Load 类型 |
| `store_type_e` | 2 | SB、SH、SW 等 Store 类型 |
| `wb_sel_e` | 2 | 最终写回选择 ALU、Load 数据还是 PC+4 |
| `branch_type_e` | 3 | BEQ、BNE、BLT 等分支类型 |
| `jump_e` | 2 | 非跳转、JAL 或 JALR 类型 |
| `uses_rs1_d` | 1 | D 级指令是否使用 `rs1`，供冒险判断 |
| `uses_rs2_d` | 1 | D 级指令是否使用 `rs2`，供冒险判断 |

### 4.5 完整输入：按三组线列出来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `fetch_unit` | `instr_d[31:0]` | 32 |
| 数据线 | `writeback_unit` | `wb_data_w[31:0]` | 32 |
| **数据线小计** |  |  | **64** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `fetch_unit` | `valid_d` | 1 |
| 信号线 | `pipeline_control_unit` | `id_ex_flush` | 1 |
| 信号线 | `writeback_unit` | `rf_we_w` | 1 |
| **信号线小计** |  |  | **5** |
| 地址/编号线 | `fetch_unit` | `pc_d[31:0]`、`pc4_d[31:0]` | 64 |
| 地址/编号线 | `writeback_unit` | `rd_w[4:0]` | 5 |
| **地址/编号线小计** |  |  | **69** |

### 4.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `execute_unit` | `rd1_e[31:0]`、`rd2_e[31:0]`、`imm_e[31:0]` | 96 |
| **数据线小计** |  |  | **96** |
| 信号线 | `execute_unit`、`pipeline_control_unit` | `valid_e`、`uses_rs1_e`、`uses_rs2_e`、`memread_e` | 4 |
| 信号线 | `execute_unit` | `alu_ctrl_e[3:0]`、`alu_src_a_sel_e[1:0]`、`alu_src_b_sel_e[1:0]`、`regwrite_e`、`memwrite_e`、`load_type_e[2:0]`、`store_type_e[1:0]`、`wb_sel_e[1:0]`、`branch_type_e[2:0]`、`jump_e[1:0]` | 22 |
| 信号线 | `pipeline_control_unit` | `uses_rs1_d`、`uses_rs2_d` | 2 |
| **信号线小计** |  |  | **28** |
| 地址/编号线 | `execute_unit` | `pc_e[31:0]`、`pc4_e[31:0]` | 64 |
| 地址/编号线 | `execute_unit`、`pipeline_control_unit` | `rs1_e[4:0]`、`rs2_e[4:0]`、`rd_e[4:0]` | 15 |
| 地址/编号线 | `pipeline_control_unit` | `rs1_d[4:0]`、`rs2_d[4:0]` | 10 |
| **地址/编号线小计** |  |  | **89** |

一根 E 级输出可以同时送给执行模块和流水控制模块。表中把两个输出对象写在同一格，因此不会重复计算位宽。

---

## 5. 模块 3：`execute_unit`（执行、比较与跳转单元）

### 5.1 它做什么

这个模块可以理解为“真正进行计算的人”。它内部包含：

- MEM/WB 前递选择器；
- ALU 输入选择器；
- RV32I ALU；
- 相等、有符号小于、无符号小于比较器；
- 分支和跳转判断；
- Branch/JAL/JALR 目标地址计算。

该模块保持纯组合逻辑，不新增流水寄存器。

### 5.2 输入三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 160 bit | `rd1_e`、`rd2_e`、`imm_e`、`mem_forward_m`、`wb_data_w`，每根 32 bit |
| 信号线 | 32 bit | 来自 ID/EX 的 26 bit 控制/状态，加三组 2 bit 前递选择 |
| 地址/编号线 | 79 bit | `pc_e[31:0]`、`pc4_e[31:0]`、`rs1_e[4:0]`、`rs2_e[4:0]`、`rd_e[4:0]` |

输入合计为 `160 + 32 + 79 = 271 bit`。

数据前递的意思是：如果 E 级需要的数据还没有正式写回寄存器堆，可以直接从 M 级或 W 级拿到，避免无意义地等待。

### 5.3 输出三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 64 bit | `alu_result_e[31:0]`、`store_data_e[31:0]` |
| 信号线 | 14 bit | 送访存单元的控制/状态 11 bit，加重定向控制 3 bit |
| 地址/编号线 | 101 bit | `pc4_e_o[31:0]`、`rd_e_o[4:0]`、`branch_target_e[31:0]`、`jalr_target_e[31:0]` |

输出合计为 `64 + 14 + 101 = 179 bit`。

其中：

- `alu_result_e` 对普通运算是计算结果，对 Load/Store 则是有效地址；
- `store_data_e` 是 Store 要写入存储器的数据；
- 两个目标地址返回 `fetch_unit`；
- `redirect` 和 `redirect_sel` 送流水控制单元决定是否改变取指路线。

### 5.4 本模块信号线清单

输入信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `valid_e` | 1 | 当前 E 级指令是否有效 |
| `uses_rs1_e` | 1 | 当前指令是否使用源操作数 1 |
| `uses_rs2_e` | 1 | 当前指令是否使用源操作数 2 |
| `alu_ctrl_e` | 4 | ALU 操作码 |
| `alu_src_a_sel_e` | 2 | ALU A 输入来源选择 |
| `alu_src_b_sel_e` | 2 | ALU B 输入来源选择 |
| `regwrite_e` | 1 | 后续是否写寄存器 |
| `memread_e` | 1 | 是否读存储器 |
| `memwrite_e` | 1 | 是否写存储器 |
| `load_type_e` | 3 | Load 类型 |
| `store_type_e` | 2 | Store 类型 |
| `wb_sel_e` | 2 | 写回来源选择 |
| `branch_type_e` | 3 | 分支类型 |
| `jump_e` | 2 | 跳转类型 |
| `fwd_a` | 2 | rs1 数据前递选择 |
| `fwd_b` | 2 | rs2 数据前递选择 |
| `fwd_store` | 2 | Store 数据前递选择 |

输出信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `valid_e_o` | 1 | 向访存单元透传 E 级有效状态 |
| `regwrite_e_o` | 1 | 向访存单元透传寄存器写控制 |
| `memread_e_o` | 1 | 向访存单元透传读存储器控制 |
| `memwrite_e_o` | 1 | 向访存单元透传写存储器控制 |
| `load_type_e_o` | 3 | 向访存单元透传 Load 类型 |
| `store_type_e_o` | 2 | 向访存单元透传 Store 类型 |
| `wb_sel_e_o` | 2 | 向访存单元透传写回选择 |
| `redirect` | 1 | 为 1 表示分支或跳转需要更换取指路线 |
| `redirect_sel` | 2 | 指出使用 Branch/JAL 目标还是 JALR 目标 |

### 5.5 完整输入：按三组线列出来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_issue_unit` | `rd1_e[31:0]`、`rd2_e[31:0]`、`imm_e[31:0]` | 96 |
| 数据线 | `memory_access_unit` | `mem_forward_m[31:0]` | 32 |
| 数据线 | `writeback_unit` | `wb_data_w[31:0]` | 32 |
| **数据线小计** |  |  | **160** |
| 信号线 | `decode_issue_unit` | `valid_e`、`uses_rs1_e`、`uses_rs2_e`、`alu_ctrl_e[3:0]`、`alu_src_a_sel_e[1:0]`、`alu_src_b_sel_e[1:0]`、`regwrite_e`、`memread_e`、`memwrite_e`、`load_type_e[2:0]`、`store_type_e[1:0]`、`wb_sel_e[1:0]`、`branch_type_e[2:0]`、`jump_e[1:0]` | 26 |
| 信号线 | `pipeline_control_unit` | `fwd_a[1:0]`、`fwd_b[1:0]`、`fwd_store[1:0]` | 6 |
| **信号线小计** |  |  | **32** |
| 地址/编号线 | `decode_issue_unit` | `pc_e[31:0]`、`pc4_e[31:0]`、`rs1_e[4:0]`、`rs2_e[4:0]`、`rd_e[4:0]` | 79 |
| **地址/编号线小计** |  |  | **79** |

### 5.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `alu_result_e[31:0]`、`store_data_e[31:0]` | 64 |
| **数据线小计** |  |  | **64** |
| 信号线 | `memory_access_unit` | `valid_e_o`、`regwrite_e_o`、`memread_e_o`、`memwrite_e_o`、`load_type_e_o[2:0]`、`store_type_e_o[1:0]`、`wb_sel_e_o[1:0]` | 11 |
| 信号线 | `pipeline_control_unit` | `redirect`、`redirect_sel[1:0]` | 3 |
| **信号线小计** |  |  | **14** |
| 地址/编号线 | `memory_access_unit` | `pc4_e_o[31:0]`、`rd_e_o[4:0]` | 37 |
| 地址/编号线 | `fetch_unit` | `branch_target_e[31:0]`、`jalr_target_e[31:0]` | 64 |
| **地址/编号线小计** |  |  | **101** |

执行单元把地址、数据和信号分别送往不同对象：跳转地址送取指单元，重定向信号送流水控制单元，正常 E 级结果送访存单元。

---

## 6. 模块 4：`memory_access_unit`（Data SRAM 与 CNN MMIO 访存单元）

### 6.1 它做什么

这个模块可以理解为“决定访问普通数据存储器还是 CNN 寄存器的人”。它内部包含：

- EX/MEM 流水寄存器；
- E 级和 M 级地址译码；
- LSU（Load/Store Unit）；
- Data SRAM 请求生成；
- CNN MMIO 路由；
- M 级读数据和前递值选择。

只有这个 CPU 内部模块直接连接 Data SRAM A 口和 CNN MMIO。

### 6.2 输入三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 96 bit | `store_data_e[31:0]`、`dmem_rdata[31:0]`、`mmio_rdata[31:0]` |
| 信号线 | 14 bit | `clk`、`rst_n`、E 级访存/写回控制以及 `mmio_ready` |
| 地址/编号线 | 69 bit | `alu_result_e[31:0]`、`pc4_e[31:0]`、`rd_e[4:0]` |

输入合计为 `96 + 14 + 69 = 179 bit`。

这里把 `alu_result_e` 放入地址组，是因为它进入访存单元后首先用于地址译码。对于普通 ADD，它仍然只是一个运算结果，不会真的发出存储器请求。

### 6.3 输出三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 160 bit | SRAM/MMIO 写数据、M 级读数据、ALU 结果和 M 级前递值 |
| 信号线 | 13 bit | SRAM、MMIO 请求控制以及 M 级状态/写回控制 |
| 地址/编号线 | 101 bit | `dmem_addr`、`mmio_addr`、`pc4_m`、`rd_m` |

输出合计为 `160 + 13 + 101 = 274 bit`。

数据线具体组成：

| 信号 | 位宽 | 去向/作用 |
|---|---:|---|
| `dmem_wdata` | 32 | 写入 Data SRAM |
| `mmio_wdata` | 32 | 写入 CNN MMIO 寄存器 |
| `read_data_m` | 32 | 送写回单元的 Load/MMIO 读结果 |
| `alu_result_m` | 32 | 送写回单元的 ALU 结果候选 |
| `mem_forward_m` | 32 | 送执行单元的 M 级前递值 |

地址/编号线具体组成：

| 信号 | 位宽 | 去向/作用 |
|---|---:|---|
| `dmem_addr` | 32 | Data SRAM A 口地址 |
| `mmio_addr` | 32 | CNN MMIO 寄存器地址 |
| `pc4_m` | 32 | M 级 PC+4 写回候选 |
| `rd_m` | 5 | M 级目的寄存器编号 |

### 6.4 本模块信号线清单

输入信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `clk` | 1 | 更新 EX/MEM |
| `rst_n` | 1 | 复位 EX/MEM，并禁止复位期间产生写请求 |
| `valid_e` | 1 | E 级内容是否有效 |
| `regwrite_e` | 1 | 后续是否写寄存器 |
| `memread_e` | 1 | 是否执行 Load |
| `memwrite_e` | 1 | 是否执行 Store |
| `load_type_e` | 3 | Load 的字节宽度和符号扩展方式 |
| `store_type_e` | 2 | Store 的字节宽度 |
| `wb_sel_e` | 2 | 后续写回来源 |
| `mmio_ready` | 1 | CNN MMIO 是否在当前周期接受并完成访问 |

输出信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `dmem_wstrb` | 4 | SRAM 四个字节通道的写使能，每一位控制一个字节 |
| `dmem_re` | 1 | Data SRAM 读请求 |
| `dmem_we` | 1 | Data SRAM 写请求 |
| `mmio_re` | 1 | CNN MMIO 读请求 |
| `mmio_we` | 1 | CNN MMIO 写请求 |
| `valid_m` | 1 | M 级内容是否有效 |
| `regwrite_m` | 1 | M 级指令最终是否写寄存器 |
| `memread_m` | 1 | M 级指令是否为 Load，供冒险单元禁止错误前递 |
| `wb_sel_m` | 2 | W 级应选择 ALU、Load 数据还是 PC+4 |

### 6.5 为什么 SRAM 和 MMIO 不是同一条外部总线

访存单元内部会判断 ALU 地址落在哪个范围：

```text
普通 SRAM 地址范围  → 产生 dmem_* 信号
CNN MMIO 地址范围   → 产生 mmio_* 信号
其他地址            → 不发出合法访问
```

所以当前设计是两个专用外部接口，不是 AXI、AHB 或 Wishbone 统一系统总线。

### 6.6 完整输入：按三组线列出来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `execute_unit` | `store_data_e[31:0]` | 32 |
| 数据线 | Data SRAM A 口 | `dmem_rdata[31:0]` | 32 |
| 数据线 | CNN MMIO | `mmio_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **96** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `execute_unit` | `valid_e_o`、`regwrite_e_o`、`memread_e_o`、`memwrite_e_o`、`load_type_e_o[2:0]`、`store_type_e_o[1:0]`、`wb_sel_e_o[1:0]` | 11 |
| 信号线 | CNN MMIO | `mmio_ready` | 1 |
| **信号线小计** |  |  | **14** |
| 地址/编号线 | `execute_unit` | `alu_result_e[31:0]`、`pc4_e_o[31:0]`、`rd_e_o[4:0]` | 69 |
| **地址/编号线小计** |  |  | **69** |

### 6.7 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `execute_unit` | `mem_forward_m[31:0]` | 32 |
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

`valid_m`、`regwrite_m` 和 `rd_m` 都有两个输出对象，但每个仍然只按自身位宽计算一次。

---

## 7. 模块 5：`writeback_unit`（写回单元）

### 7.1 它做什么

这个模块可以理解为“把最终结果交回寄存器堆的人”。它内部包含：

- MEM/WB 流水寄存器；
- 写回结果选择器；
- 寄存器堆写使能限定。

ALU 结果、Load/MMIO 读数据和 PC+4 都可能成为最终写回值，由 `wb_sel_m` 决定选择哪一个。

### 7.2 输入三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 64 bit | `read_data_m[31:0]`、`alu_result_m[31:0]` |
| 信号线 | 6 bit | `clk`、`rst_n`、`valid_m`、`regwrite_m`、`wb_sel_m[1:0]` |
| 地址/编号线 | 37 bit | `pc4_m[31:0]`、`rd_m[4:0]` |

输入合计为 `64 + 6 + 37 = 107 bit`。

### 7.3 输出三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `wb_data_w[31:0]` |
| 信号线 | 3 bit | `valid_w`、`regwrite_w`、`rf_we_w` |
| 地址/编号线 | 5 bit | `rd_w[4:0]` |

输出合计为 `32 + 3 + 5 = 40 bit`。

同一个 `wb_data_w` 有两个用途：

- 返回 `decode_issue_unit`，真正写入寄存器堆；
- 返回 `execute_unit`，作为 WB→EX 前递数据。

这是一根线的扇出，不是复制了两份写回结果。

### 7.4 本模块信号线清单

输入信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `clk` | 1 | 更新 MEM/WB |
| `rst_n` | 1 | 复位 MEM/WB |
| `valid_m` | 1 | M 级内容是否有效 |
| `regwrite_m` | 1 | 当前指令是否允许写寄存器 |
| `wb_sel_m` | 2 | 选择 ALU、读数据或 PC+4 |

输出信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `valid_w` | 1 | W 级内容是否有效 |
| `regwrite_w` | 1 | W 级指令是否具有写寄存器语义 |
| `rf_we_w` | 1 | 最终寄存器堆写使能，即 `valid_w && regwrite_w && rd_w != 0` |

### 7.5 完整输入：按三组线列出来源

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

### 7.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `decode_issue_unit`、`execute_unit` | `wb_data_w[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | `pipeline_control_unit` | `valid_w`、`regwrite_w` | 2 |
| 信号线 | `decode_issue_unit` | `rf_we_w` | 1 |
| **信号线小计** |  |  | **3** |
| 地址/编号线 | `decode_issue_unit`、`pipeline_control_unit` | `rd_w[4:0]` | 5 |
| **地址/编号线小计** |  |  | **5** |

`wb_data_w` 和 `rd_w` 都存在扇出；同一行列出多个输出对象，不重复计算端口位宽。

---

## 8. 模块 6：`pipeline_control_unit`（冒险、前递和流水门控单元）

### 8.1 它做什么

这个模块可以理解为“交通指挥员”。它不搬运计算数据，而是观察 D/E/M/W 四级的状态，然后决定：

- 是否暂停 PC 和 IF/ID；
- 是否向 ID/EX 插入 bubble；
- 分支或跳转后是否冲刷年轻指令；
- ALU 和 Store 数据应该从寄存器堆、M 级还是 W 级取得。

该模块保持纯组合逻辑，不保存流水状态。

### 8.2 输入三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 0 bit | 无计算数据输入 |
| 信号线 | 16 bit | 复位、各级 valid/读写状态、源使用标志和重定向状态 |
| 地址/编号线 | 35 bit | D/E 级源寄存器编号和 E/M/W 级目的寄存器编号 |

输入合计为 `0 + 16 + 35 = 51 bit`。

地址/编号线具体组成：

| 信号 | 位宽 |
|---|---:|
| `rs1_d` | 5 |
| `rs2_d` | 5 |
| `rs1_e` | 5 |
| `rs2_e` | 5 |
| `rd_e` | 5 |
| `rd_m` | 5 |
| `rd_w` | 5 |

控制单元比较这些 5 bit 编号。例如，如果 E 级正在执行 `ADD x6,x1,x2`，而 M 级即将写 `x1`，控制单元就能发现 `rs1_e == rd_m`，从而选择 M→EX 前递。

### 8.3 输出三组线总览

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 0 bit | 无 |
| 信号线 | 12 bit | PC/流水门控 6 bit，加三组前递选择 6 bit |
| 地址线 | 0 bit | 无 |

输出合计为 12 bit。

### 8.4 本模块信号线清单

输入信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `rst_n` | 1 | 复位期间把控制输出限制为安全值 |
| `valid_d` | 1 | D 级是否有有效指令 |
| `uses_rs1_d` | 1 | D 级指令是否使用 `rs1` |
| `uses_rs2_d` | 1 | D 级指令是否使用 `rs2` |
| `valid_e` | 1 | E 级是否有有效指令 |
| `uses_rs1_e` | 1 | E 级指令是否使用 `rs1` |
| `uses_rs2_e` | 1 | E 级指令是否使用 `rs2` |
| `memread_e` | 1 | E 级是否为 Load，用于判断 load-use |
| `valid_m` | 1 | M 级是否有效 |
| `regwrite_m` | 1 | M 级是否会写寄存器 |
| `memread_m` | 1 | M 级是否为 Load，防止把 Load 地址误当前递数据 |
| `valid_w` | 1 | W 级是否有效 |
| `regwrite_w` | 1 | W 级是否会写寄存器 |
| `redirect` | 1 | 执行级是否要求改变取指路线 |
| `redirect_sel` | 2 | 选择 Branch/JAL 或 JALR 重定向类型 |

输出信号线：

| 信号 | 位宽 | 新手理解 |
|---|---:|---|
| `pc_sel` | 2 | 下一 PC 来源选择 |
| `pc_en` | 1 | PC 写使能 |
| `if_id_en` | 1 | IF/ID 写使能 |
| `if_id_flush` | 1 | 清空 IF/ID |
| `id_ex_flush` | 1 | 清空 ID/EX，插入 bubble |
| `fwd_a` | 2 | ALU A 输入前递选择 |
| `fwd_b` | 2 | ALU B 输入前递选择 |
| `fwd_store` | 2 | Store 写数据前递选择 |

### 8.5 为什么它没有数据线

流水控制单元只需要知道“谁依赖谁”和“当前哪一级有效”，不需要看到寄存器里真正存的是 1、2 还是 100。因此它只比较寄存器编号和状态信号，不接收 32 bit 运算数据。

### 8.6 完整输入：按三组线列出来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 无 | 无 | 0 |
| **数据线小计** |  |  | **0** |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `fetch_unit` | `valid_d` | 1 |
| 信号线 | `decode_issue_unit` | `uses_rs1_d`、`uses_rs2_d`、`valid_e`、`uses_rs1_e`、`uses_rs2_e`、`memread_e` | 6 |
| 信号线 | `execute_unit` | `redirect`、`redirect_sel[1:0]` | 3 |
| 信号线 | `memory_access_unit` | `valid_m`、`regwrite_m`、`memread_m` | 3 |
| 信号线 | `writeback_unit` | `valid_w`、`regwrite_w` | 2 |
| **信号线小计** |  |  | **16** |
| 地址/编号线 | `decode_issue_unit` | `rs1_d[4:0]`、`rs2_d[4:0]`、`rs1_e[4:0]`、`rs2_e[4:0]`、`rd_e[4:0]` | 25 |
| 地址/编号线 | `memory_access_unit` | `rd_m[4:0]` | 5 |
| 地址/编号线 | `writeback_unit` | `rd_w[4:0]` | 5 |
| **地址/编号线小计** |  |  | **35** |

### 8.7 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 无 | 无 | 0 |
| **数据线小计** |  |  | **0** |
| 信号线 | `fetch_unit` | `pc_sel[1:0]`、`pc_en`、`if_id_en`、`if_id_flush` | 5 |
| 信号线 | `decode_issue_unit` | `id_ex_flush` | 1 |
| 信号线 | `execute_unit` | `fwd_a[1:0]`、`fwd_b[1:0]`、`fwd_store[1:0]` | 6 |
| **信号线小计** |  |  | **12** |
| 地址/编号线 | 无 | 无 | 0 |
| **地址/编号线小计** |  |  | **0** |

控制单元没有输出给 `memory_access_unit` 或 `writeback_unit`。发生一拍 load-use 暂停时，只保持 PC/IF/ID 并冲刷 ID/EX；更老的 M、W 级仍然正常向前推进。

---

## 9. CPU 外部模块 1：同步指令存储器 `imem_rom`

### 9.1 它做什么

IMEM 保存 CPU 要执行的程序。`fetch_unit` 给出地址和读请求，IMEM 在固定一个周期后返回 32 bit 指令。

前面的总览只计算参考图中的 CPU 侧接口；后面的“完整输入”还会把真实模块需要的公共 `clk` 和 `rst_n` 分别列出。

### 9.2 输入三组线总览（仅 CPU 侧接口）

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 0 bit | 无 |
| 信号线 | 1 bit | `imem_re` |
| 地址线 | 32 bit | `imem_addr[31:0]` |

### 9.3 输出三组线总览（仅 CPU 侧接口）

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `imem_rdata[31:0]` |
| 信号线 | 0 bit | CPU 侧没有独立 ready 信号 |
| 地址线 | 0 bit | 无 |

### 9.4 本模块信号线清单

| 方向（相对 IMEM） | 信号 | 位宽 | 新手理解 |
|---|---|---:|---|
| 输入 | `imem_re` | 1 | 为 1 时接受取指请求 |

固定一周期同步返回是双方约定，因此当前接口不需要 `imem_ready`。

### 9.5 完整输入：按三组线列出来源

| 线组 | 输入来源 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | 无 | 无 | 0 |
| **数据线小计** |  |  | **0** |
| 信号线 | SoC 时钟硬件 | `clk` | 1 |
| 信号线 | SoC 复位硬件 | `rst_n` | 1 |
| 信号线 | `fetch_unit` | `imem_re` | 1 |
| **信号线小计** |  |  | **3** |
| 地址线 | `fetch_unit` | `imem_addr[31:0]` | 32 |
| **地址线小计** |  |  | **32** |

### 9.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `fetch_unit` | `imem_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | 无 | 无 | 0 |
| **信号线小计** |  |  | **0** |
| 地址线 | 无 | 无 | 0 |
| **地址线小计** |  |  | **0** |

---

## 10. CPU 外部模块 2：双口 `Data SRAM`

### 10.1 它做什么

CPU 使用 Data SRAM 的 A 口读写普通数据。B 口留给图像输入和 CNN memory master，并在 CPU 外部经过 `sram_b_arbiter`。本节只统计参考图中 CPU→A 口的连接。

下面的总览只计算 CPU A 口。后面的“完整输入”会加入公共 `clk`、`rst_n`；独立 B 口仍单独说明，不混入 A 口统计。

### 10.2 输入三组线总览（仅 CPU A 口）

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `dmem_wdata[31:0]` |
| 信号线 | 6 bit | `dmem_wstrb[3:0]`、`dmem_re`、`dmem_we` |
| 地址线 | 32 bit | `dmem_addr[31:0]` |

CPU 到 SRAM A 口合计为 `32 + 6 + 32 = 70 bit`。

### 10.3 输出三组线总览（仅 CPU A 口）

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `dmem_rdata[31:0]` |
| 信号线 | 0 bit | 当前 A 口没有单独的 `ready/error` 返回 |
| 地址线 | 0 bit | 无 |

### 10.4 本模块信号线清单

| 方向（相对 SRAM） | 信号 | 位宽 | 新手理解 |
|---|---|---:|---|
| 输入 | `dmem_wstrb` | 4 | 每一位控制一个写字节通道 |
| 输入 | `dmem_re` | 1 | SRAM 读使能 |
| 输入 | `dmem_we` | 1 | SRAM 写使能 |

> 注意：B 口请求是另一套 70 bit 请求和 35 bit 返回接口，并且必须保留 `error`。它属于 CPU 外部系统连接，不经过 CPU 的 `pipeline_control_unit`。

### 10.5 完整输入：按三组线列出来源

以下是 Data SRAM 的 CPU A 口和公共系统输入；B 口另行说明。

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

### 10.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `dmem_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | 无（A 口没有独立 ready/error） | 无 | 0 |
| **信号线小计** |  |  | **0** |
| 地址线 | 无 | 无 | 0 |
| **地址线小计** |  |  | **0** |

B 口的输入来源是 CPU 外部 `sram_b_arbiter`，不是六个 CPU 模块中的任何一个；B 口 70 bit 请求和 35 bit 返回未计入上面的 CPU A 口小计。

---

## 11. CPU 外部模块 3：`CNN MMIO`

### 11.1 它做什么

CNN MMIO 是一组存储器映射寄存器。CPU 看起来像在读写地址，实际上是在配置 CNN 的控制寄存器、输入地址、输出地址和参数。

前面的总览只统计参考图中的 CPU 侧接口。后面的“完整输入”会加入 `clk`、`rst_n`；CNN 另一侧的 CONTROL、STATUS 和参数寄存器单独说明，不混入 CPU 侧统计。

### 11.2 输入三组线总览（仅 CPU 侧接口）

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `mmio_wdata[31:0]` |
| 信号线 | 2 bit | `mmio_re`、`mmio_we` |
| 地址线 | 32 bit | `mmio_addr[31:0]` |

CPU 到 MMIO 合计为 `32 + 2 + 32 = 66 bit`。

### 11.3 输出三组线总览（仅 CPU 侧接口）

| 组别 | 合计位宽 | 包含内容 |
|---|---:|---|
| 数据线 | 32 bit | `mmio_rdata[31:0]` |
| 信号线 | 1 bit | `mmio_ready` |
| 地址线 | 0 bit | 无 |

MMIO 返回 CPU 合计为 `32 + 1 = 33 bit`。

### 11.4 本模块信号线清单

| 方向（相对 MMIO） | 信号 | 位宽 | 新手理解 |
|---|---|---:|---|
| 输入 | `mmio_re` | 1 | CPU 请求读取一个 CNN 寄存器 |
| 输入 | `mmio_we` | 1 | CPU 请求写入一个 CNN 寄存器 |
| 输出 | `mmio_ready` | 1 | 本次合法 MMIO 访问已经就绪 |

当前 v1 约定要求合法 CNN MMIO 访问同周期 `ready=1`，不在 CPU 内增加等待状态。

### 11.5 完整输入：按三组线列出来源

下表统计图中的 CPU 侧接口和公共系统输入，不展开 CNN 核心侧寄存器端口。

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

### 11.6 完整输出：按三组线列出对象

| 线组 | 输出对象 | 信号 | 位宽 |
|---|---|---|---:|
| 数据线 | `memory_access_unit` | `mmio_rdata[31:0]` | 32 |
| **数据线小计** |  |  | **32** |
| 信号线 | `memory_access_unit` | `mmio_ready` | 1 |
| **信号线小计** |  |  | **1** |
| 地址线 | 无 | 无 | 0 |
| **地址线小计** |  |  | **0** |

CONTROL、STATUS 和参数寄存器位于 MMIO 与 CNN 核心之间，属于 CNN 侧连接，不回到 CPU 六模块，因此未计入上表。

---

## 12. 三条最容易看错的回路

### 12.1 W 级写回回路

```text
writeback_unit
  ├─ wb_data_w[31:0] ─→ decode_issue_unit 的寄存器堆写数据口
  ├─ rd_w[4:0]       ─→ 寄存器堆写地址
  └─ rf_we_w         ─→ 寄存器堆写使能
```

这条线是从右向左返回，属于正常写回，不是画反了。

### 12.2 MEM/WB 到 EX 的前递回路

```text
memory_access_unit.mem_forward_m[31:0] ─→ execute_unit
writeback_unit.wb_data_w[31:0]         ─→ execute_unit
```

它们让 E 级直接拿到较新结果，减少流水暂停。

### 12.3 EX 到取指级的跳转回路

```text
execute_unit.branch_target_e[31:0] ─→ fetch_unit
execute_unit.jalr_target_e[31:0]   ─→ fetch_unit
```

执行级同时向流水控制单元发送 `redirect` 和 `redirect_sel`。目标地址告诉取指单元“跳到哪里”，控制信号告诉它“现在是否真的要跳”。

---

## 13. 六个 CPU 模块位宽总表

以下位宽按模块的**唯一逻辑端口**统计；一根输出即使扇出到多个模块也只计算一次。

| 模块 | 输入数据线 | 输入信号线 | 输入地址/编号线 | 输出数据线 | 输出信号线 | 输出地址/编号线 |
|---|---:|---:|---:|---:|---:|---:|
| `fetch_unit` | 32 | 7 | 64 | 32 | 2 | 96 |
| `decode_issue_unit` | 64 | 5 | 69 | 96 | 28 | 89 |
| `execute_unit` | 160 | 32 | 79 | 64 | 14 | 101 |
| `memory_access_unit` | 96 | 14 | 69 | 160 | 13 | 101 |
| `writeback_unit` | 64 | 6 | 37 | 32 | 3 | 5 |
| `pipeline_control_unit` | 0 | 16 | 35 | 0 | 12 | 0 |

这些合计位宽用于检查总图有没有漏线，但不建议直接把每一行机械合并成一个巨大 RTL packed bus。实际实现时，应保持信号语义清楚，或者按流水级定义结构化 bundle。

---

## 14. 最后用一句话理解每个模块

1. `fetch_unit`：根据 PC 从 IMEM 取回指令。
2. `decode_issue_unit`：看懂指令，读取寄存器并准备 E 级材料。
3. `execute_unit`：选择前递数据，完成计算、比较和跳转判断。
4. `memory_access_unit`：连接 Data SRAM 和 CNN MMIO，并整理 M 级结果。
5. `writeback_unit`：选择最终结果并写回寄存器堆。
6. `pipeline_control_unit`：观察流水状态，指挥暂停、冲刷和前递。

外部同步 IMEM 保存程序，Data SRAM 保存普通数据和图像数据，CNN MMIO 保存 CPU 用来配置和观察 CNN 的寄存器。当前系统没有 AXI/AHB 等统一外部总线，而是使用 `imem_*`、`dmem_*`、`mmio_*` 三组专用点对点接口。
