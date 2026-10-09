# CPU 六模块与三类外部硬件 I/O 连接清单

日期：2026-09-23  
依据：[CPU 内部硬件重新划分方案](cpu_module_repartition_proposal.md)  
状态：目标接线定义；尚未据此修改生产 RTL

## 1. 本文中的模块是不是现有硬件

本文描述的是在**不改变现有硬件行为**前提下，对当前 `cpu_control` 与生产 `cpu_datapath` 进行等价重组后的目标模块边界。

- `fetch_unit`、`decode_issue_unit`、`execute_unit`、`memory_access_unit`、`writeback_unit`、`pipeline_control_unit` 是建议形成的六个 CPU 功能模块。
- `cpu_core` 是只负责实例化、参数传递和接线的集成壳，不计入六个功能模块。
- `同步 IMEM`、`Data SRAM`、`CNN MMIO` 是用户指定的三个例外模块，位于 CPU 之外，但在本文中完整列出其接线。
- `SoC 时钟硬件`、`SoC 复位硬件` 是系统信号源，不计入上述模块数量。

这些新模块目前还没有对应的生产 RTL 文件，因此本文不是“已经实现”的声明，而是后续等价重构时应遵守的端口和接线基线。模块内部继续使用现有组合逻辑与流水状态，不增加或删除硬件功能。

## 2. 硬件清单

### 2.1 CPU 六个功能模块

| 序号 | 目标硬件模块 | 合并的现有硬件/逻辑 |
|---:|---|---|
| 1 | `fetch_unit` | `pc`、`fetch_adapter`、`if_id_reg`、next-PC 选择和 `PC+4` |
| 2 | `decode_issue_unit` | `main_decoder`、`alu_decoder`、安全译码、`regfile`、`imm_gen`、`id_ex_reg` |
| 3 | `execute_unit` | 前递多路选择器、ALU 输入选择器、`alu`、比较器、`branch_control`、跳转目标计算 |
| 4 | `memory_access_unit` | `ex_mem_reg`、E/M 两组 `address_decoder` 和 `lsu`、SRAM 请求、MMIO 路由 |
| 5 | `writeback_unit` | `mem_wb_reg`、写回选择器和寄存器堆写使能限定 |
| 6 | `pipeline_control_unit` | `hazard_unit`、`pipeline_control`、前递选择复位限定 |

### 2.2 CPU 集成壳

| 硬件模块 | 含义 |
|---|---|
| `cpu_core` | 实例化六个功能模块，向外只保留时钟、复位和三类外部硬件接口；不保存状态，不增加功能逻辑 |

### 2.3 三个例外模块

| 文中名称 | 含义 | 是否计入 CPU 六模块 |
|---|---|---|
| `同步 IMEM` | 固定一周期同步指令存储器 | 否 |
| `Data SRAM` | CPU 使用的数据存储器端口 | 否 |
| `CNN MMIO` | CNN 寄存器从接口 | 否 |

### 2.4 其他系统边界硬件

| 文中名称 | 含义 |
|---|---|
| `SoC 时钟硬件` | 提供 `clk` |
| `SoC 复位硬件` | 提供同步、低有效 `rst_n` |

`cpu_control_pkg.sv` 只定义常量、枚举和结构类型，不生成独立硬件，因此不列入硬件清单。

---

## 3. `cpu_core` 顶层 I/O

`cpu_core` 是目标 CPU 顶层。它不重新解释信号，只把外部端口接到六个功能模块。

### 3.1 公共输入

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | `fetch_unit`、`decode_issue_unit`、`memory_access_unit`、`writeback_unit` |
| `rst_n` | 1 | `SoC 复位硬件` | 六个功能模块中需要复位限定的模块 |

`execute_unit` 和 `pipeline_control_unit` 保持纯组合逻辑，不使用 `clk`。`rst_n` 进入 `pipeline_control_unit` 以产生安全门控；`execute_unit` 依靠 valid 和控制输出限定，不新增复位状态。

### 3.2 指令存储器端口

| 方向 | 信号 | 位宽 | CPU 内部来源/去向 | 外部硬件 |
|---|---|---:|---|---|
| 输出 | `imem_addr` | 32 | 来源：`fetch_unit` | `同步 IMEM` |
| 输出 | `imem_re` | 1 | 来源：`fetch_unit` | `同步 IMEM` |
| 输入 | `imem_rdata` | 32 | 去向：`fetch_unit` | `同步 IMEM` |

### 3.3 Data SRAM 端口

