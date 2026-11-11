# 存储侧独立开发交付（2026-11-10）

目标板：EES331 / XC7Z020-CLG484-1。入口目录：本仓库的 `cpu_control (2)/cpu_control/storage_v2`。

本目录保存独立开发的新存储模块、来自现有工程的原始基线副本、真实 CPU 联调测试，以及 CNN v0.2 交接包。它在 `bai-datasram` 分支作为**可复现的候选存储子工程**保存；生产 `system_cnn.f` 和其它旧顶层仍使用旧模块。算子数量、整机资源优化留到最后整合。

## 本分支继续完成的独立联调

- `rtl/tile_local_ram.sv`：32 KiB 双端口 tile BRAM。计算端固定一拍，MOVER 端可背压；同字冲突时计算端优先，不依赖双写同址的未定义行为。
- `rtl/tile_row_dma.sv`：先逐行检查整个二维范围，再将每一行拆成一条顺序 MOVER 命令。DDR 行起址及步长要求 8 字节对齐；本地起址允许任意字节。首版最多 4096 行，整组失败即停止后续行。逐行预检没有使用乘法 DSP。
- `rtl/tile_dma_system.sv`：行控制器、真实 MOVER、本地 BRAM 接成独立链路，外接模拟 AXI3 DDR。任务接受时锁存 DDR 配置，外部 `enable` 撤销后已接受任务继续排空；故障锁定时拒绝新任务。
- `rtl/program_loader_csr.sv`：参数化 GP0 后级 CSR 服务接口，控制 IMEM 和 CPU RAM 的停机写入、回读与错误查询。`tb/program_loader_top.sv` 是与两块真实可下载 RAM 相连的验证顶层。它尚不是 AXI3 GP0 从设备，也不解析 RFW1/RDL1；PS 软件仍须完成包校验与安装事务。
- `tb/tile_dma_system.cpp` 使用 CNN v0.2 交接包的两组 tile 和 40 条实际搬运记录，合并为 12 组按行搬运，逐字比较 32 KiB 本地存储、64 KiB 模拟 DDR 与保护字节。最终输出由 golden 经真实计算端写入；**只验证存储传输，不声称新链路执行了 CNN 算术**。还覆盖同字冲突、配置中途变化、`enable` 撤销、参数错误和末行溢出不发 AXI。
- `tb/program_loader_top.cpp` 验证 IMEM/CPU RAM 下载、回读、`.data/.bss`、字节使能、越界与未对齐拒绝、运行中拒绝、应用复位后保留。

上述新顶层继续与生产顶层隔离；接入真实 CNN 算子、PS7、GP0 AXI、CPU 安全停机和板级时钟复位仍需对应模块联合验收。

### 加载器 CSR 草案

`program_loader_csr` 的 `BASE` 参数默认 `0x40001000`，只表示**待 GP0 桥转发的 PS 侧地址示例**，不等同于 RV32I 的 CNN MMIO 地址。正式 GP0 窗口须与 PS 方确认后设置该参数。全部寄存器为 32 位对齐、全字写；总线响应 `bus_status` 为 0 成功、1 非法访问、2 服务忙、3 应用未停机。

| 偏移 | 用途 |
|---|---|
| `0x00` | TARGET：0 IMEM，1 CPU RAM |
| `0x04` | 目标存储绝对 CPU 地址 |
| `0x08` | 写入数据 |
| `0x0c` | 实际 RAM 字节使能，低 4 位 |
| `0x10` | STATUS：bit0 忙、bit1 完成、bit2 错误、bit3 应用停机 |
| `0x14` | COMMAND：写 1 执行 RAM 写，写 2 执行 RAM 回读 |
| `0x18` | 最近一次回读数据 |
| `0x1c` | CONTROL：写 bit0 清完成/错误 |

命令写入只表示**开始**，服务软件必须轮询 STATUS 完成并检查错误，再回读验证。运行中命令直接拒绝；模块接收的 `app_halted` 必须由上层安全停机和排空逻辑证明，软件写一个位不能替代该证明。RFW1 包校验、RDL1 重传幂等和 SD 提交都属于 PS 服务，本模块不声称完成。

## 三步工作结果

