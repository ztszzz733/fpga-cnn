# CPU Control 与 CPU Datapath 硬件 I/O 连接清单

## 1. “顶层”是不是硬件

是。本文中的 `cpu_control` 和 `cpu_datapath` 都是 RTL 源码中真实声明的 `module`：

- `cpu_control` 是 CPU Control 组的顶层硬件模块。
- `cpu_datapath` 是 CPU Datapath 组的顶层硬件模块。

“顶层”只表示它位于这一组模块层次的最上面，负责连接组内子模块和组外接口。它被实例化并综合后就是实际硬件，不是文档虚构的名称。

本文只使用下列真实 RTL 模块名。顶层文件中的 `assign` 或 `always_comb` 统一归属于其真实模块 `cpu_control` 或 `cpu_datapath`，不把其中一段组合逻辑另外起名为硬件模块。

## 2. 硬件清单

### 2.1 CPU Control 组

| 硬件模块 | RTL 文件 |
|---|---|
| `cpu_control` | `rtl/cpu_control/cpu_control.sv` |
| `main_decoder` | `rtl/cpu_control/main_decoder.sv` |
| `alu_decoder` | `rtl/cpu_control/alu_decoder.sv` |
| `hazard_unit` | `rtl/cpu_control/hazard_unit.sv` |
| `branch_control` | `rtl/cpu_control/branch_control.sv` |
| `pipeline_control` | `rtl/cpu_control/pipeline_control.sv` |

### 2.2 CPU Datapath 组

| 硬件模块 | RTL 文件 |
|---|---|
| `cpu_datapath` | `rtl/cpu_datapath/cpu_datapath.sv` |
| `pc` | `rtl/cpu_datapath/pc.sv` |
| `fetch_adapter` | `rtl/cpu_datapath/fetch_adapter.sv` |
| `if_id_reg` | `rtl/cpu_datapath/if_id_reg.sv` |
| `regfile` | `rtl/cpu_datapath/regfile.sv` |
| `imm_gen` | `rtl/cpu_datapath/imm_gen.sv` |
| `id_ex_reg` | `rtl/cpu_datapath/id_ex_reg.sv` |
| `alu` | `rtl/cpu_datapath/alu.sv` |
| `address_decoder` | `rtl/cpu_datapath/address_decoder.sv`，在 E/M 级各实例化一次 |
| `lsu` | `rtl/cpu_datapath/lsu.sv`，在 E/M 级各实例化一次 |
| `ex_mem_reg` | `rtl/cpu_datapath/ex_mem_reg.sv` |
| `mem_wb_reg` | `rtl/cpu_datapath/mem_wb_reg.sv` |

Datapath RTL 来自生产快照 `build/datapath_review/20260917_211827/rtl/cpu_datapath/`；上表使用交付包内的相对目录表示。

### 2.3 两组以外的边界硬件

这些硬件不是本清单两组的生产 RTL，但它们是顶层端口的实际来源或去向，因此列名如下：

| 文中名称 | 含义 |
|---|---|
| `SoC 时钟硬件` | 为两组模块提供 `clk`；不在本次交付中 |
| `SoC 复位硬件` | 为两组模块提供低有效 `rst_n`；不在本次交付中 |
| `同步 IMEM` | 指令存储器；当前仿真连接 `imem_model` |
| `Data SRAM` | 数据存储器 A 口；当前仿真连接 `dmem_model` |
| `CNN MMIO` | CNN 寄存器接口；当前仿真连接 `cnn_mmio_stub` |

---

## 3. CPU Control 组：逐硬件 I/O

### 3.1 `cpu_control`

`cpu_control` 是真实顶层硬件模块。它包含五个 Control 子模块，并包含少量直接写在顶层中的组合连接和安全清零逻辑。

#### 输入端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | `cpu_control`；当前内部未使用 |
| `rst_n` | 1 | `SoC 复位硬件` | `cpu_control`、`pipeline_control` |
| `instr_d` | 32 | `if_id_reg` | `main_decoder`、`alu_decoder` |
| `rs1_d` | 5 | `cpu_datapath` | `hazard_unit` |
| `rs2_d` | 5 | `cpu_datapath` | `hazard_unit` |
| `rd_e` | 5 | `id_ex_reg` | `hazard_unit` |
| `rd_m` | 5 | `ex_mem_reg` | `hazard_unit` |
| `rd_w` | 5 | `mem_wb_reg` | `hazard_unit` |
| `regwrite_m` | 1 | `ex_mem_reg` | `hazard_unit` |
| `regwrite_w` | 1 | `mem_wb_reg` | `hazard_unit` |
| `memread_e` | 1 | `id_ex_reg` | `hazard_unit` |
| `cmp_eq_e` | 1 | `cpu_datapath` | `branch_control` |
| `cmp_lt_e` | 1 | `cpu_datapath` | `branch_control` |
| `cmp_ltu_e` | 1 | `cpu_datapath` | `branch_control` |
| `mul_busy` | 1 | `cpu_datapath`，当前固定为 0 | `cpu_control`；当前内部未使用 |
| `valid_d` | 1 | `if_id_reg` | `cpu_control`、`hazard_unit` |
| `valid_e` | 1 | `id_ex_reg` | `hazard_unit`、`branch_control` |
| `valid_m` | 1 | `ex_mem_reg` | `hazard_unit` |
| `valid_w` | 1 | `mem_wb_reg` | `hazard_unit` |
| `rs1_e` | 5 | `id_ex_reg` | `hazard_unit` |
| `rs2_e` | 5 | `id_ex_reg` | `hazard_unit` |
| `uses_rs1_e` | 1 | `id_ex_reg` | `hazard_unit` |
| `uses_rs2_e` | 1 | `id_ex_reg` | `hazard_unit` |
| `branch_type_e` | 3 | `id_ex_reg` | `branch_control` |
| `jump_e` | 2 | `id_ex_reg` | `branch_control` |
| `memread_m` | 1 | `ex_mem_reg` | `hazard_unit` |

