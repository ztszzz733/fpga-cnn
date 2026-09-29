# 当前硬件各模块的输入与输出

> 最新版本已统一为任务队列入口，当前说明见 [队列唯一入口版输入输出说明](hardware_inputs_outputs_queue_only.md)。下文仅供历史对照。

> 本文保留的是 2026-09-22 的双通路版本说明，不代表当前纯阵列版。2026-09-23 `codex/array-only` 的接口与连线请看 [纯阵列版输入输出汇总](hardware_inputs_outputs_array_only.md)。

依据：2026-09-22 工作区 `mobilefacenet/rtl/`，顶层为 `mobilefacenet_accelerator_top`，默认 `USE_SYSTOLIC=1`、`TASK_PREFETCH_DEPTH=4`。

本文按“这个模块收到什么、送出什么、连到谁”整理。接口表新增“信号路径（来源 → 接收方）”，表后对每个信号逐条作简短解释。以当前脉动阵列版本为主，末尾补充切换到串行版本时使用的模块。不包含根目录 `rtl/` 下的另一套 CNN 工程，也不包含 `deliveries/` 历史副本。

## 1. 阅读约定与整体关系

- **输入、输出都相对于当前小节的模块。** 同一根线对发送方是输出，对接收方是输入。
- 表格一行列多个信号时，位宽是**每个信号**的位宽，除非写明“总线”。未声明 signed 的端口按无符号位向量理解；打包总线内部的数值另行说明。
- `INT8` 是有符号 8 位数，范围 −128～127；`INT32` 是有符号 32 位数。
- 地址均为**字节地址**。外部 RAM 一次传输 32 位，即 4 个字节。
- `valid && ready` 在时钟上升沿同时成立，表示这次请求或数据被接收。`ready` 不等于整个计算已经完成。
- `done` 通常是完成事件；CPU 读到的 `STATUS.DONE` 是 MMIO 模块保存的完成状态。

### 公共时序输入

下文表格不反复列出以下端口，但各节会注明该模块具有哪些公共输入。

| 信号 | 位宽 | 来源 | 含义 |
|---|---:|---|---|
| `clk` | 1 | 顶层时钟 | 上升沿更新寄存器 |
| `rst_n` | 1 | 顶层复位 | 低有效异步复位；只对代码中相应状态/寄存器生效，不代表清空所有存储数组 |
| `clear` | 1 | 上级控制逻辑 | 同步清除，时钟上升沿执行；具体清除范围见对应小节 |
| `ce` | 1 | 上级控制逻辑 | 时钟使能，0 时暂停相应寄存器更新；PE/tile 中 clear 的优先级高于 ce |

**本表信号简释**

- `clk`：决定各时序模块何时更新。
- `rst_n`：拉低时复位。
- `clear`：在下一个时钟沿清理本模块状态。
- `ce`：决定本拍是否继续运行。

**具体来源：** clk/rst_n 从外部系统进入顶层，再沿实例层级分发。MMIO accelerator_reset 直接送队列 soft_reset、阵列 clear、原控制器 soft_reset、RAM 接口 cancel；队列把“软复位或新队列启动”组成 flush，送读取器/FIFO clear；阵列把“软复位或 CHECK”送读缓存、tile、阵列通路输出寄存器 clear；原控制器 datapath_clear 送偏置/输出寄存器和串行引擎 clear。tile.clear 再经阵列传给各 PE。tile.ce 在当前集成中固定为 1，阵列/PE ce 由 tile 的初始化/RUN 状态门控产生。串行 accumulator 的 clear 由所属 Conv/DW 引擎透传。

组合逻辑模块没有时钟或复位端口。`sample_buffer`、`input_buffer`、`weight_buffer` 只有 `clk`，没有 `rst_n`、`clear`。

### 当前连接关系

```text
CPU / 测试程序 ──MMIO──> 寄存器组 ──配置、启动──> 队列控制器
                                                    │
                           ┌────────────────────────┤
                           ▼                        ▼
                      任务读取器 ──完整任务──> 任务 FIFO
                                                    │ 队首任务
                                                    ▼
                                               队列分发逻辑
                                                    │
                         ┌──────────────────────────┴─────────────────┐
                         ▼                                            ▼
                  阵列卷积控制器                              逐元素算子控制器
                    Conv / DW                             ADD / ReLU6 / COPY / FINAL
                         │                                            │
             地址生成、读缓存、tile                            地址生成、输入缓冲
             权重/输入/偏置块 → 8×8 PE                         ADD 或输入直通
                         │                                            │
                 本通路后处理、输出寄存器                      本通路后处理、输出寄存器
                         │                                            │
                         └──────────────┬─────────────────────────────┘
                                        ▼
任务读取器的读请求 ──────────────> 顶层 RAM 请求选择逻辑
                                        │
                                  RAM 访问接口
                                        ⇅
                                    外部 RAM
```

RAM 的返回数据经访问接口送回当前请求方。任务读取器和 FIFO **实例化在队列控制器内部**；tile、读缓存、卷积窗口地址生成和阵列通路后处理**实例化在阵列卷积控制器内部**。上图将它们展开，方便说明关系，并非互相独立的顶层端口。

默认每批先读最多 4 条任务，再顺序执行；当前没有一边执行算子一边预取下一批任务，也没有 tile 加载与计算的双缓冲重叠。

## 2. 加速器顶层与外部 CPU、RAM

代码：[mobilefacenet_accelerator_top.sv](../rtl/mobilefacenet_accelerator_top.sv)。公共输入：`clk`、`rst_n`。

顶层把内部模块接在一起，对外只有 MMIO 配置接口和 RAM 主接口。项目顶层**不包含 CPU 或真实板级 RAM**；仿真中由测试程序和 RAM 模型承担这些角色。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `mmio_addr` | 32 | 外部 CPU / 测试程序 → 加速器顶层 | CPU → 顶层：要访问的控制寄存器地址 |
| 输入 | `mmio_wdata` | 32 | 外部 CPU / 测试程序 → 加速器顶层 | CPU → 顶层：写入寄存器的值 |
| 输入 | `mmio_we`、`mmio_re` | 1 | 外部 CPU / 测试程序 → 加速器顶层 | CPU → 顶层：写/读寄存器请求 |
| 输出 | `mmio_rdata` | 32 | MMIO 寄存器组 mmio_rdata → 顶层 → CPU 读数据端 | 顶层 → CPU：配置或状态的读回值 |
| 输出 | `mmio_ready` | 1 | MMIO 寄存器组 mmio_ready → 顶层 → CPU 响应端 | 顶层 → CPU：当前 MMIO 访问被响应 |
| 输出 | `mem_addr` | 32 | RAM 访问接口 mem_addr → 顶层 mem_addr → 外部 RAM 地址端 | 顶层 → RAM：对齐到 4 字节的访问地址 |
| 输出 | `mem_wdata` | 32 | RAM 访问接口 mem_wdata → 顶层 mem_wdata → 外部 RAM 写数据端 | 顶层 → RAM：整字写数据 |
| 输出 | `mem_read`、`mem_write` | 1 | RAM 访问接口 mem_read/mem_write → 顶层 → 外部 RAM 控制端 | 顶层 → RAM：读/写请求，等待时保持 |
| 输入 | `mem_rdata` | 32 | 外部 RAM mem_rdata → 顶层 → RAM 访问接口 mem_rdata | RAM → 顶层：读出的整字数据 |
| 输入 | `mem_ready` | 1 | 外部 RAM mem_ready → 顶层 → RAM 访问接口 mem_ready | RAM → 顶层：本次读/写完成确认 |

**本表信号简释**

- `mmio_addr`：CPU 要读写哪一个配置寄存器。
- `mmio_wdata`：CPU 本次准备写入寄存器的值。
- `mmio_we`：CPU 正在请求写寄存器。
- `mmio_re`：CPU 正在请求读寄存器。
- `mmio_rdata`：返回给 CPU 的寄存器内容。
- `mmio_ready`：本次寄存器访问可以在当前时钟沿被接受。
- `mem_addr`：要读写的外部 RAM 整字地址。
- `mem_wdata`：准备写入 RAM 的 32 位数据。
- `mem_read`：正在向 RAM 发起读操作。
- `mem_write`：正在向 RAM 发起写操作。
- `mem_rdata`：RAM 本次读回的 32 位数据。
- `mem_ready`：RAM 已完成当前读或写事务。

CPU 准备图像、权重、偏置和任务表，需要通过外部系统访问 RAM；这个数据准备通道不包含在上述加速器 MMIO 接口里。RAM 只响应读写请求，不主动向队列控制器发启动信号。

## 3. MMIO 寄存器组

代码：[accelerator_regs.sv](../rtl/accelerator_regs.sv)。公共输入：`clk`、`rst_n`。默认基地址 `BASE_ADDR=0x40000000`。

作用：保存 CPU 配置，产生启动/软复位脉冲，保存完成和错误状态。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `mmio_addr`、`mmio_wdata` | 32 | CPU → 顶层 MMIO 端口 → MMIO 寄存器组 | CPU 的寄存器地址、写数据 |
| 输入 | `mmio_we`、`mmio_re` | 1 | CPU → 顶层 MMIO 端口 → MMIO 寄存器组 | CPU 的寄存器写/读请求 |
| 输入 | `accelerator_busy` | 1 | 队列 active、两执行器 busy、RAM 接口 idle → 顶层忙状态汇总 → 寄存器组 | 顶层汇总：执行器忙、队列忙或 RAM 尚未空闲 |
| 输入 | `accelerator_done`、`accelerator_error` | 1 | 队列 done/error 或执行器 done/error → 顶层状态选择 → 寄存器组 | 顶层选择后的整体完成/错误事件 |
| 输出 | `mmio_rdata` | 32 | 寄存器组 → 顶层 mmio_rdata → CPU | 返回 CPU 的读数据 |
| 输出 | `mmio_ready` | 1 | 寄存器组 → 顶层 mmio_ready → CPU | 合法且对齐的寄存器访问响应 |
| 输出 | `accelerator_start` | 1 | 寄存器组 accelerator_start → 队列 start | 到队列控制器：单周期启动脉冲 |
| 输出 | `accelerator_reset` | 1 | 寄存器组 accelerator_reset → 队列 soft_reset、阵列 clear、原控制器 soft_reset、RAM 接口 cancel | 到队列、执行器、RAM 接口：软复位/取消脉冲 |
| 输出 | `op_type` | 4 | MMIO 寄存器组 → 队列控制器 | 到队列控制器：算子类型或队列模式 |
| 输出 | `input_addr`、`output_addr`、`weight_addr`、`bias_addr` | 32 | MMIO 寄存器组 → 队列控制器 | 到队列控制器：四个地址配置 |
| 输出 | `feature_size`、`channels`、`layer_param` | 32 | MMIO 寄存器组 → 队列控制器 | 到队列控制器：尺寸、通道和运算参数 |

**本表信号简释**

- `mmio_addr`：CPU 要读写哪一个配置寄存器。
- `mmio_wdata`：CPU 本次准备写入寄存器的值。
- `mmio_we`：CPU 正在请求写寄存器。
- `mmio_re`：CPU 正在请求读寄存器。
- `accelerator_busy`：整个加速器还没空闲，暂不能接新配置任务。
- `accelerator_done`：本次对 CPU 可见的任务执行完成事件。
- `accelerator_error`：本次执行发生错误的事件。
- `mmio_rdata`：返回给 CPU 的寄存器内容。
- `mmio_ready`：本次寄存器访问可以在当前时钟沿被接受。
- `accelerator_start`：通知后级开始执行一次配置好的任务。
- `accelerator_reset`：通知后级清状态并取消当前任务。
- `op_type`：这次要执行什么算子，15 表示任务队列模式。
- `input_addr`：输入数据首址；启动队列时改为任务表首址。
- `output_addr`：计算结果要存到哪里的首址。
- `weight_addr`：卷积权重首址，ADD 时是第二份输入首址。
- `bias_addr`：偏置数组的首址。
- `feature_size`：输入宽高；启动队列时改为任务条数。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：卷积核、步长、补零、右移和激活等配置的组合。

