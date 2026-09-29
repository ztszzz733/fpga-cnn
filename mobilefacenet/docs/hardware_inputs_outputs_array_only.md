# 纯阵列版：硬件模块输入输出汇总

> 本文是仍支持 MMIO 单算子直通的上一版。2026-09-27 已改为任务队列唯一入口，当前接口请看 [队列唯一入口版说明](hardware_inputs_outputs_queue_only.md)。

依据：2026-09-23 工作区 `codex/array-only` 分支当前文件（包括未提交修改），以 `mobilefacenet/rtl/files.f` 的 **15 个 RTL 模块**为范围。旧版双通路说明保留在 [上一版文档](hardware_inputs_outputs.md)，本版连线以本文为准。

## 这版与上一版的区别

- 只有阵列计算通路，支持普通 1×1/3×3 卷积、DW 3×3/7×7 卷积；队列入口 OP=15。
- 队列 `exec_start` 直接接阵列卷积控制器 `start`，`task_*` 只送这一个控制器，不再分流到原算子控制器。
- 已移出的 ADD、ReLU6、COPY、FINAL 和串行 Conv/DW 模块不属于当前有效硬件；不能按旧图继续连。
- 后处理变为一个 quantizer 完成“INT32 算术右移 → INT8 饱和”，再进入输出寄存器。`LAYER_PARAM[31:20]` 必须为 0。
- `queue_base/queue_end` 送阵列卷积控制器内部地址保护；没有旧版原算子通路的顶层保护分支。

## 怎么看这些表

每行是一个实际端口，写明方向、位宽及来源到去向；表后逐个简释。`signed` 表示有符号数。打包总线按位传输，其内部 INT8/INT32 数值按有符号解释。地址按字节计数。

“顶层”是包住整个加速器的大框；“顶层选择逻辑”是框内几组组合连线，不是另一个控制器。表中 `模块.端口` 表示该模块的接口名。普通线可在框图上标 1/32 等位宽；不是芯片外部物理引脚。

`valid && ready` 在时钟上升沿同时成立，表示请求/数据被接收；不等于计算已完成。`clk` 从外部统一分发，`rst_n` 低有效异步复位；`clear` 是同步清理，`ce` 是时钟使能。

## 总体连接

```text
CPU ──MMIO──> 寄存器组 ──配置/start──> 队列控制器
                                          │
                  内部：任务读取器 → FIFO → 任务分发
                                          │ exec_start + task_*
                                          ▼
                                   阵列卷积控制器
                         ┌────────────────┼────────────────────┐
                         ▼                ▼                    ▼
                 窗口/通用地址生成     双路读缓存             tile
                                          │          A/B/偏置块 + 馈数控制
                                          │                    ▼
                                          │               8×8 阵列
                                          │                    │ sums
                                          │                    ▼
                                          │             quantizer → 输出寄存器
                                          │                          │ 写命令
任务读取请求 ───────────┐                  └──阵列读/写命令─────────────┘
                       ▼
                 两路 RAM 请求选择 ──> RAM 访问接口 ⇄ 外部 RAM
```

上图是层级/功能关系，不是所有端口的直接接线；读缓存请求和输出寄存器数据由阵列控制器组织成访存命令。RAM 的响应经选择逻辑返回当前请求方。控制器、tile、阵列是三层：控制器启动整层，tile 管理当前块，阵列由 ce/load/valid 驱动。

## 1. 加速器顶层

代码：[mobilefacenet_accelerator_top.sv](../rtl/mobilefacenet_accelerator_top.sv)。

整个加速器的大框：包含子模块、连线、两路 RAM 请求选择和整体状态选择。不是额外的计算元件。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 外部系统时钟 → 顶层 clk → 内部所有时序模块 |
| 输入 | `rst_n` | 1 | 外部系统复位 → 顶层 rst_n → 内部带复位的模块 |
| 输入 | `mmio_addr` | 32 | CPU / 测试程序 → 顶层同名端口 → MMIO 寄存器组同名输入 |
| 输入 | `mmio_wdata` | 32 | CPU / 测试程序 → 顶层同名端口 → MMIO 寄存器组同名输入 |
| 输入 | `mmio_we` | 1 | CPU / 测试程序 → 顶层同名端口 → MMIO 寄存器组同名输入 |
| 输入 | `mmio_re` | 1 | CPU / 测试程序 → 顶层同名端口 → MMIO 寄存器组同名输入 |
| 输出 | `mmio_rdata` | 32 | MMIO 寄存器组同名输出 → 顶层 → CPU / 测试程序 |
| 输出 | `mmio_ready` | 1 | MMIO 寄存器组同名输出 → 顶层 → CPU / 测试程序 |
| 输出 | `mem_addr` | 32 | RAM 访问接口同名输出 → 顶层 → 外部 RAM |
| 输出 | `mem_wdata` | 32 | RAM 访问接口同名输出 → 顶层 → 外部 RAM |
| 输出 | `mem_read` | 1 | RAM 访问接口同名输出 → 顶层 → 外部 RAM |
| 输出 | `mem_write` | 1 | RAM 访问接口同名输出 → 顶层 → 外部 RAM |
| 输入 | `mem_rdata` | 32 | 外部 RAM → 顶层同名输入 → RAM 访问接口同名输入 |
| 输入 | `mem_ready` | 1 | 外部 RAM → 顶层同名输入 → RAM 访问接口同名输入 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
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

CPU 写入 RAM 的数据准备通道由外部系统提供，不包含在加速器 MMIO 接口中。CPU 和外部 RAM 都在顶层大框外。当前顶层只有 BASE_ADDR、TASK_PREFETCH_DEPTH 两个参数；已没有 USE_SYSTOLIC、RELU6_MAX。

## 2. MMIO 寄存器组

代码：[accelerator_regs.sv](../rtl/accelerator_regs.sv)。

