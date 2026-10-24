# EES331 PS UART1 图像服务

`server.c` 是可独立测试的任务协议/DDR 所有权逻辑；`main.c` 是 Xilinx standalone Cortex-A9 BSP 适配层。它使用 J3 上的 **PS UART1，物理基址 0xE0001000**，默认 115200。不能将现有 JTAG AXI 设计的初始化文件当成 PS DDR 初始化。

以当前板级工程导出的 XSA 新建 standalone Cortex-A9 应用，加入 `main.c/server.c/server.h`。BSP 需启用 uartps、xil_io、xil_cache、xtime。检查 UART1 的设备编号，必要时设置 `EES331_UART_DEVICE_ID`；程序会拒绝错误的硬件基址。PS 必须由与 XSA 匹配的 FSBL/`ps7_init` 先初始化 DDR、时钟和复位。链接脚本必须将应用、堆栈和其他 DMA 缓冲放在 `0x10000000..0x12000000` 之外，例如 DDR 低地址；共享区前 16 MiB 映射 CNN 逻辑地址 0，后 16 MiB 预留。没有匹配 XSA/BSP 时，不宣称此应用已生成可上板 ELF。

PS 先等待真实软 CPU 的 `CPU_READY`，通过 STATUS 确认没有正在计算、等待结果释放或故障的旧批次，并等待 cache 初始化完成。随后使用预留第二窗口 `0x11000000..0x11001000` 的 4 KiB scratch 做 DDR 读写自检，再通过 mailbox 发布 `DDR_READY`。这段 scratch 不在 CNN/cache 的 16 MiB 可访问窗口内，应用热重启不会覆盖模型或在途数据。它没有 CNN 计算实现，也不能越过软 CPU 直接访问 CNN/cache 寄存器。PS 写数据后 flush 加 DSB；CPU 完成 PL cache 输出 fence 后 PS invalidate 加 DSB 再读取结果。

IMIO/IMOR 头仍为 `<4sBBHI`：magic、op/status、tag、length、address，尾部小端 CRC32 覆盖头和有效载荷。op1 写、op2 读与旧协议兼容；op3 将 address 解释为任务编号、payload 解释为小端 uint32 数组，可用 0 字节载荷。回应载荷最多 256 字节。完整的重复请求只缓存最近一包；重发相同包幂等，不能跨新请求重放旧写请求。包间超时丢弃半包，随后扫描 IMIO magic 重新同步。

任务编号：0 CAPS，1 MODEL_BEGIN(end/version)，2 MODEL_END(CRC)，3 CFG_WRITE(offset/value)，4 TEMPLATE_COMMIT，5 DEFINE(slot/input/workspace/frame/length/workspace_bytes)，6 START(count)，7 FRAME(slot/CRC/version)，8 RESULT(offset，可省略为0)，9 ACK(frame/epoch)，10 STATUS，11 BATCH_RESET。结果载荷为 frame/address/bytes/epoch 四个 uint32，加最多 240 字节真实 DDR 输出；大结果按 offset 顺序分包，完整读完前拒绝 ACK。MODEL_BEGIN 和 BATCH_RESET 只能在旧结果全部 ACK 后执行，先由软 CPU clean+invalidate 全窗口再复用。模型与图片均顺序上传并校验完整 CRC；运行期间只允许向未提交的图片槽写入，拒绝覆盖模型、工作区和未释放图片。

这是有限四图批次协议。每批重装紧凑模板/四个描述符，模型可在批次间保留；当前主机工具默认重新装模型，便于首次验收。收到完整 CPU 回复的非法请求可以按状态修正重试；CPU 请求超时意味着副作用未知，服务会锁住后续 DDR 读写和所有状态变更，返回状态5，必须复位并重新初始化整机后重装。这样即使迟到 FRAME 提交，也不会重写它的图片。RESET 仅适用于空闲且结果全部释放的批次，不是运行中/故障时的强制 abort；cache/AXI 故障可能同样需要整机复位。没有后台自动复位或上板操作。

对应软 CPU：`../ees331_cpu/program.mem`，由 `scripts/gen_ees331_cpu.py` 生成，原 CPU Control/Datapath 保持不变。`scripts/test_ees331_control.py` 验证真实 CPU 指令运行及控制桥，CNN/cache 在该短测中是寄存器级响应模型；实际算术与缓存另由各自 RTL 测试验证。