### 寄存器具体存什么

| 偏移 | 寄存器 | 字段 |
|---:|---|---|
| `0x00` | CONTROL | bit0=START，bit1=RESET，bits[5:2]=OP_TYPE；START/RESET 命令位读回为 0 |
| `0x04` | STATUS | bit0=BUSY，bit1=DONE，bit2=ERROR；只读，DONE/ERROR 保持到新启动或复位清除 |
| `0x08` | INPUT_ADDR | 单算子模式：输入首址；队列模式：任务表首址 |
| `0x0C` | OUTPUT_ADDR | 输出首址 |
| `0x10` | WEIGHT_ADDR | 卷积权重首址；ADD 模式为第二输入首址 |
| `0x14` | BIAS_ADDR | INT32 偏置首址 |
| `0x18` | FEATURE_SIZE | 单算子模式：[15:0]宽、[31:16]高；队列模式：任务数量 |
| `0x1C` | CHANNELS | [15:0]输入通道 CI、[31:16]输出通道 CO |
| `0x20` | LAYER_PARAM | [3:0]核大小、[7:4]步长、[11:8]padding、[19:12]右移位数、bit20 ReLU、bit21 ReLU6、bit22 ADD 标志；[31:23]保留为 0 |

**本表字段简释及来源/去向**

- `CONTROL`：CPU 写入的命令；START 送队列启动，RESET 送各通路清状态，OP_TYPE 送队列判断任务类型。
- `STATUS`：硬件汇总的状态，供 CPU 读取；BUSY 是忙，DONE 是完成，ERROR 是错误。
- `INPUT_ADDR`：CPU 写入，送队列作为输入首址或任务表首址。
- `OUTPUT_ADDR`：CPU 写入，单算子模式经队列送执行器，指定结果首址。
- `WEIGHT_ADDR`：CPU 写入，单算子模式经队列送执行器，指定权重或 ADD 第二输入首址。
- `BIAS_ADDR`：CPU 写入，单算子模式经队列送执行器，指定偏置首址。
- `FEATURE_SIZE`：CPU 写入，送队列；单算子时为宽高，队列时为任务条数。
- `CHANNELS`：CPU 写入，单算子模式送执行器，说明输入/输出通道数。
- `LAYER_PARAM`：CPU 写入，单算子模式送执行器，说明核大小、步长、补零、右移和激活开关。

队列模式下 OUTPUT_ADDR/WEIGHT_ADDR/BIAS_ADDR/CHANNELS/LAYER_PARAM 的每条任务值来自描述符，不取这些 MMIO 配置寄存器。

`OP_TYPE`：0=普通卷积，1=Depthwise，2=ReLU6，3=ADD，4=COPY，5=FINAL，15=任务队列。bit22 不是 ADD 运算的唯一开关，实际算子由 OP_TYPE 选择；当前 ADD 配置允许该位为 0 或 1。

队列启动常用三次写：INPUT_ADDR=任务表首址、FEATURE_SIZE=任务数、CONTROL=`0x3D`。队列模式下每个算子的完整参数来自 RAM 任务表，不是反复改写 MMIO。

这些配置是寄存器的持续输出连线，队列控制器可以直接看到；它不是再发起一次 MMIO 总线读取。

## 4. 队列控制器

代码：[task_queue_controller.sv](../rtl/task_queue_controller.sv)。公共输入：`clk`、`rst_n`。

作用：取一批任务、控制 FIFO 出队、发出执行启动、等待本条完成，再推进下一条。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `soft_reset`、`start` | 1 | 寄存器组 accelerator_reset/start → 队列 soft_reset/start | MMIO 寄存器组的软复位、启动脉冲 |
| 输入 | `op_type` | 4 | MMIO 寄存器组对应配置输出 → 队列控制器 | 15 表示队列模式；其他值走单算子直通分发 |
| 输入 | `input_addr`、`output_addr`、`weight_addr`、`bias_addr` | 32 | MMIO 寄存器组对应配置输出 → 队列控制器 | MMIO 四个地址；队列模式从 input_addr 锁存任务表地址 |
| 输入 | `feature_size`、`channels`、`layer_param` | 32 | MMIO 寄存器组对应配置输出 → 队列控制器 | MMIO 参数；队列模式从 feature_size 锁存任务数 |
| 输入 | `exec_busy`、`exec_done`、`exec_error` | 1 | 阵列及原控制器 busy/done/error → 顶层 OR 汇总 → 队列 exec_busy/done/error | 顶层汇总的两条执行通路状态 |
| 输入 | `mem_idle` | 1 | RAM 访问接口 idle → 队列 mem_idle | RAM 访问接口空闲；防止有未完成事务时切换任务 |
| 输入 | `fetch_ready` | 1 | RAM 接口 cmd_ready → 顶层按 fetch_phase 门控 → 队列 fetch_ready → 内部读取器 cmd_ready | 公共访存选择逻辑返回：接受描述符读请求 |
| 输入 | `fetch_rsp_valid`、`fetch_rsp_data` | 1 / 32 | RAM 接口 rsp_valid/rsp_rdata → 顶层按 fetch_phase 门控有效信号 → 队列 → 内部读取器 | 访存返回有效及一个任务字，传给内部读取器 |
| 输出 | `exec_start` | 1 | 队列 exec_start → 顶层算子分流 → 阵列 start 或原控制器 start | 到任务分流逻辑：启动当前算子 |
| 输出 | `task_op` | 4 | FIFO 队首（单算子时为 MMIO op_type）→ 队列 task_op → 顶层分流及两控制器 op/op_type | 到执行器：当前任务类型 |
| 输出 | `task_input`、`task_output`、`task_weight`、`task_bias` | 32 | FIFO 队首（单算子时为 MMIO 地址）→ 队列四个 task 地址 → 阵列 ia/oa/wa/ba、原控制器对应地址输入 | 到执行器：本条任务的四个基地址 |
| 输出 | `task_size`、`task_channels`、`task_param` | 32 | FIFO 队首（单算子时为 MMIO 参数）→ 队列 task_size/channels/param → 阵列 fs/ch/lp、原控制器对应输入 | 到执行器：本条任务尺寸、通道、运算参数 |
| 输出 | `active` | 1 | 队列 active → 顶层忙/完成选择逻辑、任务表保护逻辑、阵列 queue_active | 到顶层：队列状态不是 IDLE；单算子直通时不表示算子忙 |
| 输出 | `done`、`error` | 1 | 队列 done/error → 顶层状态选择 → MMIO accelerator_done/error | 到顶层/MMIO：整队列完成或错误事件 |
| 输出 | `fetch_phase` | 1 | 队列 fetch_phase → 顶层 RAM 请求选择及响应门控 | 到访存选择逻辑：当前在 FILL 取任务阶段 |
| 输出 | `fetch_valid`、`fetch_addr` | 1 / 32 | 内部读取器 cmd_valid/cmd_addr → 队列 fetch_valid/fetch_addr → 顶层请求选择 → RAM 接口 | 内部读取器透传出的整字读请求及地址 |
| 输出 | `queue_base`、`queue_end` | 32 / 64 | 队列 queue_base/end → 阵列任务表保护、顶层原通路任务表保护 | 到执行器保护逻辑：任务表首址和不包含在内的结束地址 |
| 输出 | `completed`、`fetched`、`buffered` | 32 | 队列计数器 / FIFO level → 顶层 queue_completed/fetched/buffered（调试观察，不映射到 MMIO） | 到顶层内部调试线：完成数、已装入 FIFO 的累计任务数、FIFO 当前条数 |
| 输出 | `debug_state` | 4 | 队列状态机 → 顶层 queue_state（调试观察） | 当前队列状态，供仿真观察 |

**本表信号简释**

- `soft_reset`：清除当前任务状态的软复位命令。
- `start`：开始执行本模块负责的一次工作。
- `op_type`：这次要执行什么算子，15 表示任务队列模式。
- `input_addr`：输入数据首址；启动队列时改为任务表首址。
- `output_addr`：计算结果要存到哪里的首址。
- `weight_addr`：卷积权重首址，ADD 时是第二份输入首址。
- `bias_addr`：偏置数组的首址。
- `feature_size`：输入宽高；启动队列时改为任务条数。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：卷积核、步长、补零、右移和激活等配置的组合。
- `exec_busy`：当前执行器还在处理任务。
- `exec_done`：当前一条算子任务执行成功。
- `exec_error`：当前一条算子任务执行失败。
- `mem_idle`：RAM 接口没有尚未结束的外部事务。
- `fetch_ready`：任务字读取请求可以被 RAM 接口接受。
- `fetch_rsp_valid`：一个任务字已经返回。
- `fetch_rsp_data`：返回的那个 32 位任务字。
- `exec_start`：通知选中的执行器锁存配置并启动。
- `task_op`：当前这一条任务的算子类型。
- `task_input`：当前任务输入数据的首址。
- `task_output`：当前任务输出结果的首址。
- `task_weight`：当前任务权重或 ADD 第二输入的首址。
- `task_bias`：当前任务偏置的首址。
- `task_size`：当前任务输入宽高。
- `task_channels`：当前任务输入/输出通道数。
- `task_param`：当前任务的卷积、量化和激活配置。
- `active`：队列状态机正在处理一批任务。
- `done`：整批任务已经全部执行成功。
- `error`：队列或其中一条任务出错，停止推进后续任务。
- `fetch_phase`：现在处在读取一批任务描述符的阶段。
- `fetch_valid`：任务读取器正在请求读取一个任务字。
- `fetch_addr`：这个任务字在 RAM 中的地址。
- `queue_base`：整张任务表的起始字节地址。
- `queue_end`：整张任务表的结束边界，不包含这个地址本身。
- `completed`：已经成功执行完的任务条数。
- `fetched`：已经完整读出并放入 FIFO 的累计任务条数。
- `buffered`：当前 FIFO 中尚未出队的任务条数。
- `debug_state`：当前状态机编号，便于看仿真波形。

`queue_end = queue_base + 任务数 × 32`。任务表首址要求 32 字节对齐；输出区不能覆盖整个任务表，包括尚未预取的部分。

FIFO 队首字段通过组合分发逻辑送到执行器。在允许出队的同一个上升沿，FIFO 消耗该任务，执行器锁存配置。**FIFO 给队列送任务数据，队列给 FIFO 送出队控制，两者同时成立。**

## 5. 任务读取器

代码：[task_descriptor_reader.sv](../rtl/task_descriptor_reader.sv)。公共输入：`clk`、`rst_n`、`clear`；clear 来自新队列启动或软复位。

作用：从 RAM 连续读取 8 个 32 位字，组成一条完整的 256 位任务。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `start` | 1 | 队列控制器内部调度逻辑 → 任务读取器 | 队列控制器：开始读一条任务 |
| 输入 | `base_address` | 32 | 队列控制器内部调度逻辑 → 任务读取器 | 队列控制器：当前描述符的首址 |
| 输入 | `cmd_ready` | 1 | RAM 接口 cmd_ready → 顶层门控 → 队列 fetch_ready → 读取器 cmd_ready | RAM 接口经顶层返回：本次读请求已接受 |
| 输入 | `rsp_valid`、`rsp_data` | 1 / 32 | RAM 接口 rsp_valid/rsp_rdata → 顶层门控 → 队列 fetch_rsp_valid/data → 读取器 | RAM 接口：一个任务字返回有效及数据 |
| 输入 | `descriptor_ready` | 1 | 任务 FIFO in_ready → 读取器 descriptor_ready | FIFO 的 in_ready：可以接收完整任务 |
| 输出 | `idle` | 1 | 任务读取器 → 队列控制器内部调度逻辑 | 到队列控制器：可以开始读下一条 |
| 输出 | `cmd_valid`、`cmd_addr` | 1 / 32 | 读取器 cmd_valid/cmd_addr → 队列 fetch_valid/addr → 顶层选择 → RAM 接口 cmd_valid/addr | 经队列、请求选择逻辑送 RAM 接口：整字读请求 |
| 输出 | `descriptor_valid` | 1 | 读取器 descriptor_valid → FIFO in_valid | 到 FIFO：完整 8 个字已收齐 |
| 输出 | `descriptor` | 256 | 读取器内部 words → descriptor → FIFO in_data | 到 FIFO：完整任务内容 |

