# CPU 数据流动说明（小白版）

更新：2026-10-08。按本工程当前 `cpu_core + cpu_control + cpu_datapath` 实际代码说明，不是照搬通用 CPU 示意图。本次只新增说明，不修改 RTL。

## 1. 先用一句话理解 CPU

**CPU 从 IEM 取出指令，看懂要做什么，从寄存器拿数，执行运算或访问存储器，最后把需要保留的结果写回寄存器。**

例如 `ADD x3, x1, x2` 的意思是：把 x1 和 x2 里的数相加，结果放进 x3。
CPU 执行的其实是这条指令对应的 32 位机器码，不是直接读懂字母 `ADD`。

先分清这三种东西：

| 名称 | 例子 | 是什么，不是什么 |
|---|---|---|
| 寄存器编号 | x1、x2、x3 | CPU 内部 32 个寄存器中的编号，不是内存地址；选择一个寄存器用 5 位编号 |
| 地址 | 0x1000 | 指定存储位置的门牌号，通常用 32 位表示；不是这个位置保存的内容 |
| 数据 | 7、10、17 | 真正参与计算、被写入或读出的内容，CPU 的通用寄存器每个保存 32 位 |

`0x` 开头表示十六进制。32 位等于 4 个字节，地址增加 1 表示下一个字节。
因此，一条本工程支持的 32 位指令占 4 个字节，顺序执行时 PC 通常加 4，不是加 1。

## 2. 数据到底存在哪里

| 部件 | 在 CPU 内部吗 | 保存或处理什么 |
|---|---|---|
| PC（程序计数器） | 是 | 当前取指地址，不保存整段程序 |
| regfile（寄存器堆） | 是 | x0～x31，保存计算时常用的数；x0 读出来永远是 0 |
| 流水寄存器 | 是 | 暂存各阶段的操作数、结果、目标寄存器编号和控制信息 |
| ALU（算术逻辑单元） | 是 | 做加减、逻辑、移位等运算，本身不是长期保存数据的仓库 |
| IEM / IMEM（imem_rom） | 否，与 CPU 平级 | 保存 CPU 程序指令 |
| datasram | 否，与 CPU 平级 | 保存普通数据、图像、权重、任务描述符和结果等 |
| CNN 自带寄存器 | 否，在 CNN 内 | 保存 CNN 配置和状态，通过 MMIO 访问 |

**CPU 内部确实有寄存器，但它们不是之前图里那块共享 datasram。**
IEM 和 datasram 都不在 cpu_core 内部。两者默认地址都可以从 0 开始，因为取指口和数据口是两条独立通路，不会因为地址数字相同就自动读错存储器。

## 3. 先看两张简图

### 3.1 CPU 与外部模块

```text
IEM 中的程序 ------ 指令 ------> cpu_core
                                  |
                                  +---- 普通读写 ----> datasram A 口
                                  |<--- 读回数据 -----+
                                  |
                                  +---- MMIO读写 ----> CNN 自带寄存器
                                  |<--- 状态/配置 ----+

CNN 运算需要的数据：CNN <-------> datasram B 口
电脑上传/读回的数据：UART <----> image_bridge <----> datasram B 口
```

CNN 和图像桥共用 B 口，仲裁在 datasram 内部。**这两条数据路径不经过 CPU 的 ALU，也不经过 CPU 寄存器堆。**
clock_unit 给所有模块提供公共时钟和复位；它不搬运图像或运算数据。

### 3.2 CPU 内部主要数据路径

```text
PC -> fetch_adapter -> IEM -> fetch_adapter -> IF/ID
                                                 |
                                                 v
                                      指令译码 + 读寄存器
                                      + 提取立即数
                                                 |
                                                 v
                                              ID/EX
                                                 |
                                                 v
                                      前递选择 -> ALU/比较
                                                 |
                      +--------------------------+------------------+
                      |                          |                  |
                      v                          v                  v
              SRAM 地址与写数据               EX/MEM          分支/跳转新 PC
              在 EX 末尾提交                      |                  |
                      |                          v                  +--> PC
                      +-- SRAM 读返回 --> MEM 级选数据/访问 MMIO
                                                 |
                                                 v
                                              MEM/WB
                                                 |
                                                 v
                                          选择最终写回值
                                                 |
                                                 v
                                         regfile 的目标寄存器
```

这张图是数据路线，不是“所有指令都要读写 SRAM”的意思。加法指令经过流水线时，内存读写开关是关闭的。