| 方向 | 信号 | 位宽 | CPU 内部来源/去向 | 外部硬件 |
|---|---|---:|---|---|
| 输出 | `dmem_addr` | 32 | 来源：`memory_access_unit` | `Data SRAM` |
| 输出 | `dmem_wdata` | 32 | 来源：`memory_access_unit` | `Data SRAM` |
| 输出 | `dmem_wstrb` | 4 | 来源：`memory_access_unit` | `Data SRAM` |
| 输出 | `dmem_re` | 1 | 来源：`memory_access_unit` | `Data SRAM` |
| 输出 | `dmem_we` | 1 | 来源：`memory_access_unit` | `Data SRAM` |
| 输入 | `dmem_rdata` | 32 | 去向：`memory_access_unit` | `Data SRAM` |

### 3.4 CNN MMIO 端口

| 方向 | 信号 | 位宽 | CPU 内部来源/去向 | 外部硬件 |
|---|---|---:|---|---|
| 输出 | `mmio_addr` | 32 | 来源：`memory_access_unit` | `CNN MMIO` |
| 输出 | `mmio_wdata` | 32 | 来源：`memory_access_unit` | `CNN MMIO` |
| 输出 | `mmio_re` | 1 | 来源：`memory_access_unit` | `CNN MMIO` |
| 输出 | `mmio_we` | 1 | 来源：`memory_access_unit` | `CNN MMIO` |
| 输入 | `mmio_rdata` | 32 | 去向：`memory_access_unit` | `CNN MMIO` |
| 输入 | `mmio_ready` | 1 | 去向：`memory_access_unit` | `CNN MMIO` |

---

## 4. CPU 六模块：逐硬件 I/O

### 4.1 `fetch_unit`

`fetch_unit` 保存 PC、同步取指请求状态和 IF/ID 流水状态。它是六模块中唯一直接连接指令存储器的模块。

#### 输入端口

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | PC、取指适配状态和 IF/ID |
| `rst_n` | 1 | `SoC 复位硬件` | `fetch_unit` 全部时序状态 |
| `pc_en` | 1 | `pipeline_control_unit` | PC 写使能和取指请求门控 |
| `if_id_en` | 1 | `pipeline_control_unit` | 取指响应保持及 IF/ID 写使能 |
| `if_id_flush` | 1 | `pipeline_control_unit` | 丢弃错误路径响应并冲刷 IF/ID |
| `pc_sel` | 2 | `pipeline_control_unit` | next-PC 选择 |
| `branch_target_e` | 32 | `execute_unit` | Branch/JAL 目标地址 |
| `jalr_target_e` | 32 | `execute_unit` | JALR 目标地址，bit 0 已清零 |
| `imem_rdata` | 32 | `同步 IMEM` | 固定一周期同步返回的指令字 |

#### 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `imem_addr` | 32 | `fetch_unit` | `同步 IMEM` |
| `imem_re` | 1 | `fetch_unit` | `同步 IMEM` |
| `valid_d` | 1 | `fetch_unit` 的 IF/ID 状态 | `decode_issue_unit`、`pipeline_control_unit` |
| `instr_d` | 32 | `fetch_unit` 的 IF/ID 状态 | `decode_issue_unit` |
| `pc_d` | 32 | `fetch_unit` 的 IF/ID 状态 | `decode_issue_unit` |
| `pc4_d` | 32 | `fetch_unit` 的 IF/ID 状态 | `decode_issue_unit` |

`pc_sel` 编码继续使用现有定义：`PC_NEXT`、`PC_TARGET`、`PC_JALR`。顺序地址仍是当前 PC 加 4。

### 4.2 `decode_issue_unit`

`decode_issue_unit` 完成 D 级译码、寄存器读取和立即数扩展，并保存 ID/EX 流水状态。寄存器堆也归本模块所有，因此 W 级写回端口回到本模块。

#### 输入端口

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | 寄存器堆和 ID/EX |
| `rst_n` | 1 | `SoC 复位硬件` | 寄存器堆、ID/EX 和安全译码限定 |
| `valid_d` | 1 | `fetch_unit` | D 级有效标志 |
| `instr_d` | 32 | `fetch_unit` | 主译码、ALU 译码、寄存器号和立即数生成 |
| `pc_d` | 32 | `fetch_unit` | ID/EX |
| `pc4_d` | 32 | `fetch_unit` | ID/EX |
| `id_ex_flush` | 1 | `pipeline_control_unit` | 向 E 级插入 bubble |
| `rf_we_w` | 1 | `writeback_unit` | 寄存器堆写使能 |
| `rd_w` | 5 | `writeback_unit` | 寄存器堆写地址 |
| `wb_data_w` | 32 | `writeback_unit` | 寄存器堆写数据 |