**本表信号简释**

- `start`：开始从 base_address 读取一条任务。
- `base_address`：本次要读的那一条任务的首址。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_data`：完成响应附带的 32 位读数据。
- `descriptor_ready`：FIFO 现在能接收一整条任务。
- `idle`：当前不在读取或等待发布任务，可以开始下一条。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `descriptor_valid`：完整的 8 个任务字已经收齐，可以交付。
- `descriptor`：一整条 256 位任务说明，不是图像数据。

返回的每个字先存入内部 `words[255:0]`；`word_index` 指示写入哪一个 32 位位置。`WAIT_WORD` 只是“已发出请求，正在等这个字回来”的状态。只有 8 个字全部收齐才发布任务，并保持到 FIFO 接收。

### FIFO 中一条任务的内容

| 字编号 | descriptor 位段 | 内容 |
|---:|---|---|
| 0 | [31:0] | [7:0]算子编号、[15:8]格式版本（当前 1）、[31:16]保留为 0 |
| 1 | [63:32] | 输入首址 |
| 2 | [95:64] | 输出首址 |
| 3 | [127:96] | 权重 / ADD 第二输入首址 |
| 4 | [159:128] | 偏置首址 |
| 5 | [191:160] | FEATURE_SIZE |
| 6 | [223:192] | CHANNELS |
| 7 | [255:224] | LAYER_PARAM |

**本表字段简释及来源/去向**

整条描述符的路径是：CPU/测试程序准备 RAM → RAM 接口 → 任务读取器 words → FIFO → 队列解码 → 执行器锁存。

- 字 0 的算子编号：交给队列检查并作为 task_op 分流。
- 字 0 的格式版本：交给队列校验是否为版本 1；保留位必须为 0。
- 字 1 的输入首址：成为 task_input，告诉执行器从哪里取特征。
- 字 2 的输出首址：成为 task_output，告诉执行器往哪里写结果。
- 字 3 的权重/第二输入首址：成为 task_weight，指定卷积参数或 ADD 的 B 输入位置。
- 字 4 的偏置首址：成为 task_bias，指定 INT32 偏置位置。
- 字 5 的 FEATURE_SIZE：成为 task_size，描述输入宽高。
- 字 6 的 CHANNELS：成为 task_channels，描述输入/输出通道数。
- 字 7 的 LAYER_PARAM：成为 task_param，描述卷积、量化、激活配置。

版本号描述任务格式，不是计算轮次，也不是 Git 项目版本。

## 6. 任务 FIFO

代码：[task_descriptor_fifo.sv](../rtl/task_descriptor_fifo.sv)。公共输入：`clk`、`rst_n`、`clear`。默认 `DEPTH=4`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `in_valid` | 1 | 读取器 descriptor_valid → FIFO in_valid | 读取器：完整任务有效 |
| 输入 | `in_data` | 256 | 读取器 descriptor → FIFO in_data | 读取器：完整任务 |
| 输出 | `in_ready` | 1 | FIFO in_ready → 读取器 descriptor_ready；同时供队列判断能否启动下一次读取 | 到读取器：FIFO 还有可写空间 |
| 输出 | `out_valid` | 1 | 任务 FIFO → 队列控制器 | 到队列控制器：当前有队首任务 |
| 输出 | `out_data` | 256 | FIFO out_data → 队列 head_data 分发逻辑 → 两执行器的任务配置输入 | 到队列分发逻辑：当前队首任务字段 |
| 输入 | `out_ready` | 1 | 队列 head_ready 逻辑 → FIFO out_ready | 队列控制器：允许消费队首任务 |
| 输出 | `level` | 32 | 任务 FIFO → 队列控制器 | 到队列控制器：当前存了多少条任务 |

**本表信号简释**

- `in_valid`：写入方正在提供一条有效任务。
- `in_data`：准备存入 FIFO 的整条任务。
- `in_ready`：FIFO 当前还有空间接收任务。
- `out_valid`：FIFO 当前有一条可取出的队首任务。
- `out_data`：当前排在 FIFO 最前面的任务内容。
- `out_ready`：队列控制器允许当前队首任务出队。
- `level`：FIFO 此刻保存的任务数量。

内部保存 4×256 位任务数据，以及读指针、写指针、数量。它不存图像、权重或卷积结果，也不把数据送进输入 buffer。

## 7. 顶层中的分流和选择逻辑

这些是 [顶层代码](../rtl/mobilefacenet_accelerator_top.sv) 内的连线和组合逻辑，**不是额外的独立 module**。

| 功能 | 输入 | 输出 | 具体规则 |
|---|---|---|---|
| 任务分流 | `exec_start`、`task_op`、编译参数 `USE_SYSTOLIC` | `sx_start`、`legacy_start` | 默认 op=0/1 启动阵列；其他 op 启动原算子控制器 |
| 执行状态汇总 | 两个控制器的 busy/done/error | `exec_busy`、`exec_done`、`exec_error` | 对应状态做 OR，交给队列 |
| RAM 请求选择 | 任务读取请求、阵列请求、原控制器请求；`fetch_phase`、`sx_busy` | 公共 `cmd_valid/write/byte/addr/wdata` | 先按 fetch_phase 选读取器，否则按 sx_busy 选阵列，否则选原通路 |
| RAM 响应分发 | `bus_ready`、`bus_response`、`bus_rdata` | 各通路 ready / response_valid 与数据 | 只有当前通路收到有效握手；数据线可以共用，有效信号决定是否采样 |
| 原通路地址选择 | `address_select`、各个生成地址 | `command_addr` | 0=输入、1=权重、2=偏置、3=输出、4=ADD 第二输入 |
| 原通路结果选择 | `cop`、卷积结果、DW 结果、ADD 结果、输入 `av` | INT32 `raw_result` | 默认阵列版本中：ADD 选加法结果；ReLU6/COPY/FINAL 选输入符号扩展 |

**本表信号简释及连接**

- `exec_start`：来自队列，要求分流逻辑启动一个算子。
- `task_op`：来自队列，决定这次启动哪条通路。
- `USE_SYSTOLIC`：编译参数，决定是否实例化阵列路径，不是运行时信号。
- `sx_start`：分流输出，接阵列控制器 start。
- `legacy_start`：分流输出，接原控制器 start。
- 两执行器的 `busy` / `done` / `error`：分别表示忙、成功完成、错误；经 OR 汇总为 `exec_busy` / `exec_done` / `exec_error` 送回队列。
- `fetch_phase`：来自队列，决定 RAM 是否属于任务读取器。
- `sx_busy`：来自阵列控制器，在非取任务阶段决定 RAM 是否属于阵列路径。
- `cmd_valid`：选中通路有没有命令；`cmd_write`：读还是写；`cmd_byte`：字节还是整字；`cmd_addr`：访问哪里；`cmd_wdata`：写什么；它们共同送 RAM 接口。
- `bus_ready`：RAM 接口 cmd_ready 的顶层名字，门控后送当前请求方。
- `bus_response`：RAM 接口 rsp_valid 的顶层名字，门控后通知当前请求方操作完成。
- `bus_rdata`：RAM 接口 rsp_rdata 的顶层名字，提供返回数据。
- `address_select`：来自原控制器，决定选哪个生成地址；选出的 `command_addr` 经请求选择送 RAM 接口。
- `cop`：原控制器锁存的算子类型；`av`：input_buffer 读出的数值；共同参与结果选择。
- `raw_result`：顶层结果选择输出的 INT32 数值，送原通路 requant.value。

## 8. RAM 访问接口

代码：[accelerator_mem_if.sv](../rtl/accelerator_mem_if.sv)。公共输入：`clk`、`rst_n`。

作用：把内部“读/写一个字节或整字”的命令变成外部 32 位 RAM 事务。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `cancel` | 1 | MMIO accelerator_reset → 顶层 reset → RAM 接口 cancel | MMIO 软复位：取消当前内部操作，排空已发外部事务 |
| 输入 | `cmd_valid` | 1 | 顶层 RAM 请求选择逻辑（读取器 / 阵列 / 原通路） → RAM 访问接口 | 当前被选择的请求方：命令有效 |
| 输出 | `cmd_ready` | 1 | RAM 访问接口 → 顶层响应分发逻辑 → 当前请求方 | 到请求方：当前可以接受命令 |
| 输入 | `cmd_write` | 1 | 顶层 RAM 请求选择逻辑（读取器 / 阵列 / 原通路） → RAM 访问接口 | 1=写，0=读 |
| 输入 | `cmd_byte` | 1 | 顶层 RAM 请求选择逻辑（读取器 / 阵列 / 原通路） → RAM 访问接口 | 1=INT8 字节访问，0=32 位整字访问 |
| 输入 | `cmd_addr`、`cmd_wdata` | 32 | 顶层 RAM 请求选择逻辑（读取器 / 阵列 / 原通路） → RAM 访问接口 | 字节地址、待写数据；字节写只取 wdata[7:0] |
| 输出 | `rsp_valid` | 1 | RAM 访问接口 → 顶层响应分发逻辑 → 当前请求方 | 到请求方：读或写操作已经完成；不是只有读才返回 |
| 输出 | `rsp_rdata` | 32 | RAM 访问接口 → 顶层响应分发逻辑 → 当前请求方 | 读出的字；INT8 读会符号扩展到 32 位；写完成时为 0 |
| 输出 | `idle` | 1 | RAM 接口 idle → 顶层忙/任务表调度、队列 mem_idle、原控制器 mem_idle | 到顶层/队列/原控制器：当前无未完成外部事务 |
| 输出 | `mem_addr`、`mem_wdata` | 32 | RAM 接口 mem_addr/mem_wdata → 顶层同名端口 → 外部 RAM | 到外部 RAM：对齐地址、整字写数据 |
| 输出 | `mem_read`、`mem_write` | 1 | RAM 接口 mem_read/mem_write → 顶层同名端口 → 外部 RAM | 到 RAM：读/写请求 |
| 输入 | `mem_rdata`、`mem_ready` | 32 / 1 | 外部 RAM → 顶层 mem_rdata/mem_ready → RAM 接口 | RAM 返回的数据及完成确认 |

**本表信号简释**

- `cancel`：取消内部操作，已发出的 RAM 事务仍要排空。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `cmd_write`：这条命令是写入（1）还是读取（0）。
- `cmd_byte`：这条命令按一个字节（1）还是整字（0）访问。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `cmd_wdata`：该命令准备写入的数据。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_rdata`：完成响应的读数据；字节读已符号扩展。
- `idle`：本模块处于空闲状态。
- `mem_addr`：要读写的外部 RAM 整字地址。
- `mem_wdata`：准备写入 RAM 的 32 位数据。
- `mem_read`：正在向 RAM 发起读操作。
- `mem_write`：正在向 RAM 发起写操作。
- `mem_rdata`：RAM 本次读回的 32 位数据。
- `mem_ready`：RAM 已完成当前读或写事务。

INT8 写入采用“读原来的 32 位字 → 替换其中一个字节 → 写回整个字”，以保护另外三个字节。接口一次只处理一个命令。等待 mem_ready 时，外部地址、数据和请求保持稳定。

cancel 不会撤销已经呈现给 RAM 的请求；如果取消发生在字节写的读阶段，就不再进入后续写阶段。已经进入写阶段的事务等待完成，已写入数据不会回滚。

