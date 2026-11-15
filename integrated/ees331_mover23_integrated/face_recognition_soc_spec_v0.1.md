# 32 位 CPU + CNN 人脸识别 SoC 设计规格书

| 项目 | 内容 |
|---|---|
| 文档编号 | `FACE-SOC-SPEC-001` |
| 版本 | `v0.1 — 开工前接口冻结草案` |
| 日期 | 2026-09-11 |
| 系统结构 | 32 位五级流水线 Harvard CPU + CNN 加速器 |
| RTL 语言 | SystemVerilog-2017（如工具不支持则统一退回 Verilog-2001） |
| 三个开发部分 | CPU Control、CPU Datapath、CNN Accelerator |
| 当前基准图 | `cpu_cnn_face_recognition_architecture_v2_fixed_io.svg` |

> 本文档的首要目的，是在三位负责人分别编写 RTL 前冻结模块边界。没有在“开工前必须共同确认”章节中确认的内容，不得由某一位负责人自行假设后写入接口。

---

## 1. 项目目标与范围

芯片接收已经存入数据存储器的输入图片，由 32 位 CPU 配置并启动 CNN 加速器。CNN 从数据存储器读取输入特征、权重和 bias，完成卷积网络运算，并将输出特征或分类结果写回指定地址。CPU 根据最终输出确定与人脸数据库对应的人员编号。

本版系统只划分为以下三个主要开发部分：

1. `CPU Control`：负责指令译码、流水线控制、冒险处理、转发和分支跳转控制。
2. `CPU Datapath`：负责 PC、IR、寄存器堆、ALU、流水寄存器、访存、CNN 寄存器映射和存储器连接。
3. `CNN Accelerator`：负责 DMA 搬运、卷积计算、bias、量化、激活、池化和结果写回。

### 1.1 本版不包含

- 操作系统、虚拟内存、Cache 和内存一致性协议。
- 多核处理器。
- 浮点运算单元。
- 动态改变 CNN 硬件端口。
- 未经三方确认的新指令或自定义握手信号。

---

## 2. 系统总体处理流程

1. 外部测试平台把程序写入指令存储器 `IMEM`。
2. 外部测试平台或 CPU 把图片、权重、bias 和人脸数据库写入数据 SRAM。
3. CPU 根据网络层配置依次写入：
   - `INPUT_ADDR`
   - `OUTPUT_ADDR`
   - `WEIGHT_ADDR`
   - `BIAS_ADDR`
   - `IMAGE_SIZE`
   - `CHANNELS`
   - `CNN_PARAM`
4. CPU 最后向 `CONTROL.start` 写 1，启动本层计算。
5. CNN 拉高 `STATUS.busy`，通过 DMA 读取输入、权重和 bias。
6. CNN 完成本层后，将结果写到 `OUTPUT_ADDR`。
7. CNN 清除 `busy`，置位 `done`；若出现越界、非法参数或存储器错误，则置位 `error`。
8. CPU 轮询 `STATUS`，发现 `done=1` 后配置下一层；下一层通常交换上一层的输入、输出缓冲区地址。
9. 最后一层结束后：
   - 闭集分类模式：CPU 从 `OUTPUT_ADDR` 读取各人员类别分数并执行 `argmax`；
   - 特征向量模式：CPU 从 `OUTPUT_ADDR` 读取 embedding，并与数据库特征做相似度匹配。

> 当前 CNN 固定接口没有 `DB_ADDR`、`RESULT_ID`、`SCORE`。因此数据库匹配不能被默认放在 CNN 内部，除非后续正式升级接口版本。

---

## 3. 三部分职责与禁止越界事项

### 3.1 CPU Control

#### 负责内容

- RISC-V 指令译码。
- 立即数类型、ALU 操作、Load/Store 类型和写回来源控制。
- 五级流水线的暂停、冲刷和使能控制。
- 数据冒险检测及 EX/MEM、MEM/WB 前递选择。
- 分支、跳转和 PC 选择控制。
- 多周期单元存在时的流水线等待控制。

#### 不负责内容

- 不实例化 PC、IR、寄存器堆、ALU 或存储器。
- 不直接保存 CNN 地址和参数寄存器。
- 不直接访问数据 SRAM。
- 不解释 CNN 内部的卷积计数器。
- 本版不直接接收 `STATUS`；CPU 通过普通 `LW` 指令读取状态。