#### 输出到执行单元的 E 级端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `valid_e` | 1 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `pc_e` | 32 | ID/EX | `execute_unit` |
| `pc4_e` | 32 | ID/EX | `execute_unit` |
| `rd1_e` | 32 | ID/EX | `execute_unit` |
| `rd2_e` | 32 | ID/EX | `execute_unit` |
| `imm_e` | 32 | ID/EX | `execute_unit` |
| `rs1_e` | 5 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `rs2_e` | 5 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `rd_e` | 5 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `uses_rs1_e` | 1 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `uses_rs2_e` | 1 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `alu_ctrl_e` | 4 | ID/EX | `execute_unit` |
| `alu_src_a_sel_e` | 2 | ID/EX | `execute_unit` |
| `alu_src_b_sel_e` | 2 | ID/EX | `execute_unit` |
| `regwrite_e` | 1 | ID/EX | `execute_unit` |
| `memread_e` | 1 | ID/EX | `execute_unit`、`pipeline_control_unit` |
| `memwrite_e` | 1 | ID/EX | `execute_unit` |
| `load_type_e` | 3 | ID/EX | `execute_unit` |
| `store_type_e` | 2 | ID/EX | `execute_unit` |
| `wb_sel_e` | 2 | ID/EX | `execute_unit` |
| `branch_type_e` | 3 | ID/EX | `execute_unit` |
| `jump_e` | 2 | ID/EX | `execute_unit` |

#### 输出到流水控制单元的 D 级端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `rs1_d` | 5 | `instr_d[19:15]` | `pipeline_control_unit` |
| `rs2_d` | 5 | `instr_d[24:20]` | `pipeline_control_unit` |
| `uses_rs1_d` | 1 | 安全译码结果 | `pipeline_control_unit`、ID/EX |
| `uses_rs2_d` | 1 | 安全译码结果 | `pipeline_control_unit`、ID/EX |

其余 D 级控制字段在本模块内部直接进入 ID/EX，不再作为模块间端口。非法指令、无效 D 级和复位期间仍必须把整组控制清零。

### 4.3 `execute_unit`

`execute_unit` 是纯组合模块。它完成前递选择、ALU 运算、分支比较、重定向判断和目标地址计算，不保存流水状态。

#### E 级数据和控制输入

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `valid_e` | 1 | `decode_issue_unit` | 副作用和重定向有效限定 |
| `pc_e` | 32 | `decode_issue_unit` | ALU/Branch/JAL 目标计算 |
| `pc4_e` | 32 | `decode_issue_unit` | 后续 PC+4 写回候选 |
| `rd1_e` | 32 | `decode_issue_unit` | 未前递的 rs1 数据 |
| `rd2_e` | 32 | `decode_issue_unit` | 未前递的 rs2/Store 数据 |
| `imm_e` | 32 | `decode_issue_unit` | ALU 和跳转目标计算 |
| `rs1_e` | 5 | `decode_issue_unit` | 仅作为 E 级元数据透传/核查 |
| `rs2_e` | 5 | `decode_issue_unit` | 仅作为 E 级元数据透传/核查 |
| `rd_e` | 5 | `decode_issue_unit` | 送往 M 级 |
| `uses_rs1_e` | 1 | `decode_issue_unit` | 操作数有效语义 |
| `uses_rs2_e` | 1 | `decode_issue_unit` | 操作数有效语义 |
| `alu_ctrl_e` | 4 | `decode_issue_unit` | ALU 功能选择 |
| `alu_src_a_sel_e` | 2 | `decode_issue_unit` | ALU A 输入选择 |
| `alu_src_b_sel_e` | 2 | `decode_issue_unit` | ALU B 输入选择 |
| `regwrite_e` | 1 | `decode_issue_unit` | 送往 M 级 |
| `memread_e` | 1 | `decode_issue_unit` | 送往 M 级并限定 SRAM 读 |
| `memwrite_e` | 1 | `decode_issue_unit` | 送往 M 级并限定 SRAM 写 |
| `load_type_e` | 3 | `decode_issue_unit` | Load 类型 |
| `store_type_e` | 2 | `decode_issue_unit` | Store 类型 |
| `wb_sel_e` | 2 | `decode_issue_unit` | 后续写回来源 |
| `branch_type_e` | 3 | `decode_issue_unit` | 分支类型 |
| `jump_e` | 2 | `decode_issue_unit` | JAL/JALR 类型 |