## 9. 阵列卷积控制器

代码：[systolic_conv_controller.sv](../rtl/systolic_conv_controller.sv)。公共输入：`clk`、`rst_n`、`clear`；clear 接 MMIO 软复位。

作用：完成**整条**普通卷积或 DW 任务，控制分块、加载、运行、后处理及写回。其内部包含地址生成、读缓存、tile 和后处理模块。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `start` | 1 | 队列 exec_start + task_op → 顶层 sx_start 分流 → 阵列 start | 顶层任务分流：启动本条卷积任务 |
| 输入 | `ia`、`oa`、`wa`、`ba` | 32 | 队列 task_* 配置输出（经顶层连线） → 阵列卷积控制器 | 队列任务字段：输入、输出、权重、偏置首址 |
| 输入 | `fs`、`ch`、`lp` | 32 | 队列 task_* 配置输出（经顶层连线） → 阵列卷积控制器 | 队列任务字段：尺寸、通道、参数 |
| 输入 | `op` | 4 | 队列 task_* 配置输出（经顶层连线） → 阵列卷积控制器 | 普通卷积 0 或 DW 1 |
| 输入 | `queue_active` | 1 | 队列 active → 顶层 queue_active → 阵列 queue_active | 当前是否处于队列任务中 |
| 输入 | `queue_base`、`queue_end` | 32 / 64 | 队列 queue_base/queue_end → 阵列同名保护输入 | 任务表地址范围，用于防止输出覆盖任务表 |
| 输入 | `cmd_ready` | 1 | RAM 接口 cmd_ready → 顶层按当前阵列所有权门控 → 阵列 cmd_ready | 公共 RAM 接口接受本通路命令 |
| 输入 | `rsp_valid`、`rsp_data` | 1 / 32 | RAM 接口 rsp_valid/rsp_rdata → 顶层门控 → 阵列 rsp_valid/rsp_data | 公共 RAM 接口的完成响应及数据 |
| 输出 | `busy`、`done`、`error` | 1 | 阵列 busy/done/error → 顶层 exec_* 汇总 → 队列；单算子模式状态也送 MMIO | 经顶层汇总送队列：整条算子的状态 |
| 输出 | `cmd_valid`、`cmd_write`、`cmd_byte` | 1 | 阵列卷积控制器 → 顶层 RAM 请求选择 → RAM 访问接口 | 到 RAM 请求选择逻辑：有效、读写、字节/整字类型 |
| 输出 | `cmd_addr`、`cmd_wdata` | 32 | 阵列卷积控制器 → 顶层 RAM 请求选择 → RAM 访问接口 | 到 RAM 请求选择逻辑：地址、写数据 |
| 输出 | `array_running` | 1 | 内部 tile busy → 阵列 array_running → 顶层 array_running（仅内部观察） | 到顶层内部观察线：实际接 tile_busy，包含 tile 初始化与 RUN，并非纯 MAC 有效指示 |

**本表信号简释**

- `start`：锁存整条卷积任务配置并开始执行。
- `ia`：输入特征的首址。
- `oa`：输出结果的首址。
- `wa`：权重的首址。
- `ba`：偏置的首址。
- `fs`：输入特征的宽高配置。
- `ch`：输入、输出通道数配置。
- `lp`：卷积核、步长、补零、右移和激活配置。
- `op`：本条任务类型；阵列路径只接普通卷积 0 或 DW 1。
- `queue_active`：本条计算由队列调度，需要保护任务表地址范围。
- `queue_base`：整张任务表的起始字节地址。
- `queue_end`：整张任务表的结束边界，不包含这个地址本身。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_data`：完成响应附带的 32 位读数据。
- `busy`：本模块尚在处理当前工作。
- `done`：整条卷积任务的所有输出已完成写回。
- `error`：本模块负责的这次工作发生错误。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_write`：这条命令是写入（1）还是读取（0）。
- `cmd_byte`：这条命令按一个字节（1）还是整字（0）访问。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `cmd_wdata`：该命令准备写入的数据。
- `array_running`：tile 处于初始化或运行中，不保证每拍都有有效乘加。

控制器内部的 `cia/coa/cwa/cba/cfs/cch/clp/cop` 保存启动时锁存的配置；`mb` 为输出通道块首号、`nb` 为空间位置块首号、`kb` 为累加项块首号。`row/col/kidx` 表示当前块内位置。

每块最多 8 个输出通道×8 个输出位置，一次加载最多 8 个累加项。所有累加块算完后才量化、写回；tile_done 只表示一个累加块完成，不表示整层完成。

## 10. 卷积窗口地址生成

代码：[conv_window_address.sv](../rtl/conv_window_address.sv)。组合逻辑，无时钟。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `ia`、`oa`、`wa`、`ba` | 32 | 阵列控制器内部锁存配置 / 分块计数器 → 卷积窗口地址生成器 | 阵列控制器锁存的四个基址 |
| 输入 | `fs`、`ch`、`lp`、`op` | 32 / 32 / 32 / 4 | 阵列控制器内部锁存配置 / 分块计数器 → 卷积窗口地址生成器 | 阵列控制器锁存的任务配置 |
| 输入 | `row_base`、`col_base`、`k_base` | 32 | 阵列控制器内部锁存配置 / 分块计数器 → 卷积窗口地址生成器 | mb、nb、kb：通道块、空间块、累加块的起点 |
| 输入 | `row`、`col`、`k_index` | 3 | 阵列控制器内部锁存配置 / 分块计数器 → 卷积窗口地址生成器 | 当前块内行、列、累加项，范围 0～7 |
| 输出 | `input_address`、`weight_address`、`bias_address`、`output_address` | 32 | 窗口地址生成器 → 阵列控制器读地址选择 / 写回地址选择 → 读缓存或公共 RAM 接口 | 返回控制器：当前需要读取或写入的地址 |
| 输出 | `padding` | 1 | 窗口 padding → 阵列控制器 B_REQ 补零选择及 tile b_we/wr_value | 当前输入位置越过图像边界，应使用 0 而不是读 RAM |
| 输出 | `valid` | 1 | 窗口 valid → 阵列控制器 CHECK 状态合法性判断 | 整个算子配置合法，不是“RAM 数据返回有效” |
| 输出 | `spatial_count` | 32 | 卷积窗口地址生成器 → 阵列控制器内部逻辑 | 输出宽×输出高 |
| 输出 | `reduction_count` | 32 | 卷积窗口地址生成器 → 阵列控制器内部逻辑 | 每个输出的累加项数：普通卷积 CI×K²；DW 为 K² |
| 输出 | `output_count` | 32 | 卷积窗口地址生成器 → 阵列控制器内部逻辑 | 整层输出数量 CO×OH×OW |

**本表信号简释**

- `ia`：输入特征的首址。
- `oa`：输出结果的首址。
- `wa`：权重的首址。
- `ba`：偏置的首址。
- `fs`：输入特征的宽高配置。
- `ch`：输入、输出通道数配置。
- `lp`：卷积核、步长、补零、右移和激活配置。
- `op`：本条任务类型；阵列路径只接普通卷积 0 或 DW 1。
- `row_base`：当前输出通道块从第几个输出通道开始。
- `col_base`：当前空间块从第几个输出位置开始。
- `k_base`：当前累加块从第几个累加项开始。
- `row`：当前块内部的输出通道行号。
- `col`：当前块内部的空间位置列号。
- `k_index`：当前块内部的累加项编号。
- `input_address`：当前需要读取的输入字节地址。
- `weight_address`：当前需要读取的权重字节地址。
- `bias_address`：当前输出通道的 32 位偏置地址。
- `output_address`：当前结果应写入的字节地址。
- `padding`：当前输入位置在图像外面，应直接使用零。
- `valid`：整个算子配置合法，不是数据返回握手。
- `spatial_count`：输出图像一共有多少个空间位置，即宽乘高。
- `reduction_count`：一个输出点需要累加多少项。
- `output_count`：整层最终要产生多少个输出元素。

内部调用下一节的地址生成器，把“第几个输出位置、第几个累加项”换算为图像坐标。没有在 RAM 里生成一张展开后的大矩阵。

## 11. 通用地址生成器

代码：[address_generator.sv](../rtl/address_generator.sv)。组合逻辑，无时钟。

当前有两个用途：阵列窗口模块内部使用完整模式；顶层逐元素通路使用 `POINT_ONLY=1`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `input_base`、`output_base`、`weight_base`、`bias_base` | 32 | 阵列路径：窗口地址模块；逐元素路径：原控制器 cfg_* / 位置输出 → 通用地址生成器 | 所属控制器提供的四个基址 |
| 输入 | `feature_size`、`channels`、`layer_param` | 32 | 阵列路径：窗口地址模块；逐元素路径：原控制器 cfg_* / 位置输出 → 通用地址生成器 | 尺寸、通道、算子参数 |
| 输入 | `op_type` | 4 | 阵列路径：窗口地址模块；逐元素路径：原控制器 cfg_* / 位置输出 → 通用地址生成器 | 算子类型 |
| 输入 | `output_x`、`output_y` | 32 | 阵列路径：窗口模块将空间序号换算成 x/y → 本模块；原通路：原控制器同名输出 → 本模块 | 正在计算的输出空间坐标 |
| 输入 | `element_index` | 32 | 阵列窗口实例固定接 0；原通路由原控制器 element_index → 本模块 | 逐元素运算当前序号 |
| 输入 | `input_channel`、`output_channel` | 16 | 阵列路径：窗口模块按块坐标换算通道 → 本模块；原通路：原控制器同名输出 → 本模块 | 当前输入/输出通道号 |
| 输入 | `tap` | 6 | 阵列路径：窗口模块将累加项对 K² 取余 → 本模块；原通路：原控制器 tap → 本模块 | 卷积窗口内位置号，0～K²−1 |
| 输出 | `input_address` | 32 | 通用地址生成器 → 阵列路径：窗口地址模块；逐元素路径：顶层地址选择逻辑 | 当前输入字节地址；padding 时不能将它当作有效读地址 |
| 输出 | `weight_address` | 32 | 通用地址生成器 → 阵列路径：窗口地址模块；逐元素路径：顶层地址选择逻辑 | 当前权重字节地址 |
| 输出 | `bias_address` | 32 | 通用地址生成器 → 阵列路径：窗口地址模块；逐元素路径：顶层地址选择逻辑 | 当前输出通道的 INT32 偏置地址 |
| 输出 | `output_address` | 32 | 通用地址生成器 → 阵列路径：窗口地址模块；逐元素路径：顶层地址选择逻辑 | 当前输出字节地址 |
| 输出 | `second_address` | 32 | second_address → 顶层 command_addr 选择 → RAM 接口；阵列窗口实例接 second_unused，不消费 | ADD 第二输入地址，weight_base + element_index |
| 输出 | `output_width`、`output_height`、`output_count` | 32 | output_width/height/count → 窗口模块的空间映射/计数，或原控制器尺寸输入；顶层另用 count 保护任务表 | 输出宽、高、元素总数，返回控制器 |
| 输出 | `input_is_padding` | 1 | input_is_padding → 窗口 padding → 阵列补零逻辑，或原控制器 input_is_padding | 当前输入位置需要补零 |
| 输出 | `config_valid` | 1 | config_valid → 窗口 valid → 阵列 CHECK，或顶层与任务表保护相与后 → 原控制器 config_valid | 尺寸、算子支持范围、地址范围和区域重叠等检查是否通过 |

**本表信号简释**