接收 CPU 的寄存器访问，保存配置，发启动/复位脉冲并保存完成/错误状态。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `mmio_addr` | 32 | CPU 经顶层同名 MMIO 端口 → 本模块 `mmio_addr` |
| 输入 | `mmio_wdata` | 32 | CPU 经顶层同名 MMIO 端口 → 本模块 `mmio_wdata` |
| 输入 | `mmio_we` | 1 | CPU 经顶层同名 MMIO 端口 → 本模块 `mmio_we` |
| 输入 | `mmio_re` | 1 | CPU 经顶层同名 MMIO 端口 → 本模块 `mmio_re` |
| 输出 | `mmio_rdata` | 32 | 寄存器组输出 → 顶层同名端口 → CPU |
| 输出 | `mmio_ready` | 1 | 寄存器组输出 → 顶层同名端口 → CPU |
| 输出 | `accelerator_start` | 1 | 寄存器组 accelerator_start → 顶层 start → 队列 start |
| 输出 | `accelerator_reset` | 1 | 寄存器组 accelerator_reset → 顶层 reset → 队列 soft_reset、阵列控制器 clear、RAM 接口 cancel |
| 输出 | `op_type` | 4 | 本模块 `op_type` → 队列控制器对应输入 |
| 输入 | `accelerator_busy` | 1 | 队列 active、阵列 busy、RAM 接口 idle → 顶层忙状态组合 → 寄存器组 accelerator_busy |
| 输入 | `accelerator_done` | 1 | 队列运行时选队列 done/error，否则选阵列控制器 done/error → 寄存器组对应输入 |
| 输入 | `accelerator_error` | 1 | 队列运行时选队列 done/error，否则选阵列控制器 done/error → 寄存器组对应输入 |
| 输出 | `input_addr` | 32 | 本模块 `input_addr` → 队列控制器对应输入 |
| 输出 | `output_addr` | 32 | 本模块 `output_addr` → 队列控制器对应输入 |
| 输出 | `weight_addr` | 32 | 本模块 `weight_addr` → 队列控制器对应输入 |
| 输出 | `bias_addr` | 32 | 本模块 `bias_addr` → 队列控制器对应输入 |
| 输出 | `feature_size` | 32 | 本模块 `feature_size` → 队列控制器对应输入 |
| 输出 | `channels` | 32 | 本模块 `channels` → 队列控制器对应输入 |
| 输出 | `layer_param` | 32 | 本模块 `layer_param` → 队列控制器对应输入 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `mmio_addr`：CPU 要读写哪一个配置寄存器。
- `mmio_wdata`：CPU 本次准备写入寄存器的值。
- `mmio_we`：CPU 正在请求写寄存器。
- `mmio_re`：CPU 正在请求读寄存器。
- `mmio_rdata`：返回给 CPU 的寄存器内容。
- `mmio_ready`：本次寄存器访问可以在当前时钟沿被接受。
- `accelerator_start`：通知后级开始执行一次配置好的任务。
- `accelerator_reset`：通知后级清状态并取消当前任务。
- `op_type`：0=普通卷积、1=DW；MMIO/队列入口的 15 表示启动任务队列。
- `accelerator_busy`：整个加速器还没空闲，暂不能接新配置任务。
- `accelerator_done`：本次对 CPU 可见的任务执行完成事件。
- `accelerator_error`：本次执行发生错误的事件。
- `input_addr`：输入数据首址；启动队列时改为任务表首址。
- `output_addr`：计算结果要存到哪里的首址。
- `weight_addr`：卷积权重数组的首址。
- `bias_addr`：偏置数组的首址。
- `feature_size`：输入宽高；启动队列时改为任务条数。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：核大小、步长、补零、右移位数；高 12 位必须为 0。

9 个 MMIO 地址没有改变。CPU 写配置必须在未锁定时进行；忙时普通配置写入不会改变当前配置，重复 START 会记录错误。CONTROL 的 RESET 优先于 START。

## 3. 队列控制器

代码：[task_queue_controller.sv](../rtl/task_queue_controller.sv)。

取一批任务、允许 FIFO 出队、启动唯一的阵列卷积控制器，等待其完成后推进下一条。内部包含任务读取器和 FIFO。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `soft_reset` | 1 | MMIO accelerator_reset → 顶层 reset → 队列 soft_reset |
| 输入 | `start` | 1 | MMIO accelerator_start → 顶层 start → 队列 start |
| 输入 | `op_type` | 4 | MMIO 寄存器组对应配置输出 → 本模块 `op_type` |
| 输入 | `input_addr` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `input_addr` |
| 输入 | `output_addr` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `output_addr` |
| 输入 | `weight_addr` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `weight_addr` |
| 输入 | `bias_addr` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `bias_addr` |
| 输入 | `feature_size` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `feature_size` |
| 输入 | `channels` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `channels` |
| 输入 | `layer_param` | 32 | MMIO 寄存器组对应配置输出 → 本模块 `layer_param` |
| 输入 | `exec_busy` | 1 | 阵列控制器 busy/done/error → 顶层同名 exec_* 连线 → 队列对应输入 |
| 输入 | `exec_done` | 1 | 阵列控制器 busy/done/error → 顶层同名 exec_* 连线 → 队列对应输入 |
| 输入 | `exec_error` | 1 | 阵列控制器 busy/done/error → 顶层同名 exec_* 连线 → 队列对应输入 |
| 输入 | `mem_idle` | 1 | RAM 接口 idle → 顶层 mem_idle → 队列 mem_idle |
| 输出 | `exec_start` | 1 | 队列 exec_start → 顶层 sx_start（直接连线）→ 阵列卷积控制器 start |
| 输出 | `task_op` | 4 | FIFO 队首或单算子 MMIO 配置 → 队列 task_op → 阵列控制器 op |
| 输出 | `task_input` | 32 | FIFO 队首或 MMIO input_addr → 队列 task_input → 阵列控制器 ia |
| 输出 | `task_output` | 32 | FIFO 队首或 MMIO output_addr → 队列 task_output → 阵列控制器 oa |
| 输出 | `task_weight` | 32 | FIFO 队首或 MMIO weight_addr → 队列 task_weight → 阵列控制器 wa |
| 输出 | `task_bias` | 32 | FIFO 队首或 MMIO bias_addr → 队列 task_bias → 阵列控制器 ba |
| 输出 | `task_size` | 32 | FIFO 队首或 MMIO feature_size → 队列 task_size → 阵列控制器 fs |
| 输出 | `task_channels` | 32 | FIFO 队首或 MMIO channels → 队列 task_channels → 阵列控制器 ch |
| 输出 | `task_param` | 32 | FIFO 队首或 MMIO layer_param → 队列 task_param → 阵列控制器 lp |
| 输出 | `active` | 1 | 队列 active → 顶层状态选择和忙汇总；同时 → 阵列控制器 queue_active |
| 输出 | `done` | 1 | 队列 done/error → 顶层状态选择 → MMIO accelerator_done/accelerator_error |
| 输出 | `error` | 1 | 队列 done/error → 顶层状态选择 → MMIO accelerator_done/accelerator_error |
| 输出 | `fetch_phase` | 1 | 队列 fetch_phase → 顶层两路 RAM 请求选择、响应有效门控 |
| 输出 | `fetch_valid` | 1 | 内部读取器 cmd_valid → 队列 fetch_valid → 顶层请求选择 → RAM 接口 cmd_valid |
| 输入 | `fetch_ready` | 1 | RAM 接口 cmd_ready → 顶层与 fetch_phase 相与 → 队列 fetch_ready → 内部读取器 cmd_ready |
| 输出 | `fetch_addr` | 32 | 内部读取器 cmd_addr → 队列 fetch_addr → 顶层请求选择 → RAM 接口 cmd_addr |
| 输入 | `fetch_rsp_valid` | 1 | RAM 接口 rsp_valid → 顶层与 fetch_phase 相与 → 队列 fetch_rsp_valid → 读取器 rsp_valid |
| 输入 | `fetch_rsp_data` | 32 | RAM 接口 rsp_rdata → 顶层 bus_rdata → 队列 fetch_rsp_data → 读取器 rsp_data |
| 输出 | `queue_base` | 32 | 队列对应输出 → 阵列卷积控制器 queue_base/queue_end → 其内部 safe_table 保护逻辑 |
| 输出 | `queue_end` | 64 | 队列对应输出 → 阵列卷积控制器 queue_base/queue_end → 其内部 safe_table 保护逻辑 |
| 输出 | `completed` | 32 | 队列 completed → 顶层 queue_completed（仅内部调试，不接 MMIO） |
| 输出 | `fetched` | 32 | 队列 fetched → 顶层 queue_fetched（仅内部调试，不接 MMIO） |
| 输出 | `buffered` | 32 | 内部 FIFO level → 队列 buffered → 顶层 queue_buffered（仅内部调试） |
| 输出 | `debug_state` | 4 | 队列 debug_state → 顶层 queue_state（仅内部调试） |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `soft_reset`：清除当前任务状态的软复位命令。
- `start`：开始执行本模块负责的一次工作。
- `op_type`：0=普通卷积、1=DW；MMIO/队列入口的 15 表示启动任务队列。
- `input_addr`：输入数据首址；启动队列时改为任务表首址。
- `output_addr`：计算结果要存到哪里的首址。
- `weight_addr`：卷积权重数组的首址。
- `bias_addr`：偏置数组的首址。
- `feature_size`：输入宽高；启动队列时改为任务条数。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：核大小、步长、补零、右移位数；高 12 位必须为 0。
- `exec_busy`：阵列卷积控制器仍在执行当前任务。
- `exec_done`：阵列卷积控制器已完成一整条任务。
- `exec_error`：阵列卷积控制器报告本条任务失败。
- `mem_idle`：RAM 接口没有尚未结束的外部事务。
- `exec_start`：直接启动唯一的阵列卷积控制器，不再进行算子通路分流。
- `task_op`：当前这一条任务的算子类型。
- `task_input`：当前任务输入数据的首址。
- `task_output`：当前任务输出结果的首址。
- `task_weight`：当前卷积任务的权重首址。
- `task_bias`：当前任务偏置的首址。
- `task_size`：当前任务输入宽高。
- `task_channels`：当前任务输入/输出通道数。
- `task_param`：当前卷积的核大小、步长、补零和右移配置。
- `active`：队列状态机正在处理一批任务。
- `done`：整个任务队列全部执行成功。
- `error`：任务头或某一条任务出错，队列停止后续执行。
- `fetch_phase`：现在处在读取一批任务描述符的阶段。
- `fetch_valid`：任务读取器正在请求读取一个任务字。
- `fetch_ready`：任务字读取请求可以被 RAM 接口接受。
- `fetch_addr`：这个任务字在 RAM 中的地址。
- `fetch_rsp_valid`：一个任务字已经返回。
- `fetch_rsp_data`：返回的那个 32 位任务字。
- `queue_base`：整张任务表的起始字节地址。
- `queue_end`：整张任务表的结束边界，不包含这个地址本身。
- `completed`：已经成功执行完的任务条数。
- `fetched`：已经完整读出并放入 FIFO 的累计任务条数。
- `buffered`：当前 FIFO 中尚未出队的任务条数。
- `debug_state`：当前状态机编号，便于看仿真波形。