#### 输出端口

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `pc_sel` | 2 | `pipeline_control` | `cpu_datapath` |
| `pc_en` | 1 | `pipeline_control` | `pc`、`fetch_adapter` |
| `if_id_en` | 1 | `pipeline_control` | `fetch_adapter`、`if_id_reg` |
| `if_id_flush` | 1 | `pipeline_control` | `fetch_adapter`、`if_id_reg` |
| `id_ex_flush` | 1 | `pipeline_control` | `id_ex_reg` |
| `alu_ctrl` | 4 | `cpu_control` | `id_ex_reg` |
| `alu_src_a_sel` | 2 | `cpu_control` | `id_ex_reg` |
| `alu_src_b_sel` | 2 | `cpu_control` | `id_ex_reg` |
| `fwd_a` | 2 | `hazard_unit` 经 `cpu_control` 复位限定 | `cpu_datapath` |
| `fwd_b` | 2 | `hazard_unit` 经 `cpu_control` 复位限定 | `cpu_datapath` |
| `fwd_store` | 2 | `hazard_unit` 经 `cpu_control` 复位限定 | `cpu_datapath` |
| `regwrite_d` | 1 | `cpu_control` | `id_ex_reg` |
| `memread_d` | 1 | `cpu_control` | `id_ex_reg` |
| `memwrite_d` | 1 | `cpu_control` | `id_ex_reg` |
| `load_type_d` | 3 | `cpu_control` | `id_ex_reg` |
| `store_type_d` | 2 | `cpu_control` | `id_ex_reg` |
| `wb_sel_d` | 2 | `cpu_control` | `id_ex_reg` |
| `branch_type_d` | 3 | `cpu_control` | `id_ex_reg` |
| `jump_d` | 2 | `cpu_control` | `id_ex_reg` |
| `imm_type_d` | 3 | `cpu_control` | `imm_gen` |
| `uses_rs1_d` | 1 | `cpu_control` | `hazard_unit`、`id_ex_reg` |
| `uses_rs2_d` | 1 | `cpu_control` | `hazard_unit`、`id_ex_reg` |

说明：`alu_ctrl` 等译码输出之所以写来源为 `cpu_control`，是因为 `main_decoder` 和 `alu_decoder` 的结果还要经过 `cpu_control` 顶层的合法性及复位限定；该顶层逻辑属于真实模块 `cpu_control`，不是另一个硬件模块。

### 3.2 `main_decoder`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `instr_d` | 32 | `if_id_reg` | `main_decoder` |
| 输出 | `decoded` | 28 | `main_decoder` | `cpu_control` |
| 输出 | `legal_main` | 1 | `main_decoder` | `cpu_control` |

### 3.3 `alu_decoder`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `opcode` | 7 | `if_id_reg` 的 `instr_d[6:0]` | `alu_decoder` |
| 输入 | `funct3` | 3 | `if_id_reg` 的 `instr_d[14:12]` | `alu_decoder` |
| 输入 | `funct7` | 7 | `if_id_reg` 的 `instr_d[31:25]` | `alu_decoder` |
| 输出 | `alu_decoded` | 4 | `alu_decoder` | `cpu_control` |
| 输出 | `legal_alu` | 1 | `alu_decoder` | `cpu_control` |

`legal_alu` 不去 `pipeline_control`。它只进入 `cpu_control` 顶层的合法译码判断。

### 3.4 `hazard_unit`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `valid_d` | 1 | `if_id_reg` | `hazard_unit` |
| 输入 | `valid_e` | 1 | `id_ex_reg` | `hazard_unit` |
| 输入 | `valid_m` | 1 | `ex_mem_reg` | `hazard_unit` |
| 输入 | `valid_w` | 1 | `mem_wb_reg` | `hazard_unit` |
| 输入 | `rs1_d` | 5 | `cpu_datapath` | `hazard_unit` |
| 输入 | `rs2_d` | 5 | `cpu_datapath` | `hazard_unit` |
| 输入 | `rs1_e` | 5 | `id_ex_reg` | `hazard_unit` |
| 输入 | `rs2_e` | 5 | `id_ex_reg` | `hazard_unit` |
| 输入 | `rd_e` | 5 | `id_ex_reg` | `hazard_unit` |
| 输入 | `rd_m` | 5 | `ex_mem_reg` | `hazard_unit` |
| 输入 | `rd_w` | 5 | `mem_wb_reg` | `hazard_unit` |
| 输入 | `uses_rs1_d` | 1 | `cpu_control` | `hazard_unit` |
| 输入 | `uses_rs2_d` | 1 | `cpu_control` | `hazard_unit` |
| 输入 | `uses_rs1_e` | 1 | `id_ex_reg` | `hazard_unit` |
| 输入 | `uses_rs2_e` | 1 | `id_ex_reg` | `hazard_unit` |
| 输入 | `memread_e` | 1 | `id_ex_reg` | `hazard_unit` |
| 输入 | `memread_m` | 1 | `ex_mem_reg` | `hazard_unit` |
| 输入 | `regwrite_m` | 1 | `ex_mem_reg` | `hazard_unit` |
| 输入 | `regwrite_w` | 1 | `mem_wb_reg` | `hazard_unit` |
| 输出 | `load_use` | 1 | `hazard_unit` | `pipeline_control` |
| 输出 | `fwd_a` | 2 | `hazard_unit` | `cpu_control`，再输出到 `cpu_datapath` |
| 输出 | `fwd_b` | 2 | `hazard_unit` | `cpu_control`，再输出到 `cpu_datapath` |
| 输出 | `fwd_store` | 2 | `hazard_unit` | `cpu_control`，再输出到 `cpu_datapath` |
| 输出 | `operand_unready` | 1 | `hazard_unit` | `cpu_control` 内部未使用 |

### 3.5 `branch_control`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `valid_e` | 1 | `id_ex_reg` | `branch_control` |
| 输入 | `branch_type_e` | 3 | `id_ex_reg` | `branch_control` |
| 输入 | `jump_e` | 2 | `id_ex_reg` | `branch_control` |
| 输入 | `cmp_eq_e` | 1 | `cpu_datapath` | `branch_control` |
| 输入 | `cmp_lt_e` | 1 | `cpu_datapath` | `branch_control` |
| 输入 | `cmp_ltu_e` | 1 | `cpu_datapath` | `branch_control` |
| 输出 | `redirect` | 1 | `branch_control` | `pipeline_control` |
| 输出 | `redirect_sel` | 2 | `branch_control` | `pipeline_control` |

### 3.6 `pipeline_control`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `pipeline_control` |
| 输入 | `redirect` | 1 | `branch_control` | `pipeline_control` |
| 输入 | `load_use` | 1 | `hazard_unit` | `pipeline_control` |
| 输入 | `redirect_sel` | 2 | `branch_control` | `pipeline_control` |
| 输出 | `pc_en` | 1 | `pipeline_control` | `pc`、`fetch_adapter` |
| 输出 | `if_id_en` | 1 | `pipeline_control` | `fetch_adapter`、`if_id_reg` |
| 输出 | `if_id_flush` | 1 | `pipeline_control` | `fetch_adapter`、`if_id_reg` |
| 输出 | `id_ex_flush` | 1 | `pipeline_control` | `id_ex_reg` |
| 输出 | `pc_sel` | 2 | `pipeline_control` | `cpu_datapath` |