- `input_base`：输入数组从 RAM 的哪里开始。
- `output_base`：输出数组从 RAM 的哪里开始。
- `weight_base`：权重数组或 ADD 第二输入从哪里开始。
- `bias_base`：偏置数组从哪里开始。
- `feature_size`：当前算子的输入宽高；到地址生成器这一层时不再表示队列条数。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：卷积核、步长、补零、右移和激活等配置的组合。
- `op_type`：当前具体算子的编号 0～5；队列模式 15 不交给地址生成器执行。
- `output_x`：当前输出位置的横坐标。
- `output_y`：当前输出位置的纵坐标。
- `element_index`：逐元素任务当前处理第几个数。
- `input_channel`：当前使用的输入通道编号。
- `output_channel`：当前计算的输出通道编号。
- `tap`：卷积核窗口内的元素编号。
- `input_address`：当前需要读取的输入字节地址。
- `weight_address`：当前需要读取的权重字节地址。
- `bias_address`：当前输出通道的 32 位偏置地址。
- `output_address`：当前结果应写入的字节地址。
- `second_address`：ADD 第二份输入中当前元素的地址。
- `output_width`：计算得到的输出宽度。
- `output_height`：计算得到的输出高度。
- `output_count`：整层最终要产生多少个输出元素。
- `input_is_padding`：当前输入是否需要补零。
- `config_valid`：任务参数及相关地址范围是否通过检查。

输入/输出特征按 CHW 存放，普通权重按 OIHW 存放。普通卷积支持 K=1/3，DW 支持 K=3/7 且 CI=CO；所以“阵列可做矩阵乘法”不等于当前整套控制接口接受任意卷积核。

## 12. 双路整字读缓存

代码：[systolic_read_cache.sv](../rtl/systolic_read_cache.sv)。公共输入：`clk`、`rst_n`、`clear`。

作用：输入、参数各保留一个 32 位字，同一个字内的后续字节读取可以直接命中。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `req_valid` | 1 | 阵列卷积控制器内部读取调度逻辑 → 双路读缓存 | 阵列控制器：所需读取请求有效 |
| 输出 | `req_ready` | 1 | 双路读缓存 → 阵列卷积控制器内部读取调度逻辑 | 到阵列控制器：缓存可以接收请求 |
| 输入 | `req_addr` | 32 | 阵列卷积控制器内部读取调度逻辑 → 双路读缓存 | 所需字节或整字地址 |
| 输入 | `req_byte` | 1 | 阵列卷积控制器内部读取调度逻辑 → 双路读缓存 | 1=取一个字节；0=取整个 32 位字 |
| 输入 | `req_bank` | 1 | 阵列卷积控制器内部读取调度逻辑 → 双路读缓存 | 0=输入缓存路；1=参数缓存路，权重和偏置共用 |
| 输出 | `response_valid` | 1 | 双路读缓存 → 阵列卷积控制器内部读取调度逻辑 | 到阵列控制器：所需数据已经可用 |
| 输出 | `response_data` | 32 | 缓存 response_data → 阵列 read_data → tile wr_value / wr_bias（由写使能决定保存） | 字节模式返回低 8 位、其余补 0；整字模式返回完整字 |
| 输出 | `cmd_valid`、`cmd_addr` | 1 / 32 | 缓存 cmd_valid/cmd_addr → 阵列内部读写选择 → 顶层请求选择 → RAM 接口 | 未命中时，经阵列控制器向公共 RAM 接口请求对齐整字 |
| 输入 | `cmd_ready` | 1 | RAM 接口 cmd_ready → 顶层阵列门控 → 阵列内部 cache_ready → 缓存 cmd_ready | 公共 RAM 接口接受缓存的读命令 |
| 输入 | `rsp_valid`、`rsp_data` | 1 / 32 | RAM 接口返回 → 顶层阵列门控 → 阵列排除 WRITE_WAIT 的响应 → 缓存 rsp_valid/rsp_data | 公共 RAM 接口返回整字及有效信号 |

**本表信号简释**