图中的 `fetch_adapter` 是 CPU 原本就有的同步取指配对和缓冲逻辑，位于 cpu_datapath 内部；**不是已经取消的 CNN 存储适配器，也不是新加的第七个 SoC 大模块。**

## 4. 五个阶段分别做什么

先把流水线理解为五个工作位置：不同指令可以同时在不同位置工作。

| 阶段 | 小白解释 | 本工程主要动作 |
|---|---|---|
| IF：取指 | 取出下一条任务 | PC 给出地址，从同步 IEM 取指，fetch_adapter 保存并配对指令与它的 PC |
| ID：译码 | 看任务、准备原料 | Control 识别指令；regfile 读两个寄存器；imm_gen 提取指令中自带的常数 |
| EX：执行 | 算结果或算地址 | 选取最新操作数；ALU 运算；判断分支；产生 SRAM 访问地址和写数据 |
| MEM：访存相关处理 | 接收或选择外部返回 | 处理 SRAM 返回字；必要时访问 CNN MMIO；非访存指令把结果继续向后传 |
| WB：写回 | 把结果放回 CPU | 在 ALU 结果、读返回、PC+4 中选择一种，写入目标寄存器 |

**本工程特别注意：SRAM 在 EX 结束、进入 MEM 的上升沿接收请求；MMIO 在 MEM 阶段发起。不能把两者都写成“到了 MEM 才发出请求”。**

IF/ID、ID/EX、EX/MEM、MEM/WB 是相邻阶段之间的“暂存格”。它们保存的不仅是一个数，还包括“结果要写给谁”“是否要读内存”等信息，防止不同指令混在一起。

时钟上升沿可以理解为暂存格接收新内容的时刻。ALU、译码和选择逻辑会在两个时钟沿之间计算；不是所有电线上的数都只在上升沿才变化。
这是五级逻辑分工，不代表从外部取指请求到写回永远恰好五拍：同步取指缓冲、暂停、分支冲刷都会影响实际时间。

## 5. 例子一：ADD 的两个数怎么流动

假设 x1 里是 7，x2 里是 10，执行：

```asm
ADD x3, x1, x2
```

这条指令就是 `x3 = x1 + x2`。

1. **取指**：PC 通过 `imem_addr[31:0]` 给出程序地址，拉高 `imem_re`；IEM 返回 `imem_rdata[31:0]`，也就是 ADD 的机器码。
2. **译码**：从机器码提取 `rs1=1`、`rs2=2`、`rd=3`。这里的 1、2、3 都是寄存器编号，还不是 7、10、17。
3. **读寄存器**：regfile 根据编号读出 x1 的值 7、x2 的值 10。Control 告诉 Datapath：“ALU 做加法；结果要写回；不用访问内存。”
4. **执行**：操作数经过前递选择，再送进 ALU，得到 `7 + 10 = 17`。
5. **向后传**：17 和“目标是 x3”等信息依次进入 EX/MEM、MEM/WB。ADD 不读写 datasram，不访问 CNN。
6. **写回**：写回选择器选择 ALU 结果。WB 阶段结束的上升沿，把 17 写入 regfile 的 x3。

```text
x1 的值 7 ----+
              +--> ALU 加法 --> 17 --> 流水寄存器 --> 写回选择 --> x3
x2 的值 10 ---+
```

实际内部信号可对照：

```text
rd1_d / rd2_d
    -> rd1_e / rd2_e
    -> src1_fwd_e / src2_fwd_e
    -> alu_a_e / alu_b_e
    -> alu_result_e -> alu_result_m -> alu_result_w
    -> wb_data_w -> regfile
```

名字后缀 `_d / _e / _m / _w` 分别表示 ID、EX、MEM、WB 阶段，不是四个不同 CPU。

## 6. 例子二：LW 从 SRAM 取数

假设 x10 里是地址 `0x1000`，datasram 的这个地址保存一个 32 位数 15，执行：

```asm
LW x5, 0(x10)
```

意思是：到 `x10 + 0` 指向的位置取一个 32 位字，放进 x5。

