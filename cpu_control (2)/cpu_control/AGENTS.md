# 项目网络代理

- 用户所说的网络连接是 Codex 网络代理，不是虚拟机 SSH 或开发板。
- 已确认代理为 Clash Verge / Mihomo：`http://127.0.0.1:7897`。Windows 系统代理已经启用。
- 代理参数保存在 `network/proxy.psd1`；`.codex/config.toml` 为本项目的 Codex 命令环境设置相同的代理变量。
- 后续任务直接复用此配置。不要在每次对话开始时重新扫描端口、检查代理或重新配置系统网络；仅在实际网络请求失败或用户要求排查时诊断。
- 当前会话未加载新配置且确实需要联网命令时，在同一次 PowerShell 调用中先用 `Import-PowerShellDataFile .\network\proxy.psd1` 读取参数，再用 `[Environment]::SetEnvironmentVariable(..., ..., 'Process')` 设置代理后执行目标命令。环境变量不会从子进程反向传回已经运行的 Codex。
- 启动方式和适用范围见 `network/README.md`。更改代理地址时同步更新 `network/proxy.psd1` 和 `.codex/config.toml`。
- 不在项目中记录密码、令牌或私钥；不把代理参数持久化误称为保持跨对话连接，也不把 shell 代理配置描述为桌面客户端网络修复。

# CPU_CONTROL 工程约定

- 2026-10-22 用户已授权将今天连续帧及 FX8 修改、Markdown 说明和源码 ZIP 提交到现有 GitHub `moon` 分支。汇总说明 `docs/2026-10-22修改说明.md`；压缩包位于仓库根 `releases/2026-10-22/`。此前条目中“未提交/推送”描述的是实现完成当时的历史状态。发布不扩大为上板任务。

- 2026-10-22 FX8 接口：用户最终限定“只改代码，暂不考虑上板”。新增隔离入口 `rtl/fx8/face_soc_neureka_fx8_top.sv`，图像桥内部为 8 位 RX/TX、sys_clk/4、双时钟 FIFO、同协议 CRC、32 位字节使能打包；六模块其余内部接口/原 UART RTL 不变。`python scripts/run_fx8.py` 的最终 `20261022_182439_335221_fx8` 六项 PASS，真实主 CPU/桥/SRAM/调度加测试运算模型，四帧1820输出字节一致。真实核较早尝试 `fpga-cnn-moon` 下 `20261022_181204_716758_fx8` 编译展开后仍在 alignment_buffer:115、0 ps XSim 内核崩溃；最终收窄计数器未重新真实核验收。板级 XDC/工程/综合脚本只是草案，最新综合检查在 Gray 寄存器计数断言失败且未完成时序签核，不主动继续上板工作。详见 `docs/ees331_fx8_interface.md` 和 `docs/fx8_verification_20261022.md`。两份源码同步；本次未提交/推送。

- 2026-10-22 用户授权在 Neureka 分块入口实现“当前 CNN + 下一帧加载 + CPU 工作”，要求六模块 IO 连线不变。`face_soc_neureka_pipeline_top` 在原 `image_bridge_autoload` 上启用默认关闭的 SRAM 描述符模式（SRAM_BASE+0x60，五字 magic/source/destination/bytes/CRC），三线加载握手、旧固定批次入口及 CPU/IMEM/四 bank SRAM/CNN 算术 RTL 不改。驱动 `sw/neureka_pipeline/cnn_frames.h` 提供输入/输出帧 A/B 协作式所有权调度，与原中间 tile A/B 不同；错误冻结所有权、需复位，不宣称全 SRAM 硬件保护。`scripts/run_neureka_frames.py` 默认使用真实主 CPU/桥/SRAM/邮箱/tile 调度器加测试专用标量计算模型；20261022_165909_947172_neureka_frames 四项 PASS，覆盖快/慢加载、四帧1820字节、CPU工作、CRC失败不提交及九种描述符故障。旧 autoload 六项和 tile 控制回归 PASS。真实核 `--real-cores` 在本地 fpga-cnn-moon 副本的 20261022_170414_959878_neureka_frames 编译展开成功，仍在 CV32E40X alignment_buffer:115、0 ps 出现 XSim 内核崩溃，仿真 FAIL；不得宣称真实核数值、加速比或上板通过。详情 `docs/neureka_continuous_frames.md`。本次仅本地修改，两份代码同步，尚未提交/推送新改动。