队列表要求首址 32 字节对齐。queue_end 是不含在任务表内的结束边界，等于 queue_base + 任务数×32。默认先取最多 4 条，再顺序执行；不边算边预取下一批。

队列模式的 task_* 来自 FIFO 队首；非队列模式直接转发 MMIO 配置。允许出队的上升沿同时启动执行器并锁存配置。task_input/output/weight/bias 都是地址，task_output 不是计算结果。

## 4. 任务读取器

代码：[task_descriptor_reader.sv](../rtl/task_descriptor_reader.sv)。

只读取任务描述符：每次收一个 32 位任务字，读满 8 次后发布完整 256 位任务。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | 队列 flush（soft_reset 或 begin_queue）→ 读取器 clear |
| 输入 | `start` | 1 | 队列的 FILL、reader_idle、FIFO 可写、尚有任务等条件 → 读取器 start |
| 输入 | `base_address` | 32 | 队列 queue_base + fetched×32 → 读取器 base_address |
| 输出 | `idle` | 1 | 本模块 `idle` → 队列控制器内部调度逻辑 |
| 输出 | `cmd_valid` | 1 | 读取器 cmd_valid → 队列 fetch_valid → 顶层选择 → RAM 接口 cmd_valid |
| 输入 | `cmd_ready` | 1 | RAM 接口 cmd_ready → 顶层 fetch_phase 门控 → 队列 fetch_ready → 读取器 cmd_ready |
| 输出 | `cmd_addr` | 32 | 读取器 cmd_addr → 队列 fetch_addr → 顶层选择 → RAM 接口 cmd_addr |
| 输入 | `rsp_valid` | 1 | RAM 接口 rsp_valid → 顶层 fetch_phase 门控 → 队列 fetch_rsp_valid → 读取器 rsp_valid |
| 输入 | `rsp_data` | 32 | RAM 接口 rsp_rdata → 顶层 bus_rdata → 队列 fetch_rsp_data → 读取器 rsp_data |
| 输出 | `descriptor_valid` | 1 | 读取器 descriptor_valid → FIFO in_valid；同时供队列判断入队事件 |
| 输入 | `descriptor_ready` | 1 | FIFO in_ready → 读取器 descriptor_ready |
| 输出 | `descriptor` | 256 | 读取器 words → descriptor → FIFO in_data |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `start`：开始读 base_address 指向的这一条任务。
- `base_address`：本次要读的那一条任务的首址。
- `idle`：当前可以开始读取下一条任务。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_data`：完成响应附带的 32 位读数据。
- `descriptor_valid`：完整的 8 个任务字已经收齐，可以交付。
- `descriptor_ready`：FIFO 现在能接收一整条任务。
- `descriptor`：一整条 256 位任务说明，不是图像数据。

words[255:0] 保存逐次读回的字，word_index 指示第几个字，address 保存当前读地址。WAIT_WORD 表示等待一个 RAM 字返回；它不是独立模块。PUBLISH 时整条任务保持到 FIFO 接收。此读取器不读取图像、权重或偏置。

## 5. 任务 FIFO

代码：[task_descriptor_fifo.sv](../rtl/task_descriptor_fifo.sv)。

保存尚未分发的任务，默认深度 4，每条 256 位。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | 队列 flush（软复位或开始新队列）→ FIFO clear |
| 输入 | `in_valid` | 1 | 读取器 descriptor_valid → FIFO in_valid |
| 输出 | `in_ready` | 1 | FIFO in_ready → 读取器 descriptor_ready；同时供队列判断能否开始读取 |
| 输入 | `in_data` | 256 | 读取器 descriptor → FIFO in_data |
| 输出 | `out_valid` | 1 | FIFO out_valid → 队列 head_valid → 分发条件判断 |
| 输入 | `out_ready` | 1 | 队列 head_ready（允许分发且执行器/RAM 空闲）→ FIFO out_ready |
| 输出 | `out_data` | 256 | FIFO out_data → 队列 head_data → 解码为 task_* → 阵列控制器配置输入 |
| 输出 | `level` | 32 | FIFO level → 队列 buffered → 队列批量读取判断及顶层调试线 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `in_valid`：写入方正在提供一条有效任务。
- `in_ready`：FIFO 当前还有空间接收任务。
- `in_data`：准备存入 FIFO 的整条任务。
- `out_valid`：FIFO 当前有一条可取出的队首任务。
- `out_ready`：队列控制器允许当前队首任务出队。
- `out_data`：当前排在 FIFO 最前面的任务内容。
- `level`：FIFO 此刻保存的任务数量。

内部 storage 保存描述符，head/tail 是读写指针，used 是数量。out_valid 与 out_ready 同时为 1 时出队。FIFO 给队列送数据，队列给 FIFO 送出队控制；FIFO 不把图像送入 tile。clear 清指针/计数，不要求擦除 storage 的所有位。

## 6. RAM 访问接口

代码：[accelerator_mem_if.sv](../rtl/accelerator_mem_if.sv)。

把内部读写命令变成外部 RAM 事务；描述符读取和阵列运算共用这一个接口。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `cancel` | 1 | MMIO accelerator_reset → 顶层 reset → RAM 接口 cancel |
| 输入 | `cmd_valid` | 1 | 顶层按 fetch_phase 选择队列 fetch_valid 或阵列 cmd_valid → RAM 接口 cmd_valid |
| 输出 | `cmd_ready` | 1 | 本模块 `cmd_ready` → 顶层响应分发 → 当前请求方 |
| 输入 | `cmd_write` | 1 | 取任务时顶层固定接 0；算子运行时接阵列控制器 cmd_write/cmd_byte → RAM 接口 |
| 输入 | `cmd_byte` | 1 | 取任务时顶层固定接 0；算子运行时接阵列控制器 cmd_write/cmd_byte → RAM 接口 |
| 输入 | `cmd_addr` | 32 | 顶层按 fetch_phase 选择 fetch_addr 或阵列 cmd_addr → RAM 接口 cmd_addr |
| 输入 | `cmd_wdata` | 32 | 阵列控制器 cmd_wdata（来自输出寄存器）→ 顶层 sx_wdata → RAM 接口 cmd_wdata |
| 输出 | `rsp_valid` | 1 | 本模块 `rsp_valid` → 顶层响应分发 → 当前请求方 |
| 输出 | `rsp_rdata` | 32 | 本模块 `rsp_rdata` → 顶层响应分发 → 当前请求方 |
| 输出 | `idle` | 1 | RAM 接口 idle → 队列 mem_idle；同时 → 顶层 MMIO 忙状态汇总 |
| 输出 | `mem_addr` | 32 | RAM 接口对应输出 → 顶层同名端口 → 外部 RAM |
| 输出 | `mem_wdata` | 32 | RAM 接口对应输出 → 顶层同名端口 → 外部 RAM |
| 输出 | `mem_read` | 1 | RAM 接口对应输出 → 顶层同名端口 → 外部 RAM |
| 输出 | `mem_write` | 1 | RAM 接口对应输出 → 顶层同名端口 → 外部 RAM |
| 输入 | `mem_rdata` | 32 | 外部 RAM → 顶层同名输入 → RAM 接口对应输入 |
| 输入 | `mem_ready` | 1 | 外部 RAM → 顶层同名输入 → RAM 接口对应输入 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
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

cmd_valid 与 cmd_ready 同时成立表示命令被接收；rsp_valid 表示稍后执行完成。接口没有 rsp_ready，当前控制器在等待状态接收响应。

INT8 写采用整字读改写：读取原 32 位字，替换一个字节，再写回，保护相邻三个字节。等待 mem_ready 时请求保持稳定。cancel 排空已发事务：取消在字节写读阶段发生时不继续写，已进入写阶段则等写完。读缓存未命中和描述符读取都用整字读；接口虽保留字节读能力，当前集成读取通常不走它。

## 7. 阵列卷积控制器

代码：[systolic_conv_controller.sv](../rtl/systolic_conv_controller.sv)。

锁存整条任务，安排地址计算、偏置/权重/输入加载、tile 运行、量化和写回。它内部包含窗口地址模块、读缓存、tile、quantizer、output_buffer。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | MMIO accelerator_reset → 顶层 reset → 阵列控制器 clear |
| 输入 | `start` | 1 | 队列 exec_start → 顶层 sx_start（直接相连）→ 阵列控制器 start |
| 输入 | `ia` | 32 | 队列 task_input → 顶层 task_ia → 阵列控制器 ia |
| 输入 | `oa` | 32 | 队列 task_output → 顶层 task_oa → 阵列控制器 oa |
| 输入 | `wa` | 32 | 队列 task_weight → 顶层 task_wa → 阵列控制器 wa |
| 输入 | `ba` | 32 | 队列 task_bias → 顶层 task_ba → 阵列控制器 ba |
| 输入 | `fs` | 32 | 队列 task_size → 顶层 task_fs → 阵列控制器 fs |
| 输入 | `ch` | 32 | 队列 task_channels → 顶层 task_ch → 阵列控制器 ch |
| 输入 | `lp` | 32 | 队列 task_param → 顶层 task_lp → 阵列控制器 lp |
| 输入 | `op` | 4 | 队列 task_op → 阵列控制器 op |
| 输入 | `queue_active` | 1 | 队列 active → 顶层 queue_active → 阵列控制器 queue_active |
| 输入 | `queue_base` | 32 | 队列同名输出 → 阵列控制器对应输入 → 内部 safe_table 地址保护 |
| 输入 | `queue_end` | 64 | 队列同名输出 → 阵列控制器对应输入 → 内部 safe_table 地址保护 |
| 输出 | `busy` | 1 | 控制器 busy → sx_busy → 队列 exec_busy、MMIO 忙状态汇总及阵列响应门控 |
| 输出 | `done` | 1 | 控制器 done/error → 顶层 exec_done/exec_error → 队列；单算子时也送 MMIO 状态输入 |
| 输出 | `error` | 1 | 控制器 done/error → 顶层 exec_done/exec_error → 队列；单算子时也送 MMIO 状态输入 |
| 输出 | `cmd_valid` | 1 | 本模块 `cmd_valid` → 顶层公共 RAM 请求选择 → RAM 接口 |
| 输入 | `cmd_ready` | 1 | RAM 接口 cmd_ready → 顶层按“非 fetch_phase 且 sx_busy”门控 → 控制器 cmd_ready |
| 输出 | `cmd_write` | 1 | 本模块 `cmd_write` → 顶层公共 RAM 请求选择 → RAM 接口 |
| 输出 | `cmd_byte` | 1 | 本模块 `cmd_byte` → 顶层公共 RAM 请求选择 → RAM 接口 |
| 输出 | `cmd_addr` | 32 | 本模块 `cmd_addr` → 顶层公共 RAM 请求选择 → RAM 接口 |
| 输出 | `cmd_wdata` | 32 | 本模块 `cmd_wdata` → 顶层公共 RAM 请求选择 → RAM 接口 |
| 输入 | `rsp_valid` | 1 | RAM 接口 rsp_valid → 顶层按“非 fetch_phase 且 sx_busy”门控 → 控制器 rsp_valid |
| 输入 | `rsp_data` | 32 | RAM 接口 rsp_rdata → 顶层 bus_rdata → 控制器 rsp_data |
| 输出 | `array_running` | 1 | 内部 tile busy → 控制器 array_running → 顶层 array_running（内部观察线） |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `start`：锁存本条任务配置并开始整层计算。
- `ia`：输入特征的首址。
- `oa`：输出结果的首址。
- `wa`：权重的首址。
- `ba`：偏置的首址。
- `fs`：输入特征的宽高配置。
- `ch`：输入、输出通道数配置。
- `lp`：核大小、步长、补零、右移配置；不再支持激活开关。
- `op`：本次计算类型，合法值为普通卷积 0 或 DW 1。
- `queue_active`：本条计算由队列调度，需要保护任务表地址范围。
- `queue_base`：整张任务表的起始字节地址。
- `queue_end`：整张任务表的结束边界，不包含这个地址本身。
- `busy`：本模块尚在处理当前工作。
- `done`：整条卷积任务的所有输出已完成写回。
- `error`：本模块负责的这次工作发生错误。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `cmd_write`：这条命令是写入（1）还是读取（0）。
- `cmd_byte`：这条命令按一个字节（1）还是整字（0）访问。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `cmd_wdata`：该命令准备写入的数据。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_data`：完成响应附带的 32 位读数据。
- `array_running`：tile 处于初始化或运行中，不保证每拍都有有效乘加。

