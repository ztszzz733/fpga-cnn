# 自研 CNN 四图完整网络：仓库入口与复现

2026-10-24 更新：本文记录的是已冻结的历史 SRAM 全网基线。当前新增 DDR/cache 六模块代码入口及小图验收见 [ees331_code_integration.md](ees331_code_integration.md)；下面的全网周期、哈希和历史“尚未接入”状态不适用于新入口。

本目录交付了自研卷积、地址驱动固定流程调度、`bai-datasram` 四 bank SRAM 接入，以及四张不同 112×112 测试图的完整 MobileFaceNet **真实 RTL 仿真**。CNN 接收一份固定模板和图片地址，在输入提交、依赖和缓冲区生命周期允许时，将不同图片的任务分配给空闲算子。

最终候选为 **K3×2、K1×4、DW7/Post/Add/Pad 各一套**。同一四图、同一数据与输入节奏下，相比 K3×4/K1×2，批次周期从 **1,138,093,351** 降到 **653,428,459**，减少 **42.59%**，同频吞吐为原来的 **1.742 倍**。这不是全网串行到并行的速度比；完整串行基准未测。若假设 100 MHz，四图时间为 11.381→6.534 秒，尚未验证实际板级频率。

两轮各完成 524 个任务、935,241,728 次标量 MAC、77,349,168 个输出字节检查和四份 128 字节结果读取；候选、基线与独立整数参考输出逐值相同。输入是合成数值测试图，量化尺度是首图诊断尺度，不构成人脸识别精度验证。

**512 KB（512 KiB）片上存储适配目前只是后续方案，尚未实现或验证。** 已通过的完整仿真使用 **16 MiB SRAM 地址空间**、12,608,512 字节执行初值；不能将其描述为已经压到 512 KiB 或已适配 Zynq-7020。尚未完成上板、CPU/UART 生产集成、新整机综合或布局布线；原 Post/DW7 的存储推断问题仍需处理。已有单核 OOC 资源相加不是完整 CNN 的资源报告。

## 源码与证据

| 内容 | 入口 |
|---|---|
| 自研普通卷积 / DW3 / 1×1 | [self_conv_engine.sv](../rtl/cnn_self/self_conv_engine.sv) |
| 固定流程入口 | [self_fixed_network_top.sv](../rtl/cnn_stream/self_fixed_network_top.sv) |
| 调度、槽租约、模板展开、结果交接 | [cnn_stream](../rtl/cnn_stream) |
| SRAM 来源与原样导入文件 | [bai/SOURCE.json](../rtl/cnn_stream/bai/SOURCE.json)、[datasram_banked.sv](../rtl/cnn_stream/bai/datasram_banked.sv) |
| 完整 RTL 编译文件表 | [cnn_self_stream.f](../rtl/filelists/cnn_self_stream.f) |
| 完整网络仿真入口与真实 SRAM 检查 | [self_full_sim_top.sv](../tb/self_full_sim_top.sv)、[self_full_main.cpp](../tb/integration/self_full_main.cpp) |
| 模型恢复、量化/独立整数参考、运行 | [restore_self_full_model.py](../scripts/restore_self_full_model.py)、[gen_self_full.py](../scripts/gen_self_full.py)、[run_self_full.py](../scripts/run_self_full.py) |
| 原完整四图报告 | [self_cnn_full_frames](../deliverables/self_cnn_full_frames/README.md) |
| 最终配置比较、图表与原始证据 | [self_cnn_full_optimized](../deliverables/self_cnn_full_optimized/README.md) |
| 前期小图接口和回归 | [四图接口](self_cnn_four_frames.md)、[双图交付](../deliverables/self_cnn_pair/README.md) |

实际候选例化参数为 `K3_UNITS=2`、`K1_UNITS=4`、`POST_UNITS=1`，DW7/Add/Pad 各固定一套。顶层与运行脚本的历史默认仍是 K3×4/K1×2；复现候选必须显式传入 `--k3 2 --k1 4 --post 1`。完整仿真 wrapper 使用 `MAX_TASKS=1024`、模板容量 256，实际每图 131 步。

## 在新的 Windows 克隆中准备环境