- 2026-10-13 用户授权联合接入 NVDLA 与 Vicuna。新增隔离六模块入口 `rtl/hybrid/face_soc_hybrid_top.sv`，CNN 内包含原真实 NVDLA、CV32E40X＋Vicuna 2、16 KiB 局部程序 RAM、命令寄存器及单在途 SRAM 桥；原主 CPU Control/Datapath、DATASRAM、主 IMEM RTL 未改。必须通过零等待命令寄存器访问慢速配置，原 CPU 仅译码偏移0x00～0x20且不能等待CSB，扩大MMIO窗口不解决此问题。真实CPU固件三项测试在 `build/runs/20261013_211215_hybrid_soc` PASS（小卷积串联、多通道卷积串联、池化与FP32独立任务并发），另有 `20261013_210749_hybrid_adapters` 接口短回归 PASS。交付 `deliverables/hybrid_soc`，说明 `docs/hybrid_soc_integration.md`，构建 `scripts/run_hybrid_soc.py`（WSL，后续 `--reuse`，保留timed RAM）。本次 SRAM 预加载、UART 空闲，不是收图全链路。重要限制：集成配置的FP32先比较后乘法有错误，冗余加载诊断还触发看门狗；采用先乘法后比较的程序通过，但根因未彻底定位，不能宣称通用程序可靠。失败保留在 `20261013_210250_hybrid_soc` 和 `20261013_211032_hybrid_fp32_diagnostic`。辅助核程序RAM不等于恢复已放弃的主IMEM下载方案。

- 2026-10-09 GTKWave 交付：本机项目内便携版路径 `tools/gtkwave/portable/gtkwave64/bin/gtkwave.exe`（3.3.100，官方 SourceForge 包，哈希已核对）。无需再次搜索安装位置。`deliverables/gtkwave_soc_36/` 含与合并图相同顺序的36根信号、原生保存会话、GTKWave截图和 `.cmd` 启动入口；`open_gtkwave.cmd` 全程，`open_cnn_detail.cmd` 计算/读回，`open_write_detail.cmd` 四次输出写回。实际Tcl检查TOTAL/VISIBLE均36，`validation.json`保存检查结果。来源仍是20261008_230704历史仿真，不代表新一轮RTL仿真；未实施外部仅送图像的目标。准备脚本 `scripts/prepare_gtkwave_soc.py`，然后由GTKWave执行交付目录的 `export_and_verify.tcl`。

- 2026-10-08 最新实施：用户已授权按三线直连方案完善 RTL 和上电全程小任务仿真。新版隔离入口 `rtl/soc/autoload/face_soc_autoload_top.sv`、清单 `rtl/filelists/system_autoload.f`；六模块、外部7信号保留，CPU封装与主动图像桥之间仅增 `load_req / load_complete / load_error`。CPU封装内部保留数据地址0x40/0x44作控制/状态，原Control C1、生产Datapath、CNN、datasram、IMEM和clock_unit不改。完整四阶段握手、固定批次加载、包/整批CRC、失败锁定复位恢复已实现；配套真实RV32I固件及外部UART设备模型。测试 `python scripts/run_autoload_integration.py` 六项通过：上电正常闭环、包CRC、超时迟到、整批CRC、错误tag、63字节分包尾包。真实CNN执行2×2输入的1×1卷积，结果[5,-1,9,11]，不等于全模型或上板验收。说明见根目录 `SoC三线自动加载RTL与上电全流程仿真说明_小白版.md`、`docs/autoload_uart_protocol.md`。旧 `face_soc_top/system_cnn.f` 继续保留被动UART版本；不要混编为同一顶层，不恢复可写IMEM。外部器件尚未确定，新桥要求设备实现IMIO读请求/IMOR回复协议。当前是单次顺序演示固件，不宣称具备CNN忙闲硬件互锁或连续帧调度。

- 2026-10-08 历史说明方案：用户不采用“顶层MMIO分流到image_bridge”的接线稿，改用CPU与图像桥三线直连。原讨论稿为根目录 `SoC六模块增线说明_CPU与图像桥三线直连.md`，其中“仅文档、待实现”是当时状态；后续实施以上一条及新仿真说明为准。

- 2026-10-08 历史需求分析：上电后自动从外部存储数据源加载图像/资料，无需电脑运行时控制。原image_bridge是被动IMIO收包/回复；新版主动加载和小任务固件已另行实现，完整应用和实际外部器件仍待确定。固件指IMEM中的板内CPU程序，不等于电脑软件。早期分析见根目录 `上电自动读取外部数据与固件作用说明_小白版.md`，不重新启动已放弃的IMEM下载改造。