### 3.2 CPU Datapath

#### 负责内容

- 32 位 PC 和 Next-PC MUX。
- 独立指令存储器接口，实现 Harvard 结构。
- `IF/ID`、`ID/EX`、`EX/MEM`、`MEM/WB` 流水寄存器。
- `IF/ID` 中的 32 位 IR。
- 32×32 位通用寄存器堆，`x0` 恒为 0。
- 立即数生成、32 位 ALU、分支比较和目标地址加法。
- Load/Store Unit、字节使能、符号扩展和地址译码。
- 数据 SRAM 的 CPU 端口。
- CNN I/O 寄存器组和地址映射。
- 把 8 个只写/读写寄存器稳定输出给 CNN，并把 CNN 的 `STATUS` 返回给 CPU。

#### 不负责内容

- 不自行决定指令含义或冒险策略。
- 不生成 CNN 的 `busy/done/error`。
- 不解释卷积参数并控制 CNN PE。
- 不改变 CNN 负责人确定的 9 个端口名和位宽。

### 3.3 CNN Accelerator

#### 负责内容

- 接收并锁存 9 个固定 32 位控制/状态接口。
- 根据四个基地址生成 DMA 访问地址。
- 输入特征、权重、bias 和输出特征的本地缓冲。
- 卷积/全连接 MAC 阵列。
- 空间、通道和卷积核循环控制。
- bias、定点量化、饱和、激活及约定的池化操作。
- 结果写回 `OUTPUT_ADDR`。
- `busy/done/error` 的生成和状态保持。
- 提供 CNN 单层和小网络的独立测试向量。

#### 不负责内容

- 不取指、不执行 CPU 指令。
- 不修改 CPU 的 PC 或流水寄存器。
- 不依赖未写入固定寄存器的隐含参数。
- 不默认包含人脸数据库匹配，除非接口版本正式增加数据库相关端口。

---

## 4. 公共时钟、复位和编码约定

| 项目 | v0.1 推荐值 | 必须确认事项 |
|---|---|---|
| 时钟 | 单一上升沿 `clk` | 目标频率和仿真周期 |
| 全局复位 | `rst_n`，低有效、建议同步释放 | 异步拉低/同步释放是否统一 |
| 软件复位 | `CONTROL[1]` | 仅复位 CNN 状态和内部计数器，不复位 CPU |
| 数据位宽 | CPU、地址、寄存器均为 32 位 | 不允许部分模块使用 64 位地址 |
| 字节序 | Little-endian | 三方测试文件必须一致 |
| 地址含义 | 32 位字节地址 | 所有地址必须至少 4 字节对齐 |
| 默认握手 | `valid/ready` 或本文指定的 `req/gnt` | 不得混用不同含义 |
| 保留位 | 写入时必须为 0，读取时返回 0 | 后续版本才能重新定义 |
| 复位值 | 除特别说明外均为 0 | 测试平台必须检查 |

---

## 5. CPU Control 与 CPU Datapath 接口

建议顶层模块名：

```systemverilog
cpu_control  u_cpu_control (...);
cpu_datapath u_cpu_datapath (...);
```

### 5.1 Datapath → Control

| 信号 | 位宽 | 来源器件 | 作用 |
|---|---:|---|---|
| `instr_d` | 32 | `IF/ID.IR` | ID 级当前指令，供主译码和 ALU 译码 |
| `rs1_d` | 5 | `IF/ID.IR[19:15]` | ID 级源寄存器 1 编号 |
| `rs2_d` | 5 | `IF/ID.IR[24:20]` | ID 级源寄存器 2 编号 |
| `rd_e` | 5 | `ID/EX` | EX 级目标寄存器，用于 load-use 冒险判断 |
| `rd_m` | 5 | `EX/MEM` | MEM 级目标寄存器，用于前递判断 |
| `rd_w` | 5 | `MEM/WB` | WB 级目标寄存器，用于前递判断 |
| `regwrite_m` | 1 | `EX/MEM` 控制字段 | MEM 级将写寄存器 |
| `regwrite_w` | 1 | `MEM/WB` 控制字段 | WB 级将写寄存器 |
| `memread_e` | 1 | `ID/EX` 控制字段 | EX 级为 Load 指令，用于检测 load-use 冒险 |
| `cmp_eq_e` | 1 | 分支比较器 | 两操作数相等 |
| `cmp_lt_e` | 1 | 有符号比较器 | 有符号小于 |
| `cmp_ltu_e` | 1 | 无符号比较器 | 无符号小于 |
| `mul_busy` | 1 | 可选乘法器 | 多周期乘法器仍在工作；未实现时固定为 0 |