| 工作 | 本轮完成 | 未完成的范围 |
|---|---|---|
| 1. 验证旧 DDR/cache 基线 | 原 cache 独立 RTL 回归 826 项 PASS；另在 128 KiB cache＋真实旧 CNN＋模拟 AXI DDR 上运行交接包两种 tile，各 overlap/serial/preloaded/stress，共 8 场景 PASS。记录逐阶段结果、DDR 流量、周期与等待指标。 | **四图完整网络未复跑。** 本机只有原 full manifest／历史报告，缺少匹配的完整运行数据和原模型；新 ZIP 也明确不含完整网原始大数据。需补交原数据后继续，不将 tile PASS 当作全网 PASS。 |
| 2. CPU 本地可下载存储 | `rtl/download_ram.sv`：固定一拍 CPU 访问、停机加载、字节写、回读、范围检查、拒绝运行中加载、复位保留。8/16/64 KiB IMEM 与 16 KiB CPU RAM 的 RTL 测试通过。原 Control＋原 Datapath 执行真实下载的 RV32I 程序，两次启动均正确；新增独立 CSR 服务端和两块 RAM 联调通过。 | GP0 AXI3 从设备/地址分配、CPU 运行中安全停机控制器、RFW1/RDL1 安装服务尚未接入。测试以显式停止条件驱动加载，不把测试顶层当作生产停机控制器。 |
| 3. 最小 DATA MOVER | `rtl/data_mover.sv`：DDR↔LOCAL 双向、一条命令在途、本地任意 byte 起址、64 位 AXI3、短尾窄访问、错误及超时排空；136 条包内搬运用例＋100 条跨页随机用例＋非法命令与错误恢复测试 PASS。另与真实 tile BRAM、行控制器联调通过。 | 独立 MOVER 单测使用时序存储模型；tile 联调用真实本地 BRAM 和模拟 DDR。尚未连接真实 CNN→MOVER 适配 RTL或 PS DDR。当前采用单拍 AXI 和逐字节本地访问，未做带宽优化。 |

新 RTL 已进行 XC7Z020-CLG484-1 独立综合。各档 RAM、MOVER、tile 联调顶层和加载器联调顶层的报告见 `evidence/synth/`；该检查只确认模块实现和 RAM 推导，不评估整机资源是否足够，也不代表布局布线或上板验收。

| 独立综合配置 | LUT | FF | RAMB36 | DSP |
|---|---:|---:|---:|---:|
| 64 KiB IMEM | 93 | 38 | 16 | 0 |
| 16 KiB CPU RAM | 135 | 71 | 4 | 0 |
| 32 KiB tile RAM 单体 | 109 | 69 | 8 | 0 |
| tile 行控制＋MOVER＋tile RAM | 1223 | 662 | 8 | 0 |
| CSR 加载器＋64 KiB IMEM＋16 KiB CPU RAM | 354 | 250 | 20 | 0 |

上表不同配置有重叠模块，不能相加为整机资源；`tile_system` 中的 8 块就是其内部 tile RAM。首轮行控制器因组合乘法占 14 个 DSP，已改为先逐行预检查；最终报告为 0 DSP。

## ZIP 实际补齐的信息

`incoming/CNN_storage_handoff_v0.2` 保留原交接包内容；153 个清单文件的长度和 SHA256、源码快照、两个独立整数参考、96 组非对齐向量、随包 6 个算子测试记录及十图输出记录均经本机脚本复核。

这次真正补齐了：输入／权重／参数二进制、三个阶段 golden、layout/moves/tasks、源码及原算子测试证据。CNN 方选定由存储 MOVER 支持本地任意字节地址；不再要求 CNN 引入对齐暂存拷贝。实际地址采用 `layout.json` 中带保护区的布局，未照抄早先讨论稿的连续偏移。

本轮按用户授权，将包内 C1 v0.2 建议作为**存储侧实施版本**。它不是 PS 地址分配证明，也不表示 CPU 方已接受全部新增端口。相比旧 CPU 回复，业务响应采用 32 位 `rsp_status`；需要旧 `error` 位的接口可由适配层生成 `error=(rsp_status!=0)`。

## 首版接口约定

### 可下载 RAM