---

## 4. CPU Datapath 组：逐硬件 I/O

### 4.1 `cpu_datapath`

`cpu_datapath` 是真实顶层硬件模块。顶层中直接写出的比较、选择和请求限定都归属于 `cpu_datapath`，不另起虚构模块名。

#### Control 和公共输入

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `clk` | 1 | `SoC 时钟硬件` | `pc`、`fetch_adapter`、`if_id_reg`、`regfile`、`id_ex_reg`、`ex_mem_reg`、`mem_wb_reg` |
| `rst_n` | 1 | `SoC 复位硬件` | `cpu_datapath` 及上述所有时序模块 |
| `pc_sel` | 2 | `pipeline_control` | `cpu_datapath` |
| `pc_en` | 1 | `pipeline_control` | `pc`、`fetch_adapter` |
| `if_id_en` | 1 | `pipeline_control` | `fetch_adapter`、`if_id_reg` |
| `if_id_flush` | 1 | `pipeline_control` | `fetch_adapter`、`if_id_reg` |
| `id_ex_flush` | 1 | `pipeline_control` | `id_ex_reg` |
| `alu_ctrl` | 4 | `cpu_control` | `id_ex_reg` |
| `alu_src_a_sel` | 2 | `cpu_control` | `id_ex_reg` |
| `alu_src_b_sel` | 2 | `cpu_control` | `id_ex_reg` |
| `fwd_a` | 2 | `cpu_control` | `cpu_datapath` |
| `fwd_b` | 2 | `cpu_control` | `cpu_datapath` |
| `fwd_store` | 2 | `cpu_control` | `cpu_datapath` |
| `regwrite_d` | 1 | `cpu_control` | `id_ex_reg` |
| `memread_d` | 1 | `cpu_control` | `id_ex_reg` |
| `memwrite_d` | 1 | `cpu_control` | `id_ex_reg` |
| `load_type_d` | 3 | `cpu_control` | `id_ex_reg` |
| `store_type_d` | 2 | `cpu_control` | `id_ex_reg` |
| `wb_sel_d` | 2 | `cpu_control` | `id_ex_reg` |
| `branch_type_d` | 3 | `cpu_control` | `id_ex_reg` |
| `jump_d` | 2 | `cpu_control` | `id_ex_reg` |
| `imm_type_d` | 3 | `cpu_control` | `imm_gen` |
| `uses_rs1_d` | 1 | `cpu_control` | `id_ex_reg` |
| `uses_rs2_d` | 1 | `cpu_control` | `id_ex_reg` |

#### 输出到 Control

| 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---:|---|---|
| `instr_d` | 32 | `if_id_reg` | `main_decoder`、`alu_decoder` |
| `rs1_d` | 5 | `cpu_datapath` | `hazard_unit`、`regfile`、`id_ex_reg` |
| `rs2_d` | 5 | `cpu_datapath` | `hazard_unit`、`regfile`、`id_ex_reg` |
| `rd_e` | 5 | `id_ex_reg` | `hazard_unit`、`ex_mem_reg` |
| `rd_m` | 5 | `ex_mem_reg` | `hazard_unit`、`mem_wb_reg` |
| `rd_w` | 5 | `mem_wb_reg` | `hazard_unit`、`regfile`、`cpu_datapath` |
| `regwrite_m` | 1 | `ex_mem_reg` | `hazard_unit`、`mem_wb_reg` |
| `regwrite_w` | 1 | `mem_wb_reg` | `hazard_unit`、`cpu_datapath` |
| `memread_e` | 1 | `id_ex_reg` | `hazard_unit`、`ex_mem_reg`、`cpu_datapath` |
| `cmp_eq_e` | 1 | `cpu_datapath` | `branch_control` |
| `cmp_lt_e` | 1 | `cpu_datapath` | `branch_control` |
| `cmp_ltu_e` | 1 | `cpu_datapath` | `branch_control` |
| `mul_busy` | 1 | `cpu_datapath`，固定为 0 | `cpu_control` |
| `valid_d` | 1 | `if_id_reg` | `cpu_control`、`hazard_unit`、`id_ex_reg` |
| `valid_e` | 1 | `id_ex_reg` | `hazard_unit`、`branch_control`、`ex_mem_reg`、`cpu_datapath` |
| `valid_m` | 1 | `ex_mem_reg` | `hazard_unit`、`mem_wb_reg`、`cpu_datapath` |
| `valid_w` | 1 | `mem_wb_reg` | `hazard_unit`、`cpu_datapath` |
| `rs1_e` | 5 | `id_ex_reg` | `hazard_unit` |
| `rs2_e` | 5 | `id_ex_reg` | `hazard_unit` |
| `uses_rs1_e` | 1 | `id_ex_reg` | `hazard_unit` |
| `uses_rs2_e` | 1 | `id_ex_reg` | `hazard_unit` |
| `branch_type_e` | 3 | `id_ex_reg` | `branch_control` |
| `jump_e` | 2 | `id_ex_reg` | `branch_control` |
| `memread_m` | 1 | `ex_mem_reg` | `hazard_unit`、`cpu_datapath` |

#### 外部存储和 MMIO 端口

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输出 | `imem_addr` | 32 | `fetch_adapter` | `同步 IMEM` |
| 输出 | `imem_re` | 1 | `fetch_adapter` | `同步 IMEM` |
| 输入 | `imem_rdata` | 32 | `同步 IMEM` | `fetch_adapter` |
| 输出 | `dmem_addr` | 32 | `alu` 经 `cpu_datapath` | `Data SRAM` |
| 输出 | `dmem_wdata` | 32 | `lsu` 的 E 级实例 | `Data SRAM` |
| 输出 | `dmem_wstrb` | 4 | `lsu` 的 E 级实例经 `cpu_datapath` 限定 | `Data SRAM` |
| 输出 | `dmem_re` | 1 | `cpu_datapath` | `Data SRAM` |
| 输出 | `dmem_we` | 1 | `cpu_datapath` | `Data SRAM` |
| 输入 | `dmem_rdata` | 32 | `Data SRAM` | `lsu` 的 M 级实例 |
| 输出 | `mmio_addr` | 32 | `ex_mem_reg` | `CNN MMIO` |
| 输出 | `mmio_wdata` | 32 | `ex_mem_reg` | `CNN MMIO` |
| 输出 | `mmio_re` | 1 | `cpu_datapath` | `CNN MMIO` |
| 输出 | `mmio_we` | 1 | `cpu_datapath` | `CNN MMIO` |
| 输入 | `mmio_rdata` | 32 | `CNN MMIO` | `cpu_datapath` |
| 输入 | `mmio_ready` | 1 | `CNN MMIO` | `cpu_datapath` |