#### 前递输入

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `fwd_a` | 2 | `pipeline_control_unit` | rs1 前递选择 |
| `fwd_b` | 2 | `pipeline_control_unit` | rs2 前递选择 |
| `fwd_store` | 2 | `pipeline_control_unit` | Store 数据独立前递选择 |
| `mem_forward_m` | 32 | `memory_access_unit` | M 级非 Load 前递值 |
| `wb_data_w` | 32 | `writeback_unit` | W 级最终写回值 |

#### 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `valid_e_o` | 1 | `execute_unit` | `memory_access_unit`；值等于 `valid_e` |
| `alu_result_e` | 32 | ALU | `memory_access_unit` |
| `store_data_e` | 32 | Store 前递选择器 | `memory_access_unit` |
| `pc4_e_o` | 32 | `execute_unit` | `memory_access_unit`；值等于 `pc4_e` |
| `rd_e_o` | 5 | `execute_unit` | `memory_access_unit`；值等于 `rd_e` |
| `regwrite_e_o` | 1 | `execute_unit` | `memory_access_unit` |
| `memread_e_o` | 1 | `execute_unit` | `memory_access_unit` |
| `memwrite_e_o` | 1 | `execute_unit` | `memory_access_unit` |
| `load_type_e_o` | 3 | `execute_unit` | `memory_access_unit` |
| `store_type_e_o` | 2 | `execute_unit` | `memory_access_unit` |
| `wb_sel_e_o` | 2 | `execute_unit` | `memory_access_unit` |
| `redirect` | 1 | 分支/跳转判断 | `pipeline_control_unit` |
| `redirect_sel` | 2 | 分支/跳转判断 | `pipeline_control_unit` |
| `branch_target_e` | 32 | `pc_e + imm_e` | `fetch_unit` |
| `jalr_target_e` | 32 | `(前递后 rs1 + imm_e) & 0xffff_fffe` | `fetch_unit` |

`valid_e_o` 等 `_o` 名称只用于明确模块方向；实现时可以用结构体或 SystemVerilog modport 消除端口重名，但位宽和语义不得改变。

### 4.4 `memory_access_unit`

`memory_access_unit` 保存 EX/MEM 状态，生成 E 级 Data SRAM 请求，在 M 级处理同步读返回，并在 M 级访问 CNN MMIO。

#### E 级输入

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | EX/MEM |
| `rst_n` | 1 | `SoC 复位硬件` | EX/MEM 和请求安全限定 |
| `valid_e` | 1 | `execute_unit.valid_e_o` | SRAM 请求和 EX/MEM |
| `alu_result_e` | 32 | `execute_unit` | E 级地址译码、LSU 和 EX/MEM |
| `store_data_e` | 32 | `execute_unit` | E 级 LSU 和 EX/MEM |
| `pc4_e` | 32 | `execute_unit.pc4_e_o` | EX/MEM |
| `rd_e` | 5 | `execute_unit.rd_e_o` | EX/MEM |
| `regwrite_e` | 1 | `execute_unit.regwrite_e_o` | EX/MEM |
| `memread_e` | 1 | `execute_unit.memread_e_o` | SRAM 读请求和 EX/MEM |
| `memwrite_e` | 1 | `execute_unit.memwrite_e_o` | SRAM 写请求和 EX/MEM |
| `load_type_e` | 3 | `execute_unit.load_type_e_o` | E 级 LSU 和 EX/MEM |
| `store_type_e` | 2 | `execute_unit.store_type_e_o` | E 级 LSU 和 EX/MEM |
| `wb_sel_e` | 2 | `execute_unit.wb_sel_e_o` | EX/MEM |

#### 外部返回输入

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `dmem_rdata` | 32 | `Data SRAM` | M 级 LSU |
| `mmio_rdata` | 32 | `CNN MMIO` | M 级读数据选择 |
| `mmio_ready` | 1 | `CNN MMIO` | M 级零等待契约检查和读数据选择 |

#### 输出到 Data SRAM

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `dmem_addr` | 32 | `alu_result_e` | `Data SRAM` |
| `dmem_wdata` | 32 | E 级 LSU | `Data SRAM` |
| `dmem_wstrb` | 4 | E 级 LSU，经写请求限定 | `Data SRAM` |
| `dmem_re` | 1 | E 级 valid、类型、对齐和地址命中限定 | `Data SRAM` |
| `dmem_we` | 1 | E 级 valid、类型、对齐和地址命中限定 | `Data SRAM` |