- CPU 读请求在一个上升沿采样，该沿之后输出对应数据，保留原同步一拍契约。CPU 数据口接 LSU 的 byte 地址及已移位 `wdata/wstrb`，支持 SB/LB 等；IMEM 配置 `READ_ONLY_CPU=1`。
- IMEM 使用 `BASE=0`，CPU DATA RAM 使用 `BASE=0x00010000`。真实 CPU 测试把其 `SRAM_BASE/SRAM_SIZE` 同步配置为 `0x10000/0x4000`；没有只改 RAM 而保留旧 CPU 译码。
- 加载口地址为该存储的绝对 CPU 地址，要求 4 字节对齐；`ld_wstrb[3:0]` 选择写入字节，零选通为无副作用空写。`ld_valid&&ld_ready` 接收，响应保持到 `ld_rsp_ready`。
- 必须由上层先确认应用停止并排空，再置 `app_halted`；模块还检查当拍 CPU 无读写请求。运行中加载读写均拒绝，CPU 访问不因加载而延长。
- `app_reset` 或服务接口复位均不擦除 RAM。上电未装载内容未定义；`.data` 初值与 `.bss` 清零由加载端提供。
- 本轮真实 RV32I 测试验证 `.data=35`、`.bss=0`、加法得到 42、SB/LBU、邮箱写回及两次复位后重新执行。它是直接机器码测试，不声称使用尚未收到的 C SDK 或 RFW1 安装器。

### DATA MOVER

- 单命令从 `cmd_valid&&cmd_ready` 接收到响应消费期间独占。`cmd_src/dst/bytes/flags` 各 32 位；flags bit0：0=DDR→LOCAL，1=LOCAL→DDR；其他位必须零。
- DDR 字段为保留区偏移，本地字段为本地 byte 地址。接受时检查整个区间、33/34 位地址加法及物理溢出；物理 DDR 首地址要求 8 字节对齐，本地允许任意 byte 起址，长度为任意正整数。
- `cfg_ddr_base/cfg_ddr_bytes/cfg_local_bytes` 在空闲时配置，配置必须覆盖真实可访问的底层存储。local 使用完整 32 位存储字，底层 RAM 应覆盖其末字；本轮 local 容量均为 4 字节整数倍。`enable` 是系统准入信号，拉低后不接受新命令；已接受命令继续排空。
- AXI3 数据 64 位、ID 固定 0、INCR、LEN=0，一次最多一拍；8 字节正常访问，尾部使用 4/2/1 字节窄传输，严格不扩大 DDR 读取区间。没有任何一笔 AXI 事务跨越 4 KiB。AW/W 独立握手；写完成等待 B，读完成等待最后一次本地写响应。
- local 口为 32 位对齐字地址＋4 位字节选通，MOVER 每次访问一个有效 byte，负责选通和移位；`local_rsp_valid` 不带 ready，响应只能对应已接受请求，可在接受当拍或之后返回。字节写必须在响应前真正生效。
- `rsp_status` 保持至 `rsp_ready`；成功 `rsp_bytes_done=请求长度`，失败为 0。失败前可能已有部分写入，不支持按完成量自动续传或重试。
- 已实现状态：0成功、1非法flags、2零长度、3范围/溢出、4DDR对齐、5AXI读错误/ID不匹配、6AXI写错误/ID不匹配、7超时、10本地访问错误。8取消、9故障锁定响应编码保留；当前无 abort 命令，故障时以 `cmd_ready=0` 和 `fault_locked=1` 阻止新命令。
- watchdog 统计等待握手/响应期间的连续无进展周期，默认 1024；不统计整个长命令总时间。超时先锁故障，但继续保持已发布请求、接收在途返回。**只有排空后才发布完成响应**；永久无响应时保持忙与锁定，不能假装取消成功。
- `drained=1` 表示无在途事务，`busy=1` 包括待消费响应。错误响应消费后，在空闲且底层已排空时给 `recover` 脉冲解除锁定。应用复位不得直接复位在途 MOVER；若必须全局复位，板级需保证总线两端和在途事务一并处理。

本轮仿真中的 `0x10000000` 仅为模拟 DDR 基址。板上实际 DDR 基址、保留区和缓存交接仍需要 PS 方提供。

## 验证记录与边界