- `req_valid`：控制器向缓存提出了一次有效读取。
- `req_ready`：缓存现在可以接收这次读取。
- `req_addr`：希望缓存提供的数据地址。
- `req_byte`：取一个字节（1）还是整个字（0）。
- `req_bank`：使用输入缓存路（0）还是参数缓存路（1）。
- `response_valid`：缓存已经取得所需数据。
- `response_data`：缓存给出的字节或整字，字节模式只在低 8 位有效。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_data`：完成响应附带的 32 位读数据。

缓存字节返回是**零扩展**，公共 RAM 接口的直接字节读是**符号扩展**，二者不同；阵列后续取 `response_data[7:0]` 写入 signed INT8 buffer，因此负数含义仍正确。

内部 `data[0:1]` 存两个字，`tags[0:1]` 存对齐地址，`valid[1:0]` 表示是否有效。每条算子开始和软复位时失效；不是两套轮换的 tile 双缓冲，也不缓存写回结果。

## 13. tile：分块存储与馈数控制

代码：[systolic_tile.sv](../rtl/systolic_tile.sv)。公共输入：`clk`、`rst_n`、`clear`、`ce`。当前卷积控制器将 ce 固定为 1。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `start` | 1 | 阵列卷积控制器内部控制逻辑 → tile | 阵列控制器：当前块已装好，启动计算 |
| 输入 | `accumulate` | 1 | 阵列卷积控制器内部控制逻辑 → tile | 0=用偏置初始化；1=保留上一累加块的部分和 |
| 输入 | `dw` | 1 | 阵列卷积控制器内部控制逻辑 → tile | 0=普通阵列供数；1=DW 独立通道供数 |
| 输入 | `rows`、`cols`、`depth` | 4 | 阵列卷积控制器内部控制逻辑 → tile | 当前有效输出通道数、空间位置数、累加项数，调用方保证各为 1～8 |
| 输入 | `a_we`、`b_we`、`bias_we` | 1 | 阵列卷积控制器内部控制逻辑 → tile | 阵列控制器：写权重块 A、输入块 B、偏置块 |
| 输入 | `wr_row`、`wr_col`、`wr_k` | 3 | 阵列卷积控制器内部控制逻辑 → tile | 写入位置的行、列、累加项索引 |
| 输入 | `wr_value` | signed 8 | 读缓存 response_data[7:0] 或控制器 padding 零选择 → tile wr_value | 读缓存提供的输入或权重；padding 时控制器提供 0 |
| 输入 | `wr_bias` | signed 32 | 读缓存 response_data → 控制器 read_data → tile wr_bias | 读缓存提供的偏置 |
| 输出 | `busy` | 1 | tile busy → 阵列控制器 tile_busy → array_running（当前不是状态机推进条件） | 到阵列控制器：tile 正在初始化或运行 |
| 输出 | `done` | 1 | tile done → 阵列控制器 tile_done → RUN_WAIT 状态判断 | 到阵列控制器：当前累加块计算完成 |
| 输出 | `sums` | 2048 总线 | 内部阵列 sums → tile sums → 控制器按 row/col 选择 → 首个 quantizer.value | 64 个 INT32 累加值，供控制器逐个选择后处理 |

**本表信号简释**

- `start`：开始计算已经装入缓冲的这个累加块。
- `accumulate`：是否保留上一个累加块的部分和，1 保留、0 重新装偏置。
- `dw`：是否启用独立通道的 Depthwise 供数模式。
- `rows`：本块实际有效的输出通道行数。
- `cols`：本块实际有效的输出位置列数。
- `depth`：本次块计算需要处理的累加项数。
- `a_we`：本拍允许写入一个权重块 A 元素。
- `b_we`：本拍允许写入一个输入块 B 元素。
- `bias_we`：本拍允许保存偏置。
- `wr_row`：本次写入位于哪一行。
- `wr_col`：本次写入位于哪一列。
- `wr_k`：本次写入对应哪一个累加项。
- `wr_value`：本次要存入 A 或 B 的 INT8 数值。
- `wr_bias`：本次要存入偏置块的 INT32 数值。
- `busy`：本模块尚在处理当前工作。
- `done`：这个累加块完成，可能还需继续计算后续累加块。
- `sums`：64 个 PE 的 INT32 部分和打包成的一根总线。

buffer 只在 `ce=1 && busy=0 && clear=0` 时允许写入。先装好 A/B/偏置，再 start。clear 清控制状态与阵列累加状态，不要求把 A/B/偏置存储数组物理清零；使用前必须写好有效条目。

### tile 内部几个“元件”的输入输出

它们是 `systolic_tile` 中的数组或控制逻辑，不是独立 module。

| 元件 | 容量 / 状态 | 输入 | 输出与去向 |
|---|---|---|---|
| 权重块 A，`a[0:63]` | 64×INT8=64 字节 | a_we、wr_row、wr_k、wr_value | 按行和累加项读出权重，送馈数逻辑；索引 row×8+k |
| 输入块 B，`b[0:511]` | 512×INT8=512 字节 | b_we、wr_row、wr_col、wr_k、wr_value | 普通模式用第 0 行空间窗口；DW 用各行通道窗口；索引 (row×8+col)×8+k |
| 偏置块，`bias[0:7]` | 8×INT32=32 字节 | bias_we、wr_row、wr_bias | 向同一行各 PE 提供相同初始累加值 |
| 馈数与运行控制 | state、tick、锁存的 nr/nc/nk/mode/keep | start、维度、模式、accumulate、缓冲内容 | 阵列 ce/load、边界数据/valid 或 DW 数据/valid；到上级的 busy/done |

**本表内部信号简释及连接**

- `a_we` / `b_we` / `bias_we`：由阵列控制器生成，分别通知 A 块、B 块、偏置块保存数据。
- `wr_row` / `wr_col` / `wr_k`：来自阵列控制器的块内计数器，分别选择行、列、累加项。
- `wr_value`：读缓存数据或补零选择的输出，写入 A/B；`wr_bias`：读缓存的整字数据，写入 bias。
- `a` / `b` / `bias`：三个内部存储数组，内容交给 tile 馈数逻辑。
- `state`：tile 当前阶段；`tick`：本块已经运行到哪一拍。
- `nr` / `nc` / `nk`：启动时锁存的有效行数、列数、累加项数。
- `mode`：锁存的 DW 模式；`keep`：锁存的是否保留部分和。
- `start`：来自阵列控制器，要求 tile 开始；`accumulate`：来自控制器 kb 是否非零，要求保留或重装部分和。
- `ce`：允许阵列推进；`load`：通知 PE 装偏置；两者由 tile 控制逻辑送阵列。
- 边界数据及 `valid`：由 tile 从 A/B 取数并判断有效位置，送阵列 a_edge/b_edge/a_valid/b_valid；DW 则送 dw_inputs/dw_weights/dw_valid。
- `busy` / `done`：tile 告知上级“仍在运行”或“本块结束”。

普通模式按行/列错拍送入数据；DW 模式每行广播权重、每个 PE 单独取对应输入。普通模式 RUN 为 depth+14 个使能周期，DW 为 depth 个；初始化和启动另外计时。

## 14. 8×8 计算阵列

代码：[systolic_array8.sv](../rtl/systolic_array8.sv)。公共输入：`clk`、`rst_n`、`clear`、`ce`，来自 tile。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `load` | 1 | tile 内部馈数 / 模式控制逻辑 → 8×8 阵列 | tile：把 initial_sums 装入各 PE 的累加寄存器 |
| 输入 | `dw` | 1 | tile 内部馈数 / 模式控制逻辑 → 8×8 阵列 | tile：选择普通模式或 DW 模式接线 |
| 输入 | `initial_sums` | 2048 总线 | tile bias 数组 → seeds 打包总线 → 阵列 initial_sums | tile：64 个 INT32 初始值，当前按行复制偏置 |
| 输入 | `a_edge` | 64 总线 | tile 权重 A → ae → 阵列 a_edge → 最左列各 PE a_in | 普通模式左边界 8 路 INT8 权重，每行一路 |
| 输入 | `b_edge` | 64 总线 | tile 输入 B 第 0 行窗口 → be → 阵列 b_edge → 最上行各 PE b_in | 普通模式上边界 8 路 INT8 输入，每列一路 |
| 输入 | `a_valid`、`b_valid` | 8 | tile 错拍/边界判断 av/bv → 阵列 a_valid/b_valid → 边缘 PE 有效输入 | 普通模式各行权重、各列输入是否有效 |
| 输入 | `dw_inputs` | 512 总线 | tile 输入 B 各行窗口 → dwi → 阵列 dw_inputs → 各 PE a_in（DW） | DW 模式 64 路 INT8 输入，每个 PE 一路 |
| 输入 | `dw_weights` | 64 总线 | tile 权重 A → dww → 阵列 dw_weights → 各 PE b_in（DW，同行共用） | DW 模式 8 路 INT8 权重，每行一路 |
| 输入 | `dw_valid` | 64 | tile 有效行列判断 dwv → 阵列 dw_valid → 各 PE 的两个 valid（DW） | DW 模式每个 PE 的数据是否有效 |
| 输出 | `sums` | 2048 总线 | 64 个 PE sum → 阵列 sums → tile sums → 控制器结果选择 | 64 个 INT32 部分和，经 tile 返回控制器 |

**本表信号简释**

- `load`：本拍把初始值装入累加器，先不做乘加。
- `dw`：是否启用独立通道的 Depthwise 供数模式。
- `initial_sums`：准备分别装进 64 个 PE 的初始累加值。
- `a_edge`：普通模式从阵列左边进入的 8 路权重。
- `b_edge`：普通模式从阵列上边进入的 8 路图像输入。
- `a_valid`：8 位分别表示 8 行左边界权重是否有效。
- `b_valid`：8 位分别表示 8 列上边界输入是否有效。
- `dw_inputs`：DW 模式每个 PE 各自需要的图像输入。
- `dw_weights`：DW 模式每个通道行共用的权重。
- `dw_valid`：DW 模式哪些 PE 在本拍有有效输入和权重。
- `sums`：64 个 PE 的 INT32 部分和打包成的一根总线。

结果位置：`sums[(row*8+col)*32 +: 32]` 是第 row 行、第 col 列的结果。阵列本身没有 start/done 端口；运行多久、何时完成由 tile 管理。

普通卷积中，行表示输出通道，列表示输出空间位置；权重向右、输入向下传递，部分和留在 PE 内。DW 使用同一批 PE，但把每个 PE 的操作数直接接到独立输入与行权重。

## 15. 单个 PE 及其内部寄存器

代码：[systolic_pe.sv](../rtl/systolic_pe.sv)。阵列共实例化 64 个。公共输入：`clk`、`rst_n`、`clear`、`ce`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `load` | 1 | tile 初始化控制 → 阵列 load → PE load | 阵列转发：本拍装入初始值，优先于乘加 |
| 输入 | `initial_sum` | signed 32 | tile seeds → 阵列 initial_sums 中本 PE 的 32 位片段 → PE initial_sum | 本 PE 的初始偏置 |
| 输入 | `a_in`、`b_in` | signed 8 | 普通：左侧 a_out / 上方 b_out，边缘来自 tile；DW：dw_inputs / dw_weights → PE a_in/b_in | 本拍两个乘法操作数，具体接线见下表 |
| 输入 | `a_valid`、`b_valid` | 1 | 普通：相邻 PE 输出 valid 或边界 valid；DW：本 PE 对应 dw_valid → PE a_valid/b_valid | 两个操作数分别有效；同时为 1 才乘加 |
| 输出 | `a_out`、`b_out` | signed 8 | PE a_out → 右侧 PE a_in；PE b_out → 下方 PE b_in（普通模式，阵列外边缘不再消费） | 寄存后的操作数；普通模式传给右侧、下方 PE |
| 输出 | `a_out_valid`、`b_out_valid` | 1 | PE a_out_valid → 右侧 a_valid；PE b_out_valid → 下方 b_valid（普通模式，外边缘不再消费） | 与寄存后的操作数配套的有效标志 |
| 输出 | `sum` | signed 32 | PE sum → 阵列 sums 中本 PE 片段 → tile → 控制器结果选择 | 本地累加结果，接入阵列 sums 总线 |

**本表信号简释**

- `load`：本拍把初始值装入累加器，先不做乘加。
- `initial_sum`：这个 PE 在新输出块开始时应装入的偏置。
- `a_in`：本 PE 的第一个乘法操作数。
- `b_in`：本 PE 的第二个乘法操作数。
- `a_valid`：A 操作数有效指示。
- `b_valid`：B 操作数有效指示。
- `a_out`：寄存后的 A 操作数，普通模式向右传递。
- `b_out`：寄存后的 B 操作数，普通模式向下传递。
- `a_out_valid`：传出的 A 操作数是否有效。
- `b_out_valid`：传出的 B 操作数是否有效。
- `sum`：这个 PE 当前已经累加得到的 INT32 数值。

| 模式 | a_in 来源 | b_in 来源 | 转发输出的用途 |
|---|---|---|---|
| 普通卷积 | 左侧 PE 的权重；最左列来自 a_edge | 上方 PE 的输入；最上行来自 b_edge | 权重继续向右，输入继续向下 |
| DW | dw_inputs 中本 PE 的图像输入 | dw_weights 中本行权重 | 仍会更新转发寄存器，但 DW 下一单元的计算不依赖这些转发值 |

**本表信号简释**

- `a_in`：PE 第一个乘数；普通模式接左侧权重，DW 接该 PE 的独立图像输入。
- `b_in`：PE 第二个乘数；普通模式接上方图像输入，DW 接本行广播权重。
- `a_edge` / `b_edge`：tile 送到阵列左/上边界的权重/输入。
- `dw_inputs` / `dw_weights`：tile 送来的 DW 独立输入/行权重。
- 转发输出 `a_out` / `b_out`：普通模式分别送右侧/下方；DW 的下一 PE 改用独立供数，最外侧转发值也无人继续使用。

注意：DW 模式下 PE 的 a_in 接的是输入，b_in 接的是权重；这与普通模式相反，但乘法结果相同。

| 内部元件 | 输入 | 输出 | 更新条件 |
|---|---|---|---|
| 组合乘法器 `product` | signed INT8 a_in、b_in | signed 16 位乘积 | 随输入变化；不是独立实例化的 mac_unit |
| 累加寄存器 `sum` | initial_sum 或旧 sum + 符号扩展乘积 | INT32 部分和 | load 时装初值；否则两个 valid 都为 1 时累加；都受 ce 控制 |
| A/B 转发寄存器 | a_in、b_in | a_out、b_out | ce=1 的时钟沿更新 |
| 两个 valid 寄存器 | a_valid、b_valid | a_out_valid、b_out_valid | ce=1 更新；load 时输出 valid 清零 |

**本表信号简释及内部流向**

- `a_in` / `b_in`：阵列接给当前 PE 的两个操作数，同时送乘法器和转发寄存器。
- `product`：本 PE 内部乘法器的 16 位乘积，符号扩展后送累加加法器。
- `initial_sum`：阵列送来的偏置，在 load 时送入 sum 寄存器。
- `sum`：本 PE 自己保存的部分和，既反馈给累加加法器，又输出到阵列 sums。
- `a_out` / `b_out`：转发寄存器的输出，普通模式送右/下邻居。
- `a_valid` / `b_valid`：来自阵列或相邻 PE，决定本次是否相乘累加。
- `a_out_valid` / `b_out_valid`：当前 PE 寄存后的有效位，与转发数据一起送相邻 PE。
- `load`：来自 tile 经阵列转发，要求装初值；`ce`：同样来自 tile，决定是否更新。

复位/clear 优先于 ce。INT32 累加溢出按 32 位回绕，不在 PE 内做饱和。最终饱和由后处理完成。

## 16. 原算子控制器：当前负责逐元素通路

代码：[mobilefacenet_controller.sv](../rtl/mobilefacenet_controller.sv)。公共输入：`clk`、`rst_n`。

当前负责 ADD、ReLU6、COPY、FINAL；当 `USE_SYSTOLIC=0` 时也负责串行 Conv/DW。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `soft_reset`、`start` | 1 | MMIO accelerator_reset → soft_reset；队列启动经顶层分流 legacy_start → start | MMIO 软复位、顶层分流启动 |
| 输入 | `input_addr`、`output_addr`、`weight_addr`、`bias_addr`、`feature_size`、`channels`、`layer_param` | 32 | 队列 task_input/output/weight/bias/size/channels/param → 控制器对应配置输入 | 队列送来的本条任务配置 |
| 输入 | `op_type` | 4 | 队列 task_op → 原控制器 op_type | 本条算子类型 |
| 输入 | `config_valid` | 1 | 顶层 address_generator.config_valid 与 queue_output_safe 相与 → 控制器 config_valid | 地址生成合法性与顶层任务表保护检查的共同结果 |
| 输入 | `input_is_padding` | 1 | 顶层 address_generator.input_is_padding → 控制器 input_is_padding | 地址生成器的补零判断；当前逐元素路径不使用卷积补零 |
| 输入 | `output_width`、`output_height`、`output_count` | 32 | 顶层 address_generator.output_width/height/count → 控制器对应尺寸输入 | 地址生成器返回输出尺寸、数量 |
| 输入 | `mem_idle`、`cmd_ready`、`rsp_valid` | 1 | RAM 接口 idle 直接到 mem_idle；cmd_ready/rsp_valid 经顶层原通路门控到控制器 | RAM 接口空闲、接受请求、完成响应 |
| 输入 | `engine_ready`、`engine_done`、`engine_error` | 1 | 串行 Conv/DW sample_ready/done/error 经顶层算子选择 → 控制器；默认阵列版接固定 ready=1、done/error=0 | 串行卷积引擎握手；默认阵列版本中不用于逐元素计算 |
| 输出 | `cfg_input_addr`、`cfg_output_addr`、`cfg_weight_addr`、`cfg_bias_addr`、`cfg_feature_size`、`cfg_channels`、`cfg_layer_param` | 32 | 控制器 cfg_* → 顶层地址生成器；cfg_layer_param 另接量化/激活，串行版另接引擎；cfg_channels 串行版另接 Conv | 锁存后的配置，到地址生成器/数据通路 |
| 输出 | `cfg_op_type` | 4 | 控制器 cfg_op_type → 顶层地址生成器、结果/引擎状态选择、激活及串行引擎启动门控 | 锁存的算子类型，到结果选择和后处理 |
| 输出 | `cmd_valid`、`cmd_write`、`cmd_byte` | 1 | 控制器 cmd_valid/write/byte → 顶层 RAM 请求选择 → 公共 RAM 接口 | 到公共请求选择逻辑：访存控制 |
| 输出 | `address_select` | 3 | 控制器 address_select → 顶层地址选择 → command_addr → RAM 接口 | 到顶层地址选择逻辑：选输入/权重/偏置/输出/第二输入 |
| 输出 | `busy`、`done`、`error` | 1 | 控制器 busy/done/error → 顶层 exec_* 汇总 → 队列；单算子模式也送 MMIO | 到顶层/队列：本条任务状态 |
| 输出 | `datapath_clear` | 1 | 控制器 datapath_clear → bias_buffer.clear、output_buffer.clear；串行版另到两个引擎 clear | 到数据通路：新任务加载配置或软复位时清标量寄存器/引擎 |
| 输出 | `input_we`、`weight_we`、`bias_we` | 1 | 控制器 input_we/weight_we/bias_we → input_store/weight_store/bias_store 的 we | 到三个 buffer：在对应 RAM 响应有效时写入 |
| 输出 | `engine_start`、`sample_valid` | 1 | 控制器 engine_start/sample_valid → 顶层按 op 门控 → 串行 Conv/DW start/sample_valid；阵列版无引擎消费者 | 串行版本给卷积引擎的启动、样本有效信号 |
| 输出 | `output_we` | 1 | 控制器 output_we → 顶层 output_store.we | 到输出寄存器：保存后处理 INT8 结果 |
| 输出 | `input_zero` | 1 | 控制器 input_zero → 顶层输入写数据选择 → input_store.wdata | 到顶层输入选择：用 padding 零代替 RAM 数据 |
| 输出 | `output_x`、`output_y`、`element_index` | 32 | 控制器 output_x/output_y/element_index → 顶层地址生成器对应输入 | 到地址生成器：当前输出坐标/逐元素序号 |
| 输出 | `input_channel`、`output_channel` | 16 | 控制器 input_channel/output_channel → 顶层地址生成器对应输入 | 到地址生成器：当前输入/输出通道 |
| 输出 | `tap` | 6 | 控制器 tap → 地址生成器 tap、input_store 和 weight_store 的 waddr/raddr | 到地址生成器和 input/weight buffer：窗口位置；逐元素路径保持 0 |
| 输出 | `debug_state` | 5 | 控制器 debug_state → 顶层 state（内部波形观察） | 到顶层内部观察线：状态机编号 |

**本表信号简释**

- `soft_reset`：清除当前任务状态的软复位命令。
- `start`：开始执行本模块负责的一次工作。
- `input_addr`：当前算子的输入首址。
- `output_addr`：计算结果要存到哪里的首址。
- `weight_addr`：卷积权重首址，ADD 时是第二份输入首址。
- `bias_addr`：偏置数组的首址。
- `feature_size`：当前算子的输入宽高。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：卷积核、步长、补零、右移和激活等配置的组合。
- `op_type`：当前算子的类型，不是队列模式配置。
- `config_valid`：任务参数及相关地址范围是否通过检查。
- `input_is_padding`：当前输入是否需要补零。
- `output_width`：计算得到的输出宽度。
- `output_height`：计算得到的输出高度。
- `output_count`：整层最终要产生多少个输出元素。
- `mem_idle`：RAM 接口没有尚未结束的外部事务。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `rsp_valid`：之前发出的命令已有完成响应。
- `engine_ready`：串行计算引擎能接收下一对输入/权重。
- `engine_done`：串行引擎已经算完当前一个输出点。
- `engine_error`：串行引擎报告参数或执行错误。
- `cfg_input_addr`：启动时锁存的配置：输入数据首址。
- `cfg_output_addr`：启动时锁存的配置：计算结果要存到哪里的首址。
- `cfg_weight_addr`：启动时锁存的配置：卷积权重首址，ADD 时是第二份输入首址。
- `cfg_bias_addr`：启动时锁存的配置：偏置数组的首址。
- `cfg_feature_size`：启动时锁存的配置：输入宽高。
- `cfg_channels`：启动时锁存的配置：低 16 位是输入通道数，高 16 位是输出通道数。
- `cfg_layer_param`：启动时锁存的配置：卷积核、步长、补零、右移和激活等配置的组合。
- `cfg_op_type`：启动时锁存的当前算子编号，决定地址、结果和激活的选择。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_write`：这条命令是写入（1）还是读取（0）。
- `cmd_byte`：这条命令按一个字节（1）还是整字（0）访问。
- `address_select`：本次 RAM 命令应选择哪一种地址。
- `busy`：本模块尚在处理当前工作。
- `done`：当前一条算子的所有元素已处理和写回。
- `error`：本模块负责的这次工作发生错误。
- `datapath_clear`：通知本通路的标量寄存器和串行引擎清理状态。
- `input_we`：本拍把输入值存入 input_buffer。
- `weight_we`：本拍把权重或 ADD 第二输入存入 weight_buffer。
- `bias_we`：本拍允许保存偏置。
- `engine_start`：通知选中的串行引擎开始一个输出点。
- `sample_valid`：本拍输入和权重是一对可供计算的数据。
- `output_we`：本拍将后处理结果存入输出寄存器。
- `input_zero`：写输入 buffer 时选用 0，而不是 RAM 数据。
- `output_x`：当前输出位置的横坐标。
- `output_y`：当前输出位置的纵坐标。
- `element_index`：逐元素任务当前处理第几个数。
- `input_channel`：当前使用的输入通道编号。
- `output_channel`：当前计算的输出通道编号。
- `tap`：卷积核窗口内的元素编号。
- `debug_state`：当前状态机编号，便于看仿真波形。