ia/oa/wa/ba/fs/ch/lp/op 在 start 时锁存为 cia/coa/cwa/cba/cfs/cch/clp/cop。mb、nb、kb 分别是输出通道块、输出空间块、累加块起点；row、col、kidx 是块内位置。

保护任务表的 safe_table 现在位于本控制器内部，使用 queue_active、queue_base、queue_end、锁存的输出首址 coa、输出数 count。它与地址生成器 valid 一起决定 CHECK 能否通过；已没有旧版顶层为原算子通路设置的 queue_output_safe。

读取按偏置 → A 权重块 → B 输入块进行。每次最多 8×8 个输出、8 个累加项；tile 完成后，仍有累加项就继续装下一块，全部累加完再逐个量化写回。只有整条任务都写完才 done。

## 8. 卷积窗口地址生成

代码：[conv_window_address.sv](../rtl/conv_window_address.sv)。

把阵列分块坐标转换成卷积坐标，并调用内部 address_generator 计算 RAM 地址。组合逻辑，无时钟。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `ia` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `oa` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `wa` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `ba` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `fs` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `ch` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `lp` | 32 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `op` | 4 | 阵列控制器 cia/coa/cwa/cba/cfs/cch/clp/cop → 窗口模块对应输入 |
| 输入 | `row_base` | 32 | 阵列控制器 mb/nb/kb → 窗口 row_base/col_base/k_base |
| 输入 | `col_base` | 32 | 阵列控制器 mb/nb/kb → 窗口 row_base/col_base/k_base |
| 输入 | `k_base` | 32 | 阵列控制器 mb/nb/kb → 窗口 row_base/col_base/k_base |
| 输入 | `row` | 3 | 阵列控制器 row/col/kidx → 窗口对应输入 |
| 输入 | `col` | 3 | 阵列控制器 row/col/kidx → 窗口对应输入 |
| 输入 | `k_index` | 3 | 阵列控制器 row/col/kidx → 窗口对应输入 |
| 输出 | `input_address` | 32 | 内部地址生成器对应输出 → 窗口对应输出 → 控制器读地址选择 → 读缓存 req_addr |
| 输出 | `weight_address` | 32 | 内部地址生成器对应输出 → 窗口对应输出 → 控制器读地址选择 → 读缓存 req_addr |
| 输出 | `bias_address` | 32 | 内部地址生成器对应输出 → 窗口对应输出 → 控制器读地址选择 → 读缓存 req_addr |
| 输出 | `output_address` | 32 | 内部地址生成器 output_address → 窗口 output_address → 控制器写地址选择 → cmd_addr |
| 输出 | `padding` | 1 | 内部地址生成器 input_is_padding → 窗口 padding → 控制器补零判断和 tile 写控制 |
| 输出 | `valid` | 1 | 内部地址生成器 config_valid → 窗口 valid → 控制器 CHECK 合法性判断 |
| 输出 | `spatial_count` | 32 | 本模块 `spatial_count` → 阵列控制器内部控制逻辑 |
| 输出 | `reduction_count` | 32 | 本模块 `reduction_count` → 阵列控制器内部控制逻辑 |
| 输出 | `output_count` | 32 | 本模块 `output_count` → 阵列控制器内部控制逻辑 |

