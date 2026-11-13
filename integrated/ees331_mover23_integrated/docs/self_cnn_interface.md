# 自研卷积隔离入口：接口与第一阶段边界

入口为 `rtl/cnn_self/self_network_top.sv`，文件表为 `rtl/filelists/cnn_self.f`，从工程根目录使用文件表。旧 CNN、NEureka、CPU、UART、生产 SRAM 和 SoC 顶层均保持原样。本入口是本次“两套 3×3，其余算子各一套”试验的独立硬件，不表示生产 SoC 已替换完成。

## 实例与端口编号

|编号|硬件|命令 opcode|说明|
|---|---|---|---|
|0、1|`self_conv_engine`，K=3、TILE=2|0|普通 3×3 或 multiplier=1 的 DW3，按空闲状态动态分配|
|2|`self_conv_engine`，K=1、TILE=2|5|一套 1×1|
|3|原 `dw7_cached_engine`，MAX_WIDTH=7、LANES=8|3|一套 7×7 逐通道，stride=1、valid；通道数是 8 的倍数|
|4|原 `quant_post_engine`，mode_add=0|1|一套 INT32 后处理，含偏置、缩放、舍入、激活限幅|
|5|原 `quant_post_engine`，mode_add=1|2|一套 UINT8 残差 Add|
|6|原 `pad_hwc_engine`|4|一套四周补一像素的 HWC 补边|

Post 与 Add 是相同旧 RTL 的两个独立实例，算术定义没有重新实现。卷积模块的默认最大通道为 512。旧 DW7、Post、Add、Pad 不通过软件或测试台替算。

## 16 字命令

每条命令为 512 位。word0 位于 `[31:0]`，word1 位于 `[63:32]`，依此类推。地址以字节计。

|字|卷积 opcode 0/5|Post/Add|DW7|Pad|
|---|---|---|---|---|
|0|opcode|opcode|3|4|
|1|输入地址|输入 A 地址|输入地址|原图地址|
|2|权重地址|输入 B 地址，Post 不用|权重地址|保留|
|3|INT32 输出地址|UINT8 输出地址|INT32 输出地址|输出地址|
|4|保留|逐通道参数地址|保留|保留|
|5|保留|元素总数|保留|保留|
|6|输入通道 Cin|通道数|通道数|通道数|
|7|输入宽度|保留|输入宽度，当前必须为 7|原图宽度|
|8|输入高度|保留|输入高度|原图高度|
|9|输出通道 Cout|保留|保留|低 8 位为 zero point|
|10|stride|保留|保留|保留|
|11|bit0：depthwise|保留|保留|保留|
|12|保留|保留|保留|保留|
|13|帧号标签|帧号标签|帧号标签|帧号标签|
|14、15|保留|保留|保留|保留|

卷积核大小由 opcode 固定，opcode0 为 3×3，opcode5 为 1×1。卷积输入是 HWC UINT8，权重为有符号 INT8，输出为 HWC INT32；普通卷积权重为 `[Cout][K][K][Cin]`，自研 DW3 权重为 `[channel][KY][KX]`。原 DW7 则保持旧 `[KY][KX][channel]` 布局，数据生成时必须区分。卷积本身不隐式补边，补边必须以 opcode4 显式调度。Post/Add 参数继承旧模块每通道 5 个 32 位字的格式和 nearest/ties-away-from-zero 的一次舍入规则。

## 编程与调度

参数 `MAX_TASKS=64`，`IW=$clog2(MAX_TASKS)`，当前默认最多 64 条任务，保持 8 个物理缓冲槽。编程索引 `program_index` 和 `program_dep0/1` 为 IW 位，必须从 0 连续装入；`program_valid && program_ready` 接受一条命令。两位 `program_dep_valid` 指定至多两个前驱，前驱编号必须小于当前编号。`task_count` 为 IW+1 位，必须等于已加载命令数。最后一条命令接受后再单独脉冲 `start`。`engine_enable[1:0]` 在启动时锁存，控制两套 K3 的可用性，至少一位为 1。

`unit_start`、`unit_active`、`completion_pulse`、`operator_busy`、`operator_work` 均为 7 位。`unit_node` 为 `[6:0][IW-1:0]`，表示每个实例当前的任务编号。`completed_count` 为 IW+1 位，`completed_mask` 为 MAX_TASKS 位。每拍扫描一个候选任务，仅在前驱完成、目标算子空闲、缓冲所有权满足时发射。帧号用于跟踪，硬件不将某一帧固定绑定到某一 K3 实例。

`operator_work[0:3]` 是卷积实际 MAC 周期；`operator_work[4:6]` 是 Post/Add/Pad 输出写请求真实握手的周期。它区别于包含访存等待的 `operator_busy`。`conv_input_reads`、`conv_weight_reads`、`conv_mac_count` 均为 `[2:0][31:0]`，分别跟踪三个自研卷积实例的当前/最近任务计数；具体单位以卷积模块定义为准。`dw7_mac` 与 `operator_work[3]` 相同。

单独调用 `self_conv_engine` 时，`start` 仅在内部IDLE接受。`done/error`终结状态虽使busy为0，仍需等下一个IDLE再送新start；集成调度器利用unit_active正确隔开这两个状态。计数器在新任务开始或clear时归零，输入/权重读取以完成响应的字节数计，mac_count以实际MAC次数计，均为32位无符号回绕计数。

## 7 路存储接口

