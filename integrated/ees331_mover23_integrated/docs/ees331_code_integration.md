# 按六模块接线图完成的 DDR/cache 与新 CNN 代码

2026-10-24。用户最后明确本轮先改代码、不需要上板。本轮交付是 RTL、软 CPU 固件、PS/电脑端协议代码和离线仿真；没有下载硬件、生成新 bitstream 或进行实板测试。

## 现在使用哪个入口

新入口是 `rtl/soc/ees331/face_soc_ees331_top.sv`，文件清单 `rtl/filelists/system_ees331.f`。在这个入口中，原六个功能位置保持平级，PS7 为第七个同级实例。新文件清单不引用 `partners/cnn/FPGA1` 的旧 CNN，不引用旧 `face_soc_top.sv`，也没有在片内分配 16 MiB SRAM。

| 六模块位置 | 新入口中的实例 | 实际变化 |
|---|---|---|
| CPU_CORE | `cpu_core u_cpu_core` | 原 Control/Datapath 不变；使用零等待索引/数据寄存器，CPU 是 CNN 控制的唯一发起方 |
| CNN | `cnn_ees331 u_cnn` | 自研 K3×2、K1×4，DW7/Post/Add/Pad 各一套；四帧共享一份模板 |
| DATASRAM | `datasram_ddr_subsystem u_datasram` | 独立 CPU 本地 RAM 16 KiB，以及 CNN cache 128 KiB；HP0 连 PS DDR |
| IMEM | `imem_rom u_imem` | ROM 8 KiB；新服务程序 437 条指令、1748 B，余量补 NOP |
| IMAGE_BRIDGE | `image_control_bridge u_image_bridge` | GP0 AXI3 邮箱、CPU MMIO 转接和 cache 维护；此路线收图由 PS UART1 软件处理 |
| CLOCK_UNIT | `clock_unit u_clock_unit` | 同一 PS FCLK0 驱动六模块和 GP0/HP0 ACLK；原三拍同步释放复位保留 |

旧入口和旧 CNN 文件保留用于历史回归；继续编译旧 `system_cnn.f` 得到的是历史实现。需要新实现时选 `system_ees331.f`，不要把两份入口清单混编。

## 接线与图一致的依据

设计基线是 [七页 draw.io](../deliverables/ees331_ddr_io/ees331_soc_ddr_io.drawio)。地址、数据、控制三组仍使用该图的信号名。`scripts/check_ees331_wiring.py` 逐项核对顶层声明和两端命名连接，128 根信号全部通过，另核对统一时钟、复位和 UART1 的 MIO48/49 路线。

- CNN ↔ cache：10×32 位地址和数据、10 位 valid/write/byte/ready/response、cancel 和 fault。
- PS → 控制桥：GP0 AXI3，32 位数据、12 位 ID、4 位 LEN、2 位 LOCK。
- cache → PS：HP0 AXI3，64 位数据、6 位 ID、4 位 LEN、8 位 WSTRB。
- CPU ↔ 本地 RAM：保留固定一拍接口，没有添加 DDR 等待线。
- CPU → 控制桥 → CNN/cache：按图中 M0/M1/F 连接，没有 PS 直接启动 CNN 的旁路。

`ees331_ps_wrapper.sv` 只把 Vivado BD 接口后缀映射到图上的名称；107 个 PS 导出端口已与实际生成的 PS7 wrapper 对照。`EES331_EXTERNAL_PS` 是仿真编译开关，用 AXI 端口上的 PS/DDR 模型代替物理 PS；正常硬件编译例化真实 PS7 BD。

## 存储和调度实现

cache 为 64 B 行、2 路组相联、四个同步数据 bank、write-back/write-allocate。每行 DDR 突发为 8×64 bit。它做完整逻辑地址检查，将 `0..0x01000000` 映射到物理 `0x10000000..0x11000000`；没有截断高位地址造成别名。

首版为**全局一笔访存请求在途**，包括 hit 和 miss。不同算子能重叠计算，但 cache 访问需要仲裁；miss 或维护期间会阻塞后续请求。4 笔 miss 并发和多 bank 同拍命中仍属后续性能优化，不能把这一版称为已经实现。

维护 CSR 支持区域 clean、clean+invalidate、只读模型保护和计数器。维护命令先锁存范围，排在当前请求之后；结果只有在 dirty 行写回和 AXI B 响应完成后才交给 PS 读取。cancel 排空已接受的 AXI 事务并抑制旧 CNN 响应。若 DDR 永不返回响应，不能把软件超时当作事务已排空，详见 [cache 契约](ees331_cache_contract.md)。

紧凑调度使用 640 bit×256 行模板，逻辑容量 20 KiB；四帧各维护 PC，16 个槽只保存 owner 和最多两个最终消费者。没有 524/1024 条命令展开副本，也没有 1024×1024 的消费者表。只有最后一步结果完成且收到正确 frame/epoch ACK 才释放外部持有。非法 owner/输出槽冲突报告错误 6，避免永久等待。格式见 [CNN 寄存器与模板](ees331_compact_cnn.md)。

Post/DW7 在新入口中使用单独的同步 RAM 版本，旧算术源文件和历史证据保留。DW7 增加同步取权重等待拍，数值不变；Post 中部分参数银行被 Vivado 映射到 LUTRAM，不能宣称全部参数均占 BRAM。

## CPU、PS 和电脑端代码