以下命令在 PowerShell 中执行。仓库不包含 `.tools/`、`.venv/`、`build/` 或 `.self_full_native/` 的下载、模型、数据和编译缓存；因此新克隆不能直接复用历史 `--reuse` 缓存或历史 gate 路径。

```powershell
git clone --branch zhang --single-branch https://github.com/ztszzz733/fpga-cnn.git
Set-Location -LiteralPath '.\fpga-cnn\cpu_control (2)\cpu_control'
py -3.11 -m venv .venv
$cnnPython = '.\.venv\Scripts\python.exe'
& $cnnPython -m pip install --upgrade pip
& $cnnPython -m pip install 'numpy==2.4.1' 'Pillow==12.1.0' 'matplotlib==3.10.8'
& $cnnPython -m pip install 'torch==2.11.0+cu128' --index-url https://download.pytorch.org/whl/cu128
& $cnnPython -m pip install --target .tools/mobilefacenet-python 'onnx==1.17.0' 'onnxruntime==1.20.1' 'protobuf==5.29.5' 'numpy==2.4.1'
```

历史环境为 64 位 Python 3.11.9、PyTorch 2.11.0+cu128、ONNX 1.17.0、ONNX Runtime 1.20.1、NumPy 2.4.1、Pillow 12.1.0、Matplotlib 3.10.8。模型恢复脚本固定使用 CPU 执行；上面的 PyTorch 包选择是为了贴近原导出环境，并非要求 GPU 参与仿真。下载包及依赖不会提交到仓库。导出器或依赖版本变化可能改变 ONNX 文件字节和量化数据，应保留新生成的来源记录，不能直接宣称它们与历史 SHA256 相同。

本入口使用原生 Windows Verilator + MSVC，不依赖 WSL。需要已安装 Git、`curl.exe`、Visual Studio C++ x64 工具链、Windows SDK、CMake 和 Ninja。历史工具为 MSVC 19.44.35215（目录 14.44.35207）、CMake 3.31.6-msvc6、Ninja 1.12.1。

**先适配本机工具路径，再运行 bootstrap。** [bootstrap_verilator_native.py](../scripts/bootstrap_verilator_native.py) 目前硬编码 `D:/visual studio2`，并用 `VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe` 记录编译器来源；请将 `VS`、相关路径和版本目录改为本机实际安装位置。该适配会进入新运行的源码/工具签名；后续 gate 与 full 必须来自同一套签名和可执行文件。

Verilator 使用脚本固定 URL 和 SHA256 的第三方 Windows wheel，包版本 5.48.0，配套 runtime 头文件报告 5.49 开发版。脚本会一起准备二者并生成 `.tools/verilator-native/SOURCE.json`，不要混用其他版本的二进制和头文件。

```powershell
& $cnnPython scripts/bootstrap_verilator_native.py --proxy ''
```

这里空代理参数表示直接下载；需要代理时改为自己的地址。旧版 Windows PowerShell 若未保留空参数，可显式写 `--proxy=`。脚本默认代理为原环境的 `http://127.0.0.1:7897`，不是必须存在的服务。该命令只准备工具；本说明不要求自动运行 smoke 或完整仿真。

## 固定模型与生成数据

从固定上游恢复 checkpoint，无需上传预训练权重或整套生成数据：

```powershell
git clone https://github.com/foamliu/MobileFaceNet.git .tools/mobilefacenet-upstream
git -C .tools/mobilefacenet-upstream checkout --detach a6cc9032a659b615f477833e1a70b5e7931bcccc
& $cnnPython scripts/restore_self_full_model.py
& $cnnPython scripts/gen_self_full.py --model build/self_full_model/mobilefacenet.onnx --out build/self_full_small --frames 4 --small
& $cnnPython scripts/gen_self_full.py --model build/self_full_model/mobilefacenet.onnx --out build/self_full_data --frames 4
```

恢复脚本在加载前校验 `pretrained_model/mobilefacenet_scripted.pt` 的 SHA256：`780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a`，并检查上游 commit。它导出 ONNX、生成四张确定性 112×112 RGB 图，核对 Torch 与 ONNX 输出，记录来源和版本；图片默认由后续生成器复用。若文件校验失败，应修正模型来源，不能跳过检查。