**本表信号简释**

- `ia`：输入特征的首址。
- `oa`：输出结果的首址。
- `wa`：权重的首址。
- `ba`：偏置的首址。
- `fs`：输入特征的宽高配置。
- `ch`：输入、输出通道数配置。
- `lp`：核大小、步长、补零、右移配置；不再支持激活开关。
- `op`：本次计算类型，合法值为普通卷积 0 或 DW 1。
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

row 表示输出通道，col 表示展平的输出空间位置，k_index 表示累加项。普通卷积 reduction_count=CI×K²，DW 为 K²。spatial_count=OH×OW，output_count=CO×OH×OW。窗口按需要取数，不在外部 RAM 中构造完整 im2col 大矩阵。

## 9. 通用地址生成器

代码：[address_generator.sv](../rtl/address_generator.sv)。

在卷积窗口模块内部，根据基址、配置和坐标产生地址，并检查尺寸、范围和禁止重叠。组合逻辑，无时钟。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `input_base` | 32 | 窗口模块 ia/oa/wa/ba → 地址生成器四个 base 输入 |
| 输入 | `output_base` | 32 | 窗口模块 ia/oa/wa/ba → 地址生成器四个 base 输入 |
| 输入 | `weight_base` | 32 | 窗口模块 ia/oa/wa/ba → 地址生成器四个 base 输入 |
| 输入 | `bias_base` | 32 | 窗口模块 ia/oa/wa/ba → 地址生成器四个 base 输入 |
| 输入 | `feature_size` | 32 | 窗口模块 fs/ch/lp/op → 地址生成器对应配置输入 |
| 输入 | `channels` | 32 | 窗口模块 fs/ch/lp/op → 地址生成器对应配置输入 |
| 输入 | `layer_param` | 32 | 窗口模块 fs/ch/lp/op → 地址生成器对应配置输入 |
| 输入 | `op_type` | 4 | 窗口模块 fs/ch/lp/op → 地址生成器对应配置输入 |
| 输入 | `output_x` | 32 | 窗口空间序号 pos 除以/取余输出宽 ow → 地址生成器 output_x/output_y |
| 输入 | `output_y` | 32 | 窗口空间序号 pos 除以/取余输出宽 ow → 地址生成器 output_x/output_y |
| 输入 | `element_index` | 32 | 窗口实例固定接 32 位常量 0 → element_index；当前模块不使用该输入 |
| 输入 | `input_channel` | 16 | 窗口模块归约索引/通道块计算结果 → 地址生成器对应通道输入 |
| 输入 | `output_channel` | 16 | 窗口模块归约索引/通道块计算结果 → 地址生成器对应通道输入 |
| 输入 | `tap` | 6 | 窗口归约序号对 K² 取余 → 地址生成器 tap |
| 输出 | `input_address` | 32 | 本模块 `input_address` → 卷积窗口地址模块对应输出 |
| 输出 | `weight_address` | 32 | 本模块 `weight_address` → 卷积窗口地址模块对应输出 |
| 输出 | `bias_address` | 32 | 本模块 `bias_address` → 卷积窗口地址模块对应输出 |
| 输出 | `output_address` | 32 | 本模块 `output_address` → 卷积窗口地址模块对应输出 |
| 输出 | `second_address` | 32 | 地址生成器固定输出 0 → 窗口 second_unused；没有后续消费者 |
| 输出 | `output_width` | 32 | 地址生成器 output_width/output_height → 窗口 ow/oh，用于空间坐标及 spatial_count |
| 输出 | `output_height` | 32 | 地址生成器 output_width/output_height → 窗口 ow/oh，用于空间坐标及 spatial_count |
| 输出 | `output_count` | 32 | 地址生成器 output_count → 窗口 output_count → 控制器数量/任务表保护逻辑 |
| 输出 | `input_is_padding` | 1 | 地址生成器 input_is_padding → 窗口 padding → 控制器补零判断 |
| 输出 | `config_valid` | 1 | 地址生成器 config_valid → 窗口 valid → 控制器 CHECK |

**本表信号简释**

- `input_base`：输入数组从 RAM 的哪里开始。
- `output_base`：输出数组从 RAM 的哪里开始。
- `weight_base`：卷积权重数组的首址。
- `bias_base`：偏置数组从哪里开始。
- `feature_size`：当前输入特征的宽高，不是队列长度。
- `channels`：低 16 位是输入通道数，高 16 位是输出通道数。
- `layer_param`：核大小、步长、补零、右移位数；高 12 位必须为 0。
- `op_type`：当前卷积类型，仅 0 和 1 可以通过检查。
- `output_x`：当前输出位置的横坐标。
- `output_y`：当前输出位置的纵坐标。
- `element_index`：保留的未使用输入，当前上级固定接 0。
- `input_channel`：当前使用的输入通道编号。
- `output_channel`：当前计算的输出通道编号。
- `tap`：卷积核窗口内的元素编号。
- `input_address`：当前需要读取的输入字节地址。
- `weight_address`：当前需要读取的权重字节地址。
- `bias_address`：当前输出通道的 32 位偏置地址。
- `output_address`：当前结果应写入的字节地址。
- `second_address`：保留的未使用输出，当前固定为 0。
- `output_width`：计算得到的输出宽度。
- `output_height`：计算得到的输出高度。
- `output_count`：整层最终要产生多少个输出元素。
- `input_is_padding`：当前输入是否需要补零。
- `config_valid`：任务参数及相关地址范围是否通过检查。