| 测试 | 证据 |
|---|---|
| 旧 cache 826 项；缩小到 1 KiB 强制制造冲突 | `build/cache/result.json`、`simulation.log`、`metrics.json` |
| 128 KiB 真实 cache/CNN/模拟 DDR 的 8 场景 | `build/cache128_tiles/result.json` 和各场景 `metrics.json/simulation.log` |
| IMEM 8/16/64 KiB、数据 RAM 16 KiB | `build/ram_8192_0/`、`ram_16384_0/`、`ram_65536_0/`、`ram_16384_65536/` |
| 原 CPU Control＋Datapath 执行下载程序 | `build/cpu_download/result.json`、`simulation.log`、`tb/cpu_download.sv/.cpp` |
| MOVER 真实 RTL、AXI和local模型 | `build/data_mover/result.json`、`simulation.log` |
| 行 DMA＋真实本地 BRAM＋模拟 AXI DDR | `build/tile_dma_system/result.json`、`simulation.log` |
| CSR 加载控制＋真实 IMEM/CPU RAM | `build/program_loader_top/result.json`、`simulation.log` |
| 独立综合 | `evidence/synth/*_utilization.rpt`；本机重跑时生成 `build/synth_v2/` |

MOVER 覆盖交接包 96 个 lane 向量和两例共 40 条 moves，完整比较目标区与邻接保护字节；另加 100 次跨页随机传输，8 种非法命令、8 种错误／延迟注入，其中 3 种验证超时后继续排空。共 192,806 仿真周期、4,088 次 AXI 事务、30,834 次 local 访问。用 golden 作为搬运测试的源数据时，只验证复制，不冒充 CNN 算术执行。

128 KiB cache 诊断中的主 tile 普通模式为 2,103,703 周期，DDR 读 28,032 B、写 12,288 B；stress 为 2,141,671 周期。短行普通模式 6,180 周期、DDR 读 512 B、写 192 B；stress 为 36,297 周期。各阶段真实算子写出字节逐一核对，最终结果经 cache fence 后从模拟 DDR 读回。当前一个活动 tile，仲裁竞争指标为零；因此不能用它推算多帧吞吐或完整网络等待。

新包 fixture 使用 512 位依赖表，旧 compact 基线使用 256 位。诊断脚本先断言高 256 位为零后去除这些零字段，并允许新包头部包含额外空闲上下文。测试台只对多个活动帧要求跨帧重叠。未更改基线算术 RTL、golden 或地址数据；这些改动和检查保存在 `scripts/baseline_tiles.py` 与生成的 `tb/diagnostic_ddr_main.cpp`。

## 复现

本机 Python：`C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe`。Verilator 5.050 来自 `C:\msys64\ucrt64`，MSVC 来自 `D:\VIsual Studio\visual studio 2022`，Vivado 2025.2 来自 `D:\Xilinx\2025.2`。实际路径集中在 `scripts/run_native.py`；其他机器仅需调整工具路径，原 CPU/cache 源码已随目录提供。

在本目录依次执行（每条为独立命令）：

```text
python incoming/CNN_storage_handoff_v0.2/tools/verify_cnn_storage_bundle.py incoming/CNN_storage_handoff_v0.2
python scripts/prepare_vectors.py
python scripts/run_native.py cache
python scripts/baseline_tiles.py
python scripts/run_native.py memory
python scripts/run_native.py cpu
python scripts/run_native.py data_mover
python scripts/run_native.py tile_dma_system
python scripts/run_native.py program_loader_top
python scripts/run_synth.py
```

`run_synth.py` 将同一份 RTL 复制到无括号的临时目录启动 Vivado，避免上层工程目录名 `(2)` 被 Windows 批处理误解析；综合报告回写 `build/synth_v2/`。本机沙箱内 Vivado Tcl Store 初始化会失败，需在可正常启动 Vivado 的执行环境运行。

测试脚本会更新本目录 build 下同名结果。复现所需的基线源码与 CNN v0.2 交接包均随本目录提交；`baseline_tiles.py` 不会从其他本机目录补源。需要保存多轮测试时先复制 `build` 结果。

## 本轮修正与后续依赖

Vivado 第一次受运行权限影响，无法安装用户 Tcl 组件；在获准的执行环境中启动后恢复。第一次 CPU 双写口 RAM 综合失败，原因是两个端口放在同一个时序块；拆成两个同步端口后恢复 BRAM 推导，并重跑 RAM／真实 CPU 仿真。旧测试台不接受新 fixture 的头部／依赖表尺寸，已按上述无损缩减规则形成单独诊断入口。

后续仍需 CPU／PS 方提供：匹配的 XSA/初始化文件、实际 DDR 保留区与缓存交接、GP0 加载器窗口和固件安装协议、生产安全停机/复位控制。CNN 新 MOVER 适配 RTL 尚未收到。上述依赖均未在本轮虚构为完成；本轮交付的 RTL 和测试可独立复现。