1. ID 阶段读到 x10 的内容 `0x1000`，imm_gen 提取偏移量 0。
2. EX 阶段 ALU 计算地址 `0x1000 + 0 = 0x1000`。**此时 ALU 算的是地址，不是从内存读出的 15。**
3. address_decoder 判断这是 SRAM 地址；LSU 检查读类型和对齐。合法后输出 `dmem_addr=0x1000`、`dmem_re=1`，不拉高 dmem_we。
4. EX→MEM 的上升沿，datasram A 口接收读地址，沿后 `dmem_rdata` 给出对应的 32 位数据。
5. MEM 阶段 LSU 处理这个返回字。对 LW，整个字就是需要的数据 15；到 MEM→WB 的上升沿，把读结果存入 MEM/WB。
6. WB 选择读回数据而不是 ALU 算出的地址，把 15 写入 x5。

```text
x10 = 0x1000 -> ALU 加偏移 0 -> 地址 0x1000 -> datasram A
                                                               |
x5 <- 写回选择 <- MEM/WB <- LSU <- dmem_rdata = 15 <-------------+
```

这一笔访问的三组线：

| 线组 | 来源 → 去向 | 具体内容 |
|---|---|---|
| 地址 | CPU → datasram | dmem_addr[31:0]，32 位，值为 0x1000 |
| 数据 | datasram → CPU | dmem_rdata[31:0]，32 位，值为 15 |
| 信号 | CPU → datasram | dmem_re=1、dmem_we=0，各 1 位；dmem_wstrb[3:0]=0 |

CPU A 口是固定一拍同步读，没有 dmem_ready；不是 CPU 一直等到有人拉高 ready 才向后执行。
LB/LBU 只取返回字中的一个字节，LH/LHU 取半字，然后按指令决定符号扩展或补零；这些处理在 LSU 内。

## 7. 例子三：SW 把数存入 SRAM

假设 x10 仍为 `0x1000`，x3 为 17，执行：

```asm
SW x3, 4(x10)
```

意思是：把 x3 的 17 放进地址 `0x1004` 的一个 32 位字。

这里有两条不同的数据路线，千万不要混：

```text
地址路线：x10 = 0x1000 + 指令中的偏移 4 -> ALU -> 地址 0x1004
内容路线：x3 = 17 -> Store 前递选择 -> LSU -> 待写数据 17
```

ALU 不会把“17 加 4”当作写入值。它负责算地址；真正要保存的内容从另一路送到 SRAM。

| 线组 | 来源 → 去向 | 具体内容 |
|---|---|---|
| 地址 | CPU → datasram | dmem_addr[31:0]=0x1004，32 位 |
| 数据 | CPU → datasram | dmem_wdata[31:0]=17，32 位 |
| 信号 | CPU → datasram | dmem_we=1、dmem_re=0，各 1 位；dmem_wstrb[3:0]=1111，4 位 |

`1111` 表示四个字节都写。SB 只打开一个字节，SH 打开两个字节，LSU 同时把数据摆到对应的字节位置。
写入发生在 **EX→MEM 的上升沿**。SW 不产生需要写回通用寄存器的结果，后面不会把地址或数据再写进 x3；x3 只是被读取。

## 8. CPU 怎样控制 CNN：还是用读写指令，但走 MMIO

MMIO 可以理解为：“把某些地址指定成设备的控制按钮和状态窗口。”
同样是一条 LW 或 SW，地址不同，最终去向就不同；不是额外增加一套 CNN 专用 CPU 指令。

| 地址例子（默认配置） | 到哪里 | 含义 |
|---|---|---|
| 0x00001000 | datasram | 普通数据位置 |
| 0x40000000 | CNN CONTROL 寄存器 | 写控制命令 |
| 0x40000004 | CNN STATUS 寄存器 | 读运行状态 |
| 0x40000008 | CNN QUEUE_BASE 寄存器 | 写任务描述符队列的起始地址 |
| 0x40000018 | CNN TASK_COUNT 寄存器 | 写任务数量 |

这里只列常用地址；不是 MMIO 窗口内每个地址都可以任意访问。当前 CPU 对 CNN MMIO 使用合法、4 字节对齐的 LW/SW，不用 SB/SH 写这些寄存器。

**写 CNN 配置时：**

```text
CPU 源寄存器中的配置值
    -> Store 前递
    -> EX/MEM 的 write_data_m
    -> mmio_wdata[31:0]
    -> CNN 内部 accelerator_regs

ALU 算出的寄存器地址
    -> EX/MEM 的 alu_result_m
    -> mmio_addr[31:0]
```

MEM 阶段发出 `mmio_we=1`；CNN 原生 MMIO 给出 `mmio_ready`，在对应上升沿接收配置。此时不写 datasram。

