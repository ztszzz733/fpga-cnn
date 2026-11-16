# 任务图存储路径交接（2026-11-16）

## 配置与边界

本版本在 `bai-datasram` 四 bank 基线 `e723e0e` 上加入任务图存储路径，原始 `data_mover` 不变。`datasram_mover_subsystem.TASK_GRAPH_STORAGE=0` 仍选原分页器，`=1` 选择 `cnn_plan_storage`。SoC 顶层用 `TASK_GRAPH_STORAGE=1` 加 `EES331_PLAN_EXTERNAL` 导出计划执行器握手端口；未启用时保持旧顶层接口。

新路径保留同一块 392 KiB 4 bank RAM、同一个原始 MOVER 和一条 HP0。默认把物理地址 0～64 KiB 留给自动分页缓存，64～392 KiB 划为 328 KiB 显式本地窗口。缓存页不会置换本地窗口，二者可在同一批 RUN 中混用。`LOGICAL_BYTES=64 MiB` 保留本地窗口地址基址 `0x04000000`；任务图模式的 DDR 实际可访问范围由 `PLAN_DDR_BYTES` 指定，默认保守设为 16 MiB，交付前需与 PS 的保留区一致。

## 访问合同

- `cnn_addr < PLAN_DDR_BYTES`：原 DDR 逻辑地址，经 1 KiB 页缓存访问。
- `cnn_addr = LOCAL_BASE + local_offset`：直接访问显式本地窗口，不查页表；`local_offset < 328 KiB`。
- 其余地址、越界字访问和未对齐字访问触发 `cnn_mem_fault`。
- LOAD/STORE 命令含 `epoch/frame_id/id`、方向、DDR 偏移、本地偏移和长度。`cmd_valid && cmd_ready` 仅代表入队。完成事件保留身份，直到 `rsp_valid && rsp_ready`。队列深度为 4，满时停止接收。
- DDR 起点需 8 字节对齐；长度可含 4/2/1 字节尾部，允许跨 4 KiB。STORE 检查已启用的 DDR 只读前缀。失败的目标缓冲由执行器视为无效。
- 显式命令启动前，同步并失效相交的脏分页副本；同步扫描时暂停新的 DDR 分页请求。搬运期间非相交页的驻留命中与本地窗口访问可继续，缺页请求等待共享 MOVER。执行器/软件仍须通过 `depends_on[]` 防止 DMA 与 RUN 同时读写同一显式缓冲。
- 一个 MOVER 同时只执行一条 LOAD/STORE 或分页搬运；4 个 bank 可同拍各服务一个本地计算请求。每个客户端在前一响应返回前不应再次提交请求，因为现有接口没有请求 ID 或响应 ready。
- AXI 错误或超时可先返回失败事件；在途响应尚未排空时 `drained=0`，不可复用缓冲或清故障。仅在 `drained=1` 后拉高 `plan_recover`。

## CSR（沿用图像桥 cache CSR 窗口，字节偏移）

图像桥通过 INDEX=`0x2000 + 偏移`、DATA 访问本窗口。原有 `0x00`～`0x38` 状态和缓存统计保持；新模式增加：

| 偏移 | 只读值 |
|---|---|
| `0x3c` | 显式本地可分配字节数（默认 335872） |
| `0x40` | 本地窗口基址（默认 `0x04000000`） |
| `0x44` | 分页缓存物理字节数（默认 65536） |
| `0x48/0x4c/0x50` | 接受命令数 / 已取走完成数 / 命令背压周期 |
| `0x54` | 协议版本 1 |
| `0x58` | 允许访问的 DDR 字节数（默认 16777216） |
| `0x5c` | DDR 起点对齐要求 8 字节；长度支持任意正数 |
| `0x60` | 搬运命令/完成信用深度 4 |
| `0x64` | 从高到低的 4 个字节：DMA 口数 1、计算 bank 口数 4、计算口位宽 32、DMA 本地口位宽 32 |
| `0x68` | 位 0：显式本地访问可与非冲突 DMA 重叠；位 1：DDR 驻留命中在搬运期间可继续 |
| `0x6c/0x70` | DMA 进行时服务本地计算的周期 / 请求数 |
| `0x74` | 位 0～4：busy、drained、fault、cmd_ready、rsp_valid |
| `0x80/0x84` | HP0 实际读/写字节数（包括分页与显式搬运） |
| `0x88/0x8c` | 其中由显式 LOAD/STORE 产生的 HP0 读/写字节数 |
| `0x90/0x94` | 至少一个本地请求等待的周期 / 显式搬运忙周期 |

SoC 顶层通过 `EES331_PLAN_EXTERNAL` 暴露执行器握手端口，供 CNN 计划执行器连接；这是集成接口，尚非板级引脚方案。CPU 命令/事件寄存器地址尚需 CNN/控制封装方分配；本模块未冒用现有寄存器空间。现有 CPU 缓存维护协议仍由 PS 软件负责。若分页路径另行置位 `cnn_mem_fault`，还需按原 CSR 恢复流程清除该故障。

## 验证与下一步

执行 `simulation/scripts/run_task_graph_queue_test.ps1` 与 `simulation/scripts/run_task_graph_storage_test.ps1`。后者用 AXI3 延迟模型覆盖 DDR 与本地地址混用、脏页同步、LOAD/STORE、四客户端四 bank 同拍读、DMA 与本地访问重叠、跨 4 KiB、范围/对齐/只读、完成背压、AXI 错误、超时、迟到响应排空和恢复。顶层旧/新参数组合已通过 Verilator elaboration/lint。综合可用 `simulation/scripts/synth_task_graph_soc.tcl` 的 `legacy` 与 `plan` 参数复现。

当前仍需 CNN 方把计划执行器的命令、完成和本地地址接到 SoC 顶层，并提供约 50 任务图及两帧交错测试，才能做真实任务图端到端功能与同工作负载性能对比。默认 64 KiB 自动分页缓存目前只占物理 bank 0；若混用负载大量访问 DDR 逻辑地址，DDR 缓存命中吞吐及缺页率可能低于原 392 KiB 分页器，需基于实际任务图调节分区，不能把短测试周期当作网络加速比。
