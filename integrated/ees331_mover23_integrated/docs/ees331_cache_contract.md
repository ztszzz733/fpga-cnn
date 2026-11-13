# EES331 DATASRAM/cache 实施接口

`datasram_ddr_subsystem` 对应接线图中的 DATASRAM 位置。原 CPU 数据口接独立的 16 KiB 本地 RAM，固定一拍读、支持四个字节写使能；它不访问 DDR。CNN 的 10 路请求接新共享 cache。所有外部信号名称、位宽与 `deliverables/ees331_ddr_io/io_manifest.json` 一致。

## 首版实际结构

- 数据容量默认 128 KiB，64 B 一行，2 路组相联；四个同步 32 bit BRAM bank，按行内字位置交织。元数据分两路同步 RAM，LRU 为每组一位。
- 复位后逐组清除元数据，不复位数据数组。默认 1024 组，初始化期间不接受 CNN 请求；CSR 的 ready 位随后置 1。
- 当前版本全局至多一笔 CNN 请求在途，包括至多一笔 miss。命中、填充和替换共用控制器；**miss 期间其他命中也会等待**。四个数据 bank 用于同步访问和整行搬运，当前不代表四客户端同时命中。这是方案允许的正确性原型，尚不是四 MSHR 性能版本。
- 十路客户端轮转仲裁。`cnn_ready` 表示接受；`cnn_response` 至少在后续时钟返回。字节读符号扩展至 32 bit，与原 bai SRAM 一致；32 bit 字访问必须四字节对齐。
- write-back + write-allocate。字节写只修改对应字节；写应答表示已进入 cache，且对后续 CNN 请求可见。它不代表 DDR 已写回。
- CNN 逻辑地址窗口为 `[0,0x01000000)`，DDR 物理地址为 `0x10000000 + logical`。先检查完整地址，再映射，不通过截断地址回绕。
- AXI3 HP0 为 64 bit 数据、6 bit ID。ID 固定 0，64 B 行使用 8 拍 INCR 突发，长度字段为 7、每拍 8 B；64 B 对齐保证不跨 4 KiB。AW/W 独立推进，写完成必须等待 B；读写错误及错误 ID 被检查。

## Cache CSR

所有 CSR 都零等待，`cache_csr_ready=1`。表中为接口地址低 8 bit 的偏移。零等待意味着硬件接受寄存器操作；慢速维护操作由 `busy` 和错误位报告结果。

| 偏移 | 名称 | 语义 |
|---|---|---|
| `0x00` | STATUS | bit0 初始化完成；bit1 正在处理请求/维护或有维护排队；bit2 CSR/维护错误；bit3 CNN 存储错误；bit4 正在排空取消的请求 |
| `0x04` | COMMAND | 写 1：clean/fence；写 2：先 clean 再 invalidate；写 3：空闲时清除错误 |
| `0x08` | RANGE_START | 维护区域的逻辑起始字节地址，暂存寄存器 |
| `0x0C` | RANGE_BYTES | 维护字节数，暂存寄存器；0 表示空区域 |
| `0x10` | READONLY_END | 只读前缀的结束地址，不包含该字节；只允许空闲修改 |
| `0x14` | PROTECT_ENABLE | bit0 开启 CNN 对 `[0,READONLY_END)` 的写保护；只允许空闲修改，复位默认关闭 |
| `0x20` | HITS | 直接命中的请求数，不重复计算 miss 填充后的重放 |
| `0x24` | MISSES | miss 请求数 |
| `0x28` | WRITEBACKS | 成功完成的脏行写回数 |
| `0x2C` | FILLS | 成功完成的填充行数 |
| `0x30` | DDR_READ_BYTES | 成功填充字节数，64 B/行；错误事务不计入 |
| `0x34` | DDR_WRITE_BYTES | 成功写回字节数，64 B/行；错误事务不计入 |
| `0x38` | WAIT_CYCLES | 等待 DDR 行事务完成的累计周期 |
| `0x3C` | CACHE_BYTES | 本实例实际数据容量 |

计数器为 32 bit，自然回绕，硬复位清零。非法地址、未对齐字请求和受保护区域写请求置 `cnn_mem_fault`，不向算子发伪成功响应。AXI 读错误不安装新行；AXI 写错误保留脏行，允许故障处理后重新 clean。