**读 CNN 状态时：**

```text
CNN accelerator_regs
    -> mmio_rdata[31:0]
    -> MEM 级 read_data_m
    -> MEM/WB
    -> WB 选择读返回
    -> CPU 目标寄存器
```

CPU 用 `mmio_re` 发出读请求。mmio_re、mmio_we、mmio_ready 都是 1 位，地址、写数据、读数据各 32 位。
当前 MMIO 要求零等待响应；有 ready 引脚不代表当前 CPU 能自动支持任意长的 MMIO 等待。

软件流程通常是：先在 datasram 准备数据和描述符，再写 QUEUE_BASE、TASK_COUNT，按当前 CNN 协议启动（本次示例 CONTROL=0x3D），随后读 STATUS。
**QUEUE_BASE 写进去的是“队列地址”，不是把整队描述符通过 MMIO 传给 CNN。** CNN 启动后会自己从 datasram B 口读描述符和数据，并把计算结果写回 datasram。

## 9. Control 和 Datapath：到底谁搬数

把 Datapath 理解成“实际运算和保存数据的地方”，Control 理解成“决定选哪条路、做哪种操作的指挥逻辑”。

| 内容 | 谁提供 → 谁使用 | 作用 |
|---|---|---|
| instr_d[31:0] | Datapath → Control | 让 Control 看懂当前指令 |
| 寄存器编号、valid、访存状态 | Datapath → Control | 判断前后指令有没有数据依赖 |
| cmp_eq_e / cmp_lt_e / cmp_ltu_e | Datapath → Control | 告诉 Control 当前比较是否成立，每个 1 位 |
| alu_ctrl[3:0] | Control → Datapath | 4 位，选择 ALU 做哪一种运算 |
| alu_src_a_sel / alu_src_b_sel | Control → Datapath | 各 2 位，选择寄存器、立即数、PC 等操作数来源 |
| regwrite_d / memread_d / memwrite_d | Control → Datapath | 各 1 位，说明本条指令是否写寄存器、读或写存储器 |
| wb_sel_d[1:0] | Control → Datapath | 2 位，最后写回 ALU 结果、读返回还是 PC+4 |
| fwd_a / fwd_b / fwd_store | Control → Datapath | 各 2 位，为 EX 级选最新操作数或待写数据 |
| pc_sel[1:0]、pc_en | Control → Datapath | 选择下一个 PC，决定 PC 是否更新 |
| if_id_en / if_id_flush / id_ex_flush | Control → Datapath | 各 1 位，控制暂停或丢弃不该执行的指令 |

Control 不接收 ADD 的 7 和 10 去做加法，也不搬运图像。7、10、17 沿 Datapath 流动，Control 主要发送选择和使能信号。
ID 阶段产生的运算/访存/写回控制会随数据存入 ID/EX 等流水寄存器；前递选择则直接作用于当前 EX 阶段。Control 本身保持组合逻辑，跨时钟的状态由 Datapath 保存。

## 10. 刚算出的数还没写回，下一条要用怎么办

### 10.1 前递：从中途把最新结果送过去

```asm
ADD x3, x1, x2
ADD x4, x3, x6
```

第二条要用第一条刚算出的 x3。若还没来得及写回 regfile，直接读寄存器可能拿到旧值。
CPU 会检查寄存器编号，选择流水线里更新的结果：

```text
前一条的 MEM 级 ALU 结果 ------+
                              +--> 当前 EX 操作数选择 --> ALU
更前一条的 WB 最终结果 --------+
```

这叫“前递”，不是重新做一遍加法。它也用于分支比较和 SW 要写的数据；regfile 还有 WB 写入值到同周期读取的旁路。

### 10.2 Load-use：读内存后马上用，要停一拍

```asm
LW  x5, 0(x10)
ADD x6, x5, x1
```

LW 在 EX 阶段刚算完的只是地址，不能把这个地址当成 x5 的数据前递。
检测到这种相邻依赖时，Control 保持 PC 和 IF/ID，在 ID/EX 插入一个无效操作，也叫“气泡”。老指令继续往后走；下一拍 ADD 再进入 EX，从 WB 前递拿到正确读数。

气泡不是往 SRAM 写 0，也不是停止整个时钟。它让某个阶段这一拍不做有效工作，避免算错。

### 10.3 分支：走错方向的指令要丢弃