### 4.2 `pc`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `pc` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `pc` |
| 输入 | `pc_en` | 1 | `pipeline_control` | `pc` |
| 输入 | `next_pc` | 32 | `cpu_datapath` | `pc` |
| 输出 | `pc_q` | 32 | `pc` | `cpu_datapath`、`fetch_adapter` |

### 4.3 `fetch_adapter`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `fetch_adapter` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `fetch_adapter` |
| 输入 | `request_pc` | 32 | `pc` | `fetch_adapter` |
| 输入 | `pc_en` | 1 | `pipeline_control` | `fetch_adapter` |
| 输入 | `if_id_en` | 1 | `pipeline_control` | `fetch_adapter` |
| 输入 | `flush` | 1 | `pipeline_control` | `fetch_adapter` |
| 输出 | `imem_addr` | 32 | `fetch_adapter` | `同步 IMEM` |
| 输出 | `imem_re` | 1 | `fetch_adapter` | `同步 IMEM` |
| 输入 | `imem_rdata` | 32 | `同步 IMEM` | `fetch_adapter` |
| 输出 | `fetch_valid` | 1 | `fetch_adapter` | `if_id_reg` |
| 输出 | `fetch_instr` | 32 | `fetch_adapter` | `if_id_reg` |
| 输出 | `fetch_pc` | 32 | `fetch_adapter` | `if_id_reg` |
| 输出 | `fetch_pc4` | 32 | `fetch_adapter` | `if_id_reg` |

### 4.4 `if_id_reg`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `if_id_reg` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `if_id_reg` |
| 输入 | `en` | 1 | `pipeline_control` | `if_id_reg` |
| 输入 | `flush` | 1 | `pipeline_control` | `if_id_reg` |
| 输入 | `valid_i` | 1 | `fetch_adapter` | `if_id_reg` |
| 输入 | `instr_i` | 32 | `fetch_adapter` | `if_id_reg` |
| 输入 | `pc_i` | 32 | `fetch_adapter` | `if_id_reg` |
| 输入 | `pc4_i` | 32 | `fetch_adapter` | `if_id_reg` |
| 输出 | `valid_o` | 1 | `if_id_reg` | `cpu_control`、`hazard_unit`、`id_ex_reg` |
| 输出 | `instr_o` | 32 | `if_id_reg` | `main_decoder`、`alu_decoder`、`cpu_datapath`、`imm_gen` |
| 输出 | `pc_o` | 32 | `if_id_reg` | `id_ex_reg` |
| 输出 | `pc4_o` | 32 | `if_id_reg` | `id_ex_reg` |

### 4.5 `regfile`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `regfile` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `regfile` |
| 输入 | `rs1` | 5 | `cpu_datapath` | `regfile` |
| 输入 | `rs2` | 5 | `cpu_datapath` | `regfile` |
| 输入 | `we` | 1 | `cpu_datapath` | `regfile` |
| 输入 | `waddr` | 5 | `mem_wb_reg` | `regfile` |
| 输入 | `wdata` | 32 | `cpu_datapath` | `regfile` |
| 输出 | `rd1` | 32 | `regfile` | `id_ex_reg` |
| 输出 | `rd2` | 32 | `regfile` | `id_ex_reg` |

### 4.6 `imm_gen`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `instr` | 32 | `if_id_reg` | `imm_gen` |
| 输入 | `imm_type` | 3 | `cpu_control` | `imm_gen` |
| 输出 | `imm_ext` | 32 | `imm_gen` | `id_ex_reg` |

### 4.7 `id_ex_reg`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `id_ex_reg` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `id_ex_reg` |
| 输入 | `flush` | 1 | `pipeline_control` | `id_ex_reg` |
| 输入 | `valid_d` | 1 | `if_id_reg` | `id_ex_reg` |
| 输入 | `pc_d` | 32 | `if_id_reg` | `id_ex_reg` |
| 输入 | `pc4_d` | 32 | `if_id_reg` | `id_ex_reg` |
| 输入 | `rd1_d` | 32 | `regfile` | `id_ex_reg` |
| 输入 | `rd2_d` | 32 | `regfile` | `id_ex_reg` |
| 输入 | `imm_d` | 32 | `imm_gen` | `id_ex_reg` |
| 输入 | `rs1_d` | 5 | `cpu_datapath` | `id_ex_reg` |
| 输入 | `rs2_d` | 5 | `cpu_datapath` | `id_ex_reg` |
| 输入 | `rd_d` | 5 | `cpu_datapath` | `id_ex_reg` |
| 输入 | `uses_rs1_d` | 1 | `cpu_control` | `id_ex_reg` |
| 输入 | `uses_rs2_d` | 1 | `cpu_control` | `id_ex_reg` |
| 输入 | `alu_ctrl_d` | 4 | `cpu_control` | `id_ex_reg` |
| 输入 | `alu_src_a_sel_d` | 2 | `cpu_control` | `id_ex_reg` |
| 输入 | `alu_src_b_sel_d` | 2 | `cpu_control` | `id_ex_reg` |
| 输入 | `regwrite_d` | 1 | `cpu_control` | `id_ex_reg` |
| 输入 | `memread_d` | 1 | `cpu_control` | `id_ex_reg` |
| 输入 | `memwrite_d` | 1 | `cpu_control` | `id_ex_reg` |
| 输入 | `load_type_d` | 3 | `cpu_control` | `id_ex_reg` |
| 输入 | `store_type_d` | 2 | `cpu_control` | `id_ex_reg` |
| 输入 | `wb_sel_d` | 2 | `cpu_control` | `id_ex_reg` |
| 输入 | `branch_type_d` | 3 | `cpu_control` | `id_ex_reg` |
| 输入 | `jump_d` | 2 | `cpu_control` | `id_ex_reg` |
| 输出 | `valid_e` | 1 | `id_ex_reg` | `hazard_unit`、`branch_control`、`ex_mem_reg`、`cpu_datapath` |
| 输出 | `pc_e` | 32 | `id_ex_reg` | `cpu_datapath` |
| 输出 | `pc4_e` | 32 | `id_ex_reg` | `ex_mem_reg` |
| 输出 | `rd1_e` | 32 | `id_ex_reg` | `cpu_datapath` |
| 输出 | `rd2_e` | 32 | `id_ex_reg` | `cpu_datapath` |
| 输出 | `imm_e` | 32 | `id_ex_reg` | `cpu_datapath` |
| 输出 | `rs1_e` | 5 | `id_ex_reg` | `hazard_unit` |
| 输出 | `rs2_e` | 5 | `id_ex_reg` | `hazard_unit` |
| 输出 | `rd_e` | 5 | `id_ex_reg` | `hazard_unit`、`ex_mem_reg` |
| 输出 | `uses_rs1_e` | 1 | `id_ex_reg` | `hazard_unit` |
| 输出 | `uses_rs2_e` | 1 | `id_ex_reg` | `hazard_unit` |
| 输出 | `alu_ctrl_e` | 4 | `id_ex_reg` | `alu` |
| 输出 | `alu_src_a_sel_e` | 2 | `id_ex_reg` | `cpu_datapath` |
| 输出 | `alu_src_b_sel_e` | 2 | `id_ex_reg` | `cpu_datapath` |
| 输出 | `regwrite_e` | 1 | `id_ex_reg` | `ex_mem_reg` |
| 输出 | `memread_e` | 1 | `id_ex_reg` | `hazard_unit`、`ex_mem_reg`、`cpu_datapath` |
| 输出 | `memwrite_e` | 1 | `id_ex_reg` | `ex_mem_reg`、`cpu_datapath` |
| 输出 | `load_type_e` | 3 | `id_ex_reg` | `lsu` 的 E 级实例、`ex_mem_reg` |
| 输出 | `store_type_e` | 2 | `id_ex_reg` | `lsu` 的 E 级实例、`ex_mem_reg` |
| 输出 | `wb_sel_e` | 2 | `id_ex_reg` | `ex_mem_reg` |
| 输出 | `branch_type_e` | 3 | `id_ex_reg` | `branch_control` |
| 输出 | `jump_e` | 2 | `id_ex_reg` | `branch_control` |