## 运行中结果 fence 与一致性

CPU 读取忙闲状态后，其他 CNN 客户端仍可能开始请求，因此不能要求软件用“读空闲→写命令”实现原子操作。范围暂存寄存器允许运行中写；COMMAND 1/2 在一个入口的维护队列中锁存范围与模式。已接受的当前请求或 AXI 事务先完成，此后暂停接受新 CNN 请求并执行维护。队列非空时 STATUS.busy 保持 1。后续写暂存范围不修改已经排队或正在执行的命令。

命令队列满时再写 COMMAND 1/2 会置错误；软件对每个 fence 等待 busy 清零并检查 bit2/3 后再发下一条。clean 扫描所有组，但只写回与指定字节区间相交的有效脏行；invalidate 同时使这些行无效。即使区域不按 64 B 对齐，也维护相交的完整行，所以输入、输出、模型与其他处理器可写区域应按 cache line 隔离。

CNN 完成结果后，CPU 排队该结果的 fence，等待 busy=0 且无错误，再发布 PS 可读状态。PS 还必须处理自己的数据 cache 与内存屏障。PL cache clean 不会自动维护 Cortex-A9 cache。

## 取消与复用

`cnn_cancel` 立即阻止新请求及旧 CNN 响应；已发出的 AXI 事务继续遵守握手直到排空。取消期间不能用新图片覆盖旧事务可能写回的地址。等待 busy=0 后，软件应按所有权执行必要的 clean/invalidate，再允许 PS 写入和提交新批次。

取消不是全 cache 清空。已经被 cache 接纳的脏数据会保留；尚未完成的请求可被放弃。清除错误也不会丢弃脏行。整体硬复位要求系统协调 AXI/PS 复位；运行中的软件清除应使用 cancel 排空流程。

当前桥没有硬件超时后强行终止 AXI 的逻辑。如果 PS 没有完成初始化，或从设备永远不返回 B/RLAST，`busy` 会持续保持；软件等待超时只能报告故障，不能据此宣称事务已排空或立即复用相同 DDR 区域。恢复这种故障需要协调 PS/AXI 与 PL 的系统复位。正常 RRESP/BRESP 错误会在完整事务排空后上报。

## 验证入口

`scripts/test_cnn_ddr_cache.py` 编译这三个真实 RTL 模块，使用带独立 AW/W/R/B 随机停顿的 AXI3 内存模型。测试把 cache 缩为 1 KiB、DDR 逻辑窗口缩为 64 KiB，以频繁制造组冲突；生产默认仍为 128 KiB / 16 MiB。该内存模型只响应物理事务，不注入 CNN 算术结果。

覆盖十客户端并发提交、响应归属/延迟、同步 CPU RAM、字节写/符号扩展、脏驱逐、范围 clean/invalidate、PS 修改后可见性、地址/只读保护、运行中维护排队、独立 AXI 反压稳定性、读写错误，以及读事务和脏行写回事务中取消后排空。结果、源码哈希与日志保存在每次独立 `build/runs/*_cnn_ddr_cache` 目录。此回归不等于板上 DDR 时序、全网性能或布局布线验收。

2026-10-24 已完成的独立检查：

| 检查 | 结果 | 记录目录 |
|---|---|---|
| 上述 cache/AXI3 回归 | PASS；826 项请求值/协议检查，28,405 周期，769 次读突发、389 次写突发 | `build/runs/20261024_184132_914735_cnn_ddr_cache` |
| 默认 128 KiB cache + 16 KiB CPU RAM，xc7z020clg484-1 OOC 综合 | PASS；1,785 LUT、2,489 FF、36 RAMB36 + 2 RAMB18（37 块 BRAM36 等效）、0 DSP | `build/runs/20261024_184639_782498_cnn_ddr_cache_synth` |

综合使用 20 ns 时钟约束，内部寄存器间最差建立裕量为 +4.419 ns；尚未布局布线，也没有对该独立模块的 PS/其他模块端口添加板级输入输出延迟，不能当作整机 50 MHz 时序闭合。数据 cache、CPU RAM 和两路 tag 均实际推断到 BRAM，分别约 32、4、1 块 BRAM36 等效。两项检查记录了源码哈希并确认运行期间源码未改变。综合复现入口为 `scripts/synth_cnn_ddr_cache.py`。