控制器没有 rsp_data 数据端口；实际 RAM 数据线在顶层直接连到 buffer 的 wdata。控制器通过写使能决定 buffer 什么时候保存这根线上的值。

逐元素的顺序为：读 A →（ADD 再读 B）→ 后处理 → 输出寄存器 → RAM 写确认 → 下一个元素。FINAL 只复制已经算好的 128 个特征，不负责从任意特征图生成 128 维向量。

## 17. 输入缓冲、权重缓冲与基础存储

代码：[input_buffer.sv](../rtl/input_buffer.sv)、[weight_buffer.sv](../rtl/weight_buffer.sv)、[sample_buffer.sv](../rtl/sample_buffer.sv)。这三个模块的公共输入只有 `clk`。

input_buffer 和 weight_buffer 各自包装一个 sample_buffer，默认 DEPTH=49、ADDR_WIDTH=6；sample_buffer 默认 WIDTH=8。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `we` | 1 | 原控制器 input_we 或 weight_we → 对应 buffer.we → 内部 sample_buffer.we | 时钟上升沿是否写入 |
| 输入 | `waddr`、`raddr` | ADDR_WIDTH，默认 6 | 原控制器 tap → 对应 buffer.waddr/raddr → 内部 sample_buffer 同名端口 | 独立的写地址与读地址 |
| 输入 | `wdata` | signed 8；sample_buffer 为 signed WIDTH | RAM 接口 rsp_rdata[7:0]（输入路还可选择 padding 0）→ 对应 buffer.wdata → sample_buffer.wdata | 要保存的数据 |
| 输出 | `rdata` | signed 8；sample_buffer 为 signed WIDTH | sample_buffer.rdata → 外层 buffer.rdata → ADD；输入路另到结果直通，串行版另到 Conv/DW | 当前读地址的数据，组合读出 |

**本表信号简释**

- `we`：允许在这个时钟沿保存写数据。
- `waddr`：本次写入存储中的哪个位置。
- `raddr`：当前要读出存储中的哪个位置。
- `wdata`：本次准备存入的数值。
- `rdata`：从存储或寄存器读出的数值。

| 实例 | we / 地址来源 | wdata 来源 | rdata 去向 |
|---|---|---|---|
| 顶层 input_store | 控制器 input_we；waddr/raddr 都接 tap | RAM 返回低 8 位，或 input_zero 指定的 0 | ADD 的 A 输入、输入直通；串行版本还接卷积引擎 |
| 顶层 weight_store | 控制器 weight_we；waddr/raddr 都接 tap | RAM 返回低 8 位 | ADD 的 B 输入；串行版本还接卷积权重输入 |
| sample_buffer | 外层 input/weight_buffer 透传 | 外层透传 | 返回到外层包装模块 |

**本表信号简释**

- `input_we`：原控制器发给 input_store 的写使能。
- `weight_we`：原控制器发给 weight_store 的写使能。
- `we`：包装模块再原样送给内部 sample_buffer 的写使能。
- `tap`：原控制器提供的窗口位置，当前逐元素任务中为 0。
- `waddr`：选择写到 buffer 的哪个位置；`raddr`：选择从哪个位置读。
- `wdata`：RAM 返回低 8 位；input_store 可由 input_zero 改选 0。
- `input_zero`：来自原控制器，表示本次输入要补零。
- `rdata`：内部存储输出的当前元素；input_store 送 ADD 的 A 和输入直通，weight_store 送 ADD 的 B；串行版也送各卷积引擎。

当前逐元素运算只用索引 0。ADD 时 weight_buffer 存的是第二份特征，不是卷积权重。它们与阵列 tile 中的 A/B 存储是不同硬件。

越界读返回 0，越界写忽略；这些数组不带复位清零，必须先写后用。

## 18. 标量偏置缓冲

代码：[bias_buffer.sv](../rtl/bias_buffer.sv)。公共输入：`clk`、`rst_n`、`clear`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `we` | 1 | 原控制器 bias_we → bias_store.we | 原算子控制器 bias_we：保存本次偏置 |
| 输入 | `wdata` | signed 32 | RAM 接口 rsp_rdata → 顶层 rsp → bias_store.wdata | 公共 RAM 接口的整字返回 |
| 输出 | `rdata` | signed 32 | bias_store.rdata → 顶层 bias_value → 串行 Conv/DW bias；默认阵列版无运算消费者 | 到串行 Conv/DW 引擎：当前偏置 |

**本表信号简释**

- `we`：允许在这个时钟沿保存写数据。
- `wdata`：本次准备存入的数值。
- `rdata`：从存储或寄存器读出的数值。

这是一个 INT32 寄存器，clear 后为 0。默认阵列版本下该顶层实例仍在源码中，但逐元素通路不使用它，综合可能移除无效逻辑；阵列实际使用的是 tile 内 8 个偏置寄存器。

## 19. ADD 加法单元

代码：[add_unit.sv](../rtl/add_unit.sv)。组合逻辑，无时钟。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `input_a` | signed 8 | input_store.rdata → av → ADD input_a | input_buffer 的 rdata |
| 输入 | `input_b` | signed 8 | weight_store.rdata → wv → ADD input_b | weight_buffer 的 rdata，即残差第二输入 |
| 输出 | `result` | signed 32 | ADD result → add_result → 顶层 raw_result 选择 → requant.value | 两个输入符号扩展后相加，送顶层结果选择逻辑 |

**本表信号简释**

- `input_a`：ADD 的第一份输入元素。
- `input_b`：ADD 的第二份输入元素。
- `result`：两个输入符号扩展后相加得到的 INT32 和。

例如 127+127 输出 254，不在这里提前截断为 INT8。

## 20. 量化 / 右移模块

代码：[quantizer.sv](../rtl/quantizer.sv)。组合逻辑，无时钟。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `value` | signed 32 | 首个实例：控制器所选 PE sum / 顶层 raw_result → value；第二实例：activation.result → value | PE 累加值、ADD 结果、符号扩展输入，或激活结果 |
| 输入 | `quant_shift` | 8 | 首个实例：阵列控制器 clp[19:12] / 原控制器 cfg_layer_param[19:12] → quant_shift；第二实例固定接 0 | 算术右移的位数 |
| 输出 | `shifted` | signed 32 | 首个实例 shifted → 同通路 activation.value；第二实例 shifted → unused_shift（不消费） | value 算术右移后的结果，保留符号 |
| 输出 | `result` | signed 8 | 第二实例 result → 同通路 output_store.wdata；首个实例 result → unused_quant（不消费） | 将 shifted 限制到 −128～127 后的结果 |

**本表信号简释**

- `value`：进入本模块的待处理数值。
- `quant_shift`：把 INT32 数值算术右移多少位。
- `shifted`：右移后的 INT32 数值，还没有限幅为 INT8。
- `result`：将 shifted 限幅到 −128～127 后的 INT8 结果。

每条执行通路各实例化两次：第一次取 shifted 输出给激活模块；第二次 quant_shift=0，取 result 输出给输出寄存器。因此顺序是 **INT32 右移 → 激活 → INT8 限幅**。

阵列通路和逐元素通路的这两套实例互相独立。第一实例未使用的 result、第二实例未使用的 shifted 只是闲置输出连线。

## 21. ReLU / ReLU6 激活模块

代码：[relu6_unit.sv](../rtl/relu6_unit.sv)。组合逻辑，无时钟。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `value` | signed 32 | 阵列 shift.shifted / 顶层 requant.shifted → 对应 activation.value | 第一量化模块的 shifted |
| 输入 | `relu_enable` | 1 | 阵列 clp[20] / 原控制器 cfg_layer_param[20] → 对应 relu_enable | 配置 bit20：负数变 0 |
| 输入 | `relu6_enable` | 1 | 阵列 clp[21] → 阵列 relu6_enable；顶层 cfg_layer_param[21] 或 cfg_op_type==2 → 顶层 relu6_enable | 配置 bit21：同时限制上下界；独立 ReLU6 算子还会强制拉高此输入 |
| 输出 | `result` | signed 32 | activation.result → activated → 同通路 saturate.value | 激活后的值，送第二量化模块做 INT8 限幅 |

