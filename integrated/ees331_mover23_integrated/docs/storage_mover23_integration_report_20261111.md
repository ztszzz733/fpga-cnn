# 23 路 CNN 新存储路径集成与验证报告

日期：2026-11-11。工作目录：`D:\FPGA\fpga-cnn-integrated`。本报告记录本轮新增的真实 CPU＋CNN＋新存储路径；先前的旧缓存顶层报告在 `simulation/SYSTEM_SIM_REPORT_20261111.md`。

## 结论

已经建立独立的 `face_soc_ees331_mover_top`：真实 CPU Control/Datapath、8 KiB IMEM、16 KiB CPU 本地 RAM、23 客户端真实 CNN、32 KiB tile RAM、`data_mover`、HP0 和 PS DDR 模型形成闭环。**旧 `cnn_cache`／`cnn_ddr_bridge` 不参与新顶层的数据路径**。四组样例的完整顶层 RTL 仿真均 PASS，最终输出与旧缓存路径逐字节一致；六类算子四图样例的最终 SHA-256 也与原始清单一致。

但这不等于 FPGA 硬件验收：XC7Z020 整机综合虽 PASS，71,101 LUT 超过器件 53,200 LUT，BRAM 137.5/140 tile。没有布局布线、时钟约束验证或真实 PS7/板外 DDR 运行，也没有在新路径跑完整 131 步 MobileFaceNet。

## 新增接线和暂定标准

- `rtl/soc/ees331/face_soc_ees331_mover_top.sv` 为新顶层，默认 `POOL23=1`；`rtl/filelists/system_ees331_mover23.f` 是独立编译清单。旧顶层和原清单保留供对照。
- `rtl/cnn_ddr/datasram_mover_subsystem.sv` 保持 CPU 固定一拍本地 RAM 接口，实例化新 `download_ram` 的 CPU 端口；下载端口暂未接。CNN 侧实例化 `cnn_paged_mover`，它是 HP0 唯一的 AXI 主设备路径。
- `rtl/cnn_ddr/cnn_paged_mover.sv` 对 23 路请求做轮转仲裁，保留字/有符号字节读写和按原请求者返回的语义。32 KiB `tile_local_ram` 划成 32 个 1 KiB 页，采用全相联元数据；缺页时由 `data_mover` 搬入，脏页替换及范围栅栏时写回。一次只处理一个 CNN 请求或一个页搬运。
- 沿用 CPU 固件使用的缓存 CSR 地址与清写/失效、只读区保护、故障状态；新路径的 `0x3c` 返回 32 KiB。本方暂定接口详见 `docs/storage_mover23_contract_20261111.md`。独立的 `tile_row_dma` 没有实例化在此透明分页方案中。

## 顶层仿真结果

Verilator 5.050；真实 CPU、真实 23 客户端 CNN、真实存储 RTL；PS GP0/HP0 与 DDR 用测试模型，开启确定性 AXI 背压。仿真程序限制 180 秒和 2,000 万周期。所有场景的 `result.json` 均为 PASS，记录了 RTL/C++/固件/输入样例 SHA-256；重查后哈希与当前文件一致。

| 场景 | 图数/任务 | 中间结果逐字节核对 | 新路径周期 | 旧缓存周期 | 新路径 DDR 搬入/写回 | 结果 |
|---|---:|---:|---:|---:|---:|---|
| 短行 tile | 1 / 3 | 48 B | 24,722 | 30,196 | 1,024 / 1,024 B | PASS |
| 8×8×32 tile | 1 / 3 | 12,288 B | 519,341 | 451,539 | 28,672 / 13,312 B | PASS |
| 四帧 8×8×32，独立 DDR 工作区 | 4 / 12 | 49,152 B | 1,181,772 | 1,010,221 | 87,040 / 53,248 B | PASS |
| 四帧 7×7 合成图、六类算子 | 4 / 44 | 28,812 B | 342,441 | 239,333 | 27,648 / 23,552 B | PASS |

四帧 8×8×32 的跨图计算重叠为 177,415 周期；四帧六类算子为 2,164 周期。六类算子样例实际调度 15/23 个实例，另外 8 个 K1 实例因任务规模小未被使用，不能据此称 23 个实例均已动态覆盖。所有场景均检测到 CPU RAM 读写各一次；这是测试专用启动探针，原生产 mailbox 程序本身不访问本地 RAM。四帧六类算子的最终输出 SHA-256 为 `d961e0eb6f303e1f4e49a9792e92778ba2d4f5b4ee6600976d3417ee6f9d08f0`，与旧路径和原始样例清单一致。其他三组最终输出也与旧路径逐字节相同。

补充的物理客户端覆盖测试将同一个四帧六类算子图运行三次：一次开放全部 23 路，另外两次分别只开放 K1 的中间四路和最后四路（其余类型仍开放）。三次均完成 44 个任务和 28,812 B 中间输出检查，最终输出 SHA-256 相同；合计 23/23 个物理客户端均至少启动一次，K1 的 12 个实例各启动一次。记录在 `simulation/build/mover23_soc/coverage23.json`，入口为 `simulation/scripts/run_mover23_coverage.py`。该测试验证每个客户端能接入并得到正确结果；四帧调度器每帧最多一个在途任务，不能解释成 23 路同时并发，也不等于完整网络覆盖。