### 4.8 `alu`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `a` | 32 | `cpu_datapath` | `alu` |
| 输入 | `b` | 32 | `cpu_datapath` | `alu` |
| 输入 | `alu_ctrl` | 4 | `id_ex_reg` | `alu` |
| 输出 | `result` | 32 | `alu` | `address_decoder` 的 E 级实例、`lsu` 的 E 级实例、`ex_mem_reg`、`Data SRAM` |
| 输出 | `zero` | 1 | `alu` | `cpu_datapath` 内部未使用 |

### 4.9 `address_decoder`

同一个真实模块实例化两次，因此按实例所处级分别写来源和去向。

| 方向/信号 | 位宽 | E 级实例：来源或去向硬件 | M 级实例：来源或去向硬件 |
|---|---:|---|---|
| 输入 `addr` | 32 | 来源：`alu` | 来源：`ex_mem_reg` |
| 输出 `sram_hit` | 1 | 去向：`cpu_datapath` | 去向：`cpu_datapath` |
| 输出 `mmio_window_hit` | 1 | 去向：`cpu_datapath`，当前未使用 | 去向：`cpu_datapath`，当前未使用 |
| 输出 `mmio_reg_hit` | 1 | 去向：`cpu_datapath`，当前未使用 | 去向：`cpu_datapath` |
| 输出 `unmapped` | 1 | 去向：`cpu_datapath`，当前未使用 | 去向：`cpu_datapath`，当前未使用 |

### 4.10 `lsu`

同一个真实模块实例化两次：E 级实例生成 SRAM 写数据和请求合法性；M 级实例处理 SRAM 读返回。

| 方向/信号 | 位宽 | E 级实例：来源或去向硬件 | M 级实例：来源或去向硬件 |
|---|---:|---|---|
| 输入 `addr` | 32 | 来源：`alu` | 来源：`ex_mem_reg` |
| 输入 `store_data` | 32 | 来源：`cpu_datapath` | 来源：`ex_mem_reg` |
| 输入 `read_word` | 32 | 来源：`cpu_datapath` 的常数 0 | 来源：`Data SRAM` |
| 输入 `load_type` | 3 | 来源：`id_ex_reg` | 来源：`ex_mem_reg` |
| 输入 `store_type` | 2 | 来源：`id_ex_reg` | 来源：`ex_mem_reg` |
| 输出 `load_data` | 32 | 去向：`cpu_datapath`，当前未使用 | 去向：`cpu_datapath` |
| 输出 `load_aligned` | 1 | 去向：`cpu_datapath` | 去向：`cpu_datapath` |
| 输出 `load_type_valid` | 1 | 去向：`cpu_datapath` | 去向：`cpu_datapath` |
| 输出 `store_wdata` | 32 | 去向：`Data SRAM` | 去向：`cpu_datapath`，当前未使用 |
| 输出 `store_wstrb` | 4 | 去向：`cpu_datapath`，再到 `Data SRAM` | 去向：`cpu_datapath`，当前未使用 |
| 输出 `store_aligned` | 1 | 去向：`cpu_datapath` | 去向：`cpu_datapath`，当前未使用 |
| 输出 `store_type_valid` | 1 | 去向：`cpu_datapath` | 去向：`cpu_datapath`，当前未使用 |