**本表信号简释**

- `value`：进入本模块的待处理数值。
- `relu_enable`：启用负数归零。
- `relu6_enable`：启用负数归零并限制正数上限。
- `result`：经过 ReLU / ReLU6 或直接通过后的 INT32 数值。

默认参数 RELU6_MAX=96，是当前输出整数尺度下表示的上限。两种 enable 都为 0 时原样通过；只启用 ReLU 时没有 96 的上限。

## 22. 输出缓冲 / 输出寄存器

代码：[output_buffer.sv](../rtl/output_buffer.sv)。公共输入：`clk`、`rst_n`、`clear`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `we` | 1 | 阵列控制器 state==POST / 原控制器 output_we → 各自 output_store.we | 所属控制器 POST 阶段：锁存结果 |
| 输入 | `wdata` | signed 8 | 各通路 saturate.result → quantized → 各自 output_store.wdata | 第二量化模块的 result |
| 输出 | `rdata` | signed 8 | output_store.rdata → out_value → 补成 32 位 cmd_wdata → 顶层请求选择 → RAM 接口 | 当前待写结果，组成 RAM 命令的 cmd_wdata 低 8 位 |

**本表信号简释**

- `we`：允许在这个时钟沿保存写数据。
- `wdata`：本次准备存入的数值。
- `rdata`：从存储或寄存器读出的数值。

它只保存**一个字节**，不是整层输出缓存。阵列控制器内部一个、顶层逐元素通路一个。值保持到控制器完成当前写回流程；clear 后为 0。

最终计算结果位于 RAM 的 OUTPUT_ADDR 对应区域，不位于任务 FIFO 或 MMIO 状态寄存器中。

## 23. 切换到串行版本时的普通卷积引擎

代码：[conv_engine.sv](../rtl/conv_engine.sv)。仅在顶层 `USE_SYSTOLIC=0` 分支实例化。公共输入：`clk`、`rst_n`、`clear`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `start` | 1 | 原控制器 engine_start 与 cfg_op_type==0 相与 → Conv start | 原控制器：开始计算一个输出点 |
| 输入 | `kernel_size` | 4 | 原控制器 cfg_layer_param[3:0] → Conv kernel_size | 配置中的 K，支持 1 或 3 |
| 输入 | `input_channels` | 16 | 原控制器 cfg_channels[15:0] → Conv input_channels | 当前卷积输入通道数 CI |
| 输入 | `bias` | signed 32 | bias_store.rdata → Conv bias | bias_buffer 保存的当前输出通道偏置 |
| 输入 | `sample_valid` | 1 | 原控制器 sample_valid 与 cfg_op_type==0 相与 → Conv sample_valid | 控制器：当前输入与权重配对有效 |
| 输出 | `sample_ready` | 1 | Conv sample_ready → 顶层 engine_ready 选择 → 原控制器 engine_ready | 到控制器：引擎可以接收这对数据 |
| 输入 | `input_value`、`weight_value` | signed 8 | input_store.rdata / weight_store.rdata → Conv input_value/weight_value | input_buffer、weight_buffer 的读出值 |
| 输出 | `busy`、`done`、`error` | 1 | Conv done/error → 顶层选择 → 原控制器 engine_done/error；busy 仅接顶层 nb 观察线 | 到顶层/原控制器：一个输出点的计算状态 |
| 输出 | `result` | signed 32 | Conv 内部 accumulator.value → result → 顶层 raw_result 选择 → requant.value | 累加 K²×CI 对后的结果，送结果选择逻辑 |

**本表信号简释**

- `start`：开始计算普通卷积的一个输出点。
- `kernel_size`：卷积核一边的大小 K。
- `input_channels`：当前普通卷积要累加的输入通道数。
- `bias`：当前输出通道的 INT32 偏置。
- `sample_valid`：本拍输入和权重是一对可供计算的数据。
- `sample_ready`：串行引擎现在可以接受一对数据。
- `input_value`：当前乘法使用的输入特征值。
- `weight_value`：当前乘法使用的权重值。
- `busy`：本模块尚在处理当前工作。
- `done`：当前输出点的 K²×CI 项已全部累加。
- `error`：本模块负责的这次工作发生错误。
- `result`：当前输出点的 INT32 卷积累加结果。

该引擎不访问 RAM，只接收已经准备好的数据对。1×1 与 3×3 使用同一个引擎。

## 24. 串行 Depthwise 引擎

代码：[depthwise_conv_engine.sv](../rtl/depthwise_conv_engine.sv)。仅在 `USE_SYSTOLIC=0` 分支实例化。公共输入：`clk`、`rst_n`、`clear`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `start` | 1 | 原控制器 engine_start 与 cfg_op_type==1 相与 → DW start | 原控制器：开始计算当前通道的一个输出点 |
| 输入 | `kernel_size` | 4 | 原控制器 cfg_layer_param[3:0] → DW kernel_size | K，支持 3 或 7 |
| 输入 | `bias` | signed 32 | bias_store.rdata → DW bias | 当前通道偏置 |
| 输入 | `sample_valid` | 1 | 原控制器 sample_valid 与 cfg_op_type==1 相与 → DW sample_valid | 控制器：当前数据对有效 |
| 输出 | `sample_ready` | 1 | DW sample_ready → 顶层 engine_ready 选择 → 原控制器 engine_ready | 到控制器：可以接收数据对 |
| 输入 | `input_value`、`weight_value` | signed 8 | input_store.rdata / weight_store.rdata → DW input_value/weight_value | 两个 buffer 的输入与权重 |
| 输出 | `busy`、`done`、`error` | 1 | DW done/error → 顶层选择 → 原控制器 engine_done/error；busy 仅接顶层 db 观察线 | 当前输出点的计算状态 |
| 输出 | `result` | signed 32 | DW 内部 accumulator.value → result → 顶层 raw_result 选择 → requant.value | 累加 K² 项后的结果，送结果选择逻辑 |

**本表信号简释**

- `start`：开始计算一个通道的一个 DW 输出点。
- `kernel_size`：卷积核一边的大小 K。
- `bias`：当前输出通道的 INT32 偏置。
- `sample_valid`：本拍输入和权重是一对可供计算的数据。
- `sample_ready`：串行引擎现在可以接受一对数据。
- `input_value`：当前乘法使用的输入特征值。
- `weight_value`：当前乘法使用的权重值。
- `busy`：本模块尚在处理当前工作。
- `done`：当前输出点的 K² 项已全部累加。
- `error`：本模块负责的这次工作发生错误。
- `result`：当前通道、当前位置的 INT32 累加结果。

没有 input_channels 输入，不进行跨通道累加。选择哪个通道由控制器和地址生成器决定。

## 25. 串行引擎内部乘法器与累加器

### mac_unit

代码：[mac_unit.sv](../rtl/mac_unit.sv)。组合逻辑，无时钟。虽然名字包含 MAC，这个模块自身只产生乘积，累加由下一模块负责。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `input_value`、`weight_value` | signed 8 | 所属 Conv/DW 引擎同名操作数输入 → 串行 mac_unit | 串行卷积引擎收到的数据对 |
| 输出 | `product` | signed 32 | 串行 mac_unit → 同一引擎内部 accumulator.product | 符号扩展后的乘积，到 accumulator |

**本表信号简释**

- `input_value`：当前乘法使用的输入特征值。
- `weight_value`：当前乘法使用的权重值。
- `product`：两个 INT8 相乘后符号扩展为 INT32 的乘积。

### accumulator

代码：[accumulator.sv](../rtl/accumulator.sv)。公共输入：`clk`、`rst_n`、`clear`。

| 方向 | 端口 | 位宽 | 信号路径（来源 → 接收方） | 接口说明 |
|---|---|---:|---|---|
| 输入 | `load_bias` | 1 | 引擎内部 begin_dot（合法空闲 start）→ accumulator.load_bias | 串行引擎：用 bias 初始化当前输出点 |
| 输入 | `enable` | 1 | 引擎内部 take（sample_valid 且 sample_ready）→ accumulator.enable | 串行引擎：本拍接收了一对数据，执行累加 |
| 输入 | `bias` | signed 32 | bias_buffer → 引擎 bias → accumulator.bias | 本输出通道偏置 |
| 输入 | `product` | signed 32 | 同一引擎 mac_unit.product → accumulator.product | mac_unit 的乘积 |
| 输出 | `value` | signed 32 | 串行 accumulator → 所属串行引擎 result | 累加值，作为串行引擎 result |

**本表信号简释**

- `load_bias`：用偏置覆盖累加寄存器，开始新的输出点。
- `enable`：本拍允许把 product 加入累加值。
- `bias`：当前输出通道的 INT32 偏置。
- `product`：两个 INT8 相乘后符号扩展为 INT32 的乘积。
- `value`：累加寄存器当前保存的 INT32 和，是本模块的输出。

优先级：复位 > clear > load_bias > enable。当前脉动阵列 PE 内直接实现乘法和 sum 寄存器，不实例化这两个串行模块。

## 26. 最容易混淆的几个连接

| 问题 | 当前工程中的实际连接 |
|---|---|
| 谁启动队列？ | CPU 写 CONTROL → MMIO start 脉冲 → 队列控制器 |
| FIFO 输出给谁？ | 给队列分发逻辑，再由执行器在启动沿锁存配置 |
| 谁控制 FIFO 出队？ | 队列控制器通过 out_ready 控制 |
| FIFO 会把图像放入 buffer 吗？ | 不会。FIFO 装任务字段；图像由执行通路通过 RAM 接口读取 |
| 当前卷积使用哪个输入 buffer？ | tile 内 B 块；不是顶层旧 input_buffer |
| 权重如何到 PE？ | RAM → RAM 接口 → 读缓存 → tile 的 A 块 → 阵列馈数 → PE |
| 输入如何到 PE？ | RAM → RAM 接口 → 读缓存 → tile 的 B 块 → 阵列馈数 → PE；padding 可直接填 0 |
| 结果如何离开阵列？ | PE sum → sums 总线 → 选择一个结果 → 右移/激活/限幅 → 输出寄存器 → RAM 接口 → RAM |
| done 是同一件事吗？ | tile_done=一个累加块完成；执行器 done=一个算子完成；队列 done=所有任务完成；MMIO 保存最终事件 |
| 输入输出表里的信号都接到芯片外面吗？ | 不是。只有第 2 节顶层端口对外，其余多为模块之间的片内连线 |

**本表相关信号简释**

- `start`：启动请求，从 CPU 的 CONTROL 写入转换为 MMIO 脉冲，再由队列分发到执行器。
- `out_data`：FIFO 的队首任务，送队列；`out_ready`：队列给 FIFO 的出队许可。
- `wr_value`：进入 tile A/B 缓冲的实际输入或权重数值，不来自 FIFO。
- `sum`：单个 PE 的部分和；`sums`：所有 PE 部分和的打包输出。
- `tile_done`：tile 给阵列控制器的一个累加块完成通知。
- 执行器 `done`：给队列的一条算子完成通知。
- 队列 `done`：给 MMIO 的整批任务完成通知。
- `STATUS.DONE`：MMIO 保存的完成状态，CPU 通过 mmio_rdata 读取。

## 27. 文档核对范围

已按当前 `mobilefacenet/rtl/` 的全部 26 个 `.sv` 文件核对模块端口，覆盖默认阵列路径、逐元素路径，以及串行备用路径；模块内部数组和寄存器另作功能说明，不把综合后可能合并或删除的逻辑当作独立物理器件。

本次只更新说明文档，没有修改 RTL；未重新运行硬件仿真。具体实现变化后，应同步更新本表。
