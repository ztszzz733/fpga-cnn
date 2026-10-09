# 固定 MEM 时序契约（C1，真实 SRAM wrapper 待确认）

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## 2026-09-17 收到 Datapath 后的实际情况

已用本方真实 Control 连接收到的生产 Datapath，单条 ADD 和混合程序仿真通过，详见 [对接核查](datapath_connection_review_20260917.md)。对方在 EX→MEM 沿接受 SRAM 的全部读写请求，Load 数据在 MEM 周期稳定、MEM→WB 沿保存；这符合本文下面“旧 EX 地址先采样”的读时序例子，并使原一拍 load-use 规则通过。对方 Store 同样在 EX→MEM 沿提交，**与本文旧表中的 MEM 级 Store 写入说法有阶段差异**；CNN MMIO 则仍在 MEM 级提交并要求零等待。

当前没有修改 C1 的端口或编码，也没有代替三方重新冻结提交边沿。正式系统契约应分别记录 SRAM 的 EX 提交和 MMIO 的 MEM 提交；实体 SRAM wrapper、第二端口及冲突行为尚未验证。下文保留原契约与旧 stub 时序作为历史基线；其中“仅支持 LW/SW”是旧模型描述，当前 Control 测试 stub 已补充字节和半字行为。

2026-09-14 按 P1 更新：M 已正式接受 C1 v1.0 开发基线，详见 [P1 回复](control_reply_to_P1.md)。对齐 D1：Datapath 原则接受固定时延、无 ready/stall 的逻辑基线；提议 IMEM/Data SRAM 固定 1 周期同步读。下面的边沿表仍是 Control/stub 所需条件，并非真实同步 SRAM 的验证结果。D1 所说的“在 MEM 发起/完成”必须落实到实际采样沿，不能仅凭“一周期”认定兼容。

| 公共参数/时序 | 开发建议 | 冻结/验证状态 |
|---|---|---|
| RESET_PC | 参数默认 `32'h0000_0000`，在 Datapath 持有 | stub 已参数化；最终地址待三方确认 |
| 流水复位 | 上升沿同步低有效 | M 正式接受 CPU 流水同步低有效；全系统待共同确认 |
| IMEM | 固定 1 周期同步读 | 待 wrapper 定义、返回配对和错路丢弃测试 |
| Data SRAM A 口读 | 固定 1 周期同步读 | 待明确请求接受沿、数据有效沿及 WB 元数据配对 |
| SRAM/MMIO 写 | `valid_m && memwrite_m` 对应接受沿只写一次 | 待 wrapper 定义和实际提交检查 |
| MMIO | 第一版无额外等待，偏移 0x00～0x20 | 等待时序及 CNN_MMIO_BASE 待三方冻结 |
| 可变延迟 | 第一版不支持 | 需要时升级 C1；不得暗加保持假设 |

本接口没有 MEM ready/stall。成立条件是：Load 的地址在 M 周期稳定；数据在该周期结束的 M→W 上升沿前满足建立时间；这一沿后 WB 最终数据可用于 EX 前递。stub 用数组读表达这一功能时序，不模拟 BRAM 时序参数、外部总线或 DMA。

令 L=`LW x5,0(x0)`，C=`ADD x6,x5,x2`。`E0` 是 L 已进入 EX、C 已进入 ID 的上升沿。

| 时段/上升沿之后 | D | E | M | W | 行为 |
|---|---|---|---|---|---|
| E0→E1 | C | L | 旧指令 | 旧指令 | load_use=1；PC/IF-ID 保持，ID/EX flush=1 |
| E1→E2 | C（保持） | 气泡 | L | 旧指令 | L 不被冻结；M 周期读取数据；暂停条件消失 |
| E2→E3 | 下一条 | C | 气泡 | L | W 数据已锁存；C 的 fwd_a=WB；计算正确结果 |
| E3→E4 | 后续 | 后续 | C | 气泡 | C 正常前进 |
| E4→E5 | 后续 | 后续 | 后续 | C | C 在下一写回沿提交 |

测试数值：内存 L=42，x2=7，C 最终 x6=49；仅一次 PC 保持。LW→SW 的数据依赖也暂停一拍，Store 在 E 从 W 取得 91，随后只提交一次。

同步 BRAM 可兼容的例子：在 E→M 沿采样 **旧 E** 地址，BRAM 输出在 M 周期内有效，M→W 沿锁存。wrapper 必须保证读请求和有效指令配对。若 BRAM 只能在 M→W 沿才采样 **M** 地址，则同一沿 WB 不能直接获得新的同步读值，当前契约不兼容。

更慢或可变延迟需要新增 MEM 请求/完成握手、M/W/前级保持控制、单次访存提交及 redirect 处理，再升级接口；不得只把延迟参数改成 2 后仍使用本 load-use 规则。

IMEM stub 是组合查表，IF/ID 在沿采样 PC 对应指令。真实同步 IMEM wrapper 必须保持 PC/指令配对，stall 时保存返回指令，redirect 时丢弃错误路径返回值。当前 Control 没有取指 ready，不能支持任意读取延迟。

实际 IMEM 至少要记录请求 PC/valid：IF/ID 暂停时不能被返回覆盖；重定向时使旧请求失效，晚到返回不能变成有效目标指令。验收需覆盖暂停期间返回、重定向同沿返回、重定向后旧路径返回及连续重定向。无法在固定时延内完成缓冲/失效处理时，双方升级接口。本 stub 不模拟这些同步请求。

数据地址是 32 位字节地址、小端。stub 仅支持 1 KiB 内 4 字节对齐 LW/SW，不验证 LB/LH 等的数据拼接、未对齐异常或 CNN 双口 SRAM 冲突。Load/Store 全部类型编码由组合译码测试独立覆盖。

D1 第一版执行约束：LB/LBU/SB 允许任意字节地址；LH/LHU/SH 为 2 字节对齐；LW/SW 为 4 字节对齐；CNN 张量基地址为 4 字节对齐。不支持未对齐半字/字访问，也无异常反馈；真实测试程序不得生成这些访问。此约束不扩展 stub 的 LW/SW 模型范围。
