# EES331 新 CNN 接口与紧凑调度

`rtl/cnn_ddr/cnn_ees331.sv` 是六模块接线图中 CNN 的新实现入口。它包含零等待寄存器封装、`fixed_schedule_compact` 和真实算子池：2 套普通/深度 3×3、4 套 1×1、DW7/Post/Add/Pad 各 1 套。它不包含数据 SRAM，不引用旧 `mobilefacenet_accelerator_top` 或 NEureka。

## 与接线图对应

- `cnn_mmio_addr/wdata/rdata[31:0]`、`cnn_mmio_re/we/ready`：地址为控制桥转发后的本地字节偏移，`ready` 恒为 1。慢操作通过状态轮询完成。
- `cnn_valid/write/byte/ready/response[9:0]`：10 个独立客户端。每个客户端最多一笔请求在途；接受请求与返回响应至少相隔一拍。
- `cnn_addr/wdata/rdata[319:0]`：每个客户端占连续 32 位，客户端 0 在最低位。`cnn_cancel` 使 cache 排空并抑制旧响应；`cnn_mem_fault` 使 CNN 停止并清除算子。
- 调试端口 `unit_start/active/completion_pulse/operator_busy/operator_work/unit_node/completed_count` 仅用于仿真或内部观察，不增加六模块之间的功能连线。

客户端顺序为 K3 #0/#1、K1 #0/#1/#2/#3、DW7、Post、Add、Pad。帧间共享算子，无固定帧/算子绑定。每帧按模板顺序执行一项，帧之间可以同时计算；这不是层内像素流融合。

## 控制存储

模板最多 256 步，每步 20×32 位，总逻辑容量 20 KiB，仅保存一份。四帧分别保存 PC、输入/工作区地址和帧号；16 个物理槽保存 owner、最多两个终端消费者 ID 及外部结果占用。每个算子仅保存当前 512 位命令。没有 524/1024 份命令展开 RAM，没有任务数平方的消费者位图。

帧的 PC 只在算子完成并已收到最后存储写响应后推进。槽必须满足生产者和全部声明消费者都完成、且外部结果已 ACK，才允许释放。残差支路因此可以跨过多个模板步骤继续保留。为匹配固定网络，每个模板必须恰有一个结果项，并且是最后一项；配置期拒绝向前依赖、无效源模式、超过两个消费者、重复消费者、非法 opcode、重复地址描述和缺失结果。

## 零等待寄存器

| 本地偏移 | 名称 | 读写与含义 |
|---|---|---|
| 0x00 | ID | 只读，`0x434E4E32` |
| 0x04 | STATUS | bit0 可配置，1 busy，2 done，3 error，4 暂存槽可提交，5 结果有效，6 全部计算完成 |
| 0x08 | CONTROL | 单次写一个位：bit0 clear，1 start，2 模板提交，3 地址描述提交，4 图片提交，5 结果 ACK |
| 0x0C | IMAGE_COUNT | 1～4，默认 4 |
| 0x10 | UNIT_ENABLE | 默认 0x3FF；每一类至少启用一个算子 |
| 0x14 | TEMPLATE_INDEX | 模板顺序编号，必须从 0 连续加载 |
| 0x18 | WORD_INDEX | 暂存字索引 0～19 |
| 0x1C | WORD_DATA | 读写暂存字；写后索引自动加一，19 后回 0 |
| 0x20 | FRAME_SLOT | 0～3；配置地址和提交图片共用 |
| 0x24 | INPUT_BASE | CNN 逻辑输入地址 |
| 0x28 | WORKSPACE_BASE | CNN 逻辑工作区地址，4 字节对齐 |
| 0x2C | FRAME_ID | 32 位帧号；提交时必须匹配地址配置 |
| 0x30/34/38 | RESULT_FRAME/ADDR/BYTES | 当前结果描述，ACK 前保持不变 |
| 0x3C | ERROR_CODE | 封装命令错误优先，否则为核心错误 |
| 0x40 | COMPLETED_JOBS | 已完成任务数 |
| 0x44 | FRAMES_READY | 已提交图片位图 |
| 0x48 | LOADED_STEPS | 已加载模板项数 |
| 0x4C/50 | ACK_FRAME/ACK_EPOCH | 结果 ACK 的完整身份 |
| 0x54 | EPOCH | 初始 0，每次 clear 加一 |