### 5.2 Control → Datapath

| 信号 | 位宽 | 直接连接器件 | 作用 |
|---|---:|---|---|
| `pc_sel` | 2 | Next-PC MUX | `00=PC+4`，`01=branch_target`，`10=JALR_target` |
| `pc_en` | 1 | PC 寄存器使能 | 0 时保持 PC |
| `if_id_en` | 1 | `IF/ID` 写使能 | 冒险暂停时保持 IF/ID |
| `if_id_flush` | 1 | `IF/ID` 清零端 | 分支跳转成立时清除错误指令 |
| `id_ex_flush` | 1 | `ID/EX` 清零端 | 插入气泡或冲刷 EX 前级指令 |
| `alu_ctrl` | 4 | ALU 操作控制端 | ADD/SUB/AND/OR/XOR/SLT/移位等 |
| `alu_src_a_sel` | 2 | ALU A 端 MUX | 选择寄存器、PC 或前递值 |
| `alu_src_b_sel` | 2 | ALU B 端 MUX | 选择寄存器、立即数或前递值 |
| `fwd_a` | 2 | EX 操作数 A 前递 MUX | 原始值、MEM 前递或 WB 前递 |
| `fwd_b` | 2 | EX 操作数 B 前递 MUX | 原始值、MEM 前递或 WB 前递 |
| `fwd_store` | 2 | Store 数据前递 MUX | 保证连续计算后立即 Store 正确 |
| `regwrite_d` | 1 | 随指令进入流水寄存器 | 该指令最终是否写寄存器堆 |
| `memread_d` | 1 | 随指令进入流水寄存器 | 该指令是否读取数据存储器 |
| `memwrite_d` | 1 | 随指令进入流水寄存器 | 该指令是否写数据存储器 |
| `load_type_d` | 3 | LSU | LB/LH/LW/LBU/LHU 类型 |
| `store_type_d` | 2 | LSU | SB/SH/SW 类型 |
| `wb_sel_d` | 2 | WB MUX | ALU 结果、Load 数据或 PC+4 |
| `branch_type_d` | 3 | 分支控制器 | BEQ/BNE/BLT/BGE/BLTU/BGEU |
| `jump_d` | 2 | PC 控制器 | 无跳转、JAL、JALR |

### 5.3 Control—Datapath 时序要求

- 所有 ID 级译码控制信号必须与 `instr_d` 在同一个周期有效。
- 需要传到 EX/MEM/WB 的控制信号由 Datapath 放入相应流水寄存器。
- `flush` 的优先级高于 `enable`；复位优先级最高。
- 前递只改变 MUX 选择，不修改寄存器堆内容。
- 分支最终在哪一级判定必须冻结。本规格推荐 EX 级判定，跳转成立时冲刷 IF/ID 和 ID/EX。

---

## 6. CPU Datapath 与 CNN 固定接口

CNN 负责人提供的接口作为本版强制标准。所有信号均为 32 位。

### 6.1 CPU 侧推荐地址映射

| CPU 地址偏移 | 接口名 | 方向（相对CNN） | 属性 | 位定义与用途 | CNN 内部最终连接器件 |
|---:|---|---|---|---|---|
| `0x00` | `CONTROL[31:0]` | 输入 | W1P | `[0]=start`，`[1]=soft_reset`，其余保留 | Command Decoder / Scheduler |
| `0x04` | `STATUS[31:0]` | 输出 | RO | `[0]=busy`，`[1]=done`，`[2]=error`，其余保留 | Status Encoder |
| `0x08` | `INPUT_ADDR[31:0]` | 输入 | RW | 输入图片或输入特征图首地址 | DMA input address counter |
| `0x0C` | `OUTPUT_ADDR[31:0]` | 输入 | RW | 输出特征图或最终结果首地址 | DMA output address counter |
| `0x10` | `WEIGHT_ADDR[31:0]` | 输入 | RW | 当前层权重首地址 | DMA weight address counter |
| `0x14` | `BIAS_ADDR[31:0]` | 输入 | RW | 当前层 bias 首地址 | DMA bias address counter |
| `0x18` | `IMAGE_SIZE[31:0]` | 输入 | RW | `[31:16]=height`，`[15:0]=width` | Spatial / border loop controller |
| `0x1C` | `CHANNELS[31:0]` | 输入 | RW | `[31:16]=output_channels`，`[15:0]=input_channels` | Channel / tile loop controller |
| `0x20` | `CNN_PARAM[31:0]` | 输入 | RW | kernel、stride、padding、quant_shift 等 | PE mode and quantization controller |