- `firmware/ees331_cpu/program.mem`：真实 RV32I 服务程序，负责模板配置、四帧地址提交、结果 fence 和 epoch ACK；生成器 `scripts/gen_ees331_cpu.py`。
- `firmware/ps_image_server/server.c`：IMIO 数据/任务协议、模型和图片 CRC、上传所有权、结果分包以及超时后禁止继续写入。
- `firmware/ps_image_server/main.c`：PS UART1 的 standalone 适配，先检查 CPU 状态，再在预留第二窗口 `0x11000000` 自检；共享数据 flush/invalidate 和屏障明确分开。需要匹配的 BSP/PS 初始化，**本轮没有编译 ARM ELF 或运行该适配层**。
- `scripts/send_cnn_images.py`：准备冻结模型、20 字模板和四图上传包；不带 `--port` 只做本地校验，不访问串口。完整 131 步、四张 112×112 的上传包已准备和校验，但不等于 DDR 版全网仿真通过。

邮箱/命令说明见 [控制协议](ees331_control_protocol.md) 和 [PS 服务 README](../firmware/ps_image_server/README.md)。当前按有限四图批次工作；idle RESET 用于正常批次复用，不等于运行中 abort。结果仍被持有或事务状态未知时禁止覆盖旧图片/工作区。

## 本轮验证

以下小图使用原四张测试图的 8×8 RGB ROI、同一冻结整数参考，每图 8 步，共 32 个实际算子任务。PS/DDR 是 AXI 总线模型，CNN、CPU、控制桥和 cache 是真实 RTL。

| 检查 | 最终记录 | 结果 |
|---|---|---|
| 图与顶层逐根对照 | `build/ees331_wiring_check.json` | 128 根信号 PASS |
| cache 独立协议/数值 | `20261024_184132_914735_cnn_ddr_cache` | 826 检查 PASS，包括停顿、取消、错误和维护排队 |
| CNN 配置/租约/ACK | `20261024_215557_216919_compact_cnn` | 正常四图及非法租约、帧号、epoch、错误恢复 PASS |
| Post/DW7 数值 | `20261024_183642_006922_ees331_bram_operators` | 512 通道、滑窗、停顿、重启与复用 PASS |
| 真实 CPU 邮箱服务 | `20261024_184020_033055_ees331_control` | GP0/CPU 指令和命令握手 PASS |
| PS 可移植服务 C | `20261024_220057_896748_ees331_server` | CRC、保护、结果分包、响应/维护超时后禁止覆盖 PASS |
| CNN+cache 四模式 | `20261024_215719_084012_ees331_full` | overlap/serial/preloaded/stress 均 PASS；`full_network=false` |
| 真实六模块联合 | `20261024_215712_328991_ees331_soc` | 32 任务，71,856 输出字节逐值检查，四份结果实际 DDR 读回 PASS |

六模块联合运行计数 921,718 拍，含 CPU 配置/轮询/收尾；真实跨图算子工作重叠 146,625 拍，峰值 4 活跃帧。最终 4096 B SHA256 为 `eecab63788e81b2076db269cf649de919bfdfec17c9a5f3d5ed2e5ab2ac6be32`，与小图参考一致。

相同 CNN/cache 小图中，并行 864,284 拍、串行 1,736,040 拍，约 2.01 倍批次吞吐；预加载 855,818 拍、随机停顿/慢结果回收 909,564 拍。这是小图仿真对照，不是板上速度或完整 MobileFaceNet 性能。

已做的独立 OOC 综合仅用于检查代码映射：cache+CPU RAM 为 1785 LUT / 2489 FF / 37 BRAM36 等效 / 0 DSP；DW7 为 6757 LUT / 4075 FF / 8 BRAM36 等效 / 12 DSP；独立通用 Post 为 3402 LUT / 346 FF / 1.5 BRAM36 等效 / 22 DSP，部分参数使用 LUTRAM。**没有本轮整机资源及时序通过结论。** 此前整机工程构建遇到路径/运行器问题；用户随后收窄为代码范围，没有继续整机综合或布局布线。

本轮没有重跑 DDR 版完整 131 步×4 MobileFaceNet。历史纯 SRAM 的 653,428,459 拍及 512 B 全网输出哈希仍仅属于历史实现，不能移用于当前 DDR 版。

## 复现入口

在本项目目录、已配置的本地 Python/Verilator/MSVC 环境下运行：

```powershell
python scripts/check_ees331_wiring.py
python scripts/test_cnn_ddr_cache.py
python scripts/test_compact_cnn.py
python scripts/test_ees331_bram_operators.py
python scripts/test_ees331_control.py
python scripts/test_ees331_server.py
python scripts/run_ees331_full.py
python scripts/test_ees331_soc.py
python scripts/send_cnn_images.py --data build/self_full_data
```

`run_ees331_full.py` 默认跑小图四模式；后续明确要测完整网络时使用 `--full --data build/self_full_data --gate <同一可执行文件的四模式PASS目录>`。数据恢复方法沿用 [原数据与环境复现说明](self_cnn_repository.md)，不把 golden 数据送入存储响应器。

本轮新增/修改仅在当前代码项目；`D:/ees331_ready` 只读核对。该目录是旧 JTAG-AXI/PL 设计，没有可复用的 PS7/DDR 配置，未将它的旧 CNN 混入新入口。后续用户已明确授权将代码及更新说明发布到 `moon`，发布范围与使用入口见仓库根目录 [更新说明.md](../../../更新说明.md)。