- 2026-10-08 后续决定：用户放弃可写 IMEM、独立程序下载串口及下载互锁改造，继续使用原六模块 `face_soc_top`。此前仅新增方案文档和图，未修改 RTL，无需硬件回滚；新版下载口文档仅作未实施历史稿，不得作为当前接线或开发任务。当前上电至图像处理流程见根目录 `SoC六模块从上电到图像处理的数据流_小白版.md`，其中完整应用固件、mailbox约定和全模型验收仍未完成。

- 2026-10-08 用户授权改 SRAM 时序，将仲裁并入 datasram，并实际实现 UART 图像桥和时钟复位。当前板级顶层 `rtl/soc/face_soc_top.sv` 直接实例化 `cpu_core / mobilefacenet_accelerator_top / datasram / imem_rom / image_bridge / clock_unit` 六个平级模块；`face_soc_cnn_top` 仅为计算侧测试入口。CNN 原生 mem_* 66/33 位直接接 datasram，不经过 CPU；图像桥 io_mem_* 70/35 位保留 error。datasram 内部实现 RAM、B 仲裁与完成时序，当前 `rtl/filelists/system_cnn.f` 不编译旧存储子系统、独立 sram_b_arbiter 或假 CNN 寄存器。A 口固定一拍，Control C1 与生产 Datapath 不变。CNN 原包 RTL 保持原样，XSim 仅使用 tensor_operator_engine 语法等价副本。UART 为 IMIO 分块读写/CRC32；clock_unit 不带 PLL，复位三拍同步释放。CNN 存储故障及 UART 内存超时需系统复位；LED busy 是桥忙而非 CNN busy。最新依据：顶层 `SoC顶层连线与总体IO说明_小白版.md`、`docs/uart_image_bridge_protocol.md`、`docs/soc_six_module_verification_20261008.md`。测试 `python scripts/run_cnn_integration.py` 和 `python -m unittest discover -s tb -p test_uart_image_transfer.py`。以下带日期的旧交付状态仅为历史，不得重加外置适配器/仲裁器；不能把 RTL 仿真说成上板或完整人脸识别通过。

- 设计输入是根目录两份原始 Markdown 和用户在对话中提供的架构图；用户负责 CPU_CONTROL。原始文件保留，不擅自修改生产 Datapath/CNN。
- 已按 C1/D1 实现；根据 FACE-SOC-COORD-P1，M / Control 侧已正式接受 C1 作为 v1.0 开发基线（端口/编码/RTL 不变），不再把本方确认列为待办。D1 为 Datapath 原则接受记录；三方回签、公共地址/全局复位/真实存储时序仍待共同冻结。当前正式回复在 docs/control_reply_to_P1.md，P1 原文归档在 docs/inputs/FACE-SOC-COORD-P1.md。接口说明在 docs/cpu_control_interface.md，对齐记录在 docs/control_reply_to_D1.md，D1 原文归档于 docs/inputs/CPU-DP-IF-D1.md。2026-09-17 已收到 D:\QQ\face_recognition_soc_datapath_complete.zip，真实 Control + 生产 Datapath 的独立 ADD 和混合程序 XSim 仿真通过，双方生产 RTL 未改；存储器为同步模型，CNN MMIO 为 stub，不宣称真实 CPU/CNN/FPGA 系统通过。来源、包兼容条件、执行级末尾提交 SRAM 读写与本方旧文档阶段差异见 docs/datapath_connection_review_20260917.md；兼容共享包新哈希仍待共同归档。
- 测试统一入口：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。本机实际可用工具为 Vivado XSim 2026.1，脚本已处理其启动环境；无需每次重新发现工具路径。
- 用户教程在 docs/README_TEST.md，实际结果与限制在 docs/verification_report.md。每次运行使用独立 build/runs 子目录，不能用旧 VCD/PNG 代替本次结果。
- Control 保持组合逻辑；所有跨级状态由 Datapath 持有。CNN Driver 是普通 MMIO 软件，不添加 STATUS/CONTROL 硬件端口。
- 2026-09-28 用户确认系统 B 口采用仲裁器方案：`image_io_bridge` 与 CNN memory master 都先连接 `sram_b_arbiter`，再连接 `data_sram_tdp.B`；每个主设备请求为 70 bit（req/we/addr/wdata/be），返回为 35 bit（gnt/rvalid/rdata/error），`error` 不得删除。详细开发交接见 `docs/cnn_developer_handoff_B_port_v1.md` 和 `docs/datapath_developer_handoff_memory_v1.md`。该决定不修改 Control C1；真实 wrapper、仲裁器与 CNN RTL 仍待 D/Z 交付和验收。