### 4.11 `ex_mem_reg`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `ex_mem_reg` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `ex_mem_reg` |
| 输入 | `valid_e` | 1 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `alu_result_e` | 32 | `alu` | `ex_mem_reg` |
| 输入 | `write_data_e` | 32 | `cpu_datapath` | `ex_mem_reg` |
| 输入 | `pc4_e` | 32 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `rd_e` | 5 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `regwrite_e` | 1 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `memread_e` | 1 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `memwrite_e` | 1 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `load_type_e` | 3 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `store_type_e` | 2 | `id_ex_reg` | `ex_mem_reg` |
| 输入 | `wb_sel_e` | 2 | `id_ex_reg` | `ex_mem_reg` |
| 输出 | `valid_m` | 1 | `ex_mem_reg` | `hazard_unit`、`mem_wb_reg`、`cpu_datapath` |
| 输出 | `alu_result_m` | 32 | `ex_mem_reg` | `address_decoder` 的 M 级实例、`lsu` 的 M 级实例、`mem_wb_reg`、`cpu_datapath`、`CNN MMIO` |
| 输出 | `write_data_m` | 32 | `ex_mem_reg` | `lsu` 的 M 级实例、`CNN MMIO` |
| 输出 | `pc4_m` | 32 | `ex_mem_reg` | `mem_wb_reg`、`cpu_datapath` |
| 输出 | `rd_m` | 5 | `ex_mem_reg` | `hazard_unit`、`mem_wb_reg` |
| 输出 | `regwrite_m` | 1 | `ex_mem_reg` | `hazard_unit`、`mem_wb_reg` |
| 输出 | `memread_m` | 1 | `ex_mem_reg` | `hazard_unit`、`cpu_datapath` |
| 输出 | `memwrite_m` | 1 | `ex_mem_reg` | `cpu_datapath` |
| 输出 | `load_type_m` | 3 | `ex_mem_reg` | `lsu` 的 M 级实例、`cpu_datapath` |
| 输出 | `store_type_m` | 2 | `ex_mem_reg` | `lsu` 的 M 级实例、`cpu_datapath` |
| 输出 | `wb_sel_m` | 2 | `ex_mem_reg` | `mem_wb_reg`、`cpu_datapath` |

### 4.12 `mem_wb_reg`

| 方向 | 信号 | 位宽 | 来源硬件 | 去向硬件 |
|---|---|---:|---|---|
| 输入 | `clk` | 1 | `SoC 时钟硬件` | `mem_wb_reg` |
| 输入 | `rst_n` | 1 | `SoC 复位硬件` | `mem_wb_reg` |
| 输入 | `valid_m` | 1 | `ex_mem_reg` | `mem_wb_reg` |
| 输入 | `read_data_m` | 32 | `cpu_datapath` | `mem_wb_reg` |
| 输入 | `alu_result_m` | 32 | `ex_mem_reg` | `mem_wb_reg` |
| 输入 | `pc4_m` | 32 | `ex_mem_reg` | `mem_wb_reg` |
| 输入 | `rd_m` | 5 | `ex_mem_reg` | `mem_wb_reg` |
| 输入 | `regwrite_m` | 1 | `ex_mem_reg` | `mem_wb_reg` |
| 输入 | `wb_sel_m` | 2 | `ex_mem_reg` | `mem_wb_reg` |
| 输出 | `valid_w` | 1 | `mem_wb_reg` | `hazard_unit`、`cpu_datapath` |
| 输出 | `read_data_w` | 32 | `mem_wb_reg` | `cpu_datapath` |
| 输出 | `alu_result_w` | 32 | `mem_wb_reg` | `cpu_datapath` |
| 输出 | `pc4_w` | 32 | `mem_wb_reg` | `cpu_datapath` |
| 输出 | `rd_w` | 5 | `mem_wb_reg` | `hazard_unit`、`regfile`、`cpu_datapath` |
| 输出 | `regwrite_w` | 1 | `mem_wb_reg` | `hazard_unit`、`cpu_datapath` |
| 输出 | `wb_sel_w` | 2 | `mem_wb_reg` | `cpu_datapath` |

## 5. 连接层级使用原则

- 来源和去向只写本文件硬件清单中已有的真实模块名，或第 2.3 节明确列出的外部边界硬件。
- `cpu_control`、`cpu_datapath` 是真实 RTL 模块，因此可以作为来源或去向。
- 顶层中的组合逻辑属于所在顶层模块，不再额外命名为新的“硬件”。
- 同一个模块被实例化两次时，只用“E 级实例/M 级实例”区分，不引入新的硬件种类名称。
- `cpu_control_pkg.sv` 是常量和类型包，不生成独立硬件，因此不列入硬件清单。

## 6. 全部硬件的合并线束（唯一组号）

下表只按“来源硬件 → 去向硬件”分组：同一对有向硬件端点只画**一根示意线束**，在线旁标组号和总位宽，再由信号清单展开。全篇只有 001～085 这一套组号，不再把顶层端口和内部端口另分两套；第 3、4 节的原硬件、I/O、位宽及说明保持不变。`cpu_control` 和 `cpu_datapath` 是真实顶层模块，本表把其内部子模块与顶层自身的组合逻辑展开来画，因此已经由子模块表示的端口不再重复画一根顶层汇总线。

总位宽为本行所列原有信号位宽之和；括号中的端口别名不重复计数。固定值输入、原表注明未使用但仍列在本行的端口，也按原位宽计入，画实际电路时可按“未使用/常数”标注。线束只用于图面合并，**不是**把不同信号短接或改成新的 RTL 端口；同一信号扇出到多个硬件时会在多行出现。`address_decoder`、`lsu` 的 E/M 级是同一种硬件的不同实例。

### 6.1 全部线组