#### 输出到 CNN MMIO

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `mmio_addr` | 32 | EX/MEM 的 `alu_result_m` | `CNN MMIO` |
| `mmio_wdata` | 32 | EX/MEM 的 `write_data_m` | `CNN MMIO` |
| `mmio_re` | 1 | M 级合法对齐 LW 限定 | `CNN MMIO` |
| `mmio_we` | 1 | M 级合法对齐 SW 限定 | `CNN MMIO` |

#### 输出到写回、执行和流水控制

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `valid_m` | 1 | EX/MEM | `writeback_unit`、`pipeline_control_unit` |
| `read_data_m` | 32 | SRAM/MMIO M 级读数据选择 | `writeback_unit` |
| `alu_result_m` | 32 | EX/MEM | `writeback_unit` |
| `pc4_m` | 32 | EX/MEM | `writeback_unit` |
| `rd_m` | 5 | EX/MEM | `writeback_unit`、`pipeline_control_unit` |
| `regwrite_m` | 1 | EX/MEM | `writeback_unit`、`pipeline_control_unit` |
| `memread_m` | 1 | EX/MEM | `pipeline_control_unit` |
| `wb_sel_m` | 2 | EX/MEM | `writeback_unit` |
| `mem_forward_m` | 32 | M 级非 Load 最终值选择 | `execute_unit` |

`mem_forward_m` 仅允许 `WB_ALU` 和 `WB_PC4` 形成有效候选；M 级 Load 时不得把 `alu_result_m` 地址作为 Load 结果前递。

### 4.5 `writeback_unit`

`writeback_unit` 保存 MEM/WB 状态并形成唯一的 W 级写回值。

#### 输入端口

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | MEM/WB |
| `rst_n` | 1 | `SoC 复位硬件` | MEM/WB |
| `valid_m` | 1 | `memory_access_unit` | MEM/WB |
| `read_data_m` | 32 | `memory_access_unit` | MEM/WB |
| `alu_result_m` | 32 | `memory_access_unit` | MEM/WB |
| `pc4_m` | 32 | `memory_access_unit` | MEM/WB |
| `rd_m` | 5 | `memory_access_unit` | MEM/WB |
| `regwrite_m` | 1 | `memory_access_unit` | MEM/WB |
| `wb_sel_m` | 2 | `memory_access_unit` | MEM/WB |

#### 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `valid_w` | 1 | MEM/WB | `pipeline_control_unit` |
| `rd_w` | 5 | MEM/WB | `decode_issue_unit`、`pipeline_control_unit` |
| `regwrite_w` | 1 | MEM/WB | `pipeline_control_unit` |
| `wb_data_w` | 32 | W 级写回选择器 | `decode_issue_unit`、`execute_unit` |
| `rf_we_w` | 1 | `valid_w && regwrite_w && rd_w != 0` | `decode_issue_unit` |

写回选择仍为 `WB_ALU`、`WB_LOAD`、`WB_PC4`；非法选择输出 0。`wb_data_w` 同时用于寄存器堆写回和 WB→EX 前递。

### 4.6 `pipeline_control_unit`

`pipeline_control_unit` 是纯组合模块，集中处理 D/E/M/W 相关性、前递选择、load-use 暂停和 E 级重定向冲刷。

#### 输入端口

| 信号 | 位宽 | 来源硬件 | 去向/用途 |
|---|---:|---|---|
| `rst_n` | 1 | `SoC 复位硬件` | 全部控制输出安全限定 |
| `valid_d` | 1 | `fetch_unit` | D 级 load-use 判断 |
| `rs1_d` | 5 | `decode_issue_unit` | D 级 load-use 判断 |
| `rs2_d` | 5 | `decode_issue_unit` | D 级 load-use 判断 |
| `uses_rs1_d` | 1 | `decode_issue_unit` | D 级源使用限定 |
| `uses_rs2_d` | 1 | `decode_issue_unit` | D 级源使用限定 |
| `valid_e` | 1 | `decode_issue_unit` | E 级冒险判断 |
| `rs1_e` | 5 | `decode_issue_unit` | rs1 前递比较 |
| `rs2_e` | 5 | `decode_issue_unit` | rs2/Store 前递比较 |
| `rd_e` | 5 | `decode_issue_unit` | load-use 目的寄存器 |
| `uses_rs1_e` | 1 | `decode_issue_unit` | E 级源使用限定 |
| `uses_rs2_e` | 1 | `decode_issue_unit` | E 级源使用限定 |
| `memread_e` | 1 | `decode_issue_unit` | load-use 判断 |
| `valid_m` | 1 | `memory_access_unit` | M 级前递判断 |
| `rd_m` | 5 | `memory_access_unit` | M 级目的寄存器 |
| `regwrite_m` | 1 | `memory_access_unit` | M 级写回有效语义 |
| `memread_m` | 1 | `memory_access_unit` | 禁止 M 级 Load 地址前递 |
| `valid_w` | 1 | `writeback_unit` | W 级前递判断 |
| `rd_w` | 5 | `writeback_unit` | W 级目的寄存器 |
| `regwrite_w` | 1 | `writeback_unit` | W 级写回有效语义 |
| `redirect` | 1 | `execute_unit` | E 级重定向请求 |
| `redirect_sel` | 2 | `execute_unit` | PC 重定向类型 |