保留了 element_index、second_address 这两个旧接口名字，但当前不实现逐元素地址计算，second_address 固定为 0。

特征按 CHW，普通权重按 OIHW，DW 权重按 CKK 存储。检查包括普通 K=1/3、DW K=3/7 且 CI=CO、偏置对齐、尺寸非零、地址不越界、输出不覆盖输入/权重/偏置。任务表范围检查另在阵列控制器 safe_table 中完成。

## 10. 双路整字读缓存

代码：[systolic_read_cache.sv](../rtl/systolic_read_cache.sv)。

输入一路、参数一路，各保留一个 32 位字。同一个字内的后续字节请求命中时不访问 RAM。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | 阵列控制器 clear 或 state==CHECK → 读缓存 clear |
| 输入 | `req_valid` | 1 | 阵列控制器内部读取调度逻辑 → 本模块 `req_valid` |
| 输出 | `req_ready` | 1 | 本模块 `req_ready` → 阵列控制器内部读取调度逻辑 |
| 输入 | `req_addr` | 32 | 窗口生成地址 → 控制器偏置/权重/输入读地址选择 → 缓存 req_addr |
| 输入 | `req_byte` | 1 | 阵列控制器 state!=BIAS_REQ → 缓存 req_byte（偏置整字，输入/权重取字节） |
| 输入 | `req_bank` | 1 | 阵列控制器 state!=B_REQ → 缓存 req_bank（输入 0，权重/偏置 1） |
| 输出 | `response_valid` | 1 | 本模块 `response_valid` → 阵列控制器内部读取调度逻辑 |
| 输出 | `response_data` | 32 | 缓存 response_data → 控制器 read_data → tile wr_value / wr_bias；写使能决定何时保存 |
| 输出 | `cmd_valid` | 1 | 缓存对应输出 → 控制器读/写命令选择 → 顶层请求选择 → RAM 接口 |
| 输入 | `cmd_ready` | 1 | RAM 接口 cmd_ready → 顶层阵列门控 → 控制器 cache_ready → 缓存 cmd_ready |
| 输出 | `cmd_addr` | 32 | 缓存对应输出 → 控制器读/写命令选择 → 顶层请求选择 → RAM 接口 |
| 输入 | `rsp_valid` | 1 | RAM 接口响应经顶层 → 控制器排除 WRITE_WAIT 响应 → 缓存 rsp_valid |
| 输入 | `rsp_data` | 32 | RAM 接口 rsp_rdata → 顶层 bus_rdata → 控制器 rsp_data → 缓存 rsp_data |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `req_valid`：控制器向缓存提出了一次有效读取。
- `req_ready`：缓存现在可以接收这次读取。
- `req_addr`：希望缓存提供的数据地址。
- `req_byte`：取一个字节（1）还是整个字（0）。
- `req_bank`：使用输入缓存路（0）还是参数缓存路（1）。
- `response_valid`：缓存已经取得所需数据。
- `response_data`：缓存给出的字节或整字，字节模式只在低 8 位有效。
- `cmd_valid`：当前有一条有效的访存命令。
- `cmd_ready`：接收方现在能接受一条命令，不代表命令已经完成。
- `cmd_addr`：这条访存命令要访问的字节地址。
- `rsp_valid`：之前发出的命令已有完成响应。
- `rsp_data`：完成响应附带的 32 位读数据。

内部 data[0:1] 保存两个字，tags 保存地址，valid 表示对应字是否有效。新任务 CHECK 和软复位使缓存失效。它不是两套轮换的 tile 双缓冲。

字节模式 response_data 高 24 位补零，tile 取低 8 位存成 signed INT8，因此负数含义仍正确。公共 RAM 接口的直接字节读则采用符号扩展，两者不要混淆。

## 11. tile 分块缓冲与馈数控制

代码：[systolic_tile.sv](../rtl/systolic_tile.sv)。

保存当前权重、输入、偏置块，按普通/DW 模式给内部 8×8 阵列送数，并产生当前块的完成信号。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | 阵列控制器 clear 或 state==CHECK → tile clear；继续传给阵列/PE |
| 输入 | `ce` | 1 | 阵列控制器实例中固定接 1 → tile ce |
| 输入 | `start` | 1 | 阵列控制器 state==RUN_START → tile start |
| 输入 | `accumulate` | 1 | 阵列控制器 kb!=0 → tile accumulate |
| 输入 | `dw` | 1 | 阵列控制器锁存 cop==1 → tile dw |
| 输入 | `rows` | 4 | 阵列控制器计算的 nr/nc/nk → tile rows/cols/depth |
| 输入 | `cols` | 4 | 阵列控制器计算的 nr/nc/nk → tile rows/cols/depth |
| 输入 | `depth` | 4 | 阵列控制器计算的 nr/nc/nk → tile rows/cols/depth |
| 输入 | `a_we` | 1 | 控制器状态及读缓存 response_valid/补零条件 → tile 三个写使能 |
| 输入 | `b_we` | 1 | 控制器状态及读缓存 response_valid/补零条件 → tile 三个写使能 |
| 输入 | `bias_we` | 1 | 控制器状态及读缓存 response_valid/补零条件 → tile 三个写使能 |
| 输入 | `wr_row` | 3 | 控制器 row/col/kidx → tile 写位置 |
| 输入 | `wr_col` | 3 | 控制器 row/col/kidx → tile 写位置 |
| 输入 | `wr_k` | 3 | 控制器 row/col/kidx → tile 写位置 |
| 输入 | `wr_value` | signed 8 | 缓存 response_data 低 8 位或控制器选择的 padding 零 → tile wr_value |
| 输入 | `wr_bias` | signed 32 | 缓存 response_data → 控制器 read_data → tile wr_bias |
| 输出 | `busy` | 1 | tile busy → 控制器 tile_busy → array_running 内部观察输出 |
| 输出 | `done` | 1 | tile done → 控制器 tile_done → RUN_WAIT 的完成判断 |
| 输出 | `sums` | 2048 | 内部阵列 sums → tile sums → 控制器按 row/col 选择 32 位 → quantizer.value |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `ce`：允许本拍推进；为 0 时相关状态保持。
- `start`：已装好数据，开始计算当前累加块。
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
- `done`：当前累加块完成，不等于整条卷积任务完成。
- `sums`：64 个 PE 的 INT32 部分和打包成的一根总线。

内部存储与连接：

- A 权重块 `a[0:63]`：64 字节；接 a_we、wr_row、wr_k、wr_value，读出的权重送 tile 馈数逻辑。
- B 输入块 `b[0:511]`：512 字节；接 b_we、wr_row、wr_col、wr_k、wr_value，读出的输入送馈数逻辑。普通模式只使用第 0 行的窗口，DW 使用全部有效通道行。
- 偏置块 `bias[0:7]`：8×INT32；接 bias_we、wr_row、wr_bias，组成 seeds 总线，给同行所有 PE 提供初始值。
- 馈数状态 state、拍计数 tick 及锁存维度 nr/nc/nk：决定取哪个 A/B 数据、产生哪些有效位及何时 done。

只有 ce=1、busy=0、clear=0 时才允许写缓冲。装好后启动，加载和计算不重叠。clear 清控制/阵列状态，不要求擦除 A/B/bias 数组，使用前须写好有效条目。