任务来源：短行和单帧 8×8×32 取自 `simulation/incoming/cases/` 的确定性合成诊断样例；四帧 8×8×32 由 `simulation/scripts/make_four_frame_tile.py` 将单帧样例复制到四个独立 DDR 工作区；四帧六类算子从 `deliverables/self_cnn_four_frames/data/` 的 11 步/帧合成图经 `simulation/scripts/convert_four_frame_all_ops.py` 转成 EES331 命令格式。三组 K1 选择是本轮自行增加的仿真任务，只改变测试程序写入的实例使能掩码，不修改生产 RTL、CNN 算术或黄金输出。

四帧样例初次运行触发 2,000 万周期内部看门狗，仿真自动退出；原因是首版固定页位使相隔 32 KiB 的四帧反复冲突。改成 32 页全相联查找后，同一输入 PASS。旧 DDR 模型只接受 64 字节八拍突发，因此新增 `simulation/tb/integration/ees331_axi_mover_model.hpp`，按 MOVER 的单拍 AXI3 协议实现测试模型；未为通过测试而修改 MOVER 传输格式。

另有独立的 23 客户端故障链路测试 PASS：未对齐字访问、只读区写入、AXI 读错误传播、CSR 清错恢复，以及已接受请求取消后完整排空 128 个 AXI 单拍且不产生 CNN 响应。日志与结果在 `simulation/build/mover23_faults/`。这项测试使用真实 `cnn_paged_mover`、`data_mover`、`tile_local_ram` RTL；DDR 响应由测试程序注入。

## XC7Z020 综合

Vivado 2025.2 对 `xc7z020clg484-1` 执行完整 PL 侧 `synth_design`，外部 PS 接口、无 IOB；状态 PASS，报告、关键源码 SHA-256 清单和 checkpoint 在 `build/mover23_pl_synth/`。旧路径数字取同一工程保存的 `build/pool23_pl_synth_corrected/utilization.rpt`；两者均为综合阶段，不是布局布线结果。

| 资源 | 旧缓存顶层 | 新 MOVER 顶层 | XC7Z020 可用 | 新顶层结论 |
|---|---:|---:|---:|---|
| LUT | 88,758 | 71,101 | 53,200 | 超出 17,901 |
| FF | 47,890 | 46,017 | 106,400 | 未超出 |
| BRAM36 等效 tile | 133 | 137.5 | 140 | 仅余 2.5 |
| DSP48E1 | 61 | 61 | 220 | 未超出 |

新存储子系统自身使用 3,642 LUT、12 RAMB36、0 DSP，其中 tile RAM 8 RAMB36、CPU RAM 4 RAMB36。旧存储子系统使用 32 RAMB36；新路径释放的片上存储没有全部变成整机余量：本轮综合将更多 CNN 内部存储映射为 BRAM，CNN 层级计数从旧报告的 47 RAMB36＋108 RAMB18 增至 53 RAMB36＋145 RAMB18；相应的 LUTRAM 大幅减少。资源映射会随综合与实现策略变化，不能仅按模块标称容量估计整机 BRAM。没有板级时钟/接口约束，时序报告不能证明目标频率。

## 仍需完成

1. 为 XC7Z020 收敛 23 算子整机的 LUT/BRAM；当前综合结果已明确不能直接上板，且用户要求保持 23 路，因此不能靠偷偷降低算子数冒充完成。
2. 在新路径跑更大、更长的真实网络与高压力场景，量化页命中、DDR 流量和时延；当前全相联分页优先保证通用功能，四帧六类算子较旧路径多约 43.1% 周期。已覆盖基本故障、取消与恢复，尚需更广泛的随机故障和长期运行验证。
3. 与 PS 方确认 DDR 保留物理区、初始化和缓存一致性；接真实 PS7/DDR 并做板级时序/布局布线。当前 GP0/HP0 仿真模型不是实际 PS 软件。
4. 可下载 IMEM、CPU 停机/加载控制以及 GP0 加载器未接入这个生产顶层。`download_ram` 只接了运行端口；此项与 CNN 新存储路径分开验收。

## 复现入口

在 `D:\FPGA\fpga-cnn-integrated\simulation` 运行：

```powershell
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/prepare_pool23_soc.py
& 'C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe' scripts/run_mover23_soc.py four_frame_all_ops
```

其余场景名称：`short_row_2x2x2`、`tile_8x8x32`、`tile_8x8x32_four_frames`。各场景日志、逐字节输出与 JSON 记录在 `simulation/build/mover23_soc/<场景>/`。综合复现脚本为 `scripts/synth_ees331_mover23_pl.tcl`，原始输出在 `build/mover23_pl_synth/`，控制台日志在 `build/mover23_synth_run/vivado_console_escalated.log`。运行综合需要本机 Vivado 对安装目录和工作目录的正常访问权限。

故障链路测试命令：`python scripts/test_mover23_faults.py`（工作目录同为 `simulation/`）。

23 路物理客户端覆盖命令：`python scripts/run_mover23_coverage.py`（工作目录同为 `simulation/`）。
