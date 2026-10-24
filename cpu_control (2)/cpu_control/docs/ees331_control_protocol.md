# EES331 控制桥与固件接口

实现与七页接线图相同：CPU 的零等待 MMIO 只接第五模块 `image_control_bridge`；第五模块分别驱动 CNN 的 `cnn_mmio_*` 和 DATASRAM 的 `cache_csr_*`。PS 的 GP0 只访问邮箱。地址/数据/控制位宽来自原 `io_manifest.json`；没有新增 CPU 等待线、PS 直接 CNN 控制线或 PL UART 数据旁路。

## CPU 现有九寄存器窗口

基址 `0x40000000`，原 Control/Datapath 未改。所有访问为 32 位、四字节对齐、零等待。

| 偏移 | 读 | 写 |
|---|---|---|
| 00 | 标识 45455332 | 非法 |
| 04 | bit0 请求待处理，bit1 bridge_error | 非法 |
| 08 | 索引 | 设置索引 |
| 0C | 索引指向的数据 | 写索引指向的数据 |
| 10 | PS 请求序号 | 非法 |
| 14 | CPU 已完成序号 | 发布 ACK，必须等于当前请求序号 |
| 18 | CPU 回复状态 | 设置回复状态 |
| 1C | CPU 回复数据0 | 设置回复数据0 |
| 20 | bridge_error | bit0 清除桥错误 |

索引 `0x0000..0x0067` 对应邮箱；`0x1000..0x1FFF` 转发到 CNN 的相对寄存器地址；`0x2000..0x20FF` 转发到 cache CSR。CPU 写数据寄存器时才产生一次目的写使能。

## GP0 邮箱

GP0 为 AXI3，32 位数据、12 位 ID、4 位 LEN、2 位 LOCK。普通寄存器访问仅接受对齐的单拍全字读写；不支持的突发会完整接收或返回相应拍数后给 SLVERR，且不修改邮箱。AW/W 分别握手，支持 WVALID 先到但通过 WREADY 等待地址；B/R 在反压期间保持稳定。

| GP0 相对偏移 / CPU 索引 | 内容 | 写所有者 |
|---|---|---|
| 00 / 04 | 标识 / 状态 | 只读 |
| 08 | request_sequence | PS |
| 0C | acknowledge_sequence | CPU |
| 10 | command | PS |
| 14..4C | 15 个参数，当前固件使用前4个 | PS |
| 50 | response_status | CPU |
| 54..60 | 4 个回复数据 | CPU |
| 64 | CPU_READY=43505532 | CPU |

PS 仅在 sequence==ack 时写命令/参数，完成屏障后最后发布新序号；pending 期间改参数会得到 SLVERR。CPU 先写完整回复，再最后 ACK。重复写当前请求序号没有副作用。PS 无法直接写 CPU ACK/响应，也不能通过 GP0 地址绕过邮箱访问 CNN/cache。

## 软 CPU 命令

`scripts/gen_ees331_cpu.py` 生成真实 RV32I 服务程序，当前 437 条指令 / 1748 字节，NOP 补齐为 8 KiB ROM；无栈和本地数据 RAM 需求。模板仍在 CNN 内，不是 CPU 的指令。

| 命令 | 行为 |
|---|---|
| 1 DDR_READY | 参数0必须为44524459，确认 cache 已初始化且无错误 |
| 2 CFG_WRITE | 空闲时白名单 CNN 配置寄存器写，参数0偏移、参数1数据 |
| 3 CFG_COMMIT | 空闲时提交模板或图片地址，参数0只能为4或8 |
| 4 START | DDR 和 CNN 配置就绪后启动固定流程 |
| 5 FRAME | 参数0图片槽、参数1帧号，检查 frame_ready 后提交 |
| 6 RESULT | 读结果描述，对输出区域执行 cache fence，等待 AXI 写完成后回复 frame/address/bytes/epoch |
| 7 ACK | 参数0帧号、参数1epoch必须匹配当前结果，才释放外部持有 |
| 8 RESET | 空闲时 clean+invalidate 16MiB，然后 CNN clear 增加 epoch |
| 9 CACHE_CONFIG | 空闲时仅允许 readonly_end/protect_enable 配置 |
| 10 STATUS | 返回 CNN 状态、已完成任务数、cache 状态、epoch |
| 11 CACHE_READ | 只读 cache 低地址 CSR/计数器 |

CPU 状态：0成功，1非法命令，2暂时无结果，3忙，4未就绪，5CNN错误，6cache错误，7维护超时，8错误帧号/epoch。维护操作是异步 cache 命令加轮询，CPU 不等待 DDR 总线信号；cache 的一条待处理维护队列保证其他图片计算时也能正确请求 fence。

PS UART 层任务比本表更高一级，负责模型/图片 CRC、输入区域完整性、所有权和结果分包；详见 `firmware/ps_image_server/README.md`。软 CPU 命令超时后 PS 锁住所有写入，防止迟到 FRAME 已生效而主机仍覆盖图片；此状态需整机复位，不能将一个未确认的命令当成未执行。PS 应用启动先检查没有旧活动/错误批次，DDR 自检只写第二个预留窗口的 `0x11000000..0x11001000`，不碰 CNN 16MiB 窗口。`scripts/send_cnn_images.py` 不带 `--port` 只验证冻结测试数据并生成待上传包；带串口才执行真实传输。本轮只改代码和离线验证，没有执行传图、下载或上板。

## 验证边界

`scripts/test_ees331_control.py` 真实运行原 CPU 和新 ROM，覆盖 GP0 通道反压/非法访问/突发排空、启动门控、配置保护、输出 fence、epoch ACK 与批次 clear。此短测 CNN/cache 为寄存器级响应器，不能替代实际算术/DDR/cache 验证。`scripts/test_ees331_server.py` 编译同一 `server.c` 并验证 CRC、地址边界、四图提交、结果分包、ACK 与复用；主机回调不代表 ARM BSP 或板上执行。所有运行记录写入独立 `build/runs`。