普通模式 RUN 为 depth+14 个有效时钟，DW 为 depth 个，启动与初始化另计。accumulate=0 时装偏置；后续累加块 accumulate=1，保留部分和，不重复加偏置。

## 12. 8×8 计算阵列

代码：[systolic_array8.sv](../rtl/systolic_array8.sv)。

内部有 64 个 PE，普通卷积和 DW 共用这一组硬件。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | tile clear → 阵列 clear → 64 个 PE clear |
| 输入 | `ce` | 1 | tile array_ce（ce 且处于初始化或 RUN）→ 阵列 ce → 各 PE ce |
| 输入 | `load` | 1 | tile 初始化状态且不保留部分和 → 阵列 load → 各 PE load |
| 输入 | `dw` | 1 | tile 锁存的 mode → 阵列 dw → 各 PE 操作数选择逻辑 |
| 输入 | `initial_sums` | 2048 | tile bias 数组按行复制生成 seeds → 阵列 initial_sums → 各 PE initial_sum |
| 输入 | `a_edge` | 64 | tile A 权重块经错拍选择产生 ae → 阵列 a_edge → 最左列 PE a_in（普通模式） |
| 输入 | `b_edge` | 64 | tile B 输入块经错拍选择产生 be → 阵列 b_edge → 最上行 PE b_in（普通模式） |
| 输入 | `a_valid` | 8 | tile 边界有效判断 av/bv → 阵列 a_valid/b_valid → 边缘 PE 有效输入 |
| 输入 | `b_valid` | 8 | tile 边界有效判断 av/bv → 阵列 a_valid/b_valid → 边缘 PE 有效输入 |
| 输入 | `dw_inputs` | 512 | tile 各行 B 窗口生成 dwi → 阵列 dw_inputs → 每个 PE a_in（DW） |
| 输入 | `dw_weights` | 64 | tile 各行 A 权重生成 dww → 阵列 dw_weights → 每行各 PE b_in（DW） |
| 输入 | `dw_valid` | 64 | tile 有效行列判断 dwv → 阵列 dw_valid → 各 PE 的 a_valid 和 b_valid（DW） |
| 输出 | `sums` | 2048 | 各 PE sum → 阵列按行打包的 sums → tile sums → 控制器选择结果 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `ce`：允许本拍推进；为 0 时相关状态保持。
- `load`：本拍把初始值装入累加器，先不做乘加。
- `dw`：是否启用独立通道的 Depthwise 供数模式。
- `initial_sums`：准备分别装进 64 个 PE 的初始累加值。
- `a_edge`：普通模式从阵列左边进入的 8 路权重。
- `b_edge`：普通模式从阵列上边进入的 8 路图像输入。
- `a_valid`：8 位分别表示 8 行边界权重是否有效。
- `b_valid`：8 位分别表示 8 列边界输入是否有效。
- `dw_inputs`：DW 模式每个 PE 各自需要的图像输入。
- `dw_weights`：DW 模式每个通道行共用的权重。
- `dw_valid`：DW 模式哪些 PE 在本拍有有效输入和权重。
- `sums`：64 个 PE 的 INT32 部分和打包成的一根总线。

阵列本身没有 start/done 端口，tile 负责开始和完成管理。sums[(row×8+col)×32 +: 32] 对应一个 PE 的 INT32 结果。

普通模式权重从左向右、输入从上向下，部分和留在 PE。DW 绕过相邻传递配对，为每个 PE 独立接输入并按行广播权重。

## 13. 单个 PE

代码：[systolic_pe.sv](../rtl/systolic_pe.sv)。

做一次 INT8×INT8 乘法并累加到自己的 INT32 sum，同时寄存并转发两个操作数。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | tile → 阵列同名控制端口 → 本 PE 对应端口 |
| 输入 | `ce` | 1 | tile → 阵列同名控制端口 → 本 PE 对应端口 |
| 输入 | `load` | 1 | tile → 阵列同名控制端口 → 本 PE 对应端口 |
| 输入 | `initial_sum` | signed 32 | 阵列 initial_sums 中本 PE 对应的 32 位 → PE initial_sum |
| 输入 | `a_in` | signed 8 | 普通：左侧 PE a_out，最左列为 a_edge；DW：本 PE 对应 dw_inputs → a_in |
| 输入 | `b_in` | signed 8 | 普通：上方 PE b_out，最上行为 b_edge；DW：本行 dw_weights → b_in |
| 输入 | `a_valid` | 1 | 普通：左侧 a_out_valid 或边界 a_valid；DW：本 PE 的 dw_valid → a_valid |
| 输入 | `b_valid` | 1 | 普通：上方 b_out_valid 或边界 b_valid；DW：本 PE 的 dw_valid → b_valid |
| 输出 | `a_out` | signed 8 | 本 PE a_out → 右侧 PE a_in（普通模式）；最右列无后续消费者 |
| 输出 | `b_out` | signed 8 | 本 PE b_out → 下方 PE b_in（普通模式）；最下行无后续消费者 |
| 输出 | `a_out_valid` | 1 | 本 PE a_out_valid → 右侧 PE a_valid（普通模式）；最右列无后续消费者 |
| 输出 | `b_out_valid` | 1 | 本 PE b_out_valid → 下方 PE b_valid（普通模式）；最下行无后续消费者 |
| 输出 | `sum` | signed 32 | 本 PE sum → 阵列 sums 对应片段 → tile → 控制器结果选择 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `ce`：允许本拍推进；为 0 时相关状态保持。
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

内部元件：

- 组合乘法器 product：接 a_in/b_in，输出 signed 16 位乘积，符号扩展后送累加加法器。
- sum 寄存器：load 时接 initial_sum；否则在两个 valid 都为 1 时接“原 sum + 乘积”，输出同时反馈给加法器并接阵列 sums。
- a_out/b_out 寄存器：保存输入操作数，普通模式交给右/下邻居。
- a_out_valid/b_out_valid 寄存器：随数据保存有效标记，load 时清零。

ce=0 时保持；clear/复位优先。INT32 累加溢出回绕，最终 INT8 饱和由 quantizer 完成。DW 时 a_in 接图像输入、b_in 接权重，与普通模式的名称对应相反，但乘法等价；DW 不消费邻居的转发值。

## 14. 量化模块：右移与 INT8 限幅

代码：[quantizer.sv](../rtl/quantizer.sv)。

当前只有一个 quantizer 实例，名为 requant；不再接 ReLU/ReLU6，也不再有第二个限幅实例。组合逻辑，无时钟。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `value` | signed 32 | tile sums → 控制器按 row/col 选择一个 PE 结果 raw → requant.value |
| 输入 | `quant_shift` | 8 | 控制器锁存的 clp[19:12] → requant.quant_shift |
| 输出 | `shifted` | signed 32 | requant.shifted → 控制器内部 shifted 线；未连接后续功能模块 |
| 输出 | `result` | signed 8 | requant.result → 控制器 quantized → output_store.wdata |

**本表信号简释**

- `value`：当前选中 PE 的 INT32 累加结果。
- `quant_shift`：把 INT32 数值算术右移多少位。
- `shifted`：右移后的 INT32 数值，还没有限幅为 INT8。
- `result`：右移并限幅后的 signed INT8 输出。

模块内部先做算术右移，再限制到 −128～127。shifted 是保留的 INT32 输出端口；尽管内部限幅会使用右移值，这个外部 shifted 输出在当前实例中没有后续消费者。

## 15. 输出寄存器

代码：[output_buffer.sv](../rtl/output_buffer.sv)。