`--small` 是真实模型前三个 Conv 的 8×8 ROI，用于先验回归，不代表完整网络性能；未加 `--small` 才生成完整数据。生成器要求输出目录为空，避免覆盖已有证据。执行初值中的输入与中间区填充 A5，图片由驱动器逐张写入，独立整数 golden 仅供 checker 使用，不注入算子或替代 SRAM 响应。

## 新 gate → 完整四图仿真

先编译候选配置并完成四项小图回归：

```powershell
& $cnnPython scripts/run_self_full.py --k3 2 --k1 4 --post 1 --data build/self_full_small --modes overlap serial preloaded stress
```

命令会打印 `RUN ...`，并写入新的 `build/runs/<时间戳>_self_full/result.json`。确认该文件为 `PASS` 且包含四个场景后，把**刚刚生成的目录**填到下面变量中；不要使用报告中原机器的 194655 历史目录。

```powershell
$cnnGateRun = 'build/runs/这里替换为刚刚生成的时间戳_self_full'
& $cnnPython scripts/run_self_full.py --k3 2 --k1 4 --post 1 --reuse --full --data build/self_full_data --gate $cnnGateRun --modes overlap
```

`--reuse` 在这一步复用刚通过 gate 的编译缓存。运行器会检查数据哈希、源码/工具链签名、可执行文件哈希、算子数量和 gate 四项 PASS；修改源码、工具或数量后，应重新编译并运行匹配 gate。完整四图仿真是长运行，结束时以新 `result.json` 的最终 `PASS/FAIL` 为准，不以部分任务进度判定通过。

若要独立复测 4/2→2/4 的收益，对 `--k3 4 --k1 2 --post 1` 同样先做一个新 gate，再跑其完整 `overlap`。两配置应共用同一份 `build/self_full_data` 和相同输入节奏；默认 `--pace 80`。不要拿短图的加速比代替全网结果。

## 报告与波形

每次新运行会生成新的时间戳目录。可将新完整 PASS 目录传给 [prepare_self_full.py](../scripts/prepare_self_full.py)，或将新 4/2 与 2/4 两份完整 PASS 目录传给 [compare_self_full.py](../scripts/compare_self_full.py)。报告器会重新检查数据、命令覆盖、输出和来源签名，生成对应新运行的报告。它们使用固定交付目录；重新生成前应保留历史交付，比较脚本会拒绝覆盖属于另一组运行的现有 provenance。不要为通过检查而改写历史结果或 hash。

已提交的历史报告、JSON 和 GTKWave 会话保留原始字节，用于验证来源。因此它们中的 `D:/zhang/...` 绝对路径是**原环境记录**，在 GitHub 或其他机器上可能不可点击；它们不表示新克隆必须放在同一盘符。可从本页相对链接进入文件，或在本机新运行完成后重新生成适用于该工作目录的报告。新机器产生的 manifest 包含本机路径、耗时等信息，通常不会与历史 manifest 文件整体哈希一致。

实际波形证据为 [候选 MAC 窗口](../deliverables/self_cnn_full_optimized/evidence/candidate/mac_detail.vcd) 和 [候选跨类窗口](../deliverables/self_cnn_full_optimized/evidence/candidate/pipeline_detail.vcd)。窗口只有相对起点，不能把横轴 0 当作网络开始；完整任务时序见 [候选 events.csv](../deliverables/self_cnn_full_optimized/evidence/candidate/events.csv)。已保存的 [GTKWave 验证](../deliverables/self_cnn_full_optimized/gtkwave_validation.json) 是原环境实际两会话各 10 根唯一信号的 PASS 证据。

查看波形需另行准备可运行的 GTKWave，历史版本为 3.3.100。`open_candidate_*.cmd` 和 `validate_gtkwave.ps1` 默认查找项目内 `tools/gtkwave/portable/gtkwave64/bin/gtkwave.exe`；其他安装位置需适配启动器，或手动在 GTKWave 中载入当前克隆里的 VCD、`.gtkw` 和 `.tcl`。会话文件里的旧绝对 dumpfile 路径也需重定向到本地文件。改变会话后应重新验证并产生新的校验记录，不能继续把历史 session 哈希当作当前会话已验证。