#### 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `pc_sel` | 2 | `pipeline_control_unit` | `fetch_unit` |
| `pc_en` | 1 | `pipeline_control_unit` | `fetch_unit` |
| `if_id_en` | 1 | `pipeline_control_unit` | `fetch_unit` |
| `if_id_flush` | 1 | `pipeline_control_unit` | `fetch_unit` |
| `id_ex_flush` | 1 | `pipeline_control_unit` | `decode_issue_unit` |
| `fwd_a` | 2 | `pipeline_control_unit` | `execute_unit` |
| `fwd_b` | 2 | `pipeline_control_unit` | `execute_unit` |
| `fwd_store` | 2 | `pipeline_control_unit` | `execute_unit` |

固定仲裁优先级为：

```text
reset > EX redirect > load-use > normal
```

`operand_unready` 可以保留为模块内部诊断信号，但当前不能接成新的全流水停顿条件。`mul_busy` 当前固定为 0 且未参与控制，重组后不需要成为模块间端口。

---

## 5. 三个例外模块：逐硬件 I/O

### 5.1 `同步 IMEM`

| 方向（相对 IMEM） | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `imem_addr` | 32 | `fetch_unit` | `同步 IMEM` |
| 输入 | `imem_re` | 1 | `fetch_unit` | `同步 IMEM` |
| 输出 | `imem_rdata` | 32 | `同步 IMEM` | `fetch_unit` |

时序要求：在请求边沿接受地址，固定一周期后返回对应指令。没有 `ready` 端口；`fetch_unit` 必须继续承担请求 PC 配对、暂停缓存和 flush 丢弃旧响应。

### 5.2 `Data SRAM`

| 方向（相对 SRAM） | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `dmem_addr` | 32 | `memory_access_unit` | `Data SRAM` |
| 输入 | `dmem_wdata` | 32 | `memory_access_unit` | `Data SRAM` |
| 输入 | `dmem_wstrb` | 4 | `memory_access_unit` | `Data SRAM` |
| 输入 | `dmem_re` | 1 | `memory_access_unit` | `Data SRAM` |
| 输入 | `dmem_we` | 1 | `memory_access_unit` | `Data SRAM` |
| 输出 | `dmem_rdata` | 32 | `Data SRAM` | `memory_access_unit` |

时序要求：请求在 E 级末尾由存储器采样，读数据在对应 M 周期稳定。没有 `ready` 端口。`dmem_re` 与 `dmem_we` 必须互斥，写请求有效时 `dmem_wstrb` 必须非零。

### 5.3 `CNN MMIO`

| 方向（相对 MMIO） | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `mmio_addr` | 32 | `memory_access_unit` | `CNN MMIO` |
| 输入 | `mmio_wdata` | 32 | `memory_access_unit` | `CNN MMIO` |
| 输入 | `mmio_re` | 1 | `memory_access_unit` | `CNN MMIO` |
| 输入 | `mmio_we` | 1 | `memory_access_unit` | `CNN MMIO` |
| 输出 | `mmio_rdata` | 32 | `CNN MMIO` | `memory_access_unit` |
| 输出 | `mmio_ready` | 1 | `CNN MMIO` | `memory_access_unit` |

时序要求：请求在 M 级提交。当前 C1 没有 memory stall，合法请求必须零等待，即请求周期 `mmio_ready=1`。本接口只代表 CNN 寄存器从端口，不包含 CNN SRAM Master、Data SRAM B 口或 CNN 内部计算硬件。

---

## 6. 全部硬件的合并线束（唯一组号）

下表按“来源硬件 → 去向硬件”分组。同一对端点只画一根示意线束，在线旁标组号和总位宽，再由信号清单展开。线束只是画图和接线整理方式，**不是**把多个信号短接为一个 RTL 信号。

### 6.1 全部线组