暂存一个量化后的 INT8 结果，保持到 RAM 写回完成。当前只有阵列控制器内部这一个实例。

| 方向 | 信号 | 位宽 | 来源 → 接收方 |
|---|---|---:|---|
| 输入 | `clk` | 1 | 顶层 clk 沿所属上级模块透传 → 本模块 clk |
| 输入 | `rst_n` | 1 | 顶层 rst_n 沿所属上级模块透传 → 本模块 rst_n |
| 输入 | `clear` | 1 | 控制器 clear 或 state==CHECK → output_store.clear |
| 输入 | `we` | 1 | 控制器 state==POST → output_store.we |
| 输入 | `wdata` | signed 8 | quantizer.result → quantized → output_store.wdata |
| 输出 | `rdata` | signed 8 | output_store.rdata → out_value → 控制器 cmd_wdata 低 8 位 → 顶层选择 → RAM 接口 |

**本表信号简释**

- `clk`：统一的更新节拍，在上升沿保存新状态。
- `rst_n`：全局复位，拉低时复位相应寄存器。
- `clear`：同步清理当前运算状态，不一定清空存储数组。
- `we`：允许在这个时钟沿保存写数据。
- `wdata`：本次准备存入的数值。
- `rdata`：从存储或寄存器读出的数值。

它只保存 1 个字节，不是整层结果缓存。最终结果保存在 RAM 的 OUTPUT_ADDR 区域。clear 后寄存器为 0。

## 16. MMIO 字段与任务布局

### MMIO 寄存器

以下均为 32 位寄存器访问，共用 mmio_addr、mmio_wdata、mmio_we/mmio_re。默认基址为 `0x40000000`。

| 偏移 | 寄存器 | 来源 → 接收方 | 当前字段 |
|---|---|---|---|
| 0x00 | CONTROL | CPU → 寄存器组 → 队列启动/配置、各模块复位 | bit0 START，bit1 RESET，[5:2] OP_TYPE |
| 0x04 | STATUS | 硬件状态 → 寄存器组 → CPU | bit0 BUSY，bit1 DONE，bit2 ERROR，只读 |
| 0x08 | INPUT_ADDR | CPU → 寄存器组 → 队列 | 单算子输入首址；队列模式为任务表首址 |
| 0x0C | OUTPUT_ADDR | CPU → 寄存器组 → 单算子分发 | 结果区域首址 |
| 0x10 | WEIGHT_ADDR | CPU → 寄存器组 → 单算子分发 | 权重首址 |
| 0x14 | BIAS_ADDR | CPU → 寄存器组 → 单算子分发 | 偏置首址 |
| 0x18 | FEATURE_SIZE | CPU → 寄存器组 → 队列 | 单算子：[15:0]宽、[31:16]高；队列模式为任务数 |
| 0x1C | CHANNELS | CPU → 寄存器组 → 单算子分发 | [15:0]输入通道，[31:16]输出通道 |
| 0x20 | LAYER_PARAM | CPU → 寄存器组 → 单算子分发 | [3:0]核大小、[7:4]步长、[11:8]补零、[19:12]右移位数；[31:20]必须为 0 |

**本表字段简释**

- CONTROL：选类型、发开始或复位命令；START/RESET 读回为 0。
- STATUS：读忙、完成和错误；DONE/ERROR 被保存，等待新启动或复位清除。
- INPUT_ADDR：输入从哪读；在队列模式下是任务表从哪读。
- OUTPUT_ADDR：结果往哪写。
- WEIGHT_ADDR：权重从哪读。
- BIAS_ADDR：偏置从哪读。
- FEATURE_SIZE：图像宽高，或队列任务条数。
- CHANNELS：输入/输出分别有多少通道。
- LAYER_PARAM：按什么窗口、步长、补零及右移规则计算。

队列模式各算子配置来自 RAM 描述符；启动时常用的三次 MMIO 写为 INPUT_ADDR=任务表首址、FEATURE_SIZE=任务数、CONTROL=0x3D。直接单算子用 CONTROL=(op×4)+1，合法 op 只有 0/1；其他直接算子进入检查后报错，不执行算子数据访问。

### 每条任务仍为 256 位

| 字编号 | 位段 | 内容 | 读取后的去向 |
|---|---|---|---|
| 0 | [31:0] | [15:8]版本 1、[7:0]算子 0/1、[31:16]保留 0 | 队列校验；低 4 位作为 task_op → 控制器 op |
| 1 | [63:32] | INPUT_ADDR | task_input → 控制器 ia |
| 2 | [95:64] | OUTPUT_ADDR | task_output → 控制器 oa |
| 3 | [127:96] | WEIGHT_ADDR | task_weight → 控制器 wa |
| 4 | [159:128] | BIAS_ADDR | task_bias → 控制器 ba |
| 5 | [191:160] | FEATURE_SIZE | task_size → 控制器 fs |
| 6 | [223:192] | CHANNELS | task_channels → 控制器 ch |
| 7 | [255:224] | LAYER_PARAM | task_param → 控制器 lp |

**本表字段简释**

- 字 0：任务格式及算子编号；版本号是数据格式版本，不是项目版本。
- 字 1～4：分别给出输入、输出、权重、偏置在 RAM 中的位置。
- 字 5：输入宽高；字 6：输入/输出通道数；字 7：窗口和量化参数。

读取路径为 RAM → RAM 接口 → 任务读取器 → FIFO → 队列分发。每次 32 位，8 次组成一条任务。描述符中的 OP 15 也不合法：15 只用于 MMIO 启动队列，不能成为队列中的计算任务。

## 17. 画图时需要保留的关键连接

```text
队列 exec_start ─────────────────────────────> 阵列控制器 start
队列 task_op(4) ────────────────────────────> 阵列控制器 op
队列 task_input/output/weight/bias(各32) ────> 阵列控制器 ia/oa/wa/ba
队列 task_size/channels/param(各32) ─────────> 阵列控制器 fs/ch/lp
队列 active、queue_base(32)、queue_end(64) ──> 阵列控制器任务表保护输入
阵列控制器 busy/done/error ─────────────────> 队列 exec_busy/exec_done/exec_error

FIFO out_data(256) ──> 队列内部 head_data ──> task_* 分发
队列 head_ready ────> FIFO out_ready

任务读取器 cmd_addr ──> 队列 fetch_addr ──> RAM 选择逻辑 ──> RAM 接口 cmd_addr
阵列控制器 cmd_addr ─────────────────────> RAM 选择逻辑 ──> RAM 接口 cmd_addr

缓存 response_data ──> tile A/B/偏置缓冲 ──> 阵列各 PE
阵列 sums(2048) ──> 选择一个结果(32) ──> quantizer ──> 输出寄存器(8) ──> RAM 写回
```

请求选择只有两路：任务读取和阵列访问；这是选择“谁用 RAM”，不是选择“哪个计算模块”。fetch_phase=1 选任务读取，否则选阵列。

框图可省略公共 clk/rst_n 和调试输出，并标注“握手信号省略”；但 start/done、主要地址/配置、实际数据路径应区分。completed/fetched/buffered/debug_state/array_running 当前只接内部观察线，没有对应 CPU 可读 MMIO 寄存器。

## 18. 核对范围

本汇总逐一核对了当前 files.f 中 15 个 RTL 模块的实际端口名称、方向、位宽及实例连接。当前读缓存和 tile 没有双缓冲计算重叠；当前也没有激活与残差执行能力。

只新增本版说明文档，没有修改硬件代码或重跑 RTL 功能仿真；文档检查覆盖端口完整性、位宽、释义、代码链接和表格结构。