例如 `BEQ x1, x2, label`，CPU 在 EX 用最新操作数比较 x1 和 x2。
成立时，Control 选择分支目标 PC，清除年轻的错误路径指令，并让取指逻辑丢弃已经取回但不该执行的指令。

分支目标来自“该指令的 PC + 偏移”；JALR 目标来自“寄存器值 + 偏移，并清最低位”。JAL/JALR 还会把该跳转指令的 PC+4 经 WB 写回指定寄存器，作为返回地址。

## 11. 连起来看一个小程序

假设 x10 已经装好有效 SRAM 地址 `0x1000`，x1=7、x2=10，执行下面三条合法指令：

```asm
ADD x3, x1, x2
SW  x3, 0(x10)
LW  x4, 0(x10)
```

数据实际这样走：

```text
CPU x1 的 7 + CPU x2 的 10
             |
             v
          ALU 得到 17
             |
             +--> WB 写入 x3
             |
             +--> 必要时通过前递，作为 SW 的待写数据
                              |
                              v
                    datasram[0x1000] = 17
                              |
                              v
                      LW 读回 17 -> WB -> x4 = 17
```

这是讲解片段，假设寄存器已初始化，不是可直接烧录的完整固件。它展示了“CPU 内部算数”和“CPU 与共享 SRAM 搬数”的区别。

## 12. 回到图像识别系统

整体分工可以按下面顺序理解，实际使用还需要固件约定的数据地址和完成标志：

1. **电脑上传原始图像字节**：UART → image_bridge，校验通过后 → datasram B 口。
2. **CPU 做任务管理**：从 IEM 执行程序，通过 A 口准备描述符等数据，通过 MMIO 配置并启动 CNN。
3. **CNN 做计算**：通过自己的 mem_* 接口 → datasram B 口，读取任务和输入，计算后写回结果；这些数不用逐个绕过 CPU。
4. **CPU 判断完成**：通过 MMIO 读 STATUS，再按需要通过 A 口读取或处理结果。
5. **电脑读回**：image_bridge 从 datasram B 口读取指定结果字节，通过 UART 发回电脑。

这是数据分工说明，不表示已经交付完整人脸识别固件。UART 桥不会自己生成描述符或自动启动 CNN；软件需要约定什么时候数据可用、什么时候可以修改它。
datasram 内的仲裁只决定 B 口当前给谁用，不保证整帧数据或 CNN 的读改写过程不被其他人修改。CNN 工作期间，CPU 和电脑不能随意改它正在用的数据区。

## 13. 对照代码从哪里看

| 想看什么 | 当前文件 |
|---|---|
| CPU 和其他五个大模块的关系 | [face_soc_top.sv](rtl/soc/face_soc_top.sv) |
| CPU 内部连接 Control 与 Datapath | [cpu_core.sv](rtl/soc/cpu_core.sv) |
| 本文绝大部分数据路线 | [cpu_datapath.sv](partners/datapath/delivery/rtl/cpu_datapath/cpu_datapath.sv) |
| PC、取指、流水暂存 | 同目录的 pc.sv、fetch_adapter.sv、if_id_reg.sv、id_ex_reg.sv、ex_mem_reg.sv、mem_wb_reg.sv |
| 读写 x0～x31 | [regfile.sv](partners/datapath/delivery/rtl/cpu_datapath/regfile.sv) |
| 算数、立即数、地址选择 | 同目录的 alu.sv、imm_gen.sv、address_decoder.sv |
| 字节/半字处理、对齐与字节写使能 | [lsu.sv](partners/datapath/delivery/rtl/cpu_datapath/lsu.sv) |
| 译码和各控制子模块接法 | [cpu_control.sv](rtl/cpu_control/cpu_control.sv) |
| 前递和 Load-use 判断 | [hazard_unit.sv](rtl/cpu_control/hazard_unit.sv) |
| SRAM 真正接单、读数和写数 | [datasram.sv](rtl/soc/datasram.sv) |

进一步看外部每根线的方向和位宽：[SoC 顶层连线与总体 I/O 小白说明](SoC顶层连线与总体IO说明_小白版.md)。
看已经做过的实际测试和未验证范围：[六模块验证记录](docs/soc_six_module_verification_20261008.md)。本文例子用于解释，不作为新增仿真结果。

最后记住三句话：**指令从 IEM 来；CPU 算数主要在寄存器和 ALU 之间流动；大量图像数据由 CNN、图像桥直接与 datasram 交换。**