| 组号 | 一根线束（箭头方向） | 总位宽（bit） | 包含信号 |
|---|---|---:|---|
| 001 | `SoC 时钟硬件` → `fetch_unit` | 1 | `clk` |
| 002 | `SoC 时钟硬件` → `decode_issue_unit` | 1 | `clk` |
| 003 | `SoC 时钟硬件` → `memory_access_unit` | 1 | `clk` |
| 004 | `SoC 时钟硬件` → `writeback_unit` | 1 | `clk` |
| 005 | `SoC 复位硬件` → `fetch_unit` | 1 | `rst_n` |
| 006 | `SoC 复位硬件` → `decode_issue_unit` | 1 | `rst_n` |
| 007 | `SoC 复位硬件` → `memory_access_unit` | 1 | `rst_n` |
| 008 | `SoC 复位硬件` → `writeback_unit` | 1 | `rst_n` |
| 009 | `SoC 复位硬件` → `pipeline_control_unit` | 1 | `rst_n` |
| 010 | `fetch_unit` → `decode_issue_unit` | 97 | `valid_d`、`instr_d`、`pc_d`、`pc4_d` |
| 011 | `fetch_unit` → `pipeline_control_unit` | 1 | `valid_d` |
| 012 | `decode_issue_unit` → `execute_unit` | 201 | 全部 E 级数据和控制端口，见 4.2 节 |
| 013 | `decode_issue_unit` → `pipeline_control_unit` | 31 | `rs1_d`、`rs2_d`、`uses_rs1_d`、`uses_rs2_d`、`valid_e`、`rs1_e`、`rs2_e`、`rd_e`、`uses_rs1_e`、`uses_rs2_e`、`memread_e` |
| 014 | `pipeline_control_unit` → `fetch_unit` | 5 | `pc_sel`、`pc_en`、`if_id_en`、`if_id_flush` |
| 015 | `pipeline_control_unit` → `decode_issue_unit` | 1 | `id_ex_flush` |
| 016 | `pipeline_control_unit` → `execute_unit` | 6 | `fwd_a`、`fwd_b`、`fwd_store` |
| 017 | `execute_unit` → `fetch_unit` | 64 | `branch_target_e`、`jalr_target_e` |
| 018 | `execute_unit` → `pipeline_control_unit` | 3 | `redirect`、`redirect_sel` |
| 019 | `execute_unit` → `memory_access_unit` | 112 | `valid_e_o`、`alu_result_e`、`store_data_e`、`pc4_e_o`、`rd_e_o`、`regwrite_e_o`、`memread_e_o`、`memwrite_e_o`、`load_type_e_o`、`store_type_e_o`、`wb_sel_e_o` |
| 020 | `memory_access_unit` → `execute_unit` | 32 | `mem_forward_m` |
| 021 | `writeback_unit` → `execute_unit` | 32 | `wb_data_w` |
| 022 | `memory_access_unit` → `pipeline_control_unit` | 8 | `valid_m`、`rd_m`、`regwrite_m`、`memread_m` |
| 023 | `writeback_unit` → `pipeline_control_unit` | 7 | `valid_w`、`rd_w`、`regwrite_w` |
| 024 | `memory_access_unit` → `writeback_unit` | 105 | `valid_m`、`read_data_m`、`alu_result_m`、`pc4_m`、`rd_m`、`regwrite_m`、`wb_sel_m` |
| 025 | `writeback_unit` → `decode_issue_unit` | 38 | `rf_we_w`、`rd_w`、`wb_data_w` |
| 026 | `fetch_unit` → `同步 IMEM` | 33 | `imem_addr`、`imem_re` |
| 027 | `同步 IMEM` → `fetch_unit` | 32 | `imem_rdata` |
| 028 | `memory_access_unit` → `Data SRAM` | 70 | `dmem_addr`、`dmem_wdata`、`dmem_wstrb`、`dmem_re`、`dmem_we` |
| 029 | `Data SRAM` → `memory_access_unit` | 32 | `dmem_rdata` |
| 030 | `memory_access_unit` → `CNN MMIO` | 66 | `mmio_addr`、`mmio_wdata`、`mmio_re`、`mmio_we` |
| 031 | `CNN MMIO` → `memory_access_unit` | 33 | `mmio_rdata`、`mmio_ready` |

线组 012 的 201 bit 计算为：五个 32-bit 数据字段 160 bit，三个 5-bit 寄存器号 15 bit，其余 valid、源使用标志和控制字段 26 bit。线组 019 与 024 分别对应进入 EX/MEM 和 MEM/WB 的现有信息，不允许为减少线数而删除字段或重算时序。

### 6.2 每个硬件的输入/输出线组