错误 ACK 被拒绝且不释放结果；命令错误记录到状态，但不直接取消正在计算的正确批次。clear 清除错误、模板有效数量和帧状态。软件只能在旧 AXI 事务排空并完成 cache 维护后复用地址；CNN 的 clear 本身不等于 DDR 写回完成。

## 20 字模板格式

W0～15 沿用现有算子 512 位命令。命令中 word1/2 根据源模式加输入或工作区基址，word3 总是加工作区基址；word13/14 在发射时填入帧号与槽号。权重/量化参数的绝对逻辑地址保持原格式。

| 字 | 位域 |
|---|---|
| W16 | [3:0] 两个源模式；[5:4] 输出槽；[8:6] 三个输入槽有效位；[14:9] 三个输入槽号；[15] 结果标志；[17:16] 依赖有效；[25:18] dep0；其余保留 0 |
| W17 | [7:0] dep1；[15:8]/[23:16]/[31:24] 三个输入 owner 模板 ID |
| W18 | [7:0] consumer0；[15:8] consumer1；[17:16] 消费者数 0～2；其余保留 0 |
| W19 | 结果字节数；非结果项可为 0 |

从历史 `template_meta.hex` 转换时，取 hold mask 的置位索引，去掉生产者自身，得到终端消费者列表。原 hold mask 包含生产者自身，不能把它也计入两个消费者。

## 算子存储改造

`quant_post_bram_engine` 保留原 96 位舍入与夹紧算术，五组参数改为独立同步 RAM，读参数与输入握手重叠。`dw7_bram_engine` 保留 UINT8×INT8 累加、输入行缓存及权重复用语义，权重按 8 个 lane 分 bank，并在每个 tap 前增加同步读状态。这会改变 DW7 周期，不能沿用旧全网周期作为本实现实测值。

原算子文件和历史交付未修改。验证入口为 `scripts/test_compact_cnn.py`（MMIO 与真实多图 K1）和 `scripts/test_ees331_bram_operators.py`（独立整数参考、512 通道 DW7+Post、滑动窗口、延迟与清除重启）。整网 DDR 与板级验证由 EES331 系统测试另行报告。

## 本模块的实际验证记录

- `build/runs/20261024_184418_921525_compact_cnn`：MMIO/四图 K1 测试 PASS，4096 次真实 MAC，1487 拍两套以上 K1 同时 MAC；慢结果回收、过期 ACK、空模板启动、错误帧号、存储故障、clear 恢复均验证。
- `build/runs/20261024_183642_006922_ees331_bram_operators`：四项 PASS。7×7×512 两图分别检查 5120 字节，9×10×16 滑动窗口两图检查 1920 字节；含最大 UINT8、INT8 -128/127、权重复用、响应停顿和 clear 重启；独立 Python 整数参考仅生成 golden，不参与 RTL 的内存响应。
- `build/runs/20261024_184251_323537_ees331_operator_synth`：两个算子在 xc7z020clg484-1 的独立综合 PASS。通用 Post 为 3402 LUT、346 FF、1.5 BRAM36 等效、22 DSP；DW7 为 6757 LUT、4075 FF、8 BRAM36、12 DSP。Post 的两组乘数参数被 Vivado 吸收入 DSP 的读寄存器影响，最终映射成 704 LUTRAM，其余参数为 3 RAMB18；不存在原先整块参数 RAM 无法综合的错误。整机可进一步常量折叠 mode_add，不能把独立数据简单当作整机资源或时序结论。

以上是局部 RTL 和综合记录，不代表 DDR 实板、完整 MobileFaceNet 或最终布局布线通过。