说明：

- 表中的地址偏移是 CPU 侧推荐内存映射，必须在开工会议中签字确认。
- CNN 顶层只看到这 9 条固定信号，不需要理解 CPU 的地址译码过程。
- `CONTROL.start` 推荐定义为“写 1 产生一个时钟周期脉冲”，防止寄存器保持为 1 时重复启动。
- `STATUS.done` 推荐为粘滞位：完成后保持 1，直到下一次 `start` 或 `soft_reset`。
- `STATUS.error` 推荐为粘滞位，并在下一次启动或复位时清零。
- CPU 必须先写完全部参数，最后再写 `start`。
- CNN 在 `busy=1` 时不得接受新的 `start`。若收到，可忽略并置 `error`，具体策略需冻结。

### 6.2 `CNN_PARAM` 推荐位域

原始接口只说明其包含 kernel、stride、padding、quant_shift，尚未给出确切位域。以下为推荐草案，必须由 CNN 负责人确认后才能冻结：

| 位 | 字段 | 建议含义 |
|---|---|---|
| `[3:0]` | `kernel_size` | 1、3、5、7 等卷积核边长 |
| `[7:4]` | `stride` | 1 或 2 |
| `[11:8]` | `padding` | 每侧补零数量 |
| `[16:12]` | `quant_shift` | 定点缩放右移位数，0～31 |
| `[18:17]` | `activation` | 0=None，1=ReLU，2=ReLU6 |
| `[20:19]` | `pool_mode` | 0=None，1=MaxPool，2=AvgPool |
| `[23:21]` | `op_type` | 0=Conv，1=Depthwise，2=FC |
| `[31:24]` | `reserved` | 本版写 0、读 0 |

---

## 7. CNN 与数据 SRAM 接口

9 个固定寄存器只能传递地址和参数，不能传递实际张量。因此 CNN 必须另有一组数据存储器主接口。这组接口不是 CPU—CNN 控制寄存器的一部分，但它是 CNN 顶层正常工作的必要接口。

本版推荐使用双口 SRAM：CPU 固定使用 A 口，CNN DMA 固定使用 B 口，不设置总线仲裁。

### 7.1 CNN → Data SRAM

| 信号 | 位宽 | 作用 |
|---|---:|---|
| `cnn_mem_req` | 1 | 发起一次存储器访问 |
| `cnn_mem_we` | 1 | 1=写，0=读 |
| `cnn_mem_addr` | 32 | 字节地址，必须 4 字节对齐 |
| `cnn_mem_wdata` | 32 | 写数据 |
| `cnn_mem_be` | 4 | 每个字节的写使能 |

### 7.2 Data SRAM → CNN

| 信号 | 位宽 | 作用 |
|---|---:|---|
| `cnn_mem_gnt` | 1 | SRAM 接受本次请求 |
| `cnn_mem_rvalid` | 1 | 读数据有效 |
| `cnn_mem_rdata` | 32 | 读返回数据 |
| `cnn_mem_error` | 1 | 地址越界或访问错误；不实现时固定为 0 |

### 7.3 推荐时序

- CNN 保持 `req`、地址和控制信号，直到看到 `gnt=1`。
- 写事务在 `req && gnt && we` 时完成。
- 读事务在 `req && gnt && !we` 时被接受，数据随后通过 `rvalid` 返回。
- v0.1 建议限制为最多一个未完成读请求，先保证功能正确。
- SRAM 的确切读延迟必须在开工前确定。推荐仿真模型固定为 1 个周期。
- 如果 FPGA BRAM 只能同步读取，CPU 和 CNN 测试模型必须使用同样的延迟。

---

## 8. 开工前必须共同确定的 ISA