| 硬件 | 输入线组 | 输出线组 |
|---|---|---|
| `SoC 时钟硬件` | 无（本图外部信号源） | 001、002、003、004 |
| `SoC 复位硬件` | 无（本图外部信号源） | 005、006、007、008、009 |
| `fetch_unit` | 001、005、014、017、027 | 010、011、026 |
| `decode_issue_unit` | 002、006、010、015、025 | 012、013 |
| `execute_unit` | 012、016、020、021 | 017、018、019 |
| `memory_access_unit` | 003、007、019、029、031 | 020、022、024、028、030 |
| `writeback_unit` | 004、008、024 | 021、023、025 |
| `pipeline_control_unit` | 009、011、013、018、022、023 | 014、015、016 |
| `同步 IMEM` | 026 | 027 |
| `Data SRAM` | 028 | 029 |
| `CNN MMIO` | 030 | 031 |

`cpu_core` 是上述线组的封装边界：026～031 穿过其外部端口，001～009 由其公共端口扇出，其余线组全部位于 `cpu_core` 内部。

---

## 7. 接线时序与禁止改动项

### 7.1 四组流水状态

| 流水状态 | 所属目标模块 | 允许的控制 |
|---|---|---|
| IF/ID | `fetch_unit` | `if_id_en`、`if_id_flush` |
| ID/EX | `decode_issue_unit` | `id_ex_flush` |
| EX/MEM | `memory_access_unit` | 正常逐拍推进，不受 load-use 冻结 |
| MEM/WB | `writeback_unit` | 正常逐拍推进，不受 load-use 冻结 |

不得因为模块合并而把任何一组流水寄存器移动到组合路径另一侧，否则会改变周期行为。

### 7.2 前递和暂停

- M 级非 Load 的 ALU/PC+4 结果可以经 `mem_forward_m` 前递。
- M 级 Load 必须遮挡同目的寄存器的旧 W 级值，不能把 Load 地址前递。
- W 级只前递最终的 `wb_data_w`。
- Store 数据继续使用独立的 `fwd_store`。
- load-use 只保持 PC 和 IF/ID，并冲刷 ID/EX；M/W 不停顿。

### 7.3 重定向

- Branch、JAL、JALR 均在 E 级判定。
- redirect 时冲刷 IF/ID 和 ID/EX。
- Branch/JAL 使用 `branch_target_e`，JALR 使用 `jalr_target_e`。
- JALR 目标 bit 0 必须清零。
- reset、redirect、load-use 同周期出现时，固定优先级仍为 `reset > redirect > load-use > normal`。

### 7.4 存储器和 MMIO

- Data SRAM 地址与请求在 E 级形成，读数据在 M 级使用。
- CNN MMIO 地址和请求使用 EX/MEM 中保存的 M 级信息。
- SRAM 与 MMIO 是独立接口，允许 M 级 MMIO 与下一条 E 级 SRAM 请求同周期出现。
- 不得把 CNN MMIO 合并进 `pipeline_control_unit`，也不得新增 CNN `STATUS/CONTROL` 专用硬件端口。

## 8. 五模块版本如何改线

若最终采用五模块版本，只把 `writeback_unit` 合并进 `memory_access_unit`，并形成 `memory_writeback_unit`：

- 删除线组 024；其内容变成模块内部连接。
- 线组 021、023、025 的来源改为 `memory_writeback_unit`。
- `clk`、`rst_n` 对 `writeback_unit` 的线组 004、008 合并到 `memory_writeback_unit` 内部，不再单独画线。
- 其余信号、位宽、流水寄存器位置和三个例外模块的端口全部不变。

六模块版本的级间边界更清晰，建议作为正式接线基线；五模块版本只适合确实需要减少顶层实例数量的情况。

## 9. 实施后的接线核对要求

完成 RTL 重构后，应逐项核对：

1. 六个功能模块和三个例外模块的每个端口都能在本文找到唯一来源和去向。
2. 001～031 每个线组均已连接，不存在多驱动、悬空的有效输入或位宽截断。
3. 外部 IMEM、Data SRAM、CNN MMIO 端口与当前生产 `cpu_datapath` 的端口名称、方向和位宽一致。
4. 四组流水寄存器位置、reset/flush/enable 行为与现有 RTL 一致。
5. ADD 与混合程序的 PC、四级 valid、rd、写回、SRAM 和 MMIO 请求序列与重构前逐周期一致。

在这些检查完成前，本文只作为目标接线说明，不能替代当前已经通过联调的生产 Control 和 Datapath RTL。