| 组号 | 一根线束（箭头方向） | 总位宽（bit） | 包含的原有信号 |
|---|---|---:|---|
| 001 | `SoC 时钟硬件` → `cpu_control` | 1 | `clk`（当前内部未使用） |
| 002 | `SoC 时钟硬件` → `pc` | 1 | `clk` |
| 003 | `SoC 时钟硬件` → `fetch_adapter` | 1 | `clk` |
| 004 | `SoC 时钟硬件` → `if_id_reg` | 1 | `clk` |
| 005 | `SoC 时钟硬件` → `regfile` | 1 | `clk` |
| 006 | `SoC 时钟硬件` → `id_ex_reg` | 1 | `clk` |
| 007 | `SoC 时钟硬件` → `ex_mem_reg` | 1 | `clk` |
| 008 | `SoC 时钟硬件` → `mem_wb_reg` | 1 | `clk` |
| 009 | `SoC 复位硬件` → `cpu_control` | 1 | `rst_n` |
| 010 | `SoC 复位硬件` → `pipeline_control` | 1 | `rst_n` |
| 011 | `SoC 复位硬件` → `cpu_datapath` | 1 | `rst_n` |
| 012 | `SoC 复位硬件` → `pc` | 1 | `rst_n` |
| 013 | `SoC 复位硬件` → `fetch_adapter` | 1 | `rst_n` |
| 014 | `SoC 复位硬件` → `if_id_reg` | 1 | `rst_n` |
| 015 | `SoC 复位硬件` → `regfile` | 1 | `rst_n` |
| 016 | `SoC 复位硬件` → `id_ex_reg` | 1 | `rst_n` |
| 017 | `SoC 复位硬件` → `ex_mem_reg` | 1 | `rst_n` |
| 018 | `SoC 复位硬件` → `mem_wb_reg` | 1 | `rst_n` |
| 019 | `if_id_reg` → `main_decoder` | 32 | `instr_d`（`instr_o`） |
| 020 | `if_id_reg` → `alu_decoder` | 17 | `instr_d` 的 `opcode`、`funct3`、`funct7` 字段 |
| 021 | `main_decoder` → `cpu_control` | 29 | `decoded`、`legal_main` |
| 022 | `alu_decoder` → `cpu_control` | 5 | `alu_decoded`、`legal_alu` |
| 023 | `if_id_reg` → `cpu_control` | 1 | `valid_d`（`valid_o`） |
| 024 | `if_id_reg` → `hazard_unit` | 1 | `valid_d`（`valid_o`） |
| 025 | `if_id_reg` → `imm_gen` | 32 | `instr_o`（端口 `instr`） |
| 026 | `if_id_reg` → `cpu_datapath` | 32 | `instr_o` |
| 027 | `if_id_reg` → `id_ex_reg` | 65 | `valid_o`（`valid_d`）、`pc_o`（`pc_d`）、`pc4_o`（`pc4_d`） |
| 028 | `cpu_control` → `hazard_unit` | 2 | `uses_rs1_d`、`uses_rs2_d` |
| 029 | `cpu_control` → `id_ex_reg` | 25 | `alu_ctrl`（`alu_ctrl_d`）、`alu_src_a_sel`（`alu_src_a_sel_d`）、`alu_src_b_sel`（`alu_src_b_sel_d`）、`regwrite_d`、`memread_d`、`memwrite_d`、`load_type_d`、`store_type_d`、`wb_sel_d`、`branch_type_d`、`jump_d`、`uses_rs1_d`、`uses_rs2_d` |
| 030 | `cpu_control` → `imm_gen` | 3 | `imm_type_d`（`imm_type`） |
| 031 | `hazard_unit` → `pipeline_control` | 1 | `load_use` |
| 032 | `hazard_unit` → `cpu_control` | 7 | `fwd_a`、`fwd_b`、`fwd_store`、`operand_unready`（后者当前内部未使用） |
| 033 | `branch_control` → `pipeline_control` | 3 | `redirect`、`redirect_sel` |
| 034 | `pipeline_control` → `cpu_datapath` | 2 | `pc_sel` |
| 035 | `pipeline_control` → `pc` | 1 | `pc_en` |
| 036 | `pipeline_control` → `fetch_adapter` | 3 | `pc_en`、`if_id_en`、`if_id_flush`（端口 `flush`） |
| 037 | `pipeline_control` → `if_id_reg` | 2 | `if_id_en`（端口 `en`）、`if_id_flush`（端口 `flush`） |
| 038 | `pipeline_control` → `id_ex_reg` | 1 | `id_ex_flush`（端口 `flush`） |
| 039 | `cpu_control` → `cpu_datapath` | 6 | `fwd_a`、`fwd_b`、`fwd_store`（经顶层复位限定） |
| 040 | `cpu_datapath` → `cpu_control` | 1 | `mul_busy`（固定为 0，当前内部未使用） |
| 041 | `cpu_datapath` → `hazard_unit` | 10 | `rs1_d`、`rs2_d` |
| 042 | `cpu_datapath` → `branch_control` | 3 | `cmp_eq_e`、`cmp_lt_e`、`cmp_ltu_e` |
| 043 | `cpu_datapath` → `pc` | 32 | `next_pc` |
| 044 | `pc` → `cpu_datapath` | 32 | `pc_q` |
| 045 | `pc` → `fetch_adapter` | 32 | `pc_q`（端口 `request_pc`） |
| 046 | `fetch_adapter` → `if_id_reg` | 97 | `fetch_valid`（`valid_i`）、`fetch_instr`（`instr_i`）、`fetch_pc`（`pc_i`）、`fetch_pc4`（`pc4_i`） |
| 047 | `fetch_adapter` → `同步 IMEM` | 33 | `imem_addr`、`imem_re` |
| 048 | `同步 IMEM` → `fetch_adapter` | 32 | `imem_rdata` |
| 049 | `cpu_datapath` → `regfile` | 43 | `rs1_d`（端口 `rs1`）、`rs2_d`（端口 `rs2`）、`we`、`wdata` |
| 050 | `mem_wb_reg` → `regfile` | 5 | `rd_w`（端口 `waddr`） |
| 051 | `regfile` → `id_ex_reg` | 64 | `rd1`（`rd1_d`）、`rd2`（`rd2_d`） |
| 052 | `imm_gen` → `id_ex_reg` | 32 | `imm_ext`（`imm_d`） |
| 053 | `cpu_datapath` → `id_ex_reg` | 15 | `rs1_d`、`rs2_d`、`rd_d` |
| 054 | `id_ex_reg` → `hazard_unit` | 19 | `valid_e`、`rs1_e`、`rs2_e`、`rd_e`、`uses_rs1_e`、`uses_rs2_e`、`memread_e` |
| 055 | `id_ex_reg` → `branch_control` | 6 | `valid_e`、`branch_type_e`、`jump_e` |
| 056 | `id_ex_reg` → `cpu_datapath` | 135 | `valid_e`、`pc_e`、`rd1_e`、`rd2_e`、`imm_e`、`alu_src_a_sel_e`、`alu_src_b_sel_e`、`memread_e`、`memwrite_e` |
| 057 | `id_ex_reg` → `alu` | 4 | `alu_ctrl_e`（端口 `alu_ctrl`） |
| 058 | `id_ex_reg` → `lsu` 的 E 级实例 | 5 | `load_type_e`（`load_type`）、`store_type_e`（`store_type`） |
| 059 | `id_ex_reg` → `ex_mem_reg` | 48 | `valid_e`、`pc4_e`、`rd_e`、`regwrite_e`、`memread_e`、`memwrite_e`、`load_type_e`、`store_type_e`、`wb_sel_e` |
| 060 | `cpu_datapath` → `alu` | 64 | `a`、`b` |
| 061 | `alu` → `cpu_datapath` | 1 | `zero`（当前内部未使用） |
| 062 | `alu` → `address_decoder` 的 E 级实例 | 32 | `result`（端口 `addr`） |
| 063 | `alu` → `lsu` 的 E 级实例 | 32 | `result`（端口 `addr`） |
| 064 | `alu` → `ex_mem_reg` | 32 | `result`（`alu_result_e`） |
| 065 | `alu` → `Data SRAM` | 32 | `result`（`dmem_addr`） |
| 066 | `address_decoder` 的 E 级实例 → `cpu_datapath` | 4 | `sram_hit`、`mmio_window_hit`（未使用）、`mmio_reg_hit`（未使用）、`unmapped`（未使用） |
| 067 | `address_decoder` 的 M 级实例 → `cpu_datapath` | 4 | `sram_hit`、`mmio_window_hit`（未使用）、`mmio_reg_hit`、`unmapped`（未使用） |
| 068 | `cpu_datapath` → `lsu` 的 E 级实例 | 64 | `store_data`、`read_word`（常数 0） |
| 069 | `lsu` 的 E 级实例 → `cpu_datapath` | 40 | `load_data`（未使用）、`load_aligned`、`load_type_valid`、`store_wstrb`、`store_aligned`、`store_type_valid` |
| 070 | `lsu` 的 E 级实例 → `Data SRAM` | 32 | `store_wdata`（`dmem_wdata`） |
| 071 | `lsu` 的 M 级实例 → `cpu_datapath` | 72 | `load_data`、`load_aligned`、`load_type_valid`、`store_wdata`（未使用）、`store_wstrb`（未使用）、`store_aligned`（未使用）、`store_type_valid`（未使用） |
| 072 | `Data SRAM` → `lsu` 的 M 级实例 | 32 | `dmem_rdata`（端口 `read_word`） |
| 073 | `cpu_datapath` → `Data SRAM` | 6 | `dmem_re`、`dmem_we`、`dmem_wstrb`（由 `store_wstrb` 限定） |
| 074 | `cpu_datapath` → `ex_mem_reg` | 32 | `write_data_e` |
| 075 | `ex_mem_reg` → `hazard_unit` | 8 | `valid_m`、`rd_m`、`regwrite_m`、`memread_m` |
| 076 | `ex_mem_reg` → `cpu_datapath` | 74 | `valid_m`、`alu_result_m`、`pc4_m`、`memread_m`、`memwrite_m`、`load_type_m`、`store_type_m`、`wb_sel_m` |
| 077 | `ex_mem_reg` → `address_decoder` 的 M 级实例 | 32 | `alu_result_m`（端口 `addr`） |
| 078 | `ex_mem_reg` → `lsu` 的 M 级实例 | 69 | `alu_result_m`（`addr`）、`write_data_m`（`store_data`）、`load_type_m`（`load_type`）、`store_type_m`（`store_type`） |
| 079 | `ex_mem_reg` → `mem_wb_reg` | 73 | `valid_m`、`alu_result_m`、`pc4_m`、`rd_m`、`regwrite_m`、`wb_sel_m` |
| 080 | `ex_mem_reg` → `CNN MMIO` | 64 | `alu_result_m`（`mmio_addr`）、`write_data_m`（`mmio_wdata`） |
| 081 | `cpu_datapath` → `CNN MMIO` | 2 | `mmio_re`、`mmio_we` |
| 082 | `CNN MMIO` → `cpu_datapath` | 33 | `mmio_rdata`、`mmio_ready` |
| 083 | `cpu_datapath` → `mem_wb_reg` | 32 | `read_data_m` |
| 084 | `mem_wb_reg` → `hazard_unit` | 7 | `valid_w`、`rd_w`、`regwrite_w` |
| 085 | `mem_wb_reg` → `cpu_datapath` | 105 | `valid_w`、`read_data_w`、`alu_result_w`、`pc4_w`、`rd_w`、`regwrite_w`、`wb_sel_w` |