### 8.1 推荐基础方案

推荐使用标准 RISC-V `RV32I`，避免自定义一套指令编码。第一阶段不实现特权级、CSR、Cache、压缩指令和原子指令。

#### 必须实现的 RV32I 指令

| 类别 | 指令 |
|---|---|
| U 型 | `LUI`、`AUIPC` |
| 跳转 | `JAL`、`JALR` |
| 分支 | `BEQ`、`BNE`、`BLT`、`BGE`、`BLTU`、`BGEU` |
| Load | `LB`、`LH`、`LW`、`LBU`、`LHU` |
| Store | `SB`、`SH`、`SW` |
| 立即数运算 | `ADDI`、`SLTI`、`SLTIU`、`XORI`、`ORI`、`ANDI`、`SLLI`、`SRLI`、`SRAI` |
| 寄存器运算 | `ADD`、`SUB`、`SLL`、`SLT`、`SLTU`、`XOR`、`SRL`、`SRA`、`OR`、`AND` |

`FENCE`、`ECALL`、`EBREAK` 在裸机仿真中可先定义为 NOP 或进入统一异常状态，但三方必须统一，不能一部分按 NOP、一部分按异常处理。

### 8.2 乘法扩展决策

在开工前必须确定最终识别方式：

- 若 CNN 最后输出“已知人员分类分数”，CPU 只需要执行 `argmax`，RV32I 即可。
- 若 CNN 输出人脸 embedding，CPU 要与数据库做点积或余弦相似度，建议增加硬件 `MUL`。此时应选择完整 `RV32M`、标准 `Zmmul`，或明确只用软件乘法，不能只写一个没有工具链约定的私有 `MUL`。

v0.1 推荐：先完成 RV32I；同时在 Datapath 中预留多周期乘法器的 stall 接口。接口联调完成后再决定是否加入 `Zmmul/RV32M`。

### 8.3 CPU 必须统一的行为

- PC 初值和复位向量，例如 `0x0000_0000`。
- 未对齐取指、Load 和 Store 是报错还是不支持。
- 非法指令是停机、进入 trap，还是作为 NOP。
- 分支在哪一级判定；本规格推荐 EX 级。
- Load-use 暂停几个周期；1 周期 SRAM 时推荐至少插入 1 个气泡。
- 是否实现乘法以及多周期单元如何暂停流水线。
- 程序如何结束；推荐测试平台监测固定 `tohost` 地址，而不是依赖无限循环。

---

## 9. 开工前必须冻结的数据格式

| 项目 | v0.1 推荐值 | 说明 |
|---|---|---|
| 输入激活 | signed int8 | 四个元素打包进一个 32 位 SRAM 字 |
| 权重 | signed int8 | 四个权重打包进一个 32 位 SRAM 字 |
| bias | signed int32 | 每个输出通道一个 bias |
| MAC 累加 | signed int32 | 防止 int8 乘加快速溢出 |
| 输出激活 | signed int8，饱和截断 | 最终范围 `[-128,127]` |
| 张量布局 | HWC，C 最内层连续 | 必须与模型导出脚本一致 |
| 权重布局 | OHWI，I 最内层连续 | 输出通道、核高、核宽、输入通道 |
| 像素颜色顺序 | RGB 或灰度二选一 | 必须与训练模型一致 |
| 量化公式 | `sat_int8((acc+bias) >>> quant_shift)` | 激活/池化顺序必须确认 |
| 地址对齐 | 4 字节 | 输入不足 4 字节时的填充规则需一致 |

三方必须共同提供至少一个手算可验证的小例子，例如：`4×4×1` 输入、`3×3×1` 权重、stride=1、padding=0，并明确每一个字节在 SRAM 中的位置。

---

## 10. 三位负责人分别要交付什么

### 10.1 CPU Control 负责人交付物

- `rtl/cpu_control/main_decoder.sv`
- `rtl/cpu_control/alu_decoder.sv`
- `rtl/cpu_control/hazard_unit.sv`
- `rtl/cpu_control/branch_control.sv`
- `rtl/cpu_control/cpu_control.sv`
- 完整指令译码表：opcode、funct3、funct7 与控制输出对应关系。
- 冒险和前递规则表。
- Control 模块端口声明文件。
- 独立测试平台，至少覆盖：
  - 每条指令的译码；
  - EX/MEM、MEM/WB 前递；
  - load-use 暂停；
  - taken/not-taken 分支；
  - JAL/JALR 冲刷。