`mem_valid/write/byte/ready/response` 各为 7 位；`mem_addr/wdata/rdata` 各为 224 位，端口 e 使用 `[e*32+:32]`。一个实例对应一个端口，最多一笔在途请求。请求在 valid 与 ready 同时为 1 的边沿接受，response 是该请求的完成通知；读 response 携带 rdata，写 response 表示写已提交。response 必须在请求接受之后的周期返回，不能在接受同一拍返回。byte=1 表示单字节传输，低 8 位有效；byte=0 表示 32 位传输。真正的共享 SRAM 仲裁、带宽限制和错误上报由上层提供。

全部算子在最后一笔写 response 后才产生 done，因此调度完成位、后继读取与槽释放均不会早于输出落存储。

## 缓冲生命周期与结果握手

`program_allocate_valid/slot` 在任务发射时预约一个输出槽；`program_hold_mask[MAX_TASKS-1:0]` 必须包含使用该张量的全部末端消费者。硬件还自动加入生产任务自身。分支、残差长期保留不能只写一个最近消费者。

`program_use_valid[2:0]` 声明最多三项当前输入所有权要求；`program_use_slots[8:0]` 每项 3 位，`program_use_owners[3*IW-1:0]` 每项 IW 位。owner 是该槽最近分配任务的编号，用于阻止旧代输入误读。`buffer_live/release/allocate` 各为 8 位，`buffer_owners` 为 8*IW 位。所有消费者均完成且无外部读取保留后，槽才可释放；槽复用前仍需确认新任务的依赖与地址计划。

最终输出同时设置 `program_result_valid`、`program_result_frame/addr/bytes`，且必须有非空输出槽预约。输出任务一旦预约，`external_hold[slot]` 就保留该槽。生产者完成后，`result_valid` 发布帧号、地址和长度；反压时这些描述字段保持不变。`result_ready` 必须表示外部读取全部完成并已排空，不是“准备开始读取”。握手触发 `result_accept`，随后允许释放该槽。

`compute_done` 仅表示全部计算任务完成；`done` 还要求全部结果已被取走、槽均已释放且未取消。成功输出的 `result_error=0`。无效结果配置立即进入 cancel，`error` 在下一边沿锁存；不发布伪成功描述。未知 opcode、自依赖/前向依赖、不连续编程、任务数错误及算子/内存错误均锁定故障，直到 clear。

`clear/cancel` 会丢弃本批计算和结果状态。**上层同时必须取消所有已经接受的旧存储请求、迟到 response 和外部读取确认**，之后才能开始新批次。本接口没有跨 clear 的事务 token，不能把迟到确认接到新一轮任务。

## 当前验证和资源边界

这套默认配置用于第一阶段的小输入、两帧并行和真实整数算术验证。历史完整人脸图片、权重和软件参考的本机绝对路径不保证存在于本次克隆；不能把旧文件名或旧 PASS 记录视为本轮已经输入真实人脸。64 条任务表也不能直接装入旧完整两帧的 746 条命令。

`scripts/synth_self_cnn.py` 对完整七实例顶层做 Vivado out-of-context 综合，默认器件 `xc7z020clg484-1`、时钟目标 10 ns、MAX_TASKS=64、最大通道 512。保留原 96 位 Post/Add 算术可能仍有显著 DSP/LUT 开销，应以本轮综合报告为准。综合时序估计不等于布局布线后的 100 MHz 通过；本轮没有宣称上板、UART 连续收图、完整 MobileFaceNet 或识别准确率验收通过。

本轮完整顶层实际尝试保存在 `build/runs/20261023_150436_706083_self_cnn_synth/`。Vivado 已进入用户 RTL 综合，原 `quant_post_engine` 的 `params[2560]` 因异步复位进程中的存储访问模式无法推导 RAM，产生 `Synth 8-3391`：81920 位存储超出默认寄存器展开上限。原 DW7 也提示 200704 位权重存储将展开为寄存器，新复制调度器的 32768 位命令表同样尚未推导 RAM。在已出现致命错误后停止了继续展开，保留日志与 FAIL；没有提高展开上限、修改旧算子或伪报整机资源和时序通过。

可用 `python scripts/synth_self_cnn.py --top self_conv_engine --max-kernel 3` 和 `--max-kernel 1` 分别测量自研卷积模块。此类独立报告只覆盖一个卷积实例，不能代替七实例完整子系统、SoC 或布局布线结果。完整综合与单模块结果各自记录源文件 SHA256、器件、参数、时钟、运行时间和失败原因。

本轮两个独立卷积的 OOC 综合均已成功，最大通道 512、TILE=2，目标器件 `xc7z020clg484-1`，目标时钟 10 ns：

|单实例|LUT|寄存器|RAMB36|RAMB18|DSP|综合最差 setup slack|本次耗时|
|---|---:|---:|---:|---:|---:|---:|---:|
|K3|1938|1505|6|0|0|+0.078 ns|91.75 秒|
|K1|1951|1491|2|1|0|+0.078 ns|91.00 秒|

对应目录为 `build/runs/20261023_150913_240097_self_cnn_synth/` 与 `build/runs/20261023_151108_866766_self_cnn_synth/`，各含 `utilization.rpt`、`utilization_hierarchical.rpt`、`timing_summary.rpt`、DCP 与 JSON。单个小位宽乘法由 Vivado 映射成 LUT，因此 DSP 为实测 0，不能把 RTL 的一个 MAC 直接说成占用了一个 DSP。输入及权重缓存已经推导为块 RAM。时序报告没有板级时钟源位置，也没有布局布线，+0.078 ns 仅为综合估计，余量较小。

将这三套卷积独立报告机械相加，得到 5827 LUT、4501 寄存器、14 个 RAMB36 加 1 个 RAMB18、0 DSP；这只是两套 K3 加一套 K1 的粗略资源预算，不是完整顶层综合测量，也不包括 DW7、Post、Add、Pad、调度器及外部存储。