### 6.2 每个硬件的输入/输出线组

下面的每个组号都能在 6.1 节查到方向、总位宽和完整信号。表中“无”只用于本图外部的时钟/复位源，不表示其他硬件缺少端口。

| 硬件 | 输入线组 | 输出线组 |
|---|---|---|
| `SoC 时钟硬件` | 无（本图外部信号源） | 001、002、003、004、005、006、007、008 |
| `SoC 复位硬件` | 无（本图外部信号源） | 009、010、011、012、013、014、015、016、017、018 |
| `cpu_control` | 001、009、021、022、023、032、040 | 028、029、030、039 |
| `main_decoder` | 019 | 021 |
| `alu_decoder` | 020 | 022 |
| `hazard_unit` | 024、028、041、054、075、084 | 031、032 |
| `branch_control` | 042、055 | 033 |
| `pipeline_control` | 010、031、033 | 034、035、036、037、038 |
| `cpu_datapath` | 011、026、034、039、044、056、061、066、067、069、071、076、082、085 | 040、041、042、043、049、053、060、068、073、074、081、083 |
| `pc` | 002、012、035、043 | 044、045 |
| `fetch_adapter` | 003、013、036、045、048 | 046、047 |
| `if_id_reg` | 004、014、037、046 | 019、020、023、024、025、026、027 |
| `regfile` | 005、015、049、050 | 051 |
| `imm_gen` | 025、030 | 052 |
| `id_ex_reg` | 006、016、027、029、038、051、052、053 | 054、055、056、057、058、059 |
| `alu` | 057、060 | 061、062、063、064、065 |
| `address_decoder` 的 E 级实例 | 062 | 066 |
| `address_decoder` 的 M 级实例 | 077 | 067 |
| `lsu` 的 E 级实例 | 058、063、068 | 069、070 |
| `lsu` 的 M 级实例 | 072、078 | 071 |
| `ex_mem_reg` | 007、017、059、064、074 | 075、076、077、078、079、080 |
| `mem_wb_reg` | 008、018、079、083 | 050、084、085 |
| `同步 IMEM` | 047 | 048 |
| `Data SRAM` | 065、070、073 | 072 |
| `CNN MMIO` | 080、081 | 082 |

`hazard_unit` 并非没有输入输出：输入线组为 024（来自 `if_id_reg`）、028（来自 `cpu_control`）、041（来自 `cpu_datapath`）、054（来自 `id_ex_reg`）、075（来自 `ex_mem_reg`）、084（来自 `mem_wb_reg`）；输出线组为 031（到 `pipeline_control`）和 032（到 `cpu_control`）。前递信号 `fwd_a`、`fwd_b`、`fwd_store` 由 032 进入 `cpu_control`，经顶层复位限定后由 039 送到 `cpu_datapath`，不是 `hazard_unit` 直接输出到 `cpu_datapath`。`operand_unready` 当前在 `cpu_control` 内部未使用，仍按原表保留。