- 波形截图或自动化测试结果。

### 10.2 CPU Datapath 负责人交付物

- `rtl/cpu_datapath/pc.sv`
- `rtl/cpu_datapath/regfile.sv`
- `rtl/cpu_datapath/imm_gen.sv`
- `rtl/cpu_datapath/alu.sv`
- 四级流水寄存器模块。
- `rtl/cpu_datapath/lsu.sv`
- `rtl/cpu_datapath/cnn_reg_bank.sv`
- `rtl/cpu_datapath/cpu_datapath.sv`
- IMEM、Data SRAM 仿真模型或统一 wrapper。
- CNN 寄存器地址译码表。
- 独立测试平台，至少覆盖：
  - PC+4、branch、JAL、JALR；
  - x0 恒零；
  - ALU 边界值；
  - LB/LH/LW/LBU/LHU 与 SB/SH/SW；
  - 9 个 CNN 寄存器的读写；
  - `CONTROL.start` 单周期脉冲；
  - `STATUS` 只读回传。

### 10.3 CNN 负责人交付物

- `rtl/cnn/cnn_accel.sv` 顶层，严格使用冻结后的端口。
- `rtl/cnn/cnn_scheduler.sv`
- `rtl/cnn/cnn_dma.sv`
- 输入、权重、bias 和输出 Buffer。
- PE/MAC 阵列。
- 卷积循环控制、量化、激活及池化模块。
- 9 个寄存器的完整位域说明和复位行为。
- SRAM 主接口时序说明。
- 独立测试平台，至少覆盖：
  - reset/start/busy/done/error 状态转换；
  - 四个地址分别产生正确访问；
  - 不同 H/W、Cin/Cout；
  - kernel、stride、padding、quant_shift；
  - 写回地址和输出数值；
  - 非法参数或地址错误。
- 与 Python/Numpy 黄金模型逐元素对比的测试结果。

---

## 11. 三部分互相要交付什么

### 11.1 Control → Datapath

- 最终版控制信号端口声明。
- 每条指令对应的控制字。
- stall、flush 和 forward 的优先级。
- 可直接实例化的 `cpu_control` 模块及最小 testbench。

### 11.2 Datapath → Control

- `instr_d`、寄存器编号、比较结果和各流水级写回信息。
- 各反馈信号在哪个周期有效的时序图。
- 流水寄存器清零、保持、更新的统一优先级。

### 11.3 Datapath → CNN

- 8 个 CNN 输入端口的稳定寄存器值。
- `CONTROL.start/reset` 的单周期脉冲。
- CNN 可使用的数据 SRAM B 端口或等效 SRAM 模型。
- 清晰的数据内存地址空间分配。

### 11.4 CNN → Datapath

- `STATUS[31:0]` 的精确位定义和时序。
- DMA 请求/响应端口及访问时序。
- 写入 `OUTPUT_ADDR` 的数据长度、布局和完成时刻。
- CNN 独立仿真中使用的内存初始化文件和期望输出。

### 11.5 三方共同交付

- `rtl/common/soc_pkg.sv`：共同参数、枚举、地址和位域定义。
- `rtl/top/face_soc_top.sv`：只做模块实例化与连线，不在顶层加入业务逻辑。
- `tb/models/imem_model.sv`、`tb/models/dsram_model.sv`。
- 一套可重复运行的仿真脚本。
- 一张最终冻结的接口图。
- 一份接口冻结签字表和变更记录。

---

## 12. 推荐工程目录

```text
face_recognition_soc/
├── docs/
│   ├── FACE_SOC_SPEC.md
│   ├── interface_freeze.md
│   └── architecture.svg
├── rtl/
│   ├── common/soc_pkg.sv
│   ├── cpu_control/
│   ├── cpu_datapath/
│   ├── cnn/
│   ├── memory/
│   └── top/face_soc_top.sv
├── tb/
│   ├── unit/
│   ├── integration/
│   ├── models/
│   └── vectors/
├── sw/
│   ├── startup/
│   ├── drivers/cnn_driver.c
│   └── tests/
└── scripts/
    ├── run_unit_tests.*
    └── run_soc_test.*
```

---

## 13. 联调顺序与验收条件

### 阶段 A：接口冻结

- 三方确认所有端口名、方向、位宽、复位值和时序。
- 确认 RV32I 指令清单。
- 确认 CNN_PARAM 位域。
- 确认 SRAM 延迟和数据布局。
- 此阶段结束后创建 `interface-v1.0` 标签。

### 阶段 B：使用 Stub 并行开发

- Datapath 负责人提供 CNN stub：收到 start 后若干周期置 done。
- CNN 负责人使用 SRAM model，不等待完整 CPU。
- Control 负责人使用简化 Datapath stub 验证译码与冒险。

### 阶段 C：CPU 内部联调

- 运行 RV32I 指令程序。
- 验证数据冒险、控制冒险、Load/Store 和 CNN 寄存器映射。
- 所有测试自动比较寄存器或内存结果，不能只看波形判断。

### 阶段 D：CPU—CNN 接口联调

- CPU 写入 8 个输入寄存器。
- 检查 CNN 在 start 前不访问 SRAM。
- start 后检查 busy 和四类 DMA 地址。
- 完成后检查 OUTPUT_ADDR 内容与 done 状态。

### 阶段 E：端到端验收

- 使用一个极小 CNN 层逐元素对比黄金模型。
- 使用完整人脸模型进行至少一张图片仿真。
- 输出人员 ID 或匹配结果。
- 仿真中不得出现未知态 `X/Z` 扩散。
- 给出总周期数、CNN 周期数、CPU 等待周期数和 SRAM 访问次数。

---

## 14. 开工会议必须逐项确认的清单

- [ ] CPU ISA 采用 RV32I，是否增加 Zmmul/RV32M。
- [ ] 最终识别采用闭集分类还是 embedding 数据库匹配。
- [ ] PC 复位地址。
- [ ] 分支判定级和冲刷级数。
- [ ] IMEM、Data SRAM 容量及读取延迟。
- [ ] CNN 是否只允许一个未完成 DMA 请求。
- [ ] 9 个 CNN 寄存器的地址偏移。
- [ ] CONTROL 和 STATUS 每一位的语义。
- [ ] CNN_PARAM 的最终位域。
- [ ] 输入像素格式：RGB/BGR/灰度、取值范围和归一化方法。
- [ ] 激活张量布局 HWC/NCHW。
- [ ] 权重布局及打包顺序。
- [ ] int8 有符号规则、bias 位宽、累加位宽和饱和规则。
- [ ] padding、stride、pooling 的边界行为。
- [ ] `OUTPUT_ADDR` 输出的是中间特征、embedding 还是类别分数。
- [ ] done/error 清除条件。
- [ ] 非法 start、非法参数和地址越界的处理。
- [ ] SystemVerilog/Verilog 版本及仿真工具版本。
- [ ] 顶层模块名、端口命名规则和文件目录。
- [ ] 单元测试与集成测试的负责人及交付日期。

---

## 15. 接口变更规则

1. 接口冻结后，任何人不得直接修改端口名、方向、位宽或位域。
2. 变更必须在 `interface_change_log.md` 中说明原因、影响模块和迁移方法。
3. Control、Datapath、CNN 三方负责人全部同意后才能升级版本。
4. 只修改模块内部实现、不影响外部行为时，不需要升级接口版本。
5. 接口不兼容变更升级主版本，例如 `v1.x → v2.0`；增加向后兼容字段升级次版本。

---

## 16. v0.1 推荐冻结结论

若团队希望立即开工，建议暂时采用以下统一结论：

- CPU：RV32I、五级流水线、EX 级判定分支。
- 存储结构：独立 IMEM + 双口 Data SRAM，读取延迟固定 1 周期。
- CNN 控制接口：严格采用 9 个 32 位端口。
- CNN 数据接口：单请求、最多一个未完成读事务。
- 数据格式：signed int8 激活/权重、signed int32 bias/accumulator、HWC 布局。
- 控制：start 为单周期脉冲，busy 为电平，done/error 为粘滞位。
- 第一步验收：先完成单层卷积，不立即运行完整人脸网络。
- 识别路径：接口联调阶段使用闭集分类/argmax；embedding 匹配和乘法扩展作为下一阶段。

三方对第 14 节逐项确认后，将本文档版本升级为 `v1.0 — Interface Frozen`，再正式开始 RTL 开发。
